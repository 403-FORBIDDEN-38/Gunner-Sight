# GunnerSight 开发规范

> **读者**：改这个项目的人 / agent。
> 本文件只写**判据**：该怎么做、做错会怎样。**不写现状，不写故事，不写待办。**
> 现状 → `docs/HANDOVER.md`（唯一权威，读完再动手） · 经过 → `docs/CHANGE_LOG.md`
> 测量方法（怎么量、量哪儿）也在 HANDOVER 第九节——那是"这个项目怎么验证"，属现状。
> 最后复核：2026-10-25

---

## 0. 开工前

1. **先读 `docs/HANDOVER.md`**。它是现状的唯一权威，读完再动手。
2. **用户不写代码。** 他说的是**意图**，不是技术方案。分清楚：

   * "这该怎么实现" → 自己定，别问
   * "这算不算需求 / 这样对不对" → 问
   * 感觉类需求（"看起来不对"）→ **先量出数字**，再改
3. **先量再改。** 禁止"我觉得应该是……"。测量方法见 HANDOVER 第九节。
4. **非平凡改动先出只读计划**：动哪些文件、预计增删多少行、风险在哪、怎么验。

---

## 1. 铁律

### 1.1 同一功能只能有一个实现

发现第二种写法 = 发现了一个 bug。**去找、去合并**，而不是在旁边再写第三种。

* 颜色 / 字号 / 间距 → `core/colors.py`、`gui/widgets.py` 的工厂
  （例外：**强调色在 cfg**，走 `config.get_accent_dark()/get_accent_light()`，见 4.2）
* "搜索 + 筛选 + 列表 + CRUD" 骨架 → `gui/widgets.py::FilterListPanel`
* "输入框 + 滑块" → `gui/widgets.py::LinkedSpinSlider`
* 分组框 → `make_group_box()`（唯一权威是全局 QSS 的 padding）

### 1.2 配置驱动（空房子）

**判据（唯一判据）**：撤走所有 cfg，这段代码还会执行某个**具体功能行为**吗？
会 → 就是硬编码，必须移到 cfg。

* **该在 cfg**：键位绑定、按键序列与时序、默认数值、预设、出厂数据
* **该在代码**：绑定机制、输入钩子、配置读写、UI 框架
* 未清完的两处已登记在 HANDOVER §十二（已知问题），改造前先问

### 1.3 高频路径零全量刷新

对每个 `refresh()` / `clear()+重建`，改之前回答三问：

1. **谁触发？** 画出完整调用链
2. **多快？** 高频 = 倍率切换、弹种切换、overlay 显隐、热键触发的任何操作
3. **真会变吗？** 还是"逻辑上合理但实际不变"

三道全过才保留。高频路径只能增量更新；低频（载具切换、增删改、改热键、启动）可全量。

**配套**：高频路径禁止磁盘 IO（配置保存必须防抖）；禁止用轮询替代事件驱动
（热键/输入必须边沿检测：Down 触发一次、Up 触发一次，按住期间不重复触发）。

### 1.4 可选模块：默认关闭 + 懒加载

非核心功能默认关闭。**关闭时零开销**：不建对象、不注册钩子、不启线程。
启用时才初始化，关闭时彻底清理（`shutdown()` / `cleanup()`，清理清单见 `core/cleanup.py` 契约）。

---

## 2. 改之前的规矩

### 2.1 找根源，不打补丁

修复方案里出现下面任何一项、而你说不出"**为什么会发生**"——那就是补丁，继续找：

* 加等待 / `sleep` / `QTimer.singleShot` 延迟
* `try/except` 吞掉异常或只打印后继续
* 超时保护 / watchdog / 最大时长限制
* 在使用方加兜底（掩盖上游缺陷，如"上游不发释放信号我自己轮询"）
* 隐藏控件再清理 / 加标志位绕过异常路径

**报错就是线索**：任何 traceback 先完整读完，报错位置往往就是根源，禁止无视报错去"优化"。

**中断即泄漏**：清理方法里任何一行抛异常，后面的清理都不会执行。
因此 `__init__` 中被 `shutdown()/close()/cleanup()` 访问的属性，**必须全部先初始化**。

