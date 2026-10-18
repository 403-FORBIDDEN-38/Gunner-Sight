# GUI 控件清单（事实底稿）

> 由脚本遍历 QWidget 树导出，**不是手写**。用途：写手册时确认「页面上有什么」。
> 参数（range/当前值）来自**代码骨架默认值**；用户实际看到的值见文末「出厂配置」。

## 导航组：准星

### 准星面板  `TAB_0` = 0

```
      - QGroupBox 「载具选择」  flat
            - QLineEdit placeholder=「搜索载具...」
            - QComboBox 1 项: ['全部标签']  当前=「全部标签」
            - QListWidget 0 项  []
        - QLabel 「弹种:」
        - QComboBox 0 项: []  当前=「」
        - QPushButton 「切换倍率」
      - QGroupBox 「准星参数」
        - QLabel 「大小缩放:」
          - QDoubleSpinBox range=[1.0, 1000.0] 当前=100.0  suffix=「 %」  decimals=1
          - QSlider range=[1, 1000] 当前=100
        - QLabel 「横向偏移:」
          - QSpinBox range=[-500, 500] 当前=0  suffix=「 px」
          - QSlider range=[-500, 500] 当前=0
        - QLabel 「竖向偏移:」
          - QSpinBox range=[-500, 500] 当前=0  suffix=「 px」
          - QSlider range=[-500, 500] 当前=0
        - QLabel 「不透明度:」
          - QSpinBox range=[10, 100] 当前=100  suffix=「 %」
          - QSlider range=[10, 100] 当前=100
      - QGroupBox 「滚轮窗口」  flat
        - QLabel 「横向偏移:」
        - QSpinBox range=[-2000, 2000] 当前=0  suffix=「 px」
        - QLabel 「纵向偏移:」
        - QSpinBox range=[-2000, 2000] 当前=0  suffix=「 px」
```

### 载具配置  `TAB_1` = 1

```
  - QSplitter 3 段 sizes=[145, 194, 293]
    - QGroupBox 「标签列表」
      - QListWidget 2 项  ['全部标签', '收藏']
      - QLineEdit placeholder=「点击创建标签」
      - QPushButton 「+」
      - QPushButton 「重命名」
      - QPushButton 「删除」
    - QGroupBox 「载具列表」  flat
      - QLineEdit placeholder=「搜索载具...」
      - QListWidget 0 项  []
      - QPushButton 「添加」
      - QPushButton 「复制」
      - QPushButton 「重命名」
      - QPushButton 「删除」
      - QPushButton 「导出」
      - QPushButton 「导入」
      - QGroupBox 「载具图片」  flat
        - QListWidget 0 项  []
      - QSplitter 2 段 sizes=[0, 0]
        - QGroupBox 「弹种列表」
          - QListWidget 0 项  []
          - QPushButton 「添加」
          - QPushButton 「重命名」
          - QPushButton 「删除」
        - QGroupBox 「倍率列表」  flat
          - QListWidget 0 项  []
          - QPushButton 「添加」
          - QPushButton 「删除」
          - QCheckBox 「独立偏移」  checked=False
          - QCheckBox 「叠加载具图片」  checked=False
          - QCheckBox 「叠加弹种图片」  checked=False
      - QGroupBox 「独立偏移」
        - QLabel 「大小缩放:」
          - QSlider range=[1, 1000] 当前=100
          - QSpinBox range=[1, 1000] 当前=100  suffix=「%」
        - QLabel 「横向偏移:」
        - QSpinBox range=[-500, 500] 当前=0
        - QLabel 「竖向偏移:」
        - QSpinBox range=[-500, 500] 当前=0
        - QLabel 「不透明度:」
          - QPushButton 「-」
          - QSpinBox range=[10, 100] 当前=100  suffix=「%」
          - QSlider range=[10, 100] 当前=100
          - QPushButton 「+」
        - QLabel 「倍率选"独立"时使用此配置」  objectName=hint_text
```

### 热键设置  `TAB_2` = 2

