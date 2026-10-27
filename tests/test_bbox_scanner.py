"""core/bbox_crop.py：扫描器生命周期（M1/M2/M5）与缓存指纹判据。

两条独立契约住在这一个模块里，坏掉的代价都是「静默失效」——不崩、不报错，
只是某张图加载不出来，或者一份正确的预计算在别人机器上失效。

**扫描器**
- M1 退出/提交竞态：线程退出后的 submit 必须重启线程并处理任务，不成孤儿
  （孤儿 = _pending_scans 永久不清、本次会话该路径加载不出图）。
- M2 BboxCache 跨线程 get/has 与 set/save 并发不抛（dict 迭代期增删 RuntimeError）。
- M5 扫描完成只对当前准星路径构建 pixmap；UI 层全屏整图不进 crosshair pixmap 缓存。

**缓存指纹（sha256）**
缓存原先只认 `st_mtime_ns`，而 mtime 在分发链路上必然失真——zip 时间戳只有 2 秒
精度且向下取偶，git clone 根本不保存 mtime（检出时全部设为当前时间）。结果是一份
正确的出厂预计算在别人机器上 0 命中，并且会被 `cleanup()` 在第一个 `get()` 之前
整份清空。判据改为「mtime 快路径 + sha256 定真伪」后，以下四条必须长期成立。
其中第 3 条（cleanup 不得按 mtime 删条目）是本次真正的修复点：只改 `get()` 而不改
`cleanup()`，等于什么都没改。
"""
import json
import os
import threading
import time

import pytest

from core.bbox_crop import BboxCache, BboxScanner

PAYLOAD = b"\x89PNG\r\n\x1a\n fake crosshair payload"


# ---------------------------------------------------------------- 夹具与工具

def _make_png(path):
    """生成带不透明内容的测试 PNG（offscreen 下 QImage 可加载）。"""
    from PyQt5.QtGui import QColor, QImage

    img = QImage(8, 8, QImage.Format_ARGB32)
    img.fill(0)
    for y in range(8):
        for x in range(8):
            img.setPixelColor(x, y, QColor(255, 0, 0, 255))
    assert img.save(str(path), "PNG")
    return path


def _drain(app, results, n, timeout_ms=5000):
    """派发跨线程 queued 信号，等 results 收满 n 条。"""
    t0 = time.monotonic()
    while len(results) < n:
        if (time.monotonic() - t0) * 1000 > timeout_ms:
            break
        app.processEvents()
        time.sleep(0.002)
    return results


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


# ---------------------------------------------------------------- 扫描器生命周期

def test_scanner_processes_submits_after_idle(tmp_path, qapp):
    """M1：空闲（队列空、线程在条件变量上等待）后再 submit，任务仍被处理。

    常驻模式：线程不因队列空退出。旧起停模式在此处的竞态是
    isRunning() 在 run() 退出后、finished 前仍为 True → submit 不 start →
    孤儿。本测试锁定「空闲唤醒」路径。
    """
    scanner = BboxScanner()
    done = []
    # 必须用 lambda 收双参：PyQt 对内建 list.append 按单参内省，result 会被丢掉
    scanner.scan_done.connect(lambda path, result: done.append((path, result)))
    try:
        p1 = _make_png(tmp_path / "a.png")
        scanner.submit(str(p1))
        _drain(qapp, done, 1)
        assert [d[0] for d in done] == [str(p1)]

        # 队列已空、线程在 wait。此时 submit：旧实现可能成孤儿
        p2 = _make_png(tmp_path / "b.png")
        scanner.submit(str(p2))
        _drain(qapp, done, 2)
        assert str(p2) in [d[0] for d in done]
        assert scanner.isRunning()
    finally:
        scanner.request_stop()
        scanner.wait(2000)


def test_scanner_rapid_submit_no_orphan(tmp_path, qapp):
    """M1 压力版：submit 之间几乎不等，全部任务应有 scan_done。"""
    scanner = BboxScanner()
    done = []
    scanner.scan_done.connect(lambda path, result: done.append((path, result)))
    try:
        paths = []
        for i in range(12):
            p = _make_png(tmp_path / f"s{i}.png")
            paths.append(str(p))
        for p in paths:
            scanner.submit(p)
            time.sleep(0.001)
        _drain(qapp, done, len(paths))
        assert sorted(d[0] for d in done) == sorted(paths)
    finally:
        scanner.request_stop()
        scanner.wait(2000)