**改完自问三句**：原来的异常还会抛吗？清理能执行到最后一行吗？根因消除了还是被掩盖了？

### 2.2 改完必须查关联（零例外）

改了接口 / 字段 / 键名 / 信号 / 行为约定后，`grep` 出**所有**引用点逐一确认。

**判断是否"通用问题"**：问自己——这个根源是**这个模块独有**的，还是
"tab 创建机制 / 初始化流程 / 基类行为 / 通用组件 / 配置加载模式"这类**多处共有**的？
是多处共有的 → **列出所有使用该机制的模块全部排查**，禁止只修被点名的那一个。

**删符号之前：把"要删的名单"交给脚本去反查引用**
（`for name in 待删名单: assert name not in 全项目文本`），不要手写 grep 模式——手写必漏。
**静态检查绿 ≠ 没坏**：涉及创建/接线路径的删除，必须跑一次"全部 tab 都能创建"的冒烟。

**改既有连接 / 清理 / 注册项时，必须断言"原有的仍然生效"**：
凡修改或断开既有信号、清理方法、注册项的地方，测试要同时证明「新行为生效」和
「碰过的旧行为还活着」。只锁"我加的东西在工作"的测试，会放行「顺手把别人的槽抹了」
这类回归（案例见 CHANGE_LOG 2026-10-24 批次 4）。

**反向验收：「代码落地了」不等于「改对了」**
验收一批修复时，光看到「该有的机制存在」不算完成——必须对每一条 `disconnect` / `deleteLater` /
`stop()` / 置 `None` **单独**复核一遍：断的是不是别人那个槽、释放时对象还在不在、`stop()` 是否幂等。
这一条是有代价换来的：某一轮 5 处错判全部是同一个病——**看到机制存在，就假定机制正确**。
清单化检查，不靠印象过一遍。

---

## 3. 写文件

| 对象 | 规矩 |
|-|-|
| `.py` / `.json` | 用 Write/Edit 工具或 Python 脚本。**禁止 PowerShell `Set-Content` / `>` / `>>`**（写 UTF-8 with BOM，`json.load` / `ast.parse` 直接失败） |
| `.py` 改完 | `py -m py_compile <file>` |
| `.json` 改完 | `json.load` 验一遍 |
| `.bat` / `.cmd` | **必须 CRLF，且全文纯 ASCII**。这是两个独立的坑：① LF-only 时 `cmd.exe` 按 CR 分行，行会被拆开；② **即便已是 CRLF**，含中文的 `echo` 仍会被解析器**吞掉多字节字符**（实测：`echo 产物路径:` 被拆成 `echo 产` + 未知命令 `物路径:`，报"不是内部或外部命令"；去 BOM / `chcp 65001` / 路径加引号**全都治不了**）。另：`if (...)` 块内**不要出现 ASCII 括号**（会被当嵌套块，报"此时不应有 ."）。正解：中文说明搬到文档，`.bat` 只留 ASCII。写法 `open(p,"w",encoding="utf-8",newline="\r\n")`——注意 `newline=""` 是**不翻译**，会写出 LF。`.bat` 里的 `REM` 注释同样参与解析。改完**必须实测执行** |
| 已有的 `.py` | 先确认换行符（CRLF/LF 混存，实测约六四开，没有"唯一 LF 例外"）。按内容精确匹配时，必须按**文件实际换行符**构造待匹配串，否则 0 命中 |
| 文件损坏 | 一行能修就修，**不重写整个文件**。重写必须做方法级对比（方法列表 / 签名 / 关键逻辑） |
| 批量替换 | **先断言"预期命中 N 处"再落盘**。命中数不符 → 整体中止，不写 |

**依赖变更**：改 `pyproject.toml` / `uv.lock` 后，必须实装 + 导入 + 跑通相关功能；
lock 锁的版本与实际运行环境不符时，在 HANDOVER 登记。

**T0 事故**（方法丢失 / 语法无法修复 / 数据丢失）：立即上报，不要默默自行修复超过 3 步。

**重排 / 合并行**（压缩空行、合并段落、改换行）比替换更危险：内容"看起来"没丢，
但会**粘错地方**。必须做两件事：
① **内容守恒断言**——非空字符序列去掉空格后必须完全一致；
② 把**每一处合并打印出来人工过目**（只改几处时逐条看完全可行）。