```
      - QGroupBox 「全局热键」
          - QLabel 「显示/隐藏准星」
          - QLineEdit placeholder=「点击设置...」
          - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLineEdit placeholder=「点击设置...」
          - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLabel 「切换倍率」
          - QLineEdit placeholder=「点击设置...」
          - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLineEdit placeholder=「点击设置...」
          - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLabel 「一键反色」
          - QLineEdit placeholder=「点击设置...」
          - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLineEdit placeholder=「点击设置...」
          - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLabel 「重置倍率」
          - QLineEdit placeholder=「点击设置...」
          - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLineEdit placeholder=「点击设置...」
          - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLabel 「暂离」
          - QLineEdit placeholder=「点击设置...」
          - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLineEdit placeholder=「点击设置...」
          - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
      - QGroupBox 「弹种切换热键（当前载具）」  flat
      - QLabel 「提示：点击热键输入框后按下想要设置的按键即可绑定。按 Esc 取消设置。」  objectName=hint_text
```

### 适配设置  `TAB_7` = 7

```
  - QGroupBox 「屏幕」  flat
    - QLabel 「显示器:」
    - QComboBox 1 项: ['显示器1 (800×600)']  当前=「显示器1 (800×600)」
    - QPushButton 「识别当前屏」
  - QGroupBox 「屏幕缩放（sx/sy 机械系数）」
    - QLabel 「模式:」
    - QRadioButton 「预设」  checked=True
    - QRadioButton 「自定义」  checked=False
      - QLabel 「档位:」
      - QComboBox 3 项: ['1K', '2K', '4K']  当前=「1K」
      - QLabel 「宽高比:」
      - QComboBox 3 项: ['16:9', '16:10', '4:3']  当前=「16:9」
      - QLabel 「sx=1.000 sy=1.000」
      - QLabel 「横向缩放 sx:」
      - QDoubleSpinBox range=[0.05, 3.0] 当前=0.05  decimals=3
      - QComboBox 2 项: ['增加', '拉伸']  当前=「增加」
      - QLabel 「竖向缩放 sy:」
      - QDoubleSpinBox range=[0.05, 3.0] 当前=0.05  decimals=3
      - QComboBox 2 项: ['增加', '拉伸']  当前=「增加」
  - QGroupBox 「主题色设置」  flat
    - QLabel 「深色主题:」
    - QPushButton <无文字，纯色块/图标>
    - QLabel 「浅色主题:」
    - QPushButton <无文字，纯色块/图标>
  - QLabel 「说明：横向sx/竖向sy可各自独立选择适配逻辑。增加=游戏拓宽视野画面不拉伸，该轴等比缩放(圆不变形)；拉伸=游戏画面拉」  objectName=hint_text
```

## 导航组：工具

### 标定测距  `TAB_4` = 4

```
  - QCheckBox 「启用标定测距模块」  checked=True
    - QLabel 「操作流程：1.启用模块 2.按标定热键标定比例尺两端 3.按测距热键测距目标两端」  objectName=hint_text
    - QGroupBox 「当前状态」  flat
      - QLabel 「比例尺：300m」
      - QLabel 「标定状态：待机」
    - QGroupBox 「热键设置」
        - QLabel 「标定」
        - QLineEdit placeholder=「点击设置...」
        - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
        - QLineEdit placeholder=「点击设置...」
        - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
        - QLabel 「测距」
        - QLineEdit placeholder=「点击设置...」
        - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
        - QLineEdit placeholder=「点击设置...」
        - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
        - QLabel 「切换比例尺」
        - QLineEdit placeholder=「点击设置...」
        - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
        - QLineEdit placeholder=「点击设置...」
        - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
        - QLabel 「快速测距」
        - QLineEdit placeholder=「点击设置...」
        - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
        - QLineEdit placeholder=「点击设置...」
        - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
    - QGroupBox 「悬浮窗口设置（右下偏移）」  flat
      - QLabel 「横向偏移：」
      - QDoubleSpinBox range=[0.0, 2000.0] 当前=100.0
      - QLabel 「竖向偏移：」
      - QDoubleSpinBox range=[0.0, 2000.0] 当前=100.0
```

### 放大镜  `TAB_9` = 9

