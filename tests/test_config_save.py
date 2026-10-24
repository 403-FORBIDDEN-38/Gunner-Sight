"""契约：配置保存的并发安全（S2/M7）。

历史 bug ①：`_atomic_write` 在 `_save_lock` 之外——主线程立即保存与 Timer
防抖保存并发时，两条路径交错写同一个 `config.json.tmp` 再 os.replace，
可把半截 JSON 换成正式配置（下次启动加载失败回退骨架 = 用户设置全丢）。
历史 bug ②：旧 Timer 的回调把新 Timer 的引用清成 None，防抖失效、退出前
悬挂 Timer。
"""
import json
import threading
import time


def test_atomic_write_runs_inside_save_lock(config, monkeypatch):
    """S2 契约：_atomic_write 必须在 _save_lock 内执行（修复前在锁外）。"""
    observed = []
    real_atomic = config._atomic_write

    def spy(data):
        observed.append(config._save_lock.locked())
        return real_atomic(data)

    monkeypatch.setattr(config, "_atomic_write", spy)

    config.save_config()
    config._do_deferred_save(object())  # 直接驱动一次防抖落盘

    assert observed == [True, True]


def test_concurrent_saves_never_corrupt_config(config, tmp_path):
    """立即保存与防抖保存并发撞车：config.json 必须始终可解析、无 .tmp 残留。"""
    stop = threading.Event()

    def immediate_saver():
        while not stop.is_set():
            config.save_config()

    def deferred_saver():
        while not stop.is_set():
            config.request_save()
            time.sleep(0.6)  # >500ms 防抖窗，让 Timer 真的到点（更短会被反复取消）

    threads = [threading.Thread(target=immediate_saver) for _ in range(2)]
    threads.append(threading.Thread(target=deferred_saver))
    for t in threads:
        t.start()
    time.sleep(1.2)
    stop.set()
    for t in threads:
        t.join(timeout=5)

    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert data["my_beloved"] == "Xiaocheng"
    assert list(tmp_path.glob("*.tmp")) == []


def test_stale_deferred_callback_keeps_newer_timer_reference(config):
    """M7 契约：过期 Timer 的回调不得清掉新 Timer 的引用。"""
    config.request_save()
    first_timer, first_token = config._save_timer, config._save_token
    config.request_save()  # 取消旧的、换新的
    second_timer, second_token = config._save_timer, config._save_token
    assert second_timer is not first_timer
    assert second_token is not first_token

    try:
        # 过期的回调后跑完：不动新 Timer 的引用
        config._do_deferred_save(first_token)
        assert config._save_timer is second_timer
        assert config._save_token is second_token

        # 新 Timer 的回调：正常清引用
        config._do_deferred_save(second_token)
        assert config._save_timer is None
        assert config._save_token is None
    finally:
        for t in (first_timer, second_timer):
            t.cancel()