守恒断言挡不住"不丢内容的粘错"——断言要对着真正的失败模式设计。

---

## 4. GUI 约定

### 4.1 一律走工厂，别手搓

```
box, layout = make_group_box("标题")                           # 有边框组
box, layout = make_group_box("标题", flat=True)                # 无边框组
box, layout = make_group_box("标题", layout_cls=QFormLayout)   # 换布局类型
```

* **缩进的唯一权威是全局 QSS**（`main_window.py` 的 `QGroupBox` 规则）。工厂把布局
  `contentsMargins` 固定为 0，从根本上杜绝 "QSS padding + layout margins" 两处叠加
* 有边框组 = QSS 默认规则 `padding: 8px 8px 4px 8px`
* 无边框组 = `QGroupBox[flat="true"]`，`padding: 3px 5px 3px 5px`
* 别自己 `QGroupBox` + 内联样式。**组的边框/间距只准由 QSS 决定**

### 4.2 颜色：主色板在 `core/colors.py`，强调色在 cfg

* 主题调色板：`THEME_DARK` / `THEME_LIGHT`（键：bg/ctrl/border/hover/text/subtext/dis_text）
* **强调色来自 cfg，不是常量**：出厂默认在 `core/config/base.py` 的默认模板
  `global_settings.accent_dark` / `accent_light`，运行时用
  `config.get_accent_dark()` / `get_accent_light()`。
  **`ACCENT` / `ACCENT_HOVER` 常量已删除，不要再 import**
* 强调色底上的文字走主题字典的 `on_accent_text`
* 主题字典的键：`bg / ctrl / btn / base / border / hover / text / subtext / dis_text / on_accent_text`
  （`btn` 给按钮、`base` 给输入框；**QSS 里按钮必须显式写 `background-color`**，
  否则 Qt 会让它透明、不走 QPalette）
* 状态色：角度仪 `ANGLE_*`、标定测距 `DISTANCE_*`（**`ANGLE_*` 现在只是 `DISTANCE_*`
  的别名**，改状态色只改 DISTANCE 一处）
* 叠加层 `OVERLAY_*`：**刻意不随主题变化**——它们压在游戏画面上，浅色主题也要深底白字。
  QPainter 用 `OVERLAY_BOX_RGB` / `OVERLAY_BOX_BORDER_RGBA` 元组形式
  （QColor 不认 CSS 的 `rgba()` 字符串）
* 悬浮窗文字统一 `OVERLAY_TEXT`；底框 `OVERLAY_BOX_RGB` + `OVERLAY_BOX_BG_ALPHA`（20%）。
  **窗口级 `setWindowOpacity` 已全部取消**，透明度改由底框 alpha 表达
* **大示数（48px）** 走 objectName：`QLabel#info_title, QLabel#zoom_display`；
  变暗态用属性选择器 `[dim="true"]`——**改完属性必须** `unpolish/polish`，否则 QSS 不重算
* `gui/` 里的内联 `setStyleSheet` 已清零；叠加层必要的样式串集中在各模块顶部常量

### 4.3 两种 "成对 / 成骨架" 的控件只有一个实现

* `LinkedSpinSlider`——"输入框 + 滑块" 双向联动，自带防回路：

```
ctl = LinkedSpinSlider((1.0, 1000.0), slider_range=(1, 1000), decimals=1,
                       suffix=" %", initial=100)                # 输入框在左（默认）
ctl = LinkedSpinSlider((1, 1000), suffix="%", fixed_width=80, spin_first=False,
                       leading=minus_btn, trailing=plus_btn)    # 滑块在左，两端挂按钮
ctl.value_changed.connect(...)    # 只有用户改动才发；内部镜像同步绝不外发
ctl.set_value_silent(v)           # 载入配置：两控件同步且零信号
ctl.step_value(±5)                # +/- 按钮：走正常信号链，越界由 spin 范围收敛
```

使用方**不需要写** `blockSignals`。`set_silent()` 用 `try/finally` 保证信号一定恢复——
历史那种 `blockSignals(True); setValue(); blockSignals(False)` 一行流一旦中途抛异常，
控件会**永久静默且不留痕迹**。

