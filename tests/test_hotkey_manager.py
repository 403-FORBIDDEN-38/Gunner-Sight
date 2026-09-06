"""HotkeyManager 纯逻辑测试（键名规范化、鼠标键识别）"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.hotkey_manager import HotkeyManager, MOUSE_KEY_MAP


@pytest.fixture
def hm():
    """创建HotkeyManager实例（mock依赖）"""
    config = MagicMock()
    state = MagicMock()
    return HotkeyManager(config, state)


class TestMouseKeyDetection:
    def test_left_button_is_mouse_key(self, hm):
        assert hm._is_mouse_key("mouse_left") is True

    def test_right_button_is_mouse_key(self, hm):
        assert hm._is_mouse_key("mouse_right") is True

    def test_middle_button_is_mouse_key(self, hm):
        assert hm._is_mouse_key("mouse_middle") is True

    def test_keyboard_key_not_mouse_key(self, hm):
        assert hm._is_mouse_key("f1") is False
        assert hm._is_mouse_key("a") is False
        assert hm._is_mouse_key("space") is False

    def test_case_insensitive(self, hm):
        assert hm._is_mouse_key("Mouse_Left") is True
        assert hm._is_mouse_key("MOUSE_RIGHT") is True

    def test_empty_key_not_mouse_key(self, hm):
        assert hm._is_mouse_key("") is False


class TestMouseKeyNormalization:
    def test_normalize_left_button(self, hm):
        assert hm._normalize_mouse_key("left button") == "mouse_left"

    def test_normalize_right_button(self, hm):
        assert hm._normalize_mouse_key("right button") == "mouse_right"

    def test_normalize_mouse_left_alias(self, hm):
        assert hm._normalize_mouse_key("mouse left") == "mouse_left"

    def test_normalize_already_normalized(self, hm):
        assert hm._normalize_mouse_key("mouse_left") == "mouse_left"

    def test_normalize_unknown_key_returns_lower(self, hm):
        assert hm._normalize_mouse_key("UnknownKey") == "unknownkey"


class TestGetKeyName:
    def test_mouse_left_display_name(self):
        assert HotkeyManager.get_key_name("mouse_left") == "鼠标左键"

    def test_mouse_right_display_name(self):
        assert HotkeyManager.get_key_name("mouse_right") == "鼠标右键"

    def test_mouse_middle_display_name(self):
        assert HotkeyManager.get_key_name("mouse_middle") == "鼠标中键"

    def test_empty_key_returns_empty(self):
        assert HotkeyManager.get_key_name("") == ""

    def test_none_key_returns_empty(self):
        assert HotkeyManager.get_key_name(None) == ""

    def test_function_key_display(self):
        result = HotkeyManager.get_key_name("f1")
        assert result  # 非空

    def test_case_insensitive_lookup(self):
        assert HotkeyManager.get_key_name("F1") == HotkeyManager.get_key_name("f1")


class TestMouseKeyMapCompleteness:
    def test_mouse_key_map_has_standard_buttons(self):
        assert "mouse_left" in MOUSE_KEY_MAP
        assert "mouse_right" in MOUSE_KEY_MAP
        assert "mouse_middle" in MOUSE_KEY_MAP

    def test_mouse_key_map_values_normalized(self):
        for v in MOUSE_KEY_MAP.values():
            assert v.startswith("mouse_")
