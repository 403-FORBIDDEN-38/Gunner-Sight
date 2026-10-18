"""全局颜色常量（唯一颜色来源，禁止在别处写死颜色）

分三类：
1. 主题调色板（THEME_DARK / THEME_LIGHT）：界面自身（tab/按钮/列表）的明暗两套配色
2. 状态色：角度仪、标定测距等按运行状态变化的文字色
3. 叠加层配色：悬浮在游戏画面上的 overlay 用色。
   底框类**刻意不随主题变化**（压在游戏画面上，浅色主题也要深底）；
   overlay 文字色已改随当前主题走，运行时从 config 取（见文件中部注释）。
"""

# === 主题强调色 ===
# 出厂默认值已移至 config 默认配置模板（core/config/base.py 的 global_settings.accent_dark/light），
# 运行时值走 config.get_accent(theme)。colors.py 不再留强调色默认值。
# hover 态与常态同色，不再单分；强调色底上的文字色 on_accent_text 随主题走
# （见 THEME_DARK / THEME_LIGHT）

# === 主题调色板 ===
# 键：bg 背景 / ctrl 控件底 / border 边框 / hover 悬停
#     text 主文字 / subtext 次要文字 / dis_text 禁用文字
#     on_accent_text 强调色底上的文字
THEME_DARK = {
    "bg": "#1D1D1F",
    "ctrl": "#3A3A3E",  # Fusion 渐变拉平 + 杂项
    "btn": "#202022",  # 按钮：bg +3 明度
    "base": "#1A1A1C",  # 输入框/绑定框：bg -3 明度
    "border": "#3A3A3A",
    "hover": "#454549", "text": "#EBEBEC", "subtext": "#888888", "dis_text": "#666666",
    "on_accent_text": "#1D1D1F",
}
THEME_LIGHT = {
    "bg": "#EBEBEC",
    "ctrl": "#D8D8DC",
    "btn": "#EEEEEF",  # 按钮：bg +3 明度
    "base": "#E8E8E9",  # 输入框/绑定框：bg -3 明度
    "border": "#C8C8CC",
    "hover": "#D0D0D4", "text": "#1D1D1F", "subtext": "#666666", "dis_text": "#AAAAAA",
    "on_accent_text": "#EBEBEC",
}

# === 标定测距状态色（状态色的唯一数值来源）===
DISTANCE_DISABLED = "#888888"
DISTANCE_UNCALIBRATED = "#ff4444"
DISTANCE_CALIBRATING = "#ffaa00"
DISTANCE_CALIBRATED = "#00ff88"
DISTANCE_MEASURING = "#00aaff"

# === 角度仪状态色（与测距状态色同值，语义独立——只是同一族状态色的别名）===
ANGLE_IDLE = DISTANCE_DISABLED          # 灰
ANGLE_ACTIVE = DISTANCE_CALIBRATED     # 绿
ANGLE_PAUSED = DISTANCE_CALIBRATING    # 橙
ANGLE_CALIBRATING = DISTANCE_CALIBRATING  # 橙

# === 叠加层配色 ===
# 三个悬浮窗（滚轮/标定测距/角度仪）的配色自成体系，不随主窗口主题切换：
#   底框：深黑 OVERLAY_BOX_RGB + 不透明度 OVERLAY_BOX_BG_ALPHA（20%），边框统一。
#   文字：通用白字 OVERLAY_TEXT（#EBEBEC）；状态/结果等"关键词"色各自独立保留。
#   窗口级透明度已取消。
# 唯一来源在此，消费方不另搞。
OVERLAY_SEP = "#555555"  # 分隔符
OVERLAY_TEXT = "#EBEBEC"  # 悬浮窗通用白字（主文字/未选中/暂离角标/比例尺/提示文字/角度示数）
# QPainter 用的元组形式（QColor 不认 CSS 的 rgba() 字符串）
OVERLAY_BOX_RGB = (20, 20, 20)
OVERLAY_BOX_BG_ALPHA = 51  # 20% 不透明
OVERLAY_BOX_BORDER_RGBA = (255, 255, 255, 40)
# QSS 字符串形式（滚轮用）：与上面元组同源，不另写死
OVERLAY_BOX_BG = f"rgba({OVERLAY_BOX_RGB[0]},{OVERLAY_BOX_RGB[1]},{OVERLAY_BOX_RGB[2]},{OVERLAY_BOX_BG_ALPHA})"
OVERLAY_BOX_BORDER = f"rgba({OVERLAY_BOX_BORDER_RGBA[0]},{OVERLAY_BOX_BORDER_RGBA[1]},{OVERLAY_BOX_BORDER_RGBA[2]},{OVERLAY_BOX_BORDER_RGBA[3]})"

# === 吉祥物 / 提示条 ===
MASCOT_TEXT = "#382923"
NOTICE_TEXT = "#8A6D00"
NOTICE_BG = "rgba(255, 200, 0, 25)"
NOTICE_BORDER = "rgba(200, 160, 0, 60)"

# === 其他 ===
CAL_HINT = DISTANCE_CALIBRATING  # 标定提示文字色（与测距标定状态色同值，语义独立）
