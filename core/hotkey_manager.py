from core.logger import logger

"""
热键管理模块 (Hotkey Manager)

负责全局热键监听及事件响应。
支持键盘和鼠标按键绑定，支持按下/松开触发方式。
支持每个功能两个热键，支持弹种独立热键。

重要：鼠标低级钩子(WH_MOUSE_LL)对执行时间非常敏感，
钩子过程中不能执行任何耗时操作或访问共享状态，否则会导致系统鼠标卡死。
因此钩子过程只做最基本的事件入队，所有处理在主线程进行。
"""

from collections.abc import Callable

import keyboard
from PyQt5.QtCore import QObject, pyqtSignal

from core.mouse_hook import MouseHook
from core.win32_utils import user32  # 组合键：_check_modifiers 查询修饰键状态

# 鼠标按键名称映射（多种输入格式 → 标准下划线格式）
MOUSE_KEY_MAP = {
    # 标准格式（恒等映射，确保 _is_mouse_key 能识别）
    "mouse_left": "mouse_left",
    "mouse_right": "mouse_right",
    "mouse_middle": "mouse_middle",
    "mouse_xbutton1": "mouse_xbutton1",
    "mouse_xbutton2": "mouse_xbutton2",
    "mouse_wheel_up": "mouse_wheel_up",
    "mouse_wheel_down": "mouse_wheel_down",
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

# 修饰键位掩码（组合键支持）
MOD_CTRL = 0x01
MOD_ALT = 0x02
MOD_SHIFT = 0x04
MOD_WIN = 0x08

# 修饰键名 → (位掩码, 虚拟键码)
_MODIFIER_MAP = {
    "ctrl": (MOD_CTRL, 0x11),
    "control": (MOD_CTRL, 0x11),
    "alt": (MOD_ALT, 0x12),
    "menu": (MOD_ALT, 0x12),
    "shift": (MOD_SHIFT, 0x10),
    "win": (MOD_WIN, 0x5B),
    "windows": (MOD_WIN, 0x5B),
    "meta": (MOD_WIN, 0x5B),
}


def _normalize_keyboard_key_name(key_name):
    """统一标准化键盘键名（注册和触发时都用此函数，确保一致）。
    1. 用 keyboard.normalize_name 标准化（"capslock"→"caps lock"，"win"→"windows"）
    2. 去掉 "left "/"right " 前缀（"left ctrl"→"ctrl"，因为修饰键掩码不区分左右）
    3. "windows"→"win"（统一用短名，和 _MODIFIER_MAP 一致）
    返回标准化后的键名。"""
    if not key_name:
        return ""
    try:
        name = keyboard.normalize_name(key_name.lower().strip())
    except Exception:
        name = key_name.lower().strip()
    # 去掉左右前缀
    if name.startswith("left "):
        name = name[5:]
    elif name.startswith("right "):
        name = name[6:]
    # 统一 windows→win
    if name == "windows":
        name = "win"
    return name


def _parse_hotkey_name(key_name):
    """解析热键名，分离修饰键前缀和主键名。
    返回 (modifiers_mask, pure_key_name)。
    例如 "ctrl+alt+mouse_left" → (MOD_CTRL|MOD_ALT, "mouse_left")
    无修饰键时 modifiers_mask=0。"""
    name = key_name.lower().strip()
    parts = name.split("+")
    modifiers = 0
    pure_parts = []
    for part in parts:
        part = part.strip()
        # 支持 "left ctrl"、"right shift" 等带左右前缀的修饰键
        # 先去掉左右前缀，再判断是否是修饰键
        check_part = part
        if check_part.startswith("left "):
            check_part = check_part[5:]
        elif check_part.startswith("right "):
            check_part = check_part[6:]
        if check_part in _MODIFIER_MAP:
            modifiers |= _MODIFIER_MAP[check_part][0]
        else:
            pure_parts.append(part)
    pure_key = "+".join(pure_parts)
    # 纯修饰键绑定（如单独绑 "shift"）：主键为空，把整个键名当作普通主键处理。
    # mods=0：纯修饰键热键的意思是"这个键按下就触发"，不检查其他修饰键状态。
    # 修饰键检查的跳过逻辑在 _on_key_down 中：当前主键是修饰键时跳过 _check_modifiers。
    if not pure_key:
        return 0, _normalize_keyboard_key_name(key_name)
    # 注意：普通主键不在此标准化，因为不知道是键盘还是鼠标键。
    # 标准化在注册时分别做：_register_keyboard_hotkey 用 _normalize_keyboard_key_name，
    # _register_mouse_hotkey 用 _normalize_mouse_key。
    # 否则 "mouse_wheel_up" 会被 keyboard.normalize_name 改成 "mouse wheel up"，
    # 导致 _is_mouse_key 判断失败，走键盘热键路径，滚轮无法触发。
    return modifiers, pure_key


def _check_modifiers(modifiers_mask):
    """检查热键要求的修饰键是否都按下。
    宽松匹配：要求的修饰键全部按下即触发，额外的修饰键不影响。
    （shift绑反色同时按数字键切弹种，互不冲突，都是用户的选择。）"""
    for mask, vk in _MODIFIER_MAP.values():
        if modifiers_mask & mask:
            if not (user32.GetAsyncKeyState(vk) & 0x8000):
                return False
    return True


# 记录被注册为热键主键的修饰键名（如shift绑反色时，按住shift不应阻止其他无修饰键热键）
_primary_modifier_keys = set()

# shift+数字键的移位字符映射（美式键盘）
_UNSHIFT_MAP = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
    "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
}