```
      - QCheckBox 「启用放大镜模块」  checked=True
        - QLabel 「2.00x」  objectName=zoom_display
        - QGroupBox 「基本参数」  flat
          - QLabel 「外框半径:」
          - QSpinBox range=[10, 2000] 当前=200  suffix=「 px」
          - QLabel 「截屏帧率:」
          - QSpinBox range=[15, 144] 当前=60  suffix=「 fps」
          - QLabel 「X偏移:」
          - QSpinBox range=[-2000, 2000] 当前=0  suffix=「 px」
          - QLabel 「屏息半径步长:」
          - QSpinBox range=[1, 500] 当前=20  suffix=「 px」
          - QLabel 「屏息倍率步长:」
          - QDoubleSpinBox range=[0.0, 10.0] 当前=0.0  suffix=「x」  decimals=2
          - QLabel 「Y偏移:」
          - QSpinBox range=[-2000, 2000] 当前=0  suffix=「 px」
        - QGroupBox 「热键设置」
            - QLabel 「开关」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLabel 「放大」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLabel 「缩小」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLabel 「屏息缩放」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
        - QGroupBox 「枪械列表」  flat
            - QLineEdit placeholder=「搜索配置...」
            - QComboBox 1 项: ['全部标签']  当前=「全部标签」
            - QListWidget 0 项  []
            - QPushButton 「新建」
            - QPushButton 「重命名」
            - QPushButton 「删除」
            - QListWidget 0 项  []
```

### 角度仪  `TAB_3` = 3

```
      - QCheckBox 「启用角度仪模块」  checked=True
        - QGroupBox 「使用设置」  flat
          - QLabel 「⚠ 使用前请将炮塔调到最低角，然后按开始」  objectName=hint_text
          - QLabel 「+0.0°」  objectName=angle_display
          - QPushButton 「开始使用」
          - QLabel 「开始/停止:」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLabel 「校准确认:」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLabel 「── 微调热键 ──」  objectName=hint_text
          - QLabel 「上移微调:」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLabel 「下移微调:」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLabel 「── 高度差热键 ──」  objectName=hint_text
          - QLabel 「高度差+:」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLabel 「高度差-:」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLabel 「窗口X:」
          - QSpinBox range=[0, 9999] 当前=0
          - QLabel 「Y:」
          - QSpinBox range=[0, 9999] 当前=0
        - QGroupBox 「校准设置」
          - QLabel 「精度方案:」
          - QComboBox 3 项: ['2 点', '5 点', '11 点']  当前=「2 点」
          - QLabel 「灵敏度:」
          - QDoubleSpinBox range=[0.01, 100.0] 当前=1.0  decimals=2
          - QPushButton 「开始校准」
        - QGroupBox 「角度仪配置」  flat
          - QLabel 「最低角:」
          - QDoubleSpinBox range=[-180.0, 180.0] 当前=0.0  suffix=「°」  decimals=2
          - QLabel 「最高角:」
          - QDoubleSpinBox range=[-180.0, 180.0] 当前=0.0  suffix=「°」  decimals=2
          - QCheckBox 「启用定角装填」  checked=False
          - QLabel 「适用于开火后角度归于水平的武器」  objectName=hint_text
          - QLabel 「定角装填热键:」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
            - QLineEdit placeholder=「点击设置...」
            - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
          - QLabel 「角度仪列表与关联载具」
            - QLineEdit placeholder=「搜索配置...」
            - QComboBox 1 项: ['全部标签']  当前=「全部标签」
            - QListWidget 0 项  []
            - QPushButton 「新建」
            - QPushButton 「重命名」
            - QPushButton 「删除」
              - QLineEdit placeholder=「搜索载具...」
              - QComboBox 0 项: []  当前=「」
              - QListWidget 0 项  []
        - QGroupBox 「射表拟合」
          - QTableWidget 0行×2列  表头=['角度 (°)', '距离 (m)']
          - QPushButton 「加行」
          - QPushButton 「删行」
```

### 建队宏  `TAB_5` = 5

