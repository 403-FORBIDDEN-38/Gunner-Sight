"""
热键管理模块 (Hotkey Manager)

负责全局热键监听及事件响应。
支持键盘和鼠标按键绑定，支持按下/松开触发方式。
支持每个功能两个热键，支持弹种独立热键。

重要：鼠标低级钩子(WH_MOUSE_LL)对执行时间非常敏感，
钩子过程中不能执行任何耗时操作或访问共享状态，否则会导致系统鼠标卡死。
因此钩子过程只做最基本的事件入队，所有处理在主线程进行。
"""

from PyQt5.QtCore import QObject, pyqtSignal
from typing import Callable

import keyboard
from core.mouse_hook import MouseHook


# 鼠标按键名称映射（多种输入格式 → 标准下划线格式）
MOUSE_KEY_MAP = {
    # 标准格式（恒等映射，确保 _is_mouse_key 能识别）
    "mouse_left": "mouse_left",
    "mouse_right": "mouse_right",
    "mouse_middle": "mouse_middle",
    "mouse_xbutton1": "mouse_xbutton1",
    "mouse_xbutton2": "mouse_xbutton2",
    # 别名格式
    "mouse left": "mouse_left",
    "mouse right": "mouse_right",
    "mouse middle": "mouse_middle",
    "mouse4": "mouse_xbutton1",
    "mouse5": "mouse_xbutton2",
    "mouse xbutton1": "mouse_xbutton1",
    "mouse xbutton2": "mouse_xbutton2",
    "left button": "mouse_left",
    "right button": "mouse_right",
    "middle button": "mouse_middle",
    "xbutton1": "mouse_xbutton1",
    "xbutton2": "mouse_xbutton2",
}


