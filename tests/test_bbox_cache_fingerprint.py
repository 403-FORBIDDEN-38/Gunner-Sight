"""bbox 缓存的内容指纹（sha256）判据。

背景：缓存原先只认 `st_mtime_ns`，而 mtime 在分发链路上必然失真——
zip 时间戳只有 2 秒精度且向下取偶，git clone 根本不保存 mtime（检出时
全部设为当前时间）。结果是一份正确的出厂预计算在别人机器上 0 命中，
并且会被 `cleanup()` 在第一个 `get()` 之前整份清空。

判据改为「mtime 快路径 + sha256 定真伪」后，以下四条是必须长期成立的
契约。其中第 3 条（cleanup 不得按 mtime 删条目）是本次真正的修复点：
只改 get() 而不改 cleanup()，等于什么都没改。
"""
import json
import os

from core.bbox_crop import BboxCache

PAYLOAD = b"\x89PNG\r\n\x1a\n fake crosshair payload"


def _make_cache(tmp_path):
    """建一个带单张资源文件的缓存，返回 (cache, 图片路径, 缓存路径)"""
    res = tmp_path / "resources"
    res.mkdir()
    img = res / "crosshair.png"
    img.write_bytes(PAYLOAD)
    cache_path = tmp_path / "bbox_cache.json"
    cache = BboxCache(cache_path, resources_dir=res)
    return cache, img, cache_path


def _read(cache_path):
    return json.loads(cache_path.read_text(encoding="utf-8"))


def test_mtime_changed_content_same_hits(tmp_path):
    """解压 / clone 后 mtime 全变但内容没变 → 必须命中。

    这是整个改动的目的：让作者的预计算在别人机器上继续有效。
    """
    cache, img, _ = _make_cache(tmp_path)
    old_mtime = img.stat().st_mtime_ns
    cache.set(str(img), (3, 4, 5, 6), old_mtime, (100, 100))
    cache.save()

    os.utime(img, (1_600_000_000, 1_600_000_000))
    new_mtime = img.stat().st_mtime_ns
    assert new_mtime != old_mtime

    assert cache.has(str(img), new_mtime), "内容未变却判未命中——预计算跨机器失效"
    assert cache.get(str(img), new_mtime) == (3, 4, 5, 6)


def test_same_size_different_content_misses(tmp_path):
    """同大小不同内容 → 必须重算，不能返回旧 bbox。

    这正是 size+尺寸 方案的漏洞：371 张图只有 75 种像素尺寸（180 张
    同为 2560×1440），28 张与别的图共享 (文件大小,像素尺寸) 组合。
    """
    cache, img, _ = _make_cache(tmp_path)
    cache.set(str(img), (3, 4, 5, 6), img.stat().st_mtime_ns, (100, 100))
    cache.save()

    same_size = bytes(b ^ 0xFF for b in PAYLOAD)
    assert len(same_size) == len(PAYLOAD)
    img.write_bytes(same_size)
    os.utime(img, (1_700_000_000, 1_700_000_000))

    assert cache.get(str(img), img.stat().st_mtime_ns) is None, "同大小不同内容被误命中——bbox 会是旧的"


def test_cleanup_keeps_entries_with_stale_mtime(tmp_path):
    """cleanup() 不得因为 mtime 不符而删条目。

    回归防线：旧实现会在 BboxCache.__init__ 的 cleanup() 里按 mtime 删，
    导致别人机器上第一次启动、第一个 get() 之前就把整份缓存清空并写回
    空文件。只改 get() 不改这里，等于没改。
    """
    cache, img, cache_path = _make_cache(tmp_path)
    cache.set(str(img), (3, 4, 5, 6), img.stat().st_mtime_ns, (100, 100))
    cache.save()
    key = next(iter(_read(cache_path)))
    assert key in _read(cache_path)

    os.utime(img, (1_600_000_000, 1_600_000_000))

    # 重新构造 = 模拟下一次启动（__init__ 里 load + cleanup）
    cache2 = BboxCache(cache_path, resources_dir=tmp_path / "resources")
    assert key in _read(cache_path), "cleanup 按 mtime 删了条目——跨机器预计算会被整份清空"
    assert cache2.has(str(img), img.stat().st_mtime_ns)


def test_cleanup_heals_mtime_and_persists(tmp_path):
    """自愈必须落盘。

    全部命中时扫描线程不会启动，get() 里的 dirty 没有任何时机 save()，
    所以批量自愈放在 cleanup() 里做，并在那里写盘。否则每次启动都要
    重算一遍全部指纹（白做 48ms）。
    """
    cache, img, cache_path = _make_cache(tmp_path)
    cache.set(str(img), (3, 4, 5, 6), img.stat().st_mtime_ns, (100, 100))
    cache.save()

    os.utime(img, (1_600_000_000, 1_600_000_000))
    new_mtime = img.stat().st_mtime_ns

    BboxCache(cache_path, resources_dir=tmp_path / "resources")  # __init__ 触发 cleanup

    entry = next(iter(_read(cache_path).values()))
    assert entry["mtime"] == new_mtime, "自愈没有落盘——下次启动仍要重算全部指纹"
    assert entry["sha256"], "条目缺少指纹字段"


def test_cleanup_still_removes_orphans(tmp_path):
    """孤儿清理职责不能丢：源文件已删除的条目仍必须被移除。"""
    cache, img, cache_path = _make_cache(tmp_path)
    cache.set(str(img), (3, 4, 5, 6), img.stat().st_mtime_ns, (100, 100))
    cache.save()
    key = next(iter(_read(cache_path)))

    img.unlink()
    BboxCache(cache_path, resources_dir=tmp_path / "resources")

    assert key not in _read(cache_path), "孤儿条目未被清理"