* `FilterListPanel`——"搜索 + 标签筛选 + 双标签列表 + 新建 / 重命名 / 删除" 骨架：

```
panel = FilterListPanel(placeholder="搜索配置...", right_widget=self.link_vf,
                        min_list_height=180, list_stretch=1, right_stretch=1)
panel.set_tag_options(tags)      # 同步下拉并保持选中；选项无变化时不重建
panel.filter_values()            # -> (搜索词小写, 当前标签或 None)
panel.add_requested / rename_requested / delete_requested
```

**列表重建与选中恢复的语义不归它管**，各页自己写 —— 那里的语义本来就不同（见 4.4）。

### 4.4 列表 "重建后恢复选中" 的两种相反语义（最容易搞错）

* **必须静默**（阻断信号）：防止回写状态机形成回路。
  例：`vehicle_config_tab._select_row_by_data / _select_row_by_index`
* **必须不静默，且必须在 unblock 之后恢复**：要靠 `currentItemChanged` 级联刷新下级列表。
  例：`vehicle_config_tab._refresh_vehicle_list / _refresh_ammo_list`

**所以不要把 `vehicle_config_tab` 里那 5 个 `_refresh_*_list` 统一**：
它们分别是 "静默同步" / "级联重建" / "按索引恢复 + 外部覆盖" / "自建 QCheckable 项"
四种语义，硬合并就是把两种相反的信号语义搅在一起 —— 那是制造 bug，不是清理。

**恢复选中必须用 "实际插入的行号"**（`self.list.count() - 1`），不能用源数据的 `enumerate`
下标：搜索 / 标签筛选会让行号与源下标错位，越界时 `setCurrentRow()` 会**清空**选中
（表现为 "列表有内容但没选中 / 参数区不刷新"）。

### 4.5 主窗口尺寸：宽度 = 启动横幅的宽度

* `WINDOW_SIZE` 同时用于 `resize` 和 `setMinimumSize`：**启动尺寸 = 最小尺寸**，
  启动后没有 "能再缩小" 的余量
* 用户口径：横幅是**腰封**。横幅图 `resources/assets/splash/full.png` 是 800×151，
  另有 20 张扫描帧（尺寸相同），窗口就必须 800 宽；两者都居中，所以边缘正好对齐
* **改宽度前先看 `resources/assets/splash/` 里的图** —— 图宽是唯一权威，
  不要反过来按代码改图
* 不要再用 "按屏幕 clamp" 的逻辑决定窗口尺寸（那是为了绕开一个误判）

### 4.6 滚轮：无焦点控件不吞滚轮，且转发给最近的滚动区

统一过滤器 `gui/wheel_filter.py::install_no_wheel_filter(app)`（为什么必须用这个函数，
见 §9 行为类"程序退出时崩溃"）。

* 判定依据是**控件有没有焦点**：有焦点才允许它自己处理滚轮
* 设计意图是**恢复页面滚动**：光标停在下拉框 / 数字框上滚动 → **页面滚动**，
  不是"什么都不动"
* "转发给最近的滚动区"是刻意行为，不是遗漏。改它之前先想清楚用户在那一刻想要什么：
  在下拉框上滚动，要的是"滚页面"，不是"偷偷改我的选项"

---

## 5. 测试

**只锁契约，不锁实现。**

**值得写**：

* 曾经真实坏过、而且**坏了不报错**的行为（静默失败最值得回归）
* 跨模块约定（信号语义、回调顺序、索引恢复）
* 纯逻辑、手动验不了的（曲线换算、比例、边界）
* 修 bug 时先证明"去掉修复它就会失败"，否则这个测试没有牙
* 见 2.2 的「改既有连接必须断言原有的仍生效」

**砍掉**：

* 只有前置条件、没有独立断言价值的"跑通型"测试
* 同一公式正/反两向各写一个 → 参数化合并
* 断言"已删除的代码不再生效"（同义反复，永远为真）
* 断言私有方法被调用（mock 实现细节）
* 手感 / 视觉 / 性能 → 人工验，不要硬塞成测试

