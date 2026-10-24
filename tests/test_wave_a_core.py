"""批次 3 浪 A 契约测试（core 稳定性与性能五项）。

- M1：BboxScanner 退出/提交竞态——线程退出后的 submit 必须重启线程并处理任务，
  不成孤儿（孤儿 = _pending_scans 永久不清、本次会话该路径加载不出图）。
- M2：BboxCache 跨线程 get/has 与 set/save 并发不抛（dict 迭代期增删 RuntimeError）。
- M3：射表 profile 按 name 缓存（table 引用 is 判有效），鼠标级查询不重复重建。
- M4：注销键盘热键只摘自己的全局钩子，绝不挥舞 keyboard.unhook_all 全局服务。
- M5：扫描完成只对当前准星路径构建 pixmap；UI 层全屏整图不进 crosshair pixmap 缓存。
"""
import threading
import time

import pytest

from core.bbox_crop import BboxCache, BboxScanner


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


def test_firing_profile_cached_by_table_identity(config, monkeypatch):
    """M3：同 name 重复查询只构建一次 profile；table 换对象才重建。

    query_firing_distance 挂在 angle_changed（鼠标移动级），每次重建要做
    解析+排序+PCHIP 求导——同 table 引用（is）期间必须复用缓存。
    """
    import core.config.angle_meter as am_mod

    calls = []
    real_from_config = am_mod.BallisticProfile.from_config.__func__

    def counting(cls, data):
        calls.append(data)
        return real_from_config(cls, data)

    monkeypatch.setattr(am_mod.BallisticProfile, "from_config", classmethod(counting))

    name = "p1"
    config.add_angle_meter_profile(name)
    config.set_firing_table(name, [{"angle": 0, "distance": 100}, {"angle": 5, "distance": 200}])

    for _ in range(50):
        assert config.query_firing_distance(name, 2.5) is not None
    assert len(calls) == 1, "同 table 引用的 50 次查询只应构建 1 次 profile"

    # set_firing_table 换 list 对象 → 引用失效，重建一次
    config.set_firing_table(name, [{"angle": 0, "distance": 100}, {"angle": 5, "distance": 200}])
    assert config.query_firing_distance(name, 2.5) is not None
    assert len(calls) == 2

    # 之后同对象查询不再重建
    assert config.query_firing_distance(name, 1.0) is not None
    assert len(calls) == 2


def test_unregister_only_unhooks_own_hook(config, monkeypatch):
    """M4：注销键盘热键只摘自己的全局钩子，绝不挥舞 keyboard.unhook_all。"""
    import keyboard as kb

    from core.hotkey_manager import HotkeyManager
    from core.state_machine import StateMachine

    calls = {"unhook": [], "unhook_all": 0}
    monkeypatch.setattr(kb, "unhook", lambda h: calls["unhook"].append(h))

    def _counting_unhook_all():
        calls["unhook_all"] += 1

    monkeypatch.setattr(kb, "unhook_all", _counting_unhook_all)

    state = StateMachine(config)
    hm = HotkeyManager(config, state)
    sentinel = object()
    hm._keyboard_global_hook = sentinel
    hm._keyboard_hotkeys["a"] = {"keydown": [], "keyup": []}
    hm._unregister_all_keyboard_hotkeys()

    assert calls["unhook"] == [sentinel]
    assert calls["unhook_all"] == 0
    assert hm._keyboard_global_hook is None
    assert hm._keyboard_hotkeys == {}


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