class HotkeyManager(QObject):
    """热键管理器 - 管理全局键盘和鼠标热键"""

    # 热键触发信号
    toggle_overlay_triggered = pyqtSignal()
    cycle_magnification_triggered = pyqtSignal()
    invert_colors_triggered = pyqtSignal()
    reset_magnification_triggered = pyqtSignal()
    ammo_switch_triggered = pyqtSignal(str)  # 弹种名称
    rangefinder_measure_triggered = pyqtSignal()  # 测距仪触发
    toggle_ui_triggered = pyqtSignal()  # 有/无UI快速切换
    squad_macro_triggered = pyqtSignal()  # 建队宏
    angle_meter_toggle_triggered = pyqtSignal()  # 角度仪开始/停止
    angle_meter_pause_triggered = pyqtSignal()  # 角度仪暂离/恢复
    angle_meter_calibrate_triggered = pyqtSignal()  # 角度仪校准确认
    angle_meter_reset_triggered = pyqtSignal()  # 角度仪归零
    angle_meter_up_pressed = pyqtSignal()  # 角度仪上移微调按下
    angle_meter_up_released = pyqtSignal()  # 角度仪上移微调松开
    angle_meter_down_pressed = pyqtSignal()  # 角度仪下移微调按下
    angle_meter_down_released = pyqtSignal()  # 角度仪下移微调松开
    distance_meter_toggle_triggered = pyqtSignal()  # 标定测距启用/禁用
    distance_meter_record_triggered = pyqtSignal()  # 标定测距记录（标定）
    distance_meter_measure_triggered = pyqtSignal()  # 标定测距测算（测距）

    def __init__(self, config_manager, state_machine, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.state = state_machine

        # 键盘热键回调 {key: {"keydown": [callbacks], "keyup": [callbacks]}}
        self._keyboard_hotkeys = {}
        self._keyboard_global_hook = None
        # 已注册的鼠标热键回调 {mouse_key: {"keydown": [callbacks], "keyup": [callbacks]}}
        self._mouse_hotkeys = {}

        # 按键物理状态跟踪（边沿检测）
        self._keyboard_key_states = {}
        self._mouse_button_states = {}

        # 共享鼠标钩子信号连接（延迟到 initialize）
        self._mouse_hook_connected = False

    def initialize(self):
        """初始化热键系统"""
        global keyboard
        import keyboard
        self._register_all_hotkeys()

    def shutdown(self):
        """关闭热键系统"""
        self._unregister_all_keyboard_hotkeys()
        if self._mouse_hook_connected:
            hook = MouseHook.instance()
            try:
                hook.mouse_down.disconnect(self._on_mouse_down)
                hook.mouse_up.disconnect(self._on_mouse_up)
            except Exception:
                pass
            hook.release()
            self._mouse_hook_connected = False
        self._mouse_hotkeys.clear()

    def _unregister_all_keyboard_hotkeys(self):
        """注销所有键盘热键（P0-3：直接unhook_all，不重复操作）"""
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self._keyboard_global_hook = None
        self._keyboard_hotkeys.clear()

    def _register_all_hotkeys(self):
        """注册所有配置的热键"""
        try:
            # 先清除所有现有热键
            self._unregister_all_keyboard_hotkeys()
            self._mouse_hotkeys.clear()
            # 重置按键物理状态（重新注册后状态未知，下次事件会重新建立）
            self._keyboard_key_states.clear()
            self._mouse_button_states.clear()

            # 注册全局热键（数据驱动：toggle/cycle/invert/reset 结构完全一致）
            global_hotkeys = [
                ("toggle_overlay", self._on_toggle_overlay, "toggle"),
                ("cycle_magnification", self._on_cycle_magnification, "cycle"),
                ("invert_colors", self._on_invert_colors, "invert"),
                ("reset_magnification", self._on_reset_magnification, "reset"),
            ]
            for config_key, callback, tag_prefix in global_hotkeys:
                hk = self.config.get_hotkey(config_key)
                for slot in [1, 2]:
                    key = hk.get(f"key{slot}", "")
                    trigger = hk.get(f"trigger{slot}", "keydown")
                    if key:
                        self._register_hotkey(key, trigger, callback, f"{tag_prefix}_{slot}")

            # 注册有/无UI快速切换热键（独立于测距仪启用，但受 toggle_ui_enabled 控制）
            if self.config.is_toggle_ui_enabled():
                toggle_ui_hk = self.config.get_hotkey("toggle_ui")
                for slot in [1, 2]:
                    key = toggle_ui_hk.get(f"key{slot}", "")
                    trigger = toggle_ui_hk.get(f"trigger{slot}", "keydown")
                    if key:
                        self._register_hotkey(key, trigger, self._on_toggle_ui, f"toggle_ui_{slot}")

            # 只注册当前载具的弹种热键（按载具维度存储）
            current_vehicle = self.config.get_current_state().get("vehicle")
            if current_vehicle:
                ammo_hotkeys = self.config.get_all_hotkeys().get("ammo_types", {}).get(current_vehicle, {})
                for ammo_name, hk_config in ammo_hotkeys.items():
                    for slot in [1, 2]:
                        key = hk_config.get(f"key{slot}", "")
                        trigger = hk_config.get(f"trigger{slot}", "keydown")
                        if key:
                            self._register_ammo_hotkey(ammo_name, key, trigger)

            # 注册测距仪热键（仅当测距仪启用时）
            if self.config.is_rangefinder_enabled():
                rangefinder_hk = self.config.get_rangefinder_hotkeys().get("measure", {})
                for slot in [1, 2]:
                    key = rangefinder_hk.get(f"key{slot}", "")
                    trigger = rangefinder_hk.get(f"trigger{slot}", "keydown")
                    if key:
                        self._register_hotkey(key, trigger, self._on_rangefinder_measure, f"rangefinder_measure_{slot}")

            # 注册建队宏热键（仅启用时注册，关闭时不占用热键资源）
            if self.config.is_squad_macro_enabled():
                sm_hk = self.config.get_squad_macro_hotkey()
                sm_key = sm_hk.get("key1", "")
                sm_trigger = sm_hk.get("trigger1", "keydown")
                if sm_key:
                    self._register_hotkey(sm_key, sm_trigger, self._on_squad_macro, "squad_macro")

            # 注册角度仪热键（仅启用时注册，4个动作各单键）
            if self.config.is_angle_meter_enabled():
                am_hks = self.config.get_angle_meter_hotkeys()
                am_actions = [
                    ("toggle", self._on_angle_meter_toggle),
                    ("pause", self._on_angle_meter_pause),
                    ("calibrate", self._on_angle_meter_calibrate),
                    ("reset", self._on_angle_meter_reset),
                ]
                for action, callback in am_actions:
                    hk = am_hks.get(action, {})
                    key = hk.get("key1", "")
                    trigger = hk.get("trigger1", "keydown")
                    if key:
                        self._register_hotkey(key, trigger, callback, f"am_{action}")
                # up/down 微调热键：同时注册 keydown 和 keyup（用于长按连续输出）
                for action, down_cb, up_cb in [
                    ("up", self._on_angle_meter_up_down, self._on_angle_meter_up_up),
                    ("down", self._on_angle_meter_down_down, self._on_angle_meter_down_up),
                ]:
                    hk = am_hks.get(action, {})
                    key = hk.get("key1", "")
                    if key:
                        self._register_hotkey(key, "keydown", down_cb, f"am_{action}_down")
                        self._register_hotkey(key, "keyup", up_cb, f"am_{action}_up")
            # 距离测算热键（FEATURE-3）：toggle始终注册（可随时启用模块），record/measure仅启用时注册
            dm_hks = self.config.get_distance_meter_hotkeys()
            # toggle热键无条件注册
            for slot in (1, 2):
                hk = dm_hks.get("toggle", {})
                key = hk.get(f"key{slot}", "")
                if key:
                    trigger = hk.get(f"trigger{slot}", "keydown")
                    self._register_hotkey(key, trigger, self._on_distance_meter_toggle, f"dm_toggle_{slot}")
            # record/measure仅启用时注册
            if self.config.is_distance_meter_enabled():
                for action, cb in [
                    ("record", self._on_distance_meter_record),
                    ("measure", self._on_distance_meter_measure),
                ]:
                    hk = dm_hks.get(action, {})
                    for slot in (1, 2):
                        key = hk.get(f"key{slot}", "")
                        if key:
                            trigger = hk.get(f"trigger{slot}", "keydown")
                            self._register_hotkey(key, trigger, cb, f"dm_{action}_{slot}")

            # 如果有鼠标热键，确保共享鼠标钩子已连接并 acquire
            if self._mouse_hotkeys:
                self._connect_mouse_hook()
            else:
                self._disconnect_mouse_hook()

        except Exception as e:
            print(f"[HotkeyManager] 注册热键失败: {e}")
            import traceback
            traceback.print_exc()

    def _is_mouse_key(self, key: str) -> bool:
        """判断是否为鼠标按键"""
        return key.lower().strip() in MOUSE_KEY_MAP

    def _normalize_mouse_key(self, key: str) -> str:
        """标准化鼠标按键名称"""
        return MOUSE_KEY_MAP.get(key.lower().strip(), key.lower().strip())

    def _register_hotkey(self, key: str, trigger: str, callback: Callable, tag: str = ""):
        """注册单个热键（自动区分键盘和鼠标）"""
        key_lower = key.lower().strip()
        if not key_lower:
            return

        if self._is_mouse_key(key_lower):
            self._register_mouse_hotkey(key_lower, trigger, callback, tag)
        else:
            self._register_keyboard_hotkey(key_lower, trigger, callback, tag)

    def _register_keyboard_hotkey(self, key: str, trigger: str, callback: Callable, tag: str = ""):
        """注册键盘热键（使用一个全局钩子，自己过滤键，边沿触发）

        - keydown: 只在 Up -> Down 边沿触发，按住期间的自动重复全部忽略
        - keyup: 只在 Down -> Up 边沿触发
        同一个键可以同时注册 keydown 和 keyup 回调，互不干扰。
        """
        try:
            key_lower = key.lower().strip()

            # 将回调添加到该键的对应触发类型列表
            if key_lower not in self._keyboard_hotkeys:
                self._keyboard_hotkeys[key_lower] = {"keydown": [], "keyup": []}

            self._keyboard_hotkeys[key_lower][trigger].append(callback)

            # 如果全局钩子还没注册，注册一个
            if not self._keyboard_global_hook:
                self._keyboard_global_hook = keyboard.hook(self._on_global_keyboard_event)

        except Exception as e:
            print(f"[HotkeyManager] 注册键盘热键 {key} 失败: {e}")

    def _on_global_keyboard_event(self, event):
        """全局键盘事件处理（所有按键事件都会经过这里，自己过滤）

        严格的边沿检测：
        - down 事件且当前状态是 Up → 触发 keydown 回调，状态改为 Down
        - down 事件且当前状态是 Down → 忽略（自动重复）
        - up 事件且当前状态是 Down → 触发 keyup 回调，状态改为 Up
        - up 事件且当前状态是 Up → 忽略
        """
        try:
            event_key = event.name.lower() if event.name else ""
            if not event_key:
                return

            # 只处理注册了热键的键
            if event_key not in self._keyboard_hotkeys:
                return

            current_state = self._keyboard_key_states.get(event_key, False)

            if event.event_type == "down":
                if not current_state:
                    # Up -> Down 边沿
                    self._keyboard_key_states[event_key] = True
                    for cb in self._keyboard_hotkeys[event_key].get("keydown", []):
                        try:
                            cb()
                        except Exception as e:
                            print(f"[HotkeyManager] 键盘keydown回调错误: {e}")
                # else: 已经是 Down，自动重复，忽略
            elif event.event_type == "up":
                if current_state:
                    # Down -> Up 边沿
                    self._keyboard_key_states[event_key] = False
                    for cb in self._keyboard_hotkeys[event_key].get("keyup", []):
                        try:
                            cb()
                        except Exception as e:
                            print(f"[HotkeyManager] 键盘keyup回调错误: {e}")
                # else: 已经是 Up，忽略
        except Exception as e:
            print(f"[HotkeyManager] 全局键盘事件处理错误: {e}")

    def _register_mouse_hotkey(self, key: str, trigger: str, callback: Callable, tag: str = ""):
        """注册鼠标热键（边沿触发，状态检测在 _on_mouse_down/_on_mouse_up 中处理）"""
        try:
            mouse_key = self._normalize_mouse_key(key)

            if mouse_key not in self._mouse_hotkeys:
                self._mouse_hotkeys[mouse_key] = {"keydown": [], "keyup": []}

            self._mouse_hotkeys[mouse_key][trigger].append(callback)

        except Exception as e:
            print(f"[HotkeyManager] 注册鼠标热键 {key} 失败: {e}")

    def _register_ammo_hotkey(self, ammo_name: str, key: str, trigger: str):
        """注册弹种切换热键"""
        key_lower = key.lower().strip()
        if not key_lower:
            return

        tag = f"ammo_{ammo_name}"

        def callback():
            self._on_switch_ammo(ammo_name)

        self._register_hotkey(key_lower, trigger, callback, tag)

    def _connect_mouse_hook(self):
        """连接共享鼠标钩子信号并 acquire（引用计数）"""
        hook = MouseHook.instance()
        if not self._mouse_hook_connected:
            hook.mouse_down.connect(self._on_mouse_down)
            hook.mouse_up.connect(self._on_mouse_up)
            self._mouse_hook_connected = True
        hook.acquire()

    def _disconnect_mouse_hook(self):
        """释放共享鼠标钩子引用（最后一个持有者释放时钩子停止）"""
        if self._mouse_hook_connected:
            MouseHook.instance().release()
            # 保持信号连接，下次 acquire 时无需重连；shutdown 时才断开
            # 这里只 release，不 disconnect，避免频繁 connect/disconnect

    def _on_mouse_down(self, mouse_key: str):
        """共享鼠标钩子按下事件（主线程，Qt 自动跨线程排队）"""
        current_state = self._mouse_button_states.get(mouse_key, False)
        if not current_state:
            self._mouse_button_states[mouse_key] = True
            for cb in self._mouse_hotkeys.get(mouse_key, {}).get("keydown", []):
                try:
                    cb()
                except Exception as e:
                    print(f"[HotkeyManager] 鼠标keydown回调错误: {e}")

    def _on_mouse_up(self, mouse_key: str):
        """共享鼠标钩子松开事件（主线程，边沿检测）"""
        current_state = self._mouse_button_states.get(mouse_key, False)
        if current_state:
            self._mouse_button_states[mouse_key] = False
            for cb in self._mouse_hotkeys.get(mouse_key, {}).get("keyup", []):
                try:
                    cb()
                except Exception as e:
                    print(f"[HotkeyManager] 鼠标keyup回调错误: {e}")

    def _on_toggle_overlay(self):
        """显示/隐藏热键触发"""
        self.toggle_overlay_triggered.emit()

    def _on_cycle_magnification(self):
        """倍率切换热键触发"""
        self.cycle_magnification_triggered.emit()

    def _on_invert_colors(self):
        """一键反色热键触发"""
        self.invert_colors_triggered.emit()

    def _on_reset_magnification(self):
        """重置倍率热键触发"""
        self.reset_magnification_triggered.emit()

    def _on_switch_ammo(self, ammo_name: str):
        """弹种切换热键触发"""
        self.ammo_switch_triggered.emit(ammo_name)

    def _on_rangefinder_measure(self):
        """测距仪热键触发"""
        self.rangefinder_measure_triggered.emit()

    def _on_toggle_ui(self):
        """有/无UI快速切换热键触发"""
        self.toggle_ui_triggered.emit()

    def _on_squad_macro(self):
        """建队宏热键触发"""
        self.squad_macro_triggered.emit()

    def _on_angle_meter_toggle(self):
        self.angle_meter_toggle_triggered.emit()

    def _on_angle_meter_pause(self):
        self.angle_meter_pause_triggered.emit()

    def _on_angle_meter_calibrate(self):
        self.angle_meter_calibrate_triggered.emit()

    def _on_angle_meter_reset(self):
        self.angle_meter_reset_triggered.emit()

    def _on_angle_meter_up_down(self):
        self.angle_meter_up_pressed.emit()

    def _on_angle_meter_up_up(self):
        self.angle_meter_up_released.emit()

    def _on_angle_meter_down_down(self):
        self.angle_meter_down_pressed.emit()

    def _on_angle_meter_down_up(self):
        self.angle_meter_down_released.emit()

    def _on_distance_meter_toggle(self):
        self.distance_meter_toggle_triggered.emit()

    def _on_distance_meter_record(self):
        self.distance_meter_record_triggered.emit()

    def _on_distance_meter_measure(self):
        self.distance_meter_measure_triggered.emit()

    def reload_hotkeys(self):
        """重新加载所有热键（配置修改后调用）"""
        self._register_all_hotkeys()

    def set_hotkey_pair(self, config_key: str, hk: dict):
        """统一设置双槽热键（写入两个槽位后重载一次，避免多次全量注册）"""
        self.config.set_hotkey(config_key, hk.get("key1", ""), hk.get("trigger1", "keydown"), 1)
        self.config.set_hotkey(config_key, hk.get("key2", ""), hk.get("trigger2", "keydown"), 2)
        self.reload_hotkeys()
    @staticmethod
    def get_key_name(key_code: str) -> str:
        """获取按键的可读名称"""
        if not key_code:
            return ""

        key_lower = key_code.lower().strip()

        # 鼠标按键
        mouse_display = {
            "mouse_left": "鼠标左键",
            "mouse_right": "鼠标右键",
            "mouse_middle": "鼠标中键",
            "mouse_xbutton1": "Mouse 4",
            "mouse_xbutton2": "Mouse 5",
        }
        if key_lower in mouse_display:
            return mouse_display[key_lower]

        # 检查是否是鼠标按键的其他名称
        if key_lower in MOUSE_KEY_MAP:
            normalized = MOUSE_KEY_MAP[key_lower]
            if normalized in mouse_display:
                return mouse_display[normalized]

        # 键盘按键
        key_map = {
            "ctrl": "Ctrl",
            "left ctrl": "左Ctrl",
            "right ctrl": "右Ctrl",
            "alt": "Alt",
            "left alt": "左Alt",
            "right alt": "右Alt",
            "shift": "Shift",
            "left shift": "左Shift",
            "right shift": "右Shift",
            "space": "空格",
            "enter": "回车",
            "esc": "Esc",
            "tab": "Tab",
            "backspace": "退格",
            "caps lock": "Caps Lock",
            "up": "↑",
            "down": "↓",
            "left": "←",
            "right": "→",
            "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
            "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
            "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
        }
        return key_map.get(key_lower, key_code.upper())