**跑法**：`py -m pytest tests/ -q`，必须 exit 0。
（必须走 `tests/` 或依赖 `pyproject.toml` 的 `testpaths`——`backups/` 里存着历史副本，
裸收集会 `ImportPathMismatchError` 中断全量验证。）
Windows 上非 0 可能是退出期崩溃而非断言失败——先看是不是悬空事件过滤器之类，见 §9。

**静态测不了 OS 资源释放**：`mock` 能证明"前一步失败后一步仍执行"（代码路径），
证明不了"句柄真的还回去了"。别把前者当成后者——后者靠代码审查 + 运行时观察（句柄数、日志）。

**测试数量没有上限**。项目历史峰值 100+ passed，"≤30 条"那类红线已退役——
按契约需要写，别为凑数写，也别为省事不写。

---

## 6. 清理与交付

**墓碑清理**（功能完成即做，不等别人提）：无用导入 / 方法 / 类、重复定义、
注释掉的代码块、一次性脚本、调试 `print`。

**死表达式**：`py -m ruff check --select F401,F841,F811 core gui main.py tests` 应为空。
**注意这条命令有两处盲区**：① 路径**不含 `tools/`**（工具脚本的未用导入不在此门禁内，改 `tools/` 要自己看）；
② **ctypes 签名没有任何检查项**——所有 Win32 API 必须手动设 `argtypes`/`restype`，
漏设是 64 位指针截断，静默失败、不报错。新增 `windll` 调用时这是唯一防线，没有工具兜底。

**提交纪律**：本地 commit 随便提（细粒度、一个浪一个提交，回滚粒度才细）；
**push 前必须问用户**；能用 `git revert` / `git checkout` 回滚的，**不要重写历史**。

**清理清单只有一份**：`core/cleanup.py` 的 `TAB_CLEANUP_STEPS` +
`collect_tab_cleanup_steps` / `collect_window_cleanup_steps` / `run_cleanup_steps`。
四个调用方（`MainWindow.closeEvent`、`main.py` aboutToQuit、`tests/conftest.py` teardown、
`tools/export_gui_facts.py`）共用它。**新增要清理的对象，只改这张表/这两个 collector**，
不要去各调用方里各加一行。各清理动作必须**幂等**（正常退出会双跑）。

**清理顺序有讲究**：**越贵的资源越先释放**——`raw.close`（mss 抓屏句柄，OS 级）提到
`_shutdown_engine` 最前。不依赖"异常是否发生"就产生收益。

`_GrabWorker.stop()` 的 wait 超时只写一条 warning：**那是报告状态，不是恢复**。
线程真没退出时 mss 句柄依然泄漏。不要加重试、不要强制 terminate（QThread 没有安全终止）。

**文档对账**：改完 `docs/HANDOVER.md` / `docs/RULES.md` 必跑 `py tools/audit_docs.py`。
它把文档里的事实性断言（版本号、窗口宽度 vs 横幅宽度、颜色来源、承诺的 SSOT 组件、
引用的路径、备份约定、F841 处数、换行风格）逐条拿去和代码核对。
**这个项目的文档是"现状的唯一权威"，而它烂过一次。**
**文档漂移比代码 bug 贵：bug 会报错，过时文档不会。**

**换行符**：`AGENTS.md`（钩子）、`docs/HANDOVER.md`、`tools/audit_docs.py` 是 **CRLF**；
`docs/RULES.md`、`docs/CHANGE_LOG.md`、`README.md`、`USER_GUIDE.md` 是 **LF**。
用 Python 改它们时注意：`read_text()` 默认把 CRLF 归一成 `\n`，
再 `write_text(newline="")` 就写回 LF——**两个"默认值"叠起来正好吃掉换行风格**。
要保 CRLF 就写 `newline="\r\n"`。改完用字节计数复核（`data.count(b"\r\n")`）。

**提交前自查**（AI 高频翻车点）：

* `__init__` 里有的属性，清理方法里访问不到 → 会 `AttributeError` 中断清理
* 同一信号连接了多次 → 回调重复执行
* 定时器 / 线程 / 全局钩子 / 信号连接没在异常路径上释放 → 泄漏
* 新资源文件没进打包配置 → 打包后才炸