class HotkeyManager(QObject):
    """热键管理器 - 管理全局键盘和鼠标热键"""

    # 热键触发信号
    toggle_overlay_triggered = pyqtSignal()
    cycle_magnification_triggered = pyqtSignal()
    invert_colors_triggered = pyqtSignal()
    reset_magnification_triggered = pyqtSignal()
    ammo_switch_triggered = pyqtSignal(str)  # 弹种名称
    squad_macro_triggered = pyqtSignal()  # 建队宏
    angle_meter_toggle_triggered = pyqtSignal()  # 角度仪开始/停止
    angle_meter_pause_triggered = pyqtSignal()  # 角度仪暂离/恢复（保留兼容）
    pause1_triggered = pyqtSignal()  # 暂离键1（地图）
    pause2_triggered = pyqtSignal()  # 暂离键2（指挥面板）
    angle_meter_calibrate_triggered = pyqtSignal()  # 角度仪校准确认
    angle_meter_reset_triggered = pyqtSignal()  # 角度仪定角装填
    angle_meter_up_pressed = pyqtSignal()  # 角度仪上移微调按下
    angle_meter_up_released = pyqtSignal()  # 角度仪上移微调松开
    angle_meter_down_pressed = pyqtSignal()  # 角度仪下移微调按下
    angle_meter_down_released = pyqtSignal()  # 角度仪下移微调松开
    angle_meter_height_up_pressed = pyqtSignal()  # 高度差+按下
    angle_meter_height_up_released = pyqtSignal()  # 高度差+松开
    angle_meter_height_down_pressed = pyqtSignal()  # 高度差-按下
    angle_meter_height_down_released = pyqtSignal()  # 高度差-松开
    distance_meter_toggle_triggered = pyqtSignal()  # 标定测距启用/禁用
    distance_meter_record_triggered = pyqtSignal()  # 标定测距记录（标定）
    distance_meter_measure_triggered = pyqtSignal()  # 标定测距测算（测距）
    distance_meter_cycle_scale_triggered = pyqtSignal()  # 切换比例尺
    distance_meter_quick_measure_triggered = pyqtSignal()  # 快速测距（沿用上一次点1）
    magnifier_toggle_triggered = pyqtSignal()
    magnifier_zoom_in_triggered = pyqtSignal()
    magnifier_zoom_out_triggered = pyqtSignal()
    magnifier_breath_hold_triggered = pyqtSignal()

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
        # sanitize 模式：期间收到的 UP 事件只重置状态不触发回调。
        # sanitize 发送的注入 UP 事件会被键盘钩子捕获，此时不应触发 keyup 回调（如反色关）。
        self._sanitize_mode = False
        # 修饰键支持：每个热键自包含修饰键掩码（如 ctrl+x），不再有全局组合键状态

        # 共享鼠标钩子信号连接（延迟到 initialize）
        self._mouse_hook_connected = False
        # 弹种热键追踪：载具切换时只更新这部分，不重建全局热键
        self._ammo_keyboard_keys = set()
        self._ammo_mouse_keys = set()
        # 标定测距功能启用标志（暂离中才响应）
        self._distance_meter_active = False

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
                try:
                    hook.mouse_wheel.disconnect(self._on_mouse_wheel)
                except Exception:
                    pass
            except Exception:
                pass
            hook.release()
            self._mouse_hook_connected = False
        self._mouse_hotkeys.clear()

    def _unregister_all_keyboard_hotkeys(self):
        """注销所有键盘热键（只摘自己装的全局钩子，不重复操作）

        M4：不用 keyboard.unhook_all()——那是全局公共服务，局部重注册
        挥舞它会静默杀掉任何其他模块（含未来引入的库）注册的钩子。
        只摘自己的 self._keyboard_global_hook（见 _register_keyboard_hotkey）。
        """
        hook = self._keyboard_global_hook
        if hook is not None:
            try:
                keyboard.unhook(hook)
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
                ("pause1", self._on_pause1, "pause1"),
                ("pause2", self._on_pause2, "pause2"),
            ]
            for config_key, callback, tag_prefix in global_hotkeys:
                hk = self.config.get_hotkey(config_key)
                for slot in [1, 2]:
                    key = hk.get(f"key{slot}", "")
                    trigger = hk.get(f"trigger{slot}", "keydown")
                    if key:
                        self._register_hotkey(key, trigger, callback, f"{tag_prefix}_{slot}")

            # 只注册当前载具的弹种热键（按载具维度存储）
            self._ammo_keyboard_keys.clear()
            self._ammo_mouse_keys.clear()
            current_vehicle = self.state.current_vehicle
            if current_vehicle:
                ammo_hotkeys = self.config.get_all_hotkeys().get("ammo_types", {}).get(current_vehicle, {})
                for ammo_name, hk_config in ammo_hotkeys.items():
                    for slot in [1, 2]:
                        key = hk_config.get(f"key{slot}", "")
                        trigger = hk_config.get(f"trigger{slot}", "keydown")
                        if key:
                            self._register_ammo_hotkey(ammo_name, key, trigger)

            # 注册建队宏热键（仅启用时注册，关闭时不占用热键资源）
            if self.config.is_squad_macro_enabled():
                sm_hk = self.config.get_squad_macro_hotkey()
                for slot in (1, 2):
                    sm_key = sm_hk.get(f"key{slot}", "")
                    if sm_key:
                        sm_trigger = sm_hk.get(f"trigger{slot}", "keydown")
                        self._register_hotkey(sm_key, sm_trigger, self._on_squad_macro, f"squad_macro_{slot}")

            # 注册角度仪热键（仅启用时注册，4个动作各单键）
            if self.config.is_angle_meter_enabled():
                am_hks = self.config.get_angle_meter_hotkeys()
                am_actions = [
                    ("toggle", self._on_angle_meter_toggle),
                    ("calibrate", self._on_angle_meter_calibrate),
                    ("reset", self._on_angle_meter_reset),
                ]
                for action, callback in am_actions:
                    hk = am_hks.get(action, {})
                    for slot in (1, 2):
                        key = hk.get(f"key{slot}", "")
                        if key:
                            trigger = hk.get(f"trigger{slot}", "keydown")
                            self._register_hotkey(key, trigger, callback, f"am_{action}_{slot}")
                # up/down 微调热键：同时注册 keydown 和 keyup（用于长按连续输出）
                for action, down_cb, up_cb in [
                    ("up", self._on_angle_meter_up_down, self._on_angle_meter_up_up),
                    ("down", self._on_angle_meter_down_down, self._on_angle_meter_down_up),
                    ("height_up", self._on_angle_meter_height_up_down, self._on_angle_meter_height_up_up),
                    ("height_down", self._on_angle_meter_height_down_down, self._on_angle_meter_height_down_up),
                ]:
                    hk = am_hks.get(action, {})
                    for slot in (1, 2):
                        key = hk.get(f"key{slot}", "")
                        if key:
                            self._register_hotkey(key, "keydown", down_cb, f"am_{action}_down_{slot}")
                            self._register_hotkey(key, "keyup", up_cb, f"am_{action}_up_{slot}")
            # 距离测算热键：toggle始终注册（可随时启用模块），record/measure仅启用时注册
            dm_hks = self.config.get_distance_meter_hotkeys()
            for slot in (1, 2):
                hk = dm_hks.get("toggle", {})
                key = hk.get(f"key{slot}", "")
                if key:
                    trigger = hk.get(f"trigger{slot}", "keydown")
                    self._register_hotkey(key, trigger, self._on_distance_meter_toggle, f"dm_toggle_{slot}")
            if self.config.is_distance_meter_enabled():
                for action, cb in [
                    ("record", self._on_distance_meter_record),
                    ("measure", self._on_distance_meter_measure),
                    ("cycle_scale", self._on_distance_meter_cycle_scale),
                    ("quick_measure", self._on_distance_meter_quick_measure),
                ]:
                    hk = dm_hks.get(action, {})
                    for slot in (1, 2):
                        key = hk.get(f"key{slot}", "")
                        if key:
                            trigger = hk.get(f"trigger{slot}", "keydown")
                            self._register_hotkey(key, trigger, cb, f"dm_{action}_{slot}")

            # 放大镜热键：toggle始终注册，zoom_in/zoom_out仅启用时注册
            mag_hks = self.config.get_magnifier_hotkeys()
            for slot in (1, 2):
                hk = mag_hks.get("toggle", {})
                key = hk.get(f"key{slot}", "")
                if key:
                    trigger = hk.get(f"trigger{slot}", "toggle")
                    self._register_hotkey(key, trigger, self._on_magnifier_toggle, f"mag_toggle_{slot}")
            if self.config.is_magnifier_enabled():
                for action, cb in [
                    ("zoom_in", self._on_magnifier_zoom_in),
                    ("zoom_out", self._on_magnifier_zoom_out),
                    ("breath_hold", self._on_magnifier_breath_hold),
                ]:
                    hk = mag_hks.get(action, {})
                    for slot in (1, 2):
                        key = hk.get(f"key{slot}", "")
                        if key:
                            trigger = hk.get(f"trigger{slot}", "toggle")
                            self._register_hotkey(key, trigger, cb, f"mag_{action}_{slot}")

            # 根源修复：始终启动鼠标钩子，支持滚轮微调等全局鼠标事件
            # 之前只在有鼠标热键时启动，导致绑定键盘键时滚轮不工作
            self._connect_mouse_hook()

        except Exception as e:
            logger.info(f"[HotkeyManager] 注册热键失败: {e}")
            import traceback
            traceback.print_exc()

    def _is_mouse_key(self, key: str) -> bool:
        """判断是否为鼠标按键"""
        return key.lower().strip() in MOUSE_KEY_MAP

    def _normalize_mouse_key(self, key: str) -> str:
        """标准化鼠标按键名称"""
        return MOUSE_KEY_MAP.get(key.lower().strip(), key.lower().strip())

    def _register_hotkey(self, key: str, trigger: str, callback: Callable, tag: str = ""):
        """注册单个热键（自动区分键盘和鼠标）。
        trigger: "toggle"=按下触发一次, "hold"=按下+松开都触发(同一callback),
                 旧值"keydown"/"keyup"向后兼容。"""
        key_lower = key.lower().strip()
        if not key_lower:
            return

        # 分离修饰键和主键，用纯主键判断是键盘还是鼠标热键
        _mods, pure_key = _parse_hotkey_name(key_lower)
        if self._is_mouse_key(pure_key):
            self._register_mouse_hotkey(key_lower, trigger, callback, tag)
        else:
            self._register_keyboard_hotkey(key_lower, trigger, callback, tag)

    def _register_keyboard_hotkey(self, key: str, trigger: str, callback: Callable, tag: str = ""):
        """注册键盘热键（使用一个全局钩子，自己过滤键，边沿触发）

        trigger: "toggle"=只在按下时触发, "hold"=按下和松开都触发,
                 旧值"keydown"/"keyup"向后兼容。
        - keydown: 只在 Up -> Down 边沿触发，按住期间的自动重复全部忽略
        - keyup: 只在 Down -> Up 边沿触发
        """
        try:
            key_lower = key.lower().strip()
            modifiers, pure_key = _parse_hotkey_name(key_lower)
            pure_key = _normalize_keyboard_key_name(pure_key)

            if pure_key not in self._keyboard_hotkeys:
                self._keyboard_hotkeys[pure_key] = {"keydown": [], "keyup": []}

            # 纯修饰键绑定（如shift绑反色hold）：加入忽略列表，按住它时不阻止其他热键
            if pure_key in _MODIFIER_MAP:
                _primary_modifier_keys.add(pure_key)

            # 兼容旧值 + 新值统一映射
            if trigger in ("toggle", "keydown"):
                self._keyboard_hotkeys[pure_key]["keydown"].append((callback, modifiers))
            elif trigger == "keyup":
                self._keyboard_hotkeys[pure_key]["keyup"].append((callback, modifiers))
            elif trigger == "hold":
                self._keyboard_hotkeys[pure_key]["keydown"].append((callback, modifiers))
                self._keyboard_hotkeys[pure_key]["keyup"].append((callback, modifiers))

            if not self._keyboard_global_hook:
                self._keyboard_global_hook = keyboard.hook(self._on_global_keyboard_event)

        except Exception as e:
            logger.info(f"[HotkeyManager] 注册键盘热键 {key} 失败: {e}")

    def _on_global_keyboard_event(self, event):
        """全局键盘事件处理（布尔状态边沿检测 + 修饰键精确匹配）。

        修饰键支持：每个热键自包含 modifiers_mask，触发时检查修饰键状态精确匹配。
        事件键名标准化：用 _normalize_keyboard_key_name 统一标准化（和注册时一致），
        确保 "caps lock"、"page up" 等多词键名能正确匹配，不再用 split()[-1] 导致冲突。
        """
        try:
            # 统一标准化事件键名（和注册时用同一个函数，确保一致）
            # 根源修复：之前用 split()[-1] 会把 "caps lock"→"lock"、"page up"→"up"(和方向键冲突)
            event_key = _normalize_keyboard_key_name(event.name) if event.name else ""
            if not event_key:
                return

            # 按住shift按数字键时，keyboard库可能报"!""@"等移位字符而非"1""2"
            # 映射回基础键名，确保热键能匹配
            if event_key not in self._keyboard_hotkeys:
                event_key = _UNSHIFT_MAP.get(event_key, event_key)

            # 只处理注册了热键的主键
            if event_key not in self._keyboard_hotkeys:
                return

            if event.event_type == "down":
                # 布尔状态边沿检测（和鼠标热键一致）
                current = self._keyboard_key_states.get(event_key, False)
                if current:
                    return
                self._keyboard_key_states[event_key] = True
                # 触发回调前检查修饰键状态（精确匹配）
                # 空房子理论：主键本身是修饰键时（如单独绑shift），跳过修饰键检查。
                # 因为修饰键按下事件不需要再检查"其他修饰键是否按下"。
                is_pure_modifier = event_key in _MODIFIER_MAP
                for cb, mods in self._keyboard_hotkeys[event_key].get("keydown", []):
                    if not is_pure_modifier and not _check_modifiers(mods):
                        continue
                    try:
                        cb()
                    except Exception as e:
                        logger.info(f"[HotkeyManager] 键盘keydown回调错误: {e}")
            elif event.event_type == "up":
                # up事件重置边沿状态 + 触发keyup回调
                self._keyboard_key_states[event_key] = False
                # sanitize 模式：注入 UP 事件只重置状态，不触发回调
                if self._sanitize_mode:
                    return
                is_pure_modifier = event_key in _MODIFIER_MAP
                for cb, mods in self._keyboard_hotkeys[event_key].get("keyup", []):
                    if not is_pure_modifier and not _check_modifiers(mods):
                        continue
                    try:
                        cb()
                    except Exception as e:
                        logger.info(f"[HotkeyManager] 键盘keyup回调错误: {e}")
        except Exception as e:
            logger.info(f"[HotkeyManager] 全局键盘事件处理错误: {e}")

    def _register_mouse_hotkey(self, key: str, trigger: str, callback: Callable, tag: str = ""):
        """注册鼠标热键（边沿触发，状态检测在 _on_mouse_down/_on_mouse_up 中处理）。
        trigger: "toggle"=只在按下时触发, "hold"=按下和松开都触发,
                 旧值"keydown"/"keyup"向后兼容。"""
        try:
            modifiers, pure_key = _parse_hotkey_name(key)
            mouse_key = self._normalize_mouse_key(pure_key)

            if mouse_key not in self._mouse_hotkeys:
                self._mouse_hotkeys[mouse_key] = {"keydown": [], "keyup": []}

            if trigger in ("toggle", "keydown"):
                self._mouse_hotkeys[mouse_key]["keydown"].append((callback, modifiers))
            elif trigger == "keyup":
                self._mouse_hotkeys[mouse_key]["keyup"].append((callback, modifiers))
            elif trigger == "hold":
                self._mouse_hotkeys[mouse_key]["keydown"].append((callback, modifiers))
                self._mouse_hotkeys[mouse_key]["keyup"].append((callback, modifiers))

        except Exception as e:
            logger.info(f"[HotkeyManager] 注册鼠标热键 {key} 失败: {e}")

    def _register_ammo_hotkey(self, ammo_name: str, key: str, trigger: str):
        """注册弹种切换热键"""
        key_lower = key.lower().strip()
        if not key_lower:
            return

        tag = f"ammo_{ammo_name}"

        def callback():
            self._on_switch_ammo(ammo_name)
        callback._is_ammo = True  # 标记为弹种回调，便于部分卸载

        # 记录主键，便于载具切换时定向卸载
        _mods, pure_key = _parse_hotkey_name(key_lower)
        if self._is_mouse_key(pure_key):
            self._ammo_mouse_keys.add(self._normalize_mouse_key(pure_key))
        else:
            self._ammo_keyboard_keys.add(_normalize_keyboard_key_name(pure_key))

        self._register_hotkey(key_lower, trigger, callback, tag)

    def _connect_mouse_hook(self):
        """连接共享鼠标钩子信号并 acquire（引用计数，只在首次连接时 acquire）"""
        hook = MouseHook.instance()
        if not self._mouse_hook_connected:
            hook.mouse_down.connect(self._on_mouse_down)
            hook.mouse_up.connect(self._on_mouse_up)
            hook.mouse_wheel.connect(self._on_mouse_wheel)
            hook.acquire()
            self._mouse_hook_connected = True

    def _on_mouse_down(self, mouse_key: str):
        """共享鼠标钩子按下事件（主线程，Qt 自动跨线程排队）。
        根源修复：组合键支持，触发前检查修饰键是否匹配。"""
        current_state = self._mouse_button_states.get(mouse_key, False)
        if not current_state:
            self._mouse_button_states[mouse_key] = True
            for cb, mods in self._mouse_hotkeys.get(mouse_key, {}).get("keydown", []):
                if not _check_modifiers(mods):
                    continue
                try:
                    cb()
                except Exception as e:
                    logger.info(f"[HotkeyManager] 鼠标keydown回调错误: {e}")

    def _on_mouse_up(self, mouse_key: str):
        """共享鼠标钩子松开事件（主线程，边沿检测）。
        根源修复：组合键支持，触发前检查修饰键是否匹配。"""
        current_state = self._mouse_button_states.get(mouse_key, False)
        if current_state:
            self._mouse_button_states[mouse_key] = False
            for cb, mods in self._mouse_hotkeys.get(mouse_key, {}).get("keyup", []):
                if not _check_modifiers(mods):
                    continue
                try:
                    cb()
                except Exception as e:
                    logger.info(f"[HotkeyManager] 鼠标keyup回调错误: {e}")

    def begin_sanitize(self):
        """进入 sanitize 模式：接下来的 UP 事件只重置状态不触发回调。
        sanitize 发送的注入 UP 事件会被键盘钩子捕获，此时不应触发 keyup 回调。"""
        self._sanitize_mode = True

    def end_sanitize(self):
        """退出 sanitize 模式：恢复正常 UP 事件处理。"""
        self._sanitize_mode = False

    def reset_mouse_button_states(self):
        """重置所有鼠标按键状态（根源修复：BlockInput吞掉物理keyup后，
        注入的keyup被鼠标钩子LLMHF_INJECTED过滤，_mouse_button_states不会重置，
        导致后续keydown被边沿检测忽略，像有CD一样。流程结束后主动调用此方法。）"""
        self._mouse_button_states.clear()

    def reset_keyboard_key_states(self):
        """重置键盘边沿检测状态。"""
        self._keyboard_key_states.clear()

    def reset_flow_input_states(self):
        """流程结束回调：同时复位鼠标与键盘边沿状态。"""
        self.reset_mouse_button_states()
        self.reset_keyboard_key_states()

    def _on_mouse_wheel(self, delta: int):
        """共享鼠标钩子滚轮事件（主线程）。

        滚轮是一种完整的热键主键类型：每次滚动触发一次绑定的回调（keydown 模式）。
        delta>0=向上滚动，delta<0=向下滚动。组合键支持：触发前检查修饰键。"""
        wheel_key = "mouse_wheel_up" if delta > 0 else "mouse_wheel_down"
        for cb, mods in self._mouse_hotkeys.get(wheel_key, {}).get("keydown", []):
            if not _check_modifiers(mods):
                continue
            try:
                cb()
            except Exception as e:
                logger.info(f"[HotkeyManager] 滚轮热键回调错误: {e}")

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

    def _on_pause1(self):
        self.pause1_triggered.emit()

    def _on_pause2(self):
        self.pause2_triggered.emit()

    def _on_switch_ammo(self, ammo_name: str):
        """弹种切换热键触发"""
        self.ammo_switch_triggered.emit(ammo_name)

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

    def _on_angle_meter_height_up_down(self):
        self.angle_meter_height_up_pressed.emit()

    def _on_angle_meter_height_up_up(self):
        self.angle_meter_height_up_released.emit()

    def _on_angle_meter_height_down_down(self):
        self.angle_meter_height_down_pressed.emit()

    def _on_angle_meter_height_down_up(self):
        self.angle_meter_height_down_released.emit()

    def is_distance_meter_active(self) -> bool:
        return getattr(self, '_distance_meter_active', False)

    def set_distance_meter_active(self, active: bool):
        self._distance_meter_active = active

    def _on_distance_meter_toggle(self):
        self.distance_meter_toggle_triggered.emit()

    def _on_distance_meter_record(self):
        if not self._distance_meter_active:
            return
        self.distance_meter_record_triggered.emit()

    def _on_distance_meter_measure(self):
        if not self._distance_meter_active:
            return
        self.distance_meter_measure_triggered.emit()

    def _on_distance_meter_cycle_scale(self):
        if not self._distance_meter_active:
            return
        self.distance_meter_cycle_scale_triggered.emit()

    def _on_distance_meter_quick_measure(self):
        self.distance_meter_quick_measure_triggered.emit()

    def _on_magnifier_toggle(self):
        self.magnifier_toggle_triggered.emit()

    def _on_magnifier_zoom_in(self):
        self.magnifier_zoom_in_triggered.emit()

    def _on_magnifier_zoom_out(self):
        self.magnifier_zoom_out_triggered.emit()

    def _on_magnifier_breath_hold(self):
        self.magnifier_breath_hold_triggered.emit()

    def _unregister_ammo_hotkeys(self):
        """移除当前所有弹种热键回调（保留全局/模块热键）"""
        for key in self._ammo_keyboard_keys:
            if key in self._keyboard_hotkeys:
                for t in ("keydown", "keyup"):
                    self._keyboard_hotkeys[key][t] = [
                        (cb, mods) for cb, mods in self._keyboard_hotkeys[key][t]
                        if not getattr(cb, "_is_ammo", False)
                    ]
        for key in self._ammo_mouse_keys:
            if key in self._mouse_hotkeys:
                for t in ("keydown", "keyup"):
                    self._mouse_hotkeys[key][t] = [
                        (cb, mods) for cb, mods in self._mouse_hotkeys[key][t]
                        if not getattr(cb, "_is_ammo", False)
                    ]
        self._ammo_keyboard_keys.clear()
        self._ammo_mouse_keys.clear()

    def reload_ammo_hotkeys(self):
        """只重新注册弹种热键（载具切换时调用，不重建全局热键）"""
        self._unregister_ammo_hotkeys()
        current_vehicle = self.state.current_vehicle
        if not current_vehicle:
            return
        ammo_hotkeys = self.config.get_all_hotkeys().get("ammo_types", {}).get(current_vehicle, {})
        for ammo_name, hk_config in ammo_hotkeys.items():
            for slot in [1, 2]:
                key = hk_config.get(f"key{slot}", "")
                trigger = hk_config.get(f"trigger{slot}", "keydown")
                if key:
                    self._register_ammo_hotkey(ammo_name, key, trigger)

    def reload_hotkeys(self):
        """全量重新加载所有热键（全局热键/模块配置修改后调用）"""
        self._register_all_hotkeys()

    def set_hotkey_pair(self, config_key: str, hk: dict):
        """统一设置双槽热键（写入两个槽位后重载一次，避免多次全量注册）"""
        self.config.set_hotkey(config_key, hk.get("key1", ""), hk.get("trigger1", "keydown"), 1)
        self.config.set_hotkey(config_key, hk.get("key2", ""), hk.get("trigger2", "keydown"), 2)
        self.reload_hotkeys()

    @staticmethod
    def get_key_name(key_code: str) -> str:
        """获取按键的可读名称（支持修饰键前缀，如 "ctrl+x" -> "Ctrl+X"）。
        此方法覆盖上方的基础实现，增加修饰键解析。"""
        if not key_code:
            return ""
        key_lower = key_code.lower().strip()
        # 分离修饰键和主键
        modifiers, pure_key = _parse_hotkey_name(key_lower)
        # 用基础方法获取主键名称
        base_name = HotkeyManager._get_base_key_name(pure_key)
        if not modifiers:
            return base_name
        # 修饰键名称
        mod_names = []
        if modifiers & MOD_CTRL:
            mod_names.append("Ctrl")
        if modifiers & MOD_ALT:
            mod_names.append("Alt")
        if modifiers & MOD_SHIFT:
            mod_names.append("Shift")
        if modifiers & MOD_WIN:
            mod_names.append("Win")
        return "+".join(mod_names) + "+" + base_name

    @staticmethod
    def _get_base_key_name(key_code: str) -> str:
        """获取主键的可读名称（不含修饰键），供 get_key_name 调用。"""
        if not key_code:
            return ""
        # 先标准化，确保 "capslock"→"caps lock" 能匹配显示映射
        key_lower = _normalize_keyboard_key_name(key_code)
        mouse_display = {
            "mouse_left": "鼠标左键", "mouse_right": "鼠标右键", "mouse_middle": "鼠标中键",
            "mouse_wheel_up": "滚轮向上", "mouse_wheel_down": "滚轮向下",
            "mouse_xbutton1": "Mouse 4", "mouse_xbutton2": "Mouse 5",
        }
        if key_lower in mouse_display:
            return mouse_display[key_lower]
        if key_lower in MOUSE_KEY_MAP:
            normalized = MOUSE_KEY_MAP[key_lower]
            if normalized in mouse_display:
                return mouse_display[normalized]
        key_map = {
            "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win",
            "space": "空格", "enter": "回车", "esc": "Esc", "tab": "Tab",
            "backspace": "退格", "caps lock": "Caps Lock",
            "up": "↑", "down": "↓", "left": "←", "right": "→",
            "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
            "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
            "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
        }
        if key_lower in key_map:
            return key_map[key_lower]
        if len(key_lower) == 1:
            return key_lower.upper()
        return key_lower.capitalize()