def test_old_isrunning_logic_would_orphan(tmp_path, qapp, monkeypatch):
    """M1 有牙证明：还原旧 submit（isRunning 判活），isRunning 谎报时任务成孤儿。

    旧实现的活体判断完全依赖 isRunning()；当它不可信（线程未启动却报
    True，或 run 已退出未 finished）时，submit 不 start()，任务永久无人
    处理。本用例用恒 True 的 fake 复现该失败模式——新实现不调 isRunning
    （_started 标志 + 常驻线程），不受影响（见上面两个用例）。
    """
    from core.bbox_crop import BboxScanner

    def old_submit(self, path):
        tid = self._task_id
        self._task_id += 1
        self._tasks.insert(0, (path, tid))
        if not self.isRunning():
            self.start()
        return tid

    monkeypatch.setattr(BboxScanner, "submit", old_submit)
    monkeypatch.setattr(BboxScanner, "isRunning", lambda self: True)  # 恒谎报 alive

    scanner = BboxScanner()
    try:
        p1 = _make_png(tmp_path / "a.png")
        scanner.submit(str(p1))  # 旧逻辑：isRunning()==True → 永不 start
        scanner.wait(300)
        # 不断言 isRunning()——它正是被 patch 的对象（自证悖论）。
        # 任务原封不动躺在队列 = 无人处理 = 孤儿。
        assert scanner.pending_count() == 1, "任务原封不动躺在队列里——孤儿（本用例即修复有牙的证明）"
    finally:
        scanner.request_stop()
        scanner.wait(2000)


def test_scan_done_pixmap_only_for_current_crosshair(config, qapp, tmp_path):
    """M5：UI 层全屏整图的扫描结果不进 crosshair pixmap 缓存（只进 crop 缓存）。

    _on_scan_done/_get_crop/_load_crosshair 都在 OverlayWindow 上（crop/pixmap
    缓存与 scanner 归它管），OverlayRenderer 只是状态编排。
    """
    from PyQt5.QtGui import QImage

    from core.bbox_crop import CropResult
    from core.overlay import OverlayWindow
    from core.state_machine import StateMachine

    state = StateMachine(config)
    win = OverlayWindow()
    try:
        ui_path = str(tmp_path / "vehicle_ui.png")
        ui_result = CropResult(QImage(64, 64, QImage.Format_ARGB32), 0, 0, 64, 64, 1.0)
        win._on_scan_done(ui_path, ui_result)
        assert ui_path not in win._crosshair_pixmap_cache
        assert ui_path in win._crop_cache

        crosshair_path = str(tmp_path / "crosshair.png")
        win._crosshair_path = crosshair_path
        ch_result = CropResult(QImage(16, 16, QImage.Format_ARGB32), 0, 0, 16, 16, 2.0)
        win._on_scan_done(crosshair_path, ch_result)
        assert crosshair_path in win._crosshair_pixmap_cache
        assert win._crosshair_pixmap is not None
    finally:
        win.close()


def test_bbox_cache_concurrent_access_no_runtime_error(tmp_path):
    """M2：主线程读 vs 扫描线程写/save 并发不抛 RuntimeError。

    无锁时 json.dump 迭代 self._data 与其他线程 del/set 并发 →
    "dictionary changed size during iteration"（曾被 scanner 的 except 吞掉，
    缓存静默丢失）。预置一个结构异常条目触发 get() 内的 del 分支。
    """
    cache = BboxCache(tmp_path / "bbox_cache.json", resources_dir=tmp_path)
    for i in range(100):
        cache.set(f"img{i}.png", (0, 0, 8, 8), float(i), (8, 8))
    cache._data["bad_entry.png"] = "not a dict"  # 触发 get() 的 del 分支

    errors = []

    def writer():
        try:
            for i in range(150):
                cache.set(f"w{i}.png", (0, 0, 4, 4), 9000.0 + i, (4, 4))
                cache.save()
        except Exception as e:  # noqa: BLE001 —— 测试就是要收集任何异常
            errors.append(e)

    def reader():
        try:
            for i in range(1000):
                cache.get(f"img{i % 100}.png", float(i % 100))
                cache.has(f"img{i % 100}.png", float(i % 100))
                cache.get("bad_entry.png", 1.0)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1 = threading.Thread(target=writer)
    t2 = threading.Thread(target=reader)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert errors == []


# ---------------------------------------------------------------- 缓存指纹

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