**交付前**：`py_compile` 全过 + `pytest` exit 0 + 关闭流程无异常 + 高频操作连做 10 次不错乱。

---

## 7. 版本号

* 格式 `V{主版本}.{次版本}{签名}{更新次数}`，**每次源码行为更新 +1**。
  纯注释 / 文档 / 测试改动不算（无行为变化就不该给用户"有新版本"的信号）。
* **唯一权威**：`gui/tabs/info_tab.py` 的 `APP_VERSION`。
  `main.py` 的 `setApplicationVersion()` 和 `pyproject.toml` 都从它同步，**禁止第二处硬编码**
* 版本号在信息页显示；发布版文件名不带版本号

---

## 8. 别去修的东西（有结论的禁区）

这些不是"没来得及做"，是**做过判断、结论是不该做**。再提之前先读完理由。

| 项 | 为什么别动 |
|---|---|
| `RUF001/002/003` 歧义 Unicode（2400+ 处） | 是中文注释里的全角标点（`：`、`（）`）。中文项目的必然产物，**改了反而错** |
| `E402` 模块导入不在顶部（87 处） | **刻意为之**的懒加载（`main.py` 里 import 之间插 `processEvents()` 让横幅动画不卡）。改到顶部会让启动多卡几百毫秒 |
| `E501` 行长 / `E701` `E702` 一行多语句（196 / 25） | 纯风格，零收益；改了一堆 diff 噪音 |
| `RET505` `SIM102` `SIM105` `PERF102` `PERF203`（~45） | 纯风格建议。改动要过 AST 重构，收益为零、风险非零 |
| 超长函数（`_main`、`_setup_full_style`、各 `_build_ui`，9 个） | **本质如此**：一个是启动编排、一个是 QSS 字符串、其余是 UI 搭建。硬拆只增加跳转层级 |
| "启动慢" | **已实测**：322 ms 里 295 ms 是 `QApplication()` 自身（平台插件+字体库+样式）。换任何 Qt 程序都一样，**没有优化空间** |
| "高频路径有全量刷新" | **已核实**：倍率/弹种/载具/overlay/热键的全部接收槽都是增量更新，没有 `clear()+重建`、没有读盘 |
| 鼠标钩子设置失败的**重试策略** | 无上限、固定 1 秒间隔退避。历史 17 个日志文件 0 次失败，加上限收益为零（用户决定）。**只许改日志级别，不许加次数上限** |
| `gui/widgets.py::VehicleFilterWidget` | 看着像死代码，**实际是活控件**（三处页面 + 两处测试在用）。删它之前先跑全量测试 |
| 再给 stdout / stderr 装过滤器 | 拦不住 C 层 `fprintf`（libpng 直接写 fd，不过 Python 的 `sys.stdout`）。试过 `_LibpngFilter`，已删 |

> 这些条目与 agent 能力无关：不是"弱 agent 做不了"，而是"对任何人都零收益、非零风险"。

**它们全是 lint 噪音与已测结论，不是待办。** 有人（包括未来的你）再次提议时，答"见 §8"。

---

## 9. 坑速查（一行一条，都是实测过的）

### 改写 / 编码类

| 症状 | 根因 / 解法 |
|---|---|
| `.bat` 里含中文的 `echo` 报 "不是内部或外部命令" | **CRLF 未必是真凶**。先查换行符（LF-only 确实会被按 CR 拆行）；若已是 CRLF 仍报，那是解析器**吞多字节字符**（实测：`echo 产物路径:` 被拆成 `echo 产` + `物路径:`；去 BOM / `chcp 65001` / 加引号全都治不了）。正解：整个 `.bat` 改**纯 ASCII**，中文说明搬进文档 |
| `.bat` 报 "此时不应有 ." 并秒退 | `if (...)` 块内出现 **ASCII 括号**（如 `echo ...(~100MB)`），cmd 当成嵌套块。换成逗号或全角括号 |
| 用 Python 脚本按内容替换 "0 命中" | 文件是 CRLF，而匹配串用了 `\n`。按文件实际换行符构造 |
| `json.load` / `ast.parse` 报非法字符 | 文件被 PowerShell `Set-Content` / `>` 写了 BOM。改用 Write 工具或 Python 脚本 |
| 文件莫名带 BOM（`ast.parse` 报 U+FEFF） | PowerShell `Set-Content` 留下的。去 BOM 用字节级操作；读文件用 `encoding="utf-8-sig"` 更稳 |
| 备份体积莫名 200MB | 多半是 `.venv/`（156MB，占 78%）被拷进去了，其次才是 `dist/`、`.git/`。整目录快照排除 `dist .git .venv backups __pycache__ .pytest_cache .ruff_cache .workbuddy`。**排除名单写在目录出现之前就会漏**——新增重量级目录时顺手补名单 |
| 脚本批量替换后文件半坏 | 没做 "预期命中 N 处" 断言。**先断言再落盘** |
| 编辑 CRLF 文件后整文件 diff 变成 +900/-900 | 工具把换行符归一了。改完字节复核 `data.count(b"\r\n")`；`.md`/`.py` 坏了不会运行失败，但会淹没真实改动的可读性 |

