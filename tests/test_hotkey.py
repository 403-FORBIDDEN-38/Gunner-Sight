"""core/hotkey_manager.py + gui/hotkey_widgets.py：全局钩子的注册与释放。

这个模块的资源在 Python 之外（keyboard 的全局钩子、MouseHook 的引用计数），
泄漏了不会报错，只是钩子常驻到进程退出、或者别的软件的热键一起失灵。

**注销只摘自己的**（M4）
`keyboard.unhook_all()` 是全局服务——一挥就把别人的钩子也摘了。注销必须只对
自己登记过的那一个句柄 `unhook(h)`。

**捕获态被销毁必须释放钩子**（M14）
HotkeyLineEdit 在捕获态被 deleteLater（hotkey_tab refresh 的路径，没有
closeEvent）时，全局低级鼠标钩子必须释放——否则引用计数泄漏。正常捕获结束
释放一次之后，再销毁不得二次 release（引用计数会被多减）。
"""
from unittest.mock import MagicMock

import pytest


def _fake_mouse_hook(monkeypatch):
    from gui import hotkey_widgets

    hook = MagicMock()
    monkeypatch.setattr(hotkey_widgets.MouseHook, "instance", staticmethod(lambda: hook))
    return hook


# ---------------------------------------------------------------- 键盘钩子注销

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


# ---------------------------------------------------------------- 鼠标钩子释放

def test_capturing_edit_destroyed_releases_hook(qapp, monkeypatch):
    """M14：deleteLater 销毁路径（无 closeEvent）也必须释放钩子。"""
    from PyQt5.QtCore import QEvent

    from gui.hotkey_widgets import HotkeyLineEdit

    hook = _fake_mouse_hook(monkeypatch)
    edit = HotkeyLineEdit()
    edit._start_capture()
    assert hook.acquire.call_count == 1

    edit.deleteLater()
    # processEvents() 默认不派发 DeferredDelete，必须显式 sendPostedEvents
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    assert hook.release.call_count == 1, "捕获态被销毁后钩子未释放——引用计数泄漏"


def test_capturing_edit_close_releases_hook(qapp, monkeypatch):
    """M14：closeEvent 路径同样释放。"""
    from gui.hotkey_widgets import HotkeyLineEdit

    hook = _fake_mouse_hook(monkeypatch)
    edit = HotkeyLineEdit()
    edit._start_capture()

    edit.close()
    assert hook.release.call_count == 1


def test_finish_capture_still_releases_once(qapp, monkeypatch):
    """M14 回归：正常捕获结束释放一次；随后再销毁不二次 release（幂等）。"""
    from PyQt5.QtCore import QEvent

    from gui.hotkey_widgets import HotkeyLineEdit

    hook = _fake_mouse_hook(monkeypatch)
    edit = HotkeyLineEdit()
    edit._start_capture()

    edit._finish_capture("a")
    assert hook.release.call_count == 1

    edit.deleteLater()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    assert hook.release.call_count == 1, "销毁路径重复 release——引用计数会被多减"