```
  - QCheckBox 「启用建队循环」  checked=True
    - QGroupBox 「建队循环」  flat
      - QLabel 「建队热键:」
        - QLineEdit placeholder=「点击设置...」
        - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
        - QLineEdit placeholder=「点击设置...」
        - QComboBox 3 项: ['按下触发', '松开触发', '按住模式']  当前=「按下触发」
      - QPushButton 「开始循环」
      - QLabel 「控制台键:」
      - QLineEdit placeholder=「点击设置...」  text=「`」
      - QLabel 「间隔(ms):」
      - QSpinBox range=[50, 5000] 当前=100
      - QLabel 「无日志读取功能请自行判断循环时机。触发热键开始循环，再次触发热键会停止循环并停用建队循环，再次使用请到建队宏页面手动开启」  objectName=hint_text
    - QGroupBox 「建队设置」
      - QLabel 「小队名称:」
      - QLineEdit placeholder=「输入小队名称变量」
      - QCheckBox 「锁队建立」  checked=False
    - QGroupBox 「载具选择（点击填充小队名称）」  flat
        - QLineEdit placeholder=「搜索载具...」
        - QComboBox 1 项: ['全部标签']  当前=「全部标签」
        - QListWidget 0 项  []
```

## 导航组：相关

### 资源库  `TAB_6` = 6

```
  - QSplitter 2 段 sizes=[212, 425]
    - QGroupBox 「资源库」  flat
      - QLineEdit placeholder=「搜索资源...」
      - QTreeWidget 顶层 24 项
      - QPushButton 「导入PNG」
      - QPushButton 「重命名」
      - QPushButton 「删除」
        - QGroupBox 「图片预览」  flat
          - QLabel 「选择图片预览」  objectName=preview_box
          - QLabel 「缩放:」
          - QSlider range=[10, 400] 当前=100
          - QLabel 「100%」
        - QGroupBox 「图片信息」
          - QLabel 「文件名:」
          - QLabel 「-」
          - QLabel 「尺寸:」
          - QLabel 「-」
          - QLabel 「格式:」
          - QLabel 「-」
          - QLabel 「文件大小:」
          - QLabel 「-」
          - QLabel 「被引用:」
          - QLabel 「-」
        - QGroupBox 「文件夹信息」  flat
          - QLabel 「文件夹:」
          - QLabel 「-」
          - QLabel 「图片总数:」
          - QLabel 「-」
          - QLabel 「被引用载具:」
          - QLabel 「-」
          - QLabel 「孤儿图片:」
          - QLabel 「-」
```

### 信息  `TAB_8` = 8

```
  - QLabel 「GUNNER SIGHT」  objectName=info_title
  - QLabel 「V0.0140300174」  objectName=hint_text
  - QLabel 「屏幕准星辅助软件 — 依程序状态显示对应的炮镜图片，支持载具/弹种/倍率三级切换、一键反色、放大镜、标定测距、角度仪、建」  objectName=hint_text
  - QLabel 「本项目为免费工具，本人不收取任何费用。若遇到他人以"代下、安装、指导、内部版"等名义收费，请谨慎判断，谨防信息差，避免为」  objectName=free_notice
  - QPushButton 「简述说明」
  - QPushButton 「用户手册」
  - QCheckBox 「召唤惊天一条区」  checked=False
```

## 出厂配置关键值（**随包发布**的那份 config）

> 来源：发布包 `config/config.json`
> **用户拿到手看到的就是这些值**。使用者运行后本机 config 会变——
> 工作区 `config/config.json` 是**当前状态**，不是出厂值，别混。

| 项 | 出厂值 |
| --- | --- |
| 载具数量 | **77** |
| 标签数量 | **24** |
| 滚轮窗口偏移 | x=**900**, y=**0** |
| 全局缩放 / 偏移 | 100.0% / (0, 0) |
| 叠加层可见 / 不透明度 | True / 1.0 |
| 主题 | dark |

### 出厂热键绑定

| 功能槽 | 绑定 |
| --- | --- |
| `toggle_overlay` | f1 / — |
| `cycle_magnification` | q / mouse_right |
| `ammo_types` | — / — |
| `invert_colors` | shift / — |
| `reset_magnification` | x / — |
| `toggle_ui` | space / — |
| `toggle` | — / — |
| `cycle` | — / — |
| `global_combo` | ctrl / — |
| `pause` | caps lock / return |
| `pause1` | caps lock / — |
| `pause2` | return / — |

### 各模块电闸（出厂是否启用）

| 模块 | enabled |
| --- | --- |
| magnifier | False |
| angle_meter | False |
| distance_meter | False |
| squad_macro | False |
| mascot | False |