### 界面类

| 症状 | 根因 / 解法 |
|---|---|
| 列表不撑高 | 整条 stretch 链要通：最外层 `addWidget(x, 1)`，内部每一级也要 |
| 无边框分组框标题和内容叠在一起 | 必须 `margin-top: 16px`，不能 0 |
| tab 里什么都不显示 | `QScrollArea` 忘了 `setWidget(content)` |
| 改了控件属性但 QSS 没变 | 属性选择器要 `unpolish/polish` 才重新求值 |
| 下拉框 / 数字框的箭头显示成方块 | 用了系统原生 style。必须 `app.setStyle("Fusion")` |
| 自定义字体没生效 | `load_custom_fonts()` 必须在**任何控件创建之前**调用 |
| 缩进五花八门 | 别自己 `QGroupBox` + 内联样式，走 `make_group_box()` |

### 行为类

| 症状 | 根因 / 解法 |
|---|---|
| 热键没反应 | ① `_register_all_hotkeys()` 漏注册；② 对应 tab 没被预创建（见 HANDOVER §六）；③ 改完绑定没 `reload_hotkeys()` |
| 关了再开，功能是坏的 | "电闸关闭" 时没真正销毁，或 `__init__` 只在启用分支里初始化。见 HANDOVER §三 |
| 程序退出时崩溃（退出码非 0，但测试全过） | 悬空的事件过滤器：`installEventFilter` **不持有所有权**，临时对象会被立刻回收，QApplication 上只剩悬空指针。必须用 `wheel_filter.install_no_wheel_filter(app)` |
| 某个功能 "没保存" | `set_xxx` 里漏了 `request_save()`（写入是防抖的，不调就不落盘） |
| 日志文件里什么也没有 | 文件 sink 曾是 WARNING 级，INFO 全被丢弃（已修为 DEBUG）。见 HANDOVER §八・五 |
| bbox 缓存对不上 | 删 `config/bbox_cache.json` 重启 |
| 重建引擎后热键触发两次 / 回调重复执行 | 信号重复连接。`_init_engine` 之类必须**先无条件 disconnect 再 connect**（幂等收口）。**边界：无参 `disconnect()` 只准用在自己 connect 过的槽上——别人拥有的信号（如 tab 自己的电闸）必须 `disconnect(自己的槽)` 定向断开**，否则连别人的一起清空 |
| 标签增删后某些页的下拉里没有新标签 | 漏接 `tags_changed`，见 HANDOVER §五・五 |
| 鼠标钩子 / 线程停了但钩子还挂着 | 清理清单漏了它。走 `core/cleanup.py` 契约，别在调用方各处补 |
| PyQt 信号 `connect` 后收不到参数 | 用 `list.append` 之类单参可调用对象会被按单参内省丢参数；一律 `lambda *a: ...` 显式收参 |
| `destroyed` 连绑定方法，槽静默不触发 | 必须 `destroyed.connect(lambda *a: self.method())` |
| 反复开关某模块后内存 / 句柄缓慢上涨 | C++ 侧对象累积。置 `None` 前补 `deleteLater()`（角度仪 tuner 踩过） |
| 模块 `stop()` 后重建，回调跑两次 | 反向断开要齐：`stop()` 里把 `__init__` 连的那几条逐条 `disconnect(自己的槽)`，并加 TypeError 守卫（保证幂等） |
| 想定向断开，但拿不到那个槽的引用 | 十有八九它是**闭包**（每次调用新建，没有可引用的对象）——`disconnect(自己的槽)` 物理上做不到。此时**必须先把闭包提成实例方法**，再去定向断开。**不要**因此退回无参 `disconnect()`，那会抹掉别人的槽（P0-1 的原路） |
| 审查报告说某问题存在，但我复现不出来 | 「不可复现」**不等于**「不成立」。先查症状形态是不是变了（报错文案不同 / 触发路径被间接改掉 / 只在特定顺序下出现），再看代码里有没有**疤痕证据**（重试、护栏、`try/except`）——疤痕反证症状真发生过。定性降级要写理由 |

### 查词

| 名词 | 指什么 |
|---|---|
| 电闸 / 开关 / 暂离 | 见 HANDOVER §三 |
| 空房子 / 水泥凳子 | 配置驱动：具体功能行为必须在 cfg 里，不在代码里（本文件 §1.2） |
| 腰封 | 启动横幅。窗口宽度必须等于它（本文件 §4.5） |
| 数显模块 | **已删除**。历史文档里出现的 "数显" = 现在的标定测距（`distance_meter`） |

---

## 10. 本文件怎么维护

这三份文档按**时间性**分工，一条信息只能有一个家。新增或修改内容前，先答三问：

| 它回答什么 | 去哪 | 更新方式 |
|---|---|---|
| 下次该怎么做 / 做错会怎样 | **本文件** | 覆盖，去掉过期结论 |
| 现在是什么样 / 为什么这么设计 | `docs/HANDOVER.md` | **覆盖**，不追加 |
| 发生过什么 / 为什么改主意 | `docs/CHANGE_LOG.md` | **只追加**，永不修改 |

**否决项**：会过期的信息（版本号、行数、计数、批次名、"已完成 2026-xx-xx"）
**不准进 HANDOVER 正文**——那是日志内容。写进 HANDOVER 的只有"现在的样子"。

**一条经验的处理路径**：事故发生后，先写 CHANGE_LOG（经过 + 证据）→
提炼成一句判据进本文件（或加进 §9 坑速查）→ HANDOVER 只在"机制真变了"时覆盖对应章节。
**不要**在 HANDOVER 里记"某批次完成了什么"，那是日志的事。

**推翻规矩**：规矩是为了指向真相，不是为了遵守死板的规矩。有证据时可以明面推翻本文件任何一条，
但必须在 CHANGE_LOG 里写下理由和证据。**默默遵守和默默违反一样糟。**

## 10.1 账本纪律（处理"一批待办"时）

**开工前先机械对账，不要凭记忆**：从各份报告里提取编号全集（`grep -ohE '^#+ [SMP][0-9]+'`），
`sort -u` 后逐条映射到「做了 / 不做」。**跳过任何一项，必须留一行「不修 + 理由」**。

代价说明：曾有一项（S6）就是因为「用新判断覆盖旧账本且不留痕」而丢失，两个批次都没人发现。
对账表是唯一防止"悄悄少做一件事"的机制——**新结论不能覆盖旧账本，只能追加或标注改判**。

## 10.2 写审阅结论 / 验收结论时

* **能跑命令证明的必须实测**：读代码推断意图是最易错的一环（实测命中率远高于推断，
  某轮所有错判都出在"读代码猜意图"）。凡是能 `grep` / 跑一次就确定的，不要用推断下结论。
* **同一份文档里的结论要摆在一张表上互相看**：同一文档内两处结论互斥，是最廉价的自查信号。
  实例：`VehicleFilterWidget` 在同一篇报告里既被判"无调用方的死代码"，又被算进"被防抖覆盖的五处"。
* **审查报告不是判决书**：它自己的症状描述也可能不准（M4 的 `json.dump` 解释就是错的）。
  被审对象与审查结论都可能错，**证据在代码和可复现的实验里**，不在任何一方的措辞里。

**改完必跑** `py tools/audit_docs.py`（会校验本文件引用的路径、转义污染与换行风格）。
