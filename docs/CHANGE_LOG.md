# GunnerSight 变更日志

> 按时间线记所有动作（含回退）。docs/HANDOVER.md 只写当前状态，需要更新时从软件状态 + 本日志里挑有价值的事总结。
"有价值的 CHANGE_LOG"：
什么算有价值——只保留两类——(a) 已回退的方案及其失败原因；(b) 影响架构/接口/数据格式的改动。 其余（改个字符串、调个颜色、重写一个函数）不总结。

## 2026-10-25 推翻「config.json 永不提交」：出厂配置是被追认的状态快照

> 版本号不变（184）。代码零改动，只改提交判据与配置快照。

**旧规矩**（只写在 agent 记忆里，没进 RULES）：「`config/config.json` 的用户漂移永不纳入
提交，`git add -A` 后 `restore --staged`」。成因是早期把 config 理解成"模板 + 用户数据"
两半、分不开，于是用禁令一刀切。

**它和自己仓库的验收项直接矛盾**：`HANDOVER.md` 发布前验收第 7 项要求"解压成品
`config.json` 与源码版一致"——前提是源码版为出厂权威，而旧规矩禁止源码版更新。
结果出厂种子只进不出：`squad_macro.squad_name = "MATV M2 RWS"`（一个真实载具名）、
`current_state.ammo_type`（在 GUI 里随手选的玩笑值）这类历史残留永远没有修正通道。

**新定位**：`config.json` 是状态机的完整快照，只有一份。**「出厂配置」是追认的身份**——
使用者决定"就把这一份交出去"的那一刻，它就是出厂值。因此**不拆 `.default.json`**：
那会造出第二份状态，与「一条信息只有一个家」冲突。

**新判据**（RULES §6）：

* `git add -A` 顺带带进来、**没看过 `git diff`** → 剔除
* 主动 `git add` 且 `git diff` 看过差异 → **正常提交**

区别是**有没有人看过**，不是文件脏不脏。旧规矩管文件，新规矩管审阅。

**本次冻结的三处**（均为 GUI 里真实产生的状态）：`display_resolution` 1920x1080 →
2560x1440（作者屏，别人装上适配页基准档就是 2K，需自行改）、示例角度仪
`active_calibration_point_count` 11 → 5、`squad_name` → `AAA 示例载具`。

**顺带修正 RULES §11.4**：原句「出厂值取自发布包，不是工作区——工作区是使用者当前状态，
随时会变」结论不变，但理由换了——不是工作区不可信（工作区就是出厂的候选版本），
而是**只有发布包里那一份才是用户实际拿到的**。理由从"信任问题"变成"对象问题"。

**查过、判断为不需要动的两处**：① `_merge_config` 只补不删 → 在新定位下这是正确语义
（状态被保存就是被保存，程序无权判断某值"不该出现"）；② P6 损坏回退只有三级留痕、
留痕后没有恢复入口 → 属可用性缺口而非数据安全缺口（原文件在 `backups/` 里，弹窗告知了
路径），不构成"软件主动破坏 cfg"，不改。

## 2026-10-25 bbox 缓存判据改为内容指纹：出厂预计算首次可跨机器生效

> 版本号 183 → 184。

**问题**：`config/bbox_cache.json` 只认 `st_mtime_ns` 判断条目有效。而 mtime 在分发链路上必然失真：

* zip 时间戳只有 2 秒精度且向下取偶（源文件 `05:04:53.4133847` → zip 存 `05:04:52`）
* git clone 不保存 mtime，检出时全部设为当前时间

后果两层，第二层更致命：

1. 作者机器 371/371 命中，zip 解压后 0/371
2. `BboxCache.__init__` 在 `load()` 后立刻 `cleanup()`，而 cleanup 当时按 mtime 删条目并 `save()` 写盘——**别人第一次启动、在第一个 `get()` 之前，整份缓存就被清空并写回空文件**

所以只改 `get()` 的判据、不改 `cleanup()`，改动等于零。这是本次真正的修复点。

**判据取舍（两次自我否决）**：

* 先提「文件大小 + 像素尺寸」→ 被实测否掉：371 张图只有 75 种像素尺寸（180 张同为 2560×1440），28 张与别的图共享 `(大小,尺寸)` 组合，最撞一组 15140 字节+2560×1440 有 6 张共用
* 再量成本：sha256 全量 371 张（10.6MB）约 48ms、单张 0.1ms；被它省掉的一次全量 bbox 重扫是 40~76 秒（`find_opaque_bbox` 纯 Python 双像素循环，2560×1440 单张 200~313ms）
* 结论：48ms 换 76 秒，不存在取舍

**新判据（三级）**：

| 情形 | 行为 |
| --- | --- |
| mtime 完全一致 | 快路径，不读文件（本机日常，零额外开销） |
| mtime 不一致 + sha256 一致 | 命中并写回新 mtime（自愈，每个文件只付一次） |
| mtime 不一致 + sha256 不一致 | 未命中 → 重扫 → `set()` 覆盖 |
| 源文件不存在 | `cleanup()` 删孤儿 |

**自愈放两处、职责不同**（不是重复实现，§1.1）：`cleanup()` 做批量自愈并写盘——全部命中时扫描线程不会启动，`get()` 里的 dirty 没有任何时机落盘；`get()` 的自愈是运行期兜底。

**测试**（`tests/test_bbox_cache_fingerprint.py`，5 条）：mtime 变内容不变必命中 / 同大小不同内容必失效 / cleanup 不得按 mtime 删条目 / 自愈必须落盘 / 孤儿仍要清。已做有牙验证：把 `cleanup()` 改回旧行为，第 3、4 条立即变红，恢复后文件 md5 逐字节一致。

**数据迁移**：一次性脚本给现有 371 条补 `sha256`（bbox 本身仍有效，不重扫），44.9KB → 72.4KB。无指纹的旧条目按未命中处理、重扫后自动补上，所以不迁移也能自愈，只多付一次 40~76 秒。

**验证**：`resources/` 复制到临时目录并改写全部 396 个文件的 mtime（模拟 checkout）→ 命中 371/371、cleanup 后条目仍 371、自愈值 371/371 等于当前 mtime；全量测试 115 passed。

## 2026-10-25 许可更正成文：MIT 声明分层否认，删发布标签

> 版本号不动：无行为变化。

用户提出一个真实诉求：担心有人「下载新版 → 回滚到 MIT 时期 → 继续侵权」，最终追责到自己。
拟过的方案有三个：① 删掉历史里的 MIT 声明；② 把历史 LICENSE 一并改成 GPL；③ 声明 MIT 无效。

**否决 ① 和 ②，理由不是保守，是它们不成立：**

* **② 把历史改成 GPL 是最坏选项**：它制造"我从一开始就是 GPL"的假象。一旦被旧副本或
  缓存对照，性质从「疏忽」变成「伪造」。历史错误只能更正，不能重写。
* **① 删不干净，且方向是反的**：MIT 出现在三处（`LICENSE`、README 第 89 行、
  `136d148` 的 commit message 里就写着"MIT许可+版权声明"）。只删文件是半成品，
  看起来像掩盖；全改则是系统性篡改 26 个提交。而删除是**沉默**，在许可法里沉默不构成
  否认，反而可能被解释为默示许可——比留着更糟。

**采纳 ③，并补上一个此前没人说清的关键区分：MIT 声明是分层的。**

| 对象 | 本项目有无版权 | 声明的效力 |
| --- | --- | --- |
| 本项目自有代码 | 有 | 有效（错误但已发出，MIT 不可撤销） |
| PyQt5 | **无，也无授权资格** | **自始无效** |

所以「回滚拿到通行证」这条路根本不存在——**那张证超出签发权限，覆盖不到 PyQt5**。
别人回滚后继续分发，违反的是他与 Riverbank 的关系，不是本项目发了证。追责链在第二环就断。

落地：
* 新建 `LICENSE-HISTORY.md`（根目录，与 `LICENSE` 并列）：时间线、更正声明、分层说明、
  "从历史版本回滚过来的人该怎么做"
* `README.md` 许可节加更正段，指向该文件，写明「历史 MIT 声明不豁免 PyQt5 的 GPL 义务」
* 删除 tag `v0.0140300177`：它指向 MIT 时期，是「一句话回到错误许可状态」的入口。
  删除前发现**远端的它指向 `846796d`，该提交在本地历史里不存在**（悬空锚点，
  历史被改写过），更该删。重建命令与旧 SHA 已记在本次提交说明里。

**没做的事**：不 force push、不 filter-repo、不改任何 commit message、不动历史 `LICENSE`。
理由：分布式版本控制里「堵死」本质上不可能（fork 无法回收），能做的只有降低可发现性 +
明确否认，而这两件都不需要篡改。

## 2026-10-25 文档纠偏：手册写作规范迁出 HANDOVER

> 版本号不动：纯文档。

上一轮把"手册打磨"（原 §十一・六）搬进了 HANDOVER §一・五，理由是
「它讲文档怎么写，不是代码纪律」。**这个理由有漏洞**：不是代码纪律 ≠ 不是纪律。
它同样是"下次该怎么做"，属判据层，结果 §一・五 从一行表长到 95 行、判据占 72%。

已搬：`USER_GUIDE` 写法硬规矩、内容口径、断言的证据边界、"验了函数存在没验走哪条路径"
的六处实证 → `docs/RULES.md` §11（新节）。HANDOVER §一・五 留下分工表、
`audit_manual` 做什么、底稿是生成物这三个事实，95 → 34 行。

**真正的产物不是这次搬迁，是写进 RULES §10 的边界判定**：绑定具体代码位置的说明留
HANDOVER，脱离位置也成立的判据进 RULES。附四行对照表 + 这次判错的记录。
不写这条，同样的错会以别的形状再犯一次。

## 2026-10-25 修 Win32 签名缺陷：magnifier 归队统一入口，ctypes 门禁从"提醒"变"可执行"

> 版本号 V0.0140300182 → V0.0140300183；测试 107 → 110 passed（新增 3 项契约测试）。

**缺陷**：`core/magnifier.py` 有 4 处 `ctypes.windll.user32`（`SetWindowDisplayAffinity` ×1、
`GetSystemMetrics` ×4），**都没有 `argtypes`**。不声明签名时 ctypes 按 C `int` 传参，
64 位下 HWND 句柄被截断成 32 位。程序一直没坏，是因为**实际 HWND 值几乎都小于 2³²**——纯属碰巧。

**为什么值得修而不是"反正没坏"**：这是那种"上线三个月后在某个用户机器上炸、且炸得莫名其妙"
的缺陷。发作时表现为放大镜把截屏排除打在错误的窗口上（或直接静默失败），
日志里只会留下一个 `SetWindowDisplayAffinity returned 0`，看不出是截断。

**修法**（不是就地补两行，而是让它归队）：
- `core/win32_utils.py` 早就是"唯一 Win32 入口"（文件里写着"禁止各自 `ctypes.windll.user32`"），
  10 个模块都遵守，只有 magnifier 例外。补齐这条约定比就地补签名更治本。
- `win32_utils` 新增 `SetWindowDisplayAffinity` / `GetSystemMetrics` 的 `argtypes`/`restype`，
  并把 `WDA_EXCLUDEFROMCAPTURE`（及其配对值 `WDA_NONE`）常量收口到常量区。
- `magnifier` 改为 `from core.win32_utils import WDA_EXCLUDEFROMCAPTURE, user32`，
  4 处直调改走 `user32`，`import ctypes` 随之删除（已无其他用途）。
- `main.py` 的崩溃兜底 `MessageBoxW` **故意不 import win32_utils**：它跑在"核心模块可能已经坏掉"
  的启动失败路径上，多依赖一个项目模块就多一种连报错都弹不出来的可能。改为就地设 `argtypes`
  （只依赖标准库），理由写进代码注释。

**新增门禁 `tests/test_win32_entry.py`（3 项）**：此前 RULES §6 写着"ctypes 签名没有任何检查项，
这是唯一防线"，等于承认全靠人眼。现在三条断言：① 除三个白名单文件外禁止
`ctypes.windll.user32` / `WinDLL("user32")` 直调；② `REQUIRED_SIGNATURES` 里 12 个在用 API
都必须已设 `argtypes`；③ 返回 BOOL/int 的 API `restype` 必须明确。
**有牙已验证**：临时注释掉一行 `argtypes`，测试立即变红并报出函数名；恢复后与备份逐字节一致。

**代价**：新增 API 时必须同步往 `REQUIRED_SIGNATURES` 里加一条，否则测试给不了保护。
这条已写进 RULES §6（把原文的"没有工具兜底"改成"有检查但只覆盖已登记的"）。

**验证**：pytest 110 passed、ruff F401/F841/F811 全绿、py_compile 全过；
实跑确认签名与真实实参兼容（真 winId 调用返回 0 不抛异常，传 >2³² 的假句柄也完整传下去未截断）。
HANDOVER §十二「magnifier 直调 user32 且没设签名」这条已知债**修完即删**（判据已进 RULES §6）。

## 2026-10-25 审查档案归档：删 docs/reviews/ 11 份，17 条判据先榨后删

> 版本号**不动**（V0.0140300182）：只删档案 + 改文档，无行为变化。
> **指针重定向**：历史上 3 处「见 FIX_PLAN 附表」（批次 4 的 P3-2、P3-3，批次 5 的编号说明）
> 现在指向**本条末尾的附表**。原文件已删；历史正文按「只追加不修改」保持原样，不做回改。

**动机**：`docs/reviews/` 混装三类东西——一次性审查报告、元审查套娃（审查「审查者的审查」）、
活资产。前两类是**对话存档，不是知识**，留着只会让后人以为还有 900 行没处理。

**但不能直接删**：同一天早上刚演过一遍「删段落连带删掉 9 条判据」。
所以先做逐份通读 + 关键词反查（在 RULES / HANDOVER / CHANGE_LOG 里 grep 确认确实没有），
捞出 **17 条不可替代信息**，其中 1 条是硬前置。

**硬前置：SMP 编号处置表**（原 FIX_PLAN 附表，48 条）——P3-2/P3-3 的唯一载体，
知识库里只有指针没有副本。已整表迁到本条末尾。

**新补进知识库的判据（原先只活在审查报告里）**：

- RULES §6 提交纪律（本地可提交 / push 前问 / 能用 git 回滚就别重写）
- RULES §2.2 反向验收（「代码落地了」≠「改对了」，每条断开/释放/停止/置空单独复核）
- RULES §10 账本纪律（按编号全集机械对账；跳过或改判必须留一行「不修 + 理由」）
  + 审阅结论的写法（能跑命令的必须实测；跨文档摆一张表能反查自相矛盾）
- RULES §9 闭包形式的槽**无法定向断开**，必须先提成实例方法
- RULES §6 机械门禁两处盲区：ruff 门禁不含 `tools/`；ctypes 签名无任何检查
- HANDOVER §四 锁内 IO 是**有意取舍**（别为了性能把落盘移出锁，移出去正好回到 S2 并发损坏）
- HANDOVER §十 `pip install .` 装得上但是**空壳**（wheel 不含 `config/`、`resources/`）
- HANDOVER §四・五 射表 profile 缓存靠**对象同一性**，原地改内容不会失效（静默无报错）
- HANDOVER §十 `resources/` 下有 20+ 个含空格/逗号的英文目录名（如 `USMC, LAV-25`）
- HANDOVER §十二 三项结构性已知债（`_connect_tab_signals` if-elif 树、两份热键控件拷贝、
  `magnifier` 直调 user32 绕过统一入口）
- 本条下方：`json.dump` 的 **补正**、mss「版本无关导入」为何被否、P11/P13 won't-fix 的真实理由

### 补正：`json.dump` 不是「持 GIL 原子执行」

2026-10-24 批次 3 的 M4 条目里写过「CPython 的 `json.dump` 是 C 实现、持 GIL 原子执行」。
**这个表述不准确，现补正**：

`json.dump` 的实际形态是 `for chunk in iterencode(obj): fp.write(chunk)`——它是**生成器逐块写**，
每次 `fp.write` 都会释放 GIL，生成器的迭代状态跨 yield 保留。所以它**不是**一个不可分割的操作。

这直接影响 M4 的定性：`_dump_config` 里那 3 次 `RuntimeError` 重试不是「防御不存在的问题」，
而是**症状真实发生过的疤痕**。错的是当时的解释，不是重试本身。

### 已否决方案的失败原因（补记，防止后人重选同一条路）

- **mss「写 try/except 做版本无关导入，兼容 9 和 10」——做不到**：
  两个版本的 `CAPTUREBLT` 分居 `mss/windows.py`（模块级）与 `mss/windows/gdi.py`，
  `import mss.windows as _gdi` 不能通吃。所以只能锁版本，没有「一套代码兼容两个大版本」的写法。
  当前约束 `>=10.0,<11`；将来放宽前必须重看这条。
- **P11 won't-fix（中文目录名压缩）的真实理由**：本项目**仅 Windows 分发**；
  `.gsv` 由 Python `zipfile` 写入 UTF-8 标志位，第三方压缩器不在支持路径内。
  由此推出一条操作约束：**发布包必须在 Windows 侧打包**，否则中文与含空格目录名会乱码，
  对应载具准星不显示，且不会报错。
- **P13 won't-fix（外链声明）**：全仓零网络代码（无 requests / urllib / socket 调用，已实测）。

### 附表：SMP 编号全集处置（原 `docs/reviews/FIX_PLAN_2026-10-24.md` 附表，迁移）

机械提取：`grep -ohE '^#+ [SMP][0-9]+' docs/reviews/*.md | sort -u`（22 个标题编号）
+ CODE_REVIEW §二/§三 表格行内编号，逐条映射：

**S 级（CODE_REVIEW §一，7 项）**

| 编号 | 处置 |
|---|---|
| S1 放大镜线程启动即死 | 批次 1（worker try/finally）；定性修正见 CODE_REVIEW 附录 B；依赖约束批次 2 |
| S2 配置保存并发 | 批次 1（原子写入锁） |
| S3 .gsv 导入未绑定变量 / 路径穿越 | 批次 1（S3a/S3b） |
| S4 复制路径 NameError | 批次 1 |
| S5 tuner 重复连接 | 批次 1（断开逻辑前移）+ 批次 4 浪3（C++ 释放，半修补齐） |
| S6 桌宠 parent | 批次 4 浪1（潜在陷阱处置） |
| S7 OverlayRenderer 无断开 | 批次 1 |

**M 级（CODE_REVIEW §二，24 项）**

| 编号 | 处置 |
|---|---|
| M1 refresh_min_max 越权 | 批次 1 |
| M2 scanner 竞态 | 批次 3（FIX_PLAN M1） |
| M3 ctypes 缺签名 | 批次 1 |
| M4 BboxCache 无锁 | 批次 3（FIX_PLAN M2；症状描述修正见本条「补正」） |
| M5 射表重建 | 批次 3（FIX_PLAN M3） |
| M6 stop 语义 | 批次 1（_enabled）+ 批次 4 浪3（信号断开） |
| M7 deferred save 引用 | 批次 1（与 S2 合并） |
| M8 unhook_all | 批次 3（FIX_PLAN M4） |
| M9 放大镜 worker | 批次 1（与 S1 合并） |
| M10 crosshair pixmap | 批次 3（FIX_PLAN M5） |
| M11 join 竞态 | 批次 4 浪2 |
| M12 重命名误报 | 批次 3（FIX_PLAN M10） |
| M13 mag 回写抑制 | 批次 3（FIX_PLAN M11） |
| M14 搜索防抖 | 批次 3（FIX_PLAN M12；增量过滤不做的理由见批次 3 条目） |
| M15 adapt 私有 API | 批次 3（FIX_PLAN M13） |
| M16 热键捕获 hook 泄漏 | 批次 3（FIX_PLAN M14） |
| M17 wheel 补偿 | 批次 3（FIX_PLAN M15）→ 引入 P0 回归 → 批次 4 浪1 修复 |
| M18 _loading try/finally | 批次 3（FIX_PLAN M16） |
| M19 splitter 高频写 | 批次 3（FIX_PLAN M17） |
| M20 ammo_wheel acquire 不释放 | 批次 3（FIX_PLAN M18：stop 进退出路径） |
| M21 启动日志裸 open | 批次 2（P4 三处 try + %TEMP% 降级） |
| M22 _LibpngFilter | 批次 4 浪2（删除） |
| M23 清理契约四份 | 批次 3（FIX_PLAN M19）+ 批次 4 浪2（export window 侧） |
| M24 ROOT 依赖 CWD | 批次 2 已顺手修（无记录）→ 批次 4 浪4 补记 |

**P 级（PORTABILITY_REVIEW，17 项）**

| 编号 | 处置 |
|---|---|
| P1 | 批次 2 |
| P2 | 批次 2 |
| P3 build.bat BOM / jobs 硬编码 | 批次 5 |
| P4 | 批次 2 |
| P5 | 批次 2 + 批次 4 浪2（resources 半修补齐） |
| P6 | 批次 2 |
| P7 | 批次 2 |
| P8 requires-python 上界 | 批次 5 |
| P9 非 Windows 平台守卫 | 批次 5 |
| P10 | 批次 2（拍板 D；载具数修正 77） |
| P11 中文目录名压缩 | **won't-fix**：仅 Windows 分发；`.gsv` 由 Python zipfile 写 UTF-8 标志，第三方压缩器不属支持路径 |
| P12 图标死分支 | 批次 5 |
| P13 外链声明 | **won't-fix**：全仓零网络代码（实证），仅文档文本含第三方地址 |
| P14 GS_DEBUG | 无需处置（审查结论：干净） |
| P15 x64-only 声明 | 批次 5（README 一行） |
| P16 | 无需处置（审查结论：无问题） |
| P17 py 启动器假设 | 批次 2 随 P2 修复（build.bat 解释器自适应）；批次 5 实测复核 |

**未单独编号的轻级条目（CODE_REVIEW §三）**：该节是「选摘」，未逐条编号，故不做逐条映射。
其中「死代码 / 命名统一 / 魔法数字」三组由批次 5 承接；性能细节与其余一致性项**明确不修**
（收益低于风险，同类项已在 RULES「别去修的东西」清单内）。

### 删掉的三份「活资产」及理由

| 文件 | 为什么敢删 |
|---|---|
| `GUI_INVENTORY.md` | 是**可重跑产物**（`tools/export_gui_facts.py`，20 秒重建），不是文档。留着反而会过期成假事实——与 `.venv` / `egg-info` 不入库同理：**生成物不该入库** |
| `MANUAL_OUTLINE.md` | 手册组织结构的提案，手册已按它写完，规划无人再读 |
| `REAL_OVERLAY_RESEARCH.md` | Real Overlay 功能**至今未实现**（全仓 grep `real_overlay` 零命中）。技术调研有保鲜期，将来真要做应当重做而不是照着 2026-10 的笔记做。**元信息已登记进 HANDOVER §十二** |

## 2026-10-25 许可证 MIT → GPL-3.0-only（PyQt5 是 GPLv3，MIT 声明不成立）

> 版本号不动（V0.0140300182）：改的是分发条款，不是源码行为，按 RULES §7 不 +1。
> 下一个真有行为更新的版本起，发布物按 GPL-3.0-only 分发。

**怎么发现的**：用户问「我的依赖是不是太小众变态」，去查 PyPI 文件清单，发现
`pyqt5-qt5` 全平台只有 `5.15.2` 提供 Windows 二进制（5.15.3 零文件、5.15.11~19 只有 mac/linux）。
顺手核许可，发现冲突。

**问题**：本仓 `LICENSE` 是 MIT，而 PyQt5 是 **GPL v3 / 商业授权**双许可且**无 linking exception**。
程序 import PyQt5，整体分发就必须走 GPL v3。README 写 `Released under the MIT License` 与实际不符。
不是「选错了库」，而是这个组合本身不成立——MIT + GPL 依赖是业内经典坑。

**处置**：`LICENSE` 全文替换为 GPLv3 官方文本（未做任何删改）；README §许可 同步改写。
依赖兼容性已逐个核对：PyQt5 (GPLv3) / Qt5 (GPLv3) / Pillow (HPND) / loguru·mss·keyboard (MIT) /
Nuitka (Apache-2.0)，全部与 GPLv3 相容，没有第二个冲突。

**关于「要不要补救历史版本」**：**不需要，也没法**。MIT 是**不可撤销**许可——
已按 MIT 发布的版本（tag `v0.0140300177` 及之前）永久保持 MIT，拿到的人可以继续按 MIT 使用它。
改 LICENSE 只对**之后的版本**生效。本仓尚无正式 Release、未对外宣传，实际持有者极少，
所以「历史版本仍是 MIT」在法律上无害、在事实上也几乎没人被影响。

**未做**：`pyproject.toml` 仍然没有 `license` 字段（本来也没有）。wheel 元数据靠 setuptools
自动带的 `License-File: LICENSE`，所以换 LICENSE 内容即已生效。要显式声明 SPDX 得等
`setuptools>=77`，暂不动。

## 2026-10-25 打包前自动备份排除 `.venv/`（备份 199MB → 43MB）

**怎么发现的**：查"`gunnersight.egg-info` 这目录是啥"时顺手 `du -sh backups/auto_before_build`，
发现 199MB 里 156MB 是 `.venv`。

**根因**：`tools/build.bat` 第 24 行的 `/XD` 排除名单写在 `.venv` 出现之前。
今天 09:19 第一次 `uv sync` 建出 `.venv`（156MB）之后，每次构建前 `robocopy /MIR` 都把它整个复制一遍。
**排除名单是会随新目录出现而失效的**——这类名单没有自我提醒机制，只能靠发现。

**改了什么**：
- `tools/build.bat`：`/XD` 加 `.venv`（仍纯 ASCII + CRLF，73/73，0 非 ASCII 字节）
- 清掉 `backups/auto_before_build/.venv`：199MB → 43MB
- HANDOVER §十 备份节：排除名单补 `.venv/` + 写清"为什么必须在里面"；
  本机目录表补 `.venv/` 与 `gunnersight.egg-info/` 两行（回答"这目录是啥"）
- RULES 坑速查：「备份体积莫名 200MB」原先归因 `dist`/`.git`，**归因不准**——
  实际主因是 `.venv`；顺带补一句"排除名单写在目录出现之前就会漏"

**顺带对齐目录**：`docs/` 下三份非正式文档被移进 `docs/reviews/`
（`GUI_INVENTORY` / `MANUAL_OUTLINE` / `REAL_OVERLAY_RESEARCH`，`docs/` 根只留三份 agent 文档 + CREDITS）。
随之改引用：`tools/export_gui_facts.py` 输出路径（docstring + 写盘 + print 三处）、
HANDOVER §一・五 正文引用、§六 目录树。
实跑脚本验证：440 行，与移动前**逐字节一致**（可复现，未把用户运行期配置漂移写进底稿）。

**验证**：`robocopy /L` 干跑确认源 519 文件、涉及 `.venv` 的行数为 0（排除生效）；
`audit_docs` 34/34。版本号不动（构建脚本，不影响运行时行为）。

## 2026-10-25 文档三分法：新建 docs/RULES.md，AGENTS.md 降为人格层

> 版本号**不动**（V0.0140300182）——纯文档结构 + 注释引用，无行为变化；
> 按 RULES §7「源码**行为**更新才 +1」，不给用户"有新版本"的假信号。
> 测试维持 107 passed；`tools/audit_docs.py` 29 → 34 项全绿。

**动机（诊断）**：HANDOVER §十一 长到 216 行（全文 24%），满是"已完成 2026-xx-xx"。
根因不是某次偷懒，是**整套文档缺"未来"这一维**：一条经验既不是现状也不是事件，
它回答"下次该怎么做"，无处可去就被塞进待办清单当战绩。
改动日志与交接混淆的是**经验**，交接与 AGENTS 混淆的是**纪律**。

**新分工**（按时间性，一条信息只能有一个家）：

- `docs/RULES.md` = **判据（未来）**：该怎么做、做错会怎样。**入库**，随代码 review
- `docs/HANDOVER.md` = **现状**：长什么样、为什么这么设计。**只覆盖不追加**
- `docs/CHANGE_LOG.md` = **经过**：发生了什么、哪些方向回退过。**只追加不修改**

**动作**：

- 新建 `docs/RULES.md`（约 340 行 / 10 节）：AGENTS 全部判据 + HANDOVER §八 GUI 约定
  + §十二 坑速查 41 条 + §十一・五「不该动的」lint 表 + §八・五 的两条已测结论
  （启动无优化空间、高频槽只准增量）。末节 §10 是维护办法（三问判据 + 时间性否决项）。
- `AGENTS.md` 187 → 25 行：只留人格层（用户说意图不说方案；失败模式是"自信型幻觉"；
  规矩指向真相、可明面推翻但要在本文件记账）与三份文档指针。
  **文件名不能删**——自动加载认的是这个文件名，删了通道就断。
  旧版备份在 `backups/AGENTS_pre_rulemd_2026-10-25.md`（它从未入库，没有 git 可回滚）。
- `HANDOVER.md` 917 → 572 行：§十一 216 → 25 行（只留非作者机器验收三项）；
  §十一・五/・六 删除（已完成或已迁出）；§十二 坑速查迁出后原 §十三 升为 §十二；
  §八 GUI 约定改为指针（保编号，不让旧引用失效）；§十一・六 的手册口径 4+4 条并入 §一・五。
- **修 4 处事实漂移**（这批比冗长危险）：① §二 退出链还写着"aboutToQuit 兜底清理放大镜"
  （实为与 closeEvent 跑同一份清理契约）；② §四・五「灵敏度换算见十一・5」指错项
  （内容在第 6 项）；③ §七 `cleanup.py` 描述停在"safe_call 助手"（实为契约 SSOT）；
  ④ §十 HEAD 写死 `d514ae7`（早已过期，改为"以 `git log` 为准，别写死"）。
- `tools/audit_docs.py`：新增 RULES 路径校验、RULES/CHANGE_LOG 换行校验（LF）、
  AGENTS 钩子有效性（必须指向 RULES + HANDOVER）。共 34 项。
- 代码/测试注释 5 处 `AGENTS §x` → `docs/RULES.md §x`（`core/cleanup.py`、
  `core/mouse_hook.py`、`gui/main_window.py`、`tests/test_wave_d_contract.py` ×2）。
  **本文件里的历史引用一律不动**——历史就是历史，它记录的是当时的事实。

**改变了旧决定**：2026-10-24 定过"`AGENTS.md` 永不入库（只约束自己，不做脱敏版）"。
新规矩文档入库，理由：规矩要能被 diff、被 review、改坏能回滚，公开规范也是开源项目常规做法。
`AGENTS.md` 本身仍不入库——它只剩人格与指针，丢了重建成本极低。

## 2026-10-25 批次 5：轻量与墓碑清理（原 FIX_PLAN 批次 4）

> 版本号 V0.0140300181 → V0.0140300182；测试维持 107 passed（删码/改名不加同义反复测试）。
> 范围 = FIX_PLAN 原批次 4 清单 + PORTABILITY P3/P8/P9/P12/P15/P17。

- **死代码删除**：AST 定位 + 全仓引用反查为零后再删（`RegionSelector` / `PointPicker` /
  `CrosshairPreviewWidget` / `make_int_spin` / `_update_mag_item_text` / `SKIP_TYPES` /
  `ChatBubble.set_persistent`、`set_volume` / `SoundPlayer.set_volume` /
  `distance_meter.is_modifier_pressed` + `_resolve_combo_vk` /
  `angle_meter_pause_triggered` + `_on_angle_meter_pause` / `squad_macro_tab.showEvent`
  懒加载死分支 + `_data_loaded`）。**VehicleFilterWidget 未删**——三处页面 + 两处测试在用
  （处置单 §2.4 的坑）。
- **命名统一**：`offset_x/offset_y` → `*_spin`；启用槽三种命名 → `_on_enable_toggle`。
- **音量三源收敛**：新常量 `DEFAULT_MASCOT_VOLUME=0.1125`；ChatBubble 原 `setVolume(10)`
  与 SoundPlayer/config 的 0.1125 不一致，统一走常量。
- **P3 build.bat**：**根因不是 BOM**——cmd 批处理解析器在 UTF-8 下会吞多字节字符
  （真实事故：`echo 产物路径:` 被拆成 `echo 产` + 未知命令 `物路径:`，报"不是内部或
  外部命令"；先去的 BOM + `chcp 65001` + 路径加引号三招都没治好，第二次构建仍复现）。
  最终方案：批处理文本改**纯 ASCII + CRLF**（中文说明留在 CHANGE_LOG/HANDOVER），
  `--jobs` 改 `%NUMBER_OF_PROCESSORS%`。**教训**：.bat 里不要写中文——不是编码页问题，
  是解析器本身的缺陷。
- **P8/P9/P12**：requires-python 上界 `<3.14`；非 Windows 平台守卫；删 PyInstaller
  `_MEIPASS` 死路径（项目用 Nuitka onedir）。
- **P15/P17**：README x64 声明与 build.bat 解释器自适应在批次 2 已落地，本批次复核确认。
- **明确不修**（FIX_PLAN §零 硬约束覆盖）：CODE_REVIEW §三 的性能细节（逐像素扫描、
  paintEvent 新建 QFont、滚轮全量重建）与其余一致性项——收益低于风险，且同属
  「高频路径已核实为增量」的保护名单。§三 为选摘、无编号，故不逐条映射（附表已说明）。

## 2026-10-25 批次 4：回归修复与账本（浪 1-4）

> 依据 docs/reviews/CONSOLIDATED_ACTIONS_FOR_STEP5.md（三轮交叉审查合并处置单，基线 186faf0）。
> 版本号 V0.0140300180 → V0.0140300181；测试 91 → 107 passed。
> 编号说明：处置单的 P0/P1/P2/P3 是「本轮处置优先级」，与 CODE_REVIEW 的 S/M/P 编号无关；映射见 FIX_PLAN 附表。

### 浪 1：P0 两项 + 桌宠生命周期

- **P0-1 无参 disconnect 抹掉别人的槽**（gui/main_window.py）：on_ammo_wheel_ready 的补偿连接用 `toggled.disconnect()`（无参 = 清空该信号**全部**槽），把标定测距 tab 自己的电闸 `_on_enable_toggle` 一并抹掉 → 勾选框彻底失效（不写配置/不起停引擎/不注册热键）。触发链：config 启用标定测距 → 预创建 tab 连电闸 → 100ms 后 wheel 就绪走补偿。**91 passed 全绿的原因**：旧测试只断言「新连接生效」，不锁「碰过的旧槽还活着」。
  - 修法：创建路径与补偿路径的两份同款闭包（同一功能两个实现）收敛为实例方法 `self._on_distance_toggle`；补偿路径 `disconnect(self._on_distance_toggle)` 定向摘除。
  - **规矩升级**：HANDOVER §十二「先断再连」补边界——无参 disconnect 只准用在自己拥有、打算全清的信号上。
  - 有牙证明：HEAD 版 main_window 下 `test_ammo_wheel_ready_keeps_tab_own_slot_alive` 必红（配置未被写入），恢复后 md5 一致。
- **P0-2 桌宠 parent（S6）**（gui/tabs/info_tab.py + main_window.py）：`__init__` 先连信号再 setChecked，config 称启用时同步走创建路径；彼时 tab 未 insertWidget，`window()` 返回自身 → 桌宠 parent 成页面子控件，切 tab 即消失。
  - 修法：`blockSignals` 包 setChecked；创建交 showEvent / MainWindow 创建回调（新增 TAB_INFO 分支 → `InfoTab.ensure_mascot()`）；`_create_mascot` 断言 `window() is not self`。
  - **与处置单不符（§〇-3 记账）**：`config.is_mascot_enabled()` 自 2026-09-07（c0973fe）起硬编码 `return False`（「不持久化，每次启动默认关闭」），`set_mascot_enabled` 只写一个全仓无人读的 `_mascot_enabled_runtime`。故处置单描述的触发链**当前生产不可达**——这是**潜在陷阱**：一旦恢复持久化，bug 立刻复活。测试用 monkeypatch 把 getter 钉成 True 锁契约，与持久化策略解耦。**是否恢复 mascot 持久化属产品决策——2026-10-25 用户拍板：不恢复。** 理由：吉祥物是「彩蛋性质」的玩意，每次启动默认关闭是设计意图。修复转为永久陷阱防护。
  - 验收按代码设计修正（用户批准）：parent 是主窗口（不是 None，也不是 tab）+ 切页不消失（`isVisible` 依赖祖先链）+ resize 重定位。
- **桌宠退出生命周期（P0-2 顺带暴露）**：`MascotWidget.hideEvent` 无保护 `_anim.stop()`，窗口销毁级联里踩已删除的 `QPropertyAnimation`（间歇 RuntimeError，新测试首次真创建桌宠才暴露）。分层处置：① `MascotWidget`/`ChatBubble` 增加 `shutdown()`，先停动画/定时器/音频再隐藏（已隐藏则销毁时不再触发 hideEvent——主修复）；② hideEvent 加 RuntimeError 护栏（Qt 自主销毁级联兜底）；③ 桌宠 parent 是主窗口 → 窗口级资源，进 M19 清理契约（`collect_window_cleanup_steps` 新增「桌宠」项 → `InfoTab.shutdown_mascot()`）。

### 浪 2：P1 五项

- **P1-1 uv.lock 与源码割裂**：临时目录实验推翻处置单的病源判断——不是镜像缺失，而是**批次 3 版本号 179→180 后未重锁**（`uv lock --check` 判定 lock 过期，按 pypi.org 重解析 175 包）。pyproject 显式声明 `[[tool.uv.index]]`（aliyun, default=true）后重锁，lock **只变 2 行**（project version + mss specifier），1437 处 source 不动。验证：不设 `UV_DEFAULT_INDEX` 跑 check → exit 0（1ms）。
- **P1-2 resources 未降级（P5 半修补齐）**：读路径保持 exe 同级（随包出厂资源）；新增 `resources_write_dir`（exe 同级不可写时降级 config 侧 resources）+ `resolve_resource_path()`（读多路径：出厂优先→写目录兜底）。`ResourceManager` 新增 `write_dir`/`get_write_dir()`：list 取并集（assets 仍排除）、get 两处找、import 落写路径、remove/rename 跨路径定位；导入/导出 .gsv 改用写路径。Program Files 标准用户不再静默失败。
- **P1-3 export 缺 window 侧**：export_gui_facts 补 `collect_window_cleanup_steps`；四调用方双 collector 接线加静态契约测试（§2.3 漏项根因）。
- **P1-4 M22 `_LibpngFilter` 删除**：它只替换 `sys.stderr`，拦不住 libpng 的 C 层 `fprintf(fd 2)`。留着就是一段撒谎的注释。
- **P1-5 M11 join 竞态**：`MouseHook._stop` 的 `join(0.5)` 超时补 warning 留痕（线程卡事件队列无法强杀，至少不静默）。

### 浪 3：P2 四项

- **P2-1 S5 补全**：`_shutdown_engine` 里 tuner 置 None 前 `deleteLater()`——parent 是 tab，此前每轮禁用/启用累积一个带 2 个 QTimer 的 QObject。
- **P2-2 M6 补全**：`AmmoWheelSelector.stop()` 反向断开四条连接（MouseHook 单例两条 + state 两条），TypeError 守卫保证幂等（closeEvent + aboutToQuit 双跑安全）。stop() 是退出路径专用（start 仅 main.py 一处）。
- **P2-3**：FIX_PLAN 死码清单点名 `RegionSelector`/`PointPicker`/`CrosshairPreviewWidget` + `make_int_spin`；明写 `VehicleFilterWidget` 是活控件（三页 + 两处测试）**不得进删除名单**。
- **P2-4**：`mss>=10.0,<11`（9→10 的 breaking change 已咬过一次）。

### 浪 4：P3 账本

- **P3-1 版本同步守卫**：`tests/test_batch4_p3_ledger.py` 断言 pyproject version == `APP_VERSION.lstrip("V")`（此前 tests/ 零命中，全靠人工 + 注释约定）。
- **P3-2 SMP 编号全集对账**：见 FIX_PLAN 附表（S1-S7 / M1-M24 / P1-P17 逐条映射到批次或「不修 + 理由」）。
- **P3-3 未排期项**：P3/P8/P9/P12/P15/P17 归入批次 5；P11/P13 won't-fix（理由见附表）。
- **P3-4 M24 补记**：`export_gui_facts` 的 ROOT 早已改 `Path(__file__).resolve().parent.parent`（批次 2 顺手改），但任何批次记录都没提——本条补记，避免将来回溯以为没人管过。

### 横切

- **AGENTS §4 新规矩**：改既有连接/清理/注册项时，必须断言「原有的仍然生效」，不只锁「新加的在工作」（§五 根因的直接对策）。
- 版本 V0.0140300180 → V0.0140300181（info_tab APP_VERSION + pyproject 双处 + uv.lock 重锁 1 行）。
- 测试 91 → 107 passed（新增 16：浪1 七项、浪2 六项、浪3 两项、浪4 一项）。

## 2026-10-24 批次 3：中坏味道十五项（浪 A/B/C1/C2/C3/D）

> 依据 docs/reviews/CODE_REVIEW_2026-10-24.md 中坏味道清单，执行 docs/reviews/FIX_PLAN_2026-10-24.md 批次 3。
> 版本号 V0.0140300179 → V0.0140300180；测试 54 → 91 passed（新增 37 个契约测试，分六个测试文件）。
> 编号说明：FIX_PLAN 批次 3 清单的 M13/M15 与 CODE_REVIEW 原编号有错位，执行时标签以 CODE_REVIEW 为准（M15=adapt 公共信号、M17=splitter+ammo_wheel 补偿），FIX_PLAN 已完成标注处附对照。

### 浪 A：core 稳定性与性能（5 项）

- **M1 BboxScanner 起停竞态 → 常驻线程**（core/bbox_crop.py）：原实现每次 submit 起停 QThread，stop/start 窗口期 submit 会踩到"线程已死但引用还在"/重复 start。**首版修复已回退**：用 `_running` 标志 + submit 里 `wait(1000)` 等旧线程——start() 后新线程 run() 置位前也有窗口，此窗口内 submit 的 wait 会等一个**健康运行中**的线程；tab 构造的 prescan 连续触发几十次 submit，全量测试从 30s 劣化到 527s（单个用例 160s）。最终方案 QMutex + QWaitCondition **常驻模式**：只 request_stop 退出，`_started` 保证只 start 一次，request_stop 清队列使 wait 只等当前一张。conftest teardown 补 overlay.shutdown() 停 scanner。
- **M2 BboxCache 加锁**（core/bbox_crop.py）：load/cleanup/save/get/set/has/all_paths 全部持 threading.RLock。**审查报告的症状描述不准**：预期的「迭代期增删 RuntimeError」不可复现——CPython 的 `json.dump` 是 C 实现、持 GIL 原子执行。锁的价值改为「_dirty 复合竞争防护 + 序列化器演进防御」，测试保留作回归。
- **M3 射表查询缓存**（core/config/angle_meter.py、base.py）：query_firing_distance 每次全量构建 BallisticProfile → 按 name 缓存 profile（table 引用 `is` 判有效）。鼠标级热路径。
- **M4 热键 unhook 误伤**（core/hotkey_manager.py）：_unregister_all_keyboard_hotkeys 从 `keyboard.unhook_all()` 改为 `keyboard.unhook(hook)`，只摘自己的钩子。
- **M5 crosshair pixmap 缓存污染**（core/overlay.py）：_on_scan_done 仅 `path == self._crosshair_path` 才构建 QPixmap，UI 全屏整图不再进 crosshair 缓存。

### 浪 B：vehicle_config_tab 列表语义（3 项）

- **M10 重命名误报**：取消/空名/同名静默 return，不再弹"重命名成功"。
- **M11 mag 列表回写抑制**：_refresh_mag_list 选中恢复包 _suppress_mag_writeback + try/finally 复位。
- **M17 splitter 停止才存**：_on_splitter_moved 只打脏标记，eventFilter 拦 handle 的 MouseButtonRelease 才存尺寸（拖拽中每像素写盘 → 停止写一次）。resource_tab 同改。

### 浪 C1：搜索防抖（5 页 + 1 共用控件）

- **M12**：textChanged 每按键全量重建列表（资源页还叠加磁盘列举+引用索引重建）→ 180ms singleShot 防抖，停止输入才过滤一次。覆盖 vehicle_config / resource / magnifier preset / angle_meter profile / VehicleFilterWidget（overview、squad_macro、angle_meter link 三处共用）。
- **接口变更**：**既有测试 test_widgets.py::test_list_row_restored_under_filter 同步更新**——原假设搜索后同步过滤，加 `QTest.qWait(400)` 跨过防抖窗口（测试对象是选中恢复，不是防抖本身）。
- **范围决策：增量过滤本轮不做**——77 载具规模防抖后重建 5-10ms 无感；资源树增量有父子可见性坑，收益/风险比差。留待确有性能证据再议。

### 浪 C2：跨页信号与补偿（2 项）

- **M15 adapt_tab 越权读 window 私有状态**：新增公共信号 `theme_reapply_requested(str)`，_pick_accent 只 emit 不再读 window 私有状态/调私有方法；main_window 连信号 + _on_theme_reapply_requested（仅当前主题才 _apply_theme）。
- **M17 补偿**：main_window 新增 `on_ammo_wheel_ready()`（补同步 set_function_active + 先断再连 toggled），main.py 后台任务创建 AmmoWheelSelector 后调用——此前 wheel 未创建时 toggled 连接缺失。

### 浪 C3：异常路径兜底（2 项）

- **M14 热键捕获 hook 释放**（gui/hotkey_widgets.py）：抽出 _release_capture_hook()；`destroyed` 连 **lambda 捕获 self**（PyQt 坑：destroyed 连对象自身绑定方法时 slot 静默不触发）；加 closeEvent 兜底。
- **M16 `_loading` 标志泄漏**（gui/tabs/angle_meter_tab.py）：_load_profile_params 整体 try/finally 复位——中途抛异常会把"加载中"锁死，后续交互全部静默失效。

### 浪 D：退出路径收口（2 项）

- **M18 ammo_wheel.stop() 进退出路径**：滚轮常驻鼠标钩子（MouseHook）与超时定时器，此前四份清理实现（closeEvent / aboutToQuit / conftest / export_gui_facts）没有一处停它——关窗后钩子还挂着，滚轮事件继续注入。
- **M19 清理契约 SSOT**（core/cleanup.py，在既有 safe_call 基础上扩建）：TAB_CLEANUP_STEPS 表 + `collect_tab_cleanup_steps`（get_tab 纯查询，不触发懒加载）+ `collect_window_cleanup_steps` + `run_cleanup_steps`（safe_call 逐项隔离 + on_step 耗时回调）。四份调用方收敛为一份：main_window.closeEvent（保留逐项耗时日志）、main.py aboutToQuit 兜底（原只停 overlay+放大镜，扩为全契约）、conftest teardown、export_gui_facts（删五个历史方法名探测）。各清理动作幂等（正常退出双跑安全）。
- **验证纪律**：浪 D 有牙证明——把 main_window.py 临时换回 HEAD 版，test_close_event_stops_ammo_wheel 必红（stop_called=False），恢复后 md5 一致。
- **新增测试**（37 个）：test_wave_a_core(7) / test_wave_b_tabs(8) / test_wave_c1_search(6) / test_wave_c2_signals(4) / test_wave_c3_fallbacks(4) / test_wave_d_contract(8)。
- **顺带**：pyproject 增 `[tool.pytest.ini_options] testpaths=["tests"]`（裸 pytest 会连 backups/ 里的历史副本一起收集，ImportPathMismatchError 中断全量验证）；export_gui_facts 产物归一化（mkdtemp 随机路径 → `<临时数据目录>` 占位，重生成可复现，双跑指纹一致）；GUI_INVENTORY.md 重新生成（版本号/数据目录行/版权行/适配页控件重排）。
- **验证**：pytest 91 passed、compileall 全过、audit_docs 29/29、export_gui_facts 实跑 + 双跑指纹一致、浪 D 有牙证明。
- 遗留（待用户手动验证）：splitter 拖拽停存手感、搜索防抖延迟观感、滚轮/角度仪既有手感项——真实 GUI 操作，按项目测试边界先例不自动化。

---

## 2026-10-24 批次 2：发布兼容性必修（P1/P2/P4/P5/P6/P7 + 2.8）

> 依据 docs/reviews/PORTABILITY_REVIEW_2026-10-24.md，执行 docs/reviews/FIX_PLAN_2026-10-24.md 批次 2。
> 用户拍板 A-D 全部按推荐：A mss>=10.0 重锁；B README 构建口径 uv 化；C 数据目录加只读降级；D 出厂 77 载具库保留 + README 明示。
> 版本号 V0.0140300178 → V0.0140300179；测试 42 → 54 passed（新增 12 个契约测试）。

- **P1 `pip install .` 必败**（pyproject.toml）：补 `[build-system]`（setuptools）+ `[tool.setuptools.packages.find] include=["core*","gui*"]` + `py-modules=["main"]`。实证：干净副本 `pip wheel .` 出包，wheel 含 core(29 模块)/gui(21)/main.py，无 config/resources/tests 泄漏。
- **P7 mss 版本矛盾**：约束 `>=9.0,<10.0` → `>=10.0`；uv.lock 重锁 9.0.2 → 10.2.0（uv 0.13.5 装入隔离 venv 执行，`UV_DEFAULT_INDEX` 指向 aliyun 保持镜像来源一致；重锁顺带修正 lock 里过期的项目版本号 141→178）。实证：干净副本 `uv sync` 后 `import mss.windows.gdi` / `core.magnifier` / `main` 全部通过。
- **2.8（P 报告漏项，本轮实证发现）pyqt5-qt5 约束放行了无 Windows wheel 的版本**：PyQt5 5.15.11 的 win_amd64 wheel 对 PyQt5-Qt5 是**无 marker 强依赖**，而 [5.15.2,5.16.0) 内唯一有 win_amd64 wheel 的是 **5.15.2**（PyPI 实证：5.15.3~5.15.10 无任何文件，5.15.11+ 仅 macOS wheel）。旧约束 `<5.15.14` + 旧 lock 锁 5.15.13 → **所有 Windows 机器 `uv sync` 必败**（作者不走 uv 故从未暴露，P1 报告只测了 pip wheel 没测 uv sync）。改 `>=5.15.2,<5.15.3`，与用户本机 5.15.2 对齐，重锁后 uv sync 通过。
- **P4 启动期写盘即死**（main.py、core/logger.py）：startup_log/crash_log 四处裸 open 全部 try + %TEMP% 降级；logger 日志目录 mkdir 失败降级 %TEMP%/GunnerSight/logs 并记一条"日志去哪了"的日志；frozen 崩溃时 `MessageBoxW` 弹窗（发布版无控制台，否则用户看到的就是"双击什么都没发生"）。
- **P5 数据目录只读即丢**（core/config/base.py）：启动可写性探测（**真实写探针文件**，不信 os.access），决策链 便携（exe 同级 config）→ `%APPDATA%\GunnerSight\config`（首次降级把出厂 config.json 复制过去做种子，77 载具库不丢）→ `%TEMP%\GunnerSight\config`（保命，设置不持久）；`bbox_cache.json` 跟随同一决策（OverlayWindow 新增 `config_dir` 参数，不再自己拼 exe 同级路径）；信息页显示当前数据目录。`resources/` 不降级（只读位置读出厂资源无问题，受影响的仅"导入新图"）。
- **P6 回退覆盖原配置**（core/config/base.py）：损坏回退改为**先留痕再覆盖**——rename 到 `backups/` → 同目录改名 → 写恢复副本（配置目录 / %TEMP%）逐级降级；全部失败则原文件原地保留，启动路径绝不静默覆盖用户数据；回退后启动弹一次提示（`config.recovery_notices`，main.py 接线）。
- **P2 打包链未声明**（tools/build.bat、README.md、pyproject.toml）：build.bat 解释器自适应（有 uv 走 `uv run --with nuitka --with zstandard`，否则 `py`；作者机器无 uv，行为逐字不变）+ nuitka 预检人话错误 + APP_VER 兜底；README 构建章节写明两种方式与"首次构建需联网下载 MinGW C 编译器（约 100MB）"；pyproject 增 `[project.optional-dependencies] build`。
- **P10 出厂载具库**：用户拍板保留。README 已有明示（"77 套载具分划，开箱即用"）。顺带修正 P 报告里"79 个载具"的笔误——committed config 实证为 **77**（与 README 一致）。
- **新增测试**（12 个，tests/test_data_dir_fallback.py）：可写探测真/假、便携维持、APPDATA 降级+出厂种子、降级不覆盖用户已有数据、TEMP 保命、P6 三级留痕（backups / 同目录改名 / 全失败保原文件）、日志目录降级、信息页数据目录显示。
- **验证**：pytest 54 passed、py_compile 全过、audit_docs 29/29、`pip wheel .` 实证出包且内容正确、干净副本 `uv sync` + mss 10.2.0 import 实证。
- 遗留（待非作者机器验证）：Program Files 标准用户只读运行与设置持久化、从零构建、非 Windows 人话报错（P9 未做，连同 P3/P8/P11-P17 留批次 4）。

---

## 2026-10-24 批次 1：正确性必修十项（S2/S3/S4/S5/S7/M1/M3/M6/M9）

> 依据 docs/reviews/CODE_REVIEW_2026-10-24.md，执行 docs/reviews/FIX_PLAN_2026-10-24.md 批次 1。
> 版本号 V0.0140300177 → V0.0140300178；测试 29 → 42 passed（新增 13 个契约测试）。

- **S2/M7 配置保存并发**（core/config/base.py）：`_atomic_write` 纳入 `_save_lock`（序列化+落盘全程锁内）；tmp 名带线程标识 + finally 清理；防抖 Timer 引入 token，过期回调不再清掉新 Timer 的引用。修复前两条保存路径并发可把半截 JSON 换成正式配置。
- **S3 .gsv 导入**（core/vehicle_io.py）：manifest 目录条目/文件名路径穿越校验（越界拒绝且不落盘）；复制中途失败时在**复制的发生地**回滚。测试逼出的改进：仅在调用方预初始化 copied 只能挡 NameError，孤儿清理是空转（异常路径上赋值不发生）——导入必须是原子操作。
- **S4 资源库“复制路径”**（gui/tabs/resource_tab.py）：右键菜单复制分支补 `full_path` 定义，修复必崩。
- **S5 微调 tuner**（gui/tabs/angle_meter_tab.py）：断开逻辑从 `_init_engine`（对 None 空转的死代码）前移至 `_shutdown_engine`；修复禁用→启用后新旧 tuner 双调（注入翻倍）与每轮泄露。
- **S7 OverlayRenderer**（core/overlay.py、gui/main_window.py、main.py）：新增 `shutdown()` 断 5 个 StateMachine 信号；closeEvent 与 aboutToQuit 兜底均接线。
- **M1 refresh_min_max**（core/angle_meter.py）：仅 IDLE 状态更新 current_angle，测量中不再被拽回最小值。
- **M3 ctypes 签名**（core/win32_utils.py、core/angle_meter.py）：GetWindowLongW/SetWindowLongW/GetLastError/RegisterRawInputDevices/GetRawInputData 补 argtypes/restype（64 位安全；新旧约定已做四探测点逐位对比，行为一致；overlay_base 经共享 user32 实例间接受益）。
- **M6 ammo_wheel**（core/ammo_wheel_selector.py）：`start()/stop()` 的 `_enabled` 状态对称收口。
- **M9 放大镜抓屏线程**（core/magnifier.py）：`run()` 整体 try/finally 保证 `_cam.close()`，异常发 error 信号报出而非静默死亡；`_grab_loop` 抽出保持原循环体不动。
- **新增测试**（13 个）：test_config_save.py（锁内落盘契约 + 并发不损坏 + token 机制）、test_vehicle_io_import.py（穿越拒绝 + 复制失败报原始异常并回滚 + 正常对照）、test_angle_meter_minmax.py、test_overlay_shutdown.py、test_close_path.py（closeEvent 零异常 + tuner 断开探针 + 10 轮循环）。
- **验证**：pytest 42 passed、py_compile 全过、audit_docs 29/29、离屏真实启动冒烟无异常（超时终止）。
- 遗留（待用户手动验证）：S4 复制路径、S5 微调单次注入——需真实 GUI/热键操作，按项目测试边界先例不自动化。

---

## 2026-10-24 AGENTS.md 保守档手术：切除故事与劝诫修辞

> 用户批准（保守档，过几天亲自复审）。动因：文件随历代 agent 增改脱离定位——
> 禁故事却写故事、"三条铁律"实为四条、长度违背"短到能记住"；读者是 agent，
> 文体却像写给人类同事。

7 处替换（CRLF 字节级，逐处断言，186 → 182 行）：

- 开头定位：删伪目标"短到能记住"，改为"只放判据和动作，不放故事"+ 指针到
  HANDOVER/CHANGE_LOG（从根上消解自相矛盾，标准从长度改为信噪比）
- §0.4 删劝诫句"一次计划评审比三次返工便宜"
- §1 标题"三条铁律" → "铁律"（实际四条）
- §2.2 删符号真事（删懒加载属性漏 overview_tab，含情节数字）压为"手写必漏"
+ 正确姿势单行；判据与冒烟要求不动
- §3 重排条目的自述故事（"我先只加了守恒断言……"）压为一句判据
- §5 文档腐烂事故压为一句 + 指针 CHANGE_LOG「2026-10-08 SSOT 改造」
- G1 括注"mss 事件"压为"（先例：lock 与实跑版本脱节）"

规则内容零删减——只切文体。版本号未 +1。

---

## 2026-10-24 G3 立项：发布前验收矩阵抄入 HANDOVER §十

> 来源：`docs/reviews/PORTABILITY_REVIEW_2026-10-24.md` 第七节。八项逐字保留，
> 第 7 项按 `my_beloved` 署名决定改写。当前 P1/P2/P4/P5/P6/P7 未修，矩阵作为
> 批次 2 修完后的回归关卡；中档脚本（pre_release_check.py）待批次 2 完成后
> 评估是否值得——现在写只会验一堆已知会挂的项。

---

## 2026-10-24 规矩总审计：测试红线退役与三项规则变动

> 依据：docs/reviews/RULES_AUDIT_2026-10-24.md（52 条规矩四分类过堂）

### 退役

- **AGENTS §4 测试红线（≤30 test function / <10s）正式退役**。用户明判：无红线可言，
  项目屎山期 117 passed。同步删除 audit_docs 检查⑦（其注释还停在 "<20"，连执行器
  自身都已漂移；检查数 30→29）。此后测试数量按需增长，不再设上限。

### 新增

- **AGENTS §3 依赖变更实测纪律**（G1）：改 pyproject/uv.lock 后必须实装 + 导入 +
  跑通相关功能；lock 版本与实际运行环境不符时在 HANDOVER 登记。
  来源：mss 事件（三份文档互洽、全部过审、合起来是假的）。
- **规则退役纪律**（G2，元规则）：退役规矩须明面记录于本日志，禁止默默遵守或
  默默违反。本次红线退役即首例。

### 修订

- AGENTS §3 换行符括注改述：CRLF/LF 混存（实测 39/24 约六四开），删去
  "config_manager.py 是 LF" 的失真举例。
- HANDOVER §十一 §2 空房子暂缓令补理由：2026-10-24 用户确认维持
  （硬编码即理论最优解 + 无改造意愿，原话含"懒"）。
- HANDOVER §十一・五 "不该动的"清单改述：从"别浪费额度"框架改为 agent 无关的
  "零收益、非零风险"。
- HANDOVER §十一・六 手册打磨标记完成：DS v4.1 flash 执行，用户确认收尾。

### 决定

- AGENTS.md 永久不进仓库（含用户审美取向，只用于约束自己）；不制作脱敏公开版。
- 版本号未 +1（纯文档/工具变更，AGENTS §6）。

---

## 2026-10-24 工程整理：.workbuddy 隔离与打包前自动备份

### 改动

- .gitignore 增加 .workbuddy/：Agent 工作区数据（项目记忆）仅存本机，不进版本控制。该目录从未被 git 跟踪（git ls-files 为空），此前只是未被忽略，以 ?? 形式暴露在 git status
- backups/GunnerSight_src_20261024_154439/（用户备份）中误扫入的 .workbuddy/ 已剔除（497 → 496 文件，源码部分未动）
- tools/build.bat 增加打包前自动备份：robocopy . backups\auto_before_build /MIR，排除 .git dist backups .workbuddy __pycache__ .pytest_cache .ruff_cache——落实 docs/HANDOVER.md"每次打包前覆盖、不增殖"约定（此前该约定无任何脚本承载，auto_before_build 一直停留在 10-18 的整理前结构）
- 已手动刷新一次 auto_before_build（robocopy 退出码 3=复制+清陈旧，485 文件，违禁目录检查为空）
- 清理源码树 __pycache__ 与 .pytest_cache（解释器字节码缓存，验证命令所产生，随时可再生）

### 未做

- 版本号未 +1：无应用源码变更（AGENTS §6）

---

## 2026-10-24 仓库整理：文档与脚本归类（docs/ 与 tools/）

### 改动

- 根目录只保留 AGENTS.md、README.md、USER_GUIDE.md、LICENSE、main.py、pyproject.toml、uv.lock、.gitignore；LICENSE 按开源生态惯例留根目录（GitHub 自动识别，build.bat 的 --include-data-files 也依赖该路径）
- 文档归类 docs/：HANDOVER.md、CHANGE_LOG.md、GUI_INVENTORY.md、MANUAL_OUTLINE.md、CREDITS.md、REAL_OVERLAY_RESEARCH.md
- 审查产物归类 docs/reviews/：CODE_REVIEW_2026-10-24.md、PORTABILITY_REVIEW_2026-10-24.md、FIX_PLAN_2026-10-24.md（三者互引为同目录相对名，仍有效）
- build.bat 移到 tools/build.bat：开头 cd /d "%~dp0.." 自行回到仓库根目录，任意位置双击或命令行调用均可；图标参数改 resources/app_icon.ico，CREDITS 参数改 docs/CREDITS.md=CREDITS.md（包内文件名不变）
- app_icon.ico：根目录副本与 resources/app_icon.ico 逐字节相同（md5 一致），git rm 去重，图标唯一位置为 resources/app_icon.ico
- edit_demo.py（一次性演示脚本，含本机绝对路径）移到 tools/，并加入 .gitignore 仅本机使用
- .gitignore 增加 frames/（帧图实验产物）
- 删除根目录 startup_log.txt（空文件、运行时产物、gitignore 已覆盖，启动时自动重建）
- 引用同步更新：AGENTS.md、README.md、docs/HANDOVER.md（头部/一・五表/第七节目录树/第十节）、tools/audit_docs.py、tools/export_gui_facts.py、tools/build.bat、docs/reviews/ 三份报告（含互相引用的行号）

### 有意保持不变的引用

- CHANGE_LOG 历史条目中的 build.bat / CREDITS.md 等名称：时间线记录当时动作，不回改历史
- docs/HANDOVER.md 第十二节 BOM 条目里的 HANDOVER.md：2026-10-13 历史笔记，同上
- main.py get_app_icon_path()：根目录两个查找分支变为无害空转，resources 分支照旧命中，启动路径零改动
- gui/tabs/info_tab.py 的"详见 CREDITS.md"文案：面向发布版用户（CREDITS.md 随包位于 exe 同级），不是仓库内路径引用
- MANUAL_OUTLINE.md 内对 GUI_INVENTORY.md 的引用：同迁入 docs/，同目录相对引用仍有效

### 未做

- 版本号未 +1：本次无 core/gui/main.py 应用源码变更（AGENTS §6 文档/测试不算；tools 与 build.bat 属开发工具链）

---

## 2026-10-20 文档：cfg 兼容性条款更新

- HANDOVER §配置：从"不存在配置迁移/向后兼容，软件从未发布"改为"配置必须向后兼容，软件已发布"
- 原因：2026-10-18 软件已开源发布，用户手上有旧 cfg
- 规则：加字段不需要迁移（默认值兜底），删字段或改语义需标 breaking change 并说明影响

---

## 2026-10-20 适配设置页：适配逻辑下拉框独立于模式

### 改动

- `adapt_tab.py`：把 sx/sy 的"增加/拉伸"下拉框从 custom_widget 移到独立行，预设和自定义模式下均可用
- 之前：预设模式下拉框被禁用，想换拉伸必须切自定义手填 sx/sy
- 现在：预设模式下直接切适配逻辑，数值仍由档位+宽高比自动计算
- cfg 无变化，`sx_adapt_mode`/`sy_adapt_mode` 本就是独立字段

---

## 2026-10-20 用户手册第二轮错误修正 + git 历史清理

### USER_GUIDE.md 错误修正（7 处）

1. 删"全局组合键前缀 Ctrl"（1-5 和附录 C 两处）——代码里无此概念，大 agent 写手册时编造
2. 暂离描述从"两套独立状态"改为"移交退出权"——按另一个暂离键会转移退出权，再按新键退出
3. 弹种图片从"替换分划"改为"叠加层之一，与倍率图多层叠加"
4. 倍率添加从"输入名称 1x/4x/8x"改为"直接添加，自动命名第 N 档"——GUI 无输入名称对话框
5. 载具图片从"仅用于列表识别"改为"可作为叠加层显示，与弹种/倍率图多层叠加"
6. 比例尺从"页面上填写数值"改为"热键循环切换四档：33/100/300/900m"

### 代码有但 GUI 未开放的功能

- 倍率重命名：`update_magnification(label=)` 接口存在，cfg 手动改 label 仍生效，GUI 无入口。保留不砍。

### git 历史重写

- 删除 AGENTS.md、docs/ 全部、_tmp 临时脚本、version_info.txt、GunnerSight.spec
- 替换全部历史中的本地用户路径
- force push 覆盖远程

---

## 2026-10-18 数值范围统一 + 角度仪 overlay 语义变更 + 手册错误修正

### 准星面板载具列表拉伸修复

根因：`overview_tab._build_ui` 末尾 `layout.addStretch()` 吃掉所有剩余空间，载具组 stretch 链全没传 1。修复 5 处联动（含通用组件 `widgets.py::VehicleFilterWidget`），载具配置页中栏列表同样受益。

### 数值范围统一：准星/独立偏移 ±500 → ±2000

- `overview_tab.py`：全局偏移 LinkedSpinSlider (-500,500) → (-2000,2000)
- `vehicle_config_tab.py`：独立偏移 QSpinBox (-500,500) → (-2000,2000)
- 原因：4K 屏 ±500 不够用

### 角度仪 overlay 语义变更（breaking change）

- 从屏幕绝对坐标（0~9999，左上角原点）改为相对屏幕中心偏移（±2000）
- `_show_overlay` / `_on_overlay_pos_changed` 改为 `move(center.x()+ox, center.y()+oy)`
- 默认位置从 (100,100) 改为屏幕中心 (0,0 偏移)
- 影响：已有用户 config 里存的绝对坐标值会被解释为偏移量，位置会变。无自动迁移。

### 用户手册错误修正（USER_GUIDE.md）

1. 反色：从"切换式"改为"按住式"（config 里 trigger='hold'，按下松开各触发一次 toggle）
2. 出厂预设：从"LAV-6 / SMK"改为"AAA 示例载具 / AP"（与 current_state 一致）
3. 放大镜预设：从"不会跨重启保存"改为"会跨重启保存"（config 里 current_preset 非空）
4. 分辨率挡位：从"出厂预配 1K"改为"点识别当前屏后自动匹配"
5. 配置迁移：从"不做配置迁移"改为"只补全新字段默认值，不做版本间格式转换"

### 版本

V0.0140300174 → V0.0140300175

### DEDICATION 纪念（三层）

- 源码：`info_tab.py` 加 `DEDICATION = "Dedicated to Xiaocheng"`，信息页版本号下面一行灰色小字
- exe 属性：`build.bat` 加 `--copyright="Copyright © 2026 [403 FORBIDDEN]. Dedicated to Xiaocheng."`，Windows 文件属性→详细信息可见
- cfg：已有 `my_beloved: "Xiaocheng"` 受保护字段（base.py `_PROTECTED_CONFIG_KEYS`）

### 素材版权声明（无敌大甲）

- 新增 `CREDITS.md`：通用 blanket statement，覆盖所有素材（版权归原作者、非商业用途、48小时下架、免责担保）
- `README.md` 加"素材版权声明"节
- `info_tab.py` 加一行短声明

### build.bat 改进

- 转 UTF-8 with BOM + CRLF（cmd.exe 才能正确解析 © 字符）
- 动态读取版本号：`for /f` 从 `info_tab.APP_VERSION` 转换为 Windows 4段格式（V0.0140300177 → 0.14.3.177）
- 加 `--product-version`（Nuitka 要求提供 copyright 时必须同时提供版本号）
- 加 `--include-data-files=CREDITS.md=CREDITS.md`（打进发布包）
- 踩坑：`--windows-legal-copyright` 不是有效参数，正确的是 `--copyright`

### 版本

V0.0140300175 → V0.0140300177

### 打包 V0.0140300177

备份 → py_compile + pytest 29 passed → build.bat（Nuitka 4.2.1，zig 后端）→ robocopy /MIR 覆盖桌面版。exe 版权属性验证通过，CREDITS.md 已进包。

---

## 2026-10-18 滚轮边界 bug + GitHub 开源 + my_beloved 保护 + 手册文风讨论

### 滚轮切弹种桌面焦点边界 bug（已闭环，非代码 bug）

**现象**：鼠标焦点在 Windows 桌面时滚轮无法触发弹种预选，其他窗口正常。

**排查**：加临时日志确认——`fg=Notepad` / `fg=Qt5152QWindowIcon`（软件自身）时 `[MouseHook] WHEEL` 正常 emit 且 `_on_wheel` 正常响应；桌面前台时段底层钩子零条日志。

**结论**：WH_MOUSE_LL 低级钩子在前台为桌面（Progman/WorkerW）时收不到 WM_MOUSEWHEEL，Windows 系统层行为，代码层无解。已记入 HANDOVER §十三。

**教训**：项目用 `from core.logger import logger`（loguru），不是标准库 `logging`。第一次加日志误用 logging 导致 NameError。

### 打包 V0.0140300174

清理临时日志改了 .py，按 AGENTS §6 升版本。单箭头流程：备份 → py_compile + pytest 29 passed + audit_docs 30/30 → build.bat（Nuitka）→ robocopy /MIR 覆盖桌面版。

### 项目安全检查（开源前）

- 凭据扫描：全项目 grep api_key/secret/token/password/bearer/sk- 等，0 匹配
- 依赖：pyproject.toml 仅 5 个（PyQt5、Pillow、keyboard、loguru、mss），全本地库
- 网络请求：0 匹配 requests/urllib/socket/websocket/QNetworkAccessManager。两处 URL（squadcalc.app、squad-armor.com）通过 QDesktopServices.openUrl() 调系统浏览器，用户主动点击
- 打包产物 464 文件，无 .pdb/.env/.key/.pem
- 结果：PASS 7 / UNKNOWN 2（Git 历史扫描当时无 git CLI；干净环境启动未实测）/ FAIL 0

### Git 安装与 GitHub 开源

- winget 安装 Git.Git 2.55.0.windows.5
- 项目已有 .git（从 V0.0140300054 起完整历史，最新提交 9860d90），V0.0140300086 后大规模重构未提交
- 配置 git 身份：user.name=403-FORBIDDEN-38, user.email=3117023693@qq.com, core.autocrlf=false
- 创建/更新 .gitignore（排除 dist/、backups/、logs/、构建日志、__pycache__、AGENTS.md 等；config/config.json 不排除——是项目核心数据应公开）
- 基线提交 c856842：566 files changed, +25474 / -7213
- 推送到 https://github.com/403-FORBIDDEN-38/Gunner-Sight.git（master 分支）
- 随后清理仓库：git rm --cached AGENTS.md（本地保留，加 .gitignore）、删 airsoft 版 USER_GUIDE.md、git mv USER_GUIDE_formal.md → USER_GUIDE.md，force push 覆盖

### my_beloved 受保护配置字段

用户在 cfg 骨架 `_get_minimal_skeleton()` 加了 `"my_beloved": "Xiaocheng"`，要求加保护防止被误删。

**第一次实现的 bug**：把兜底逻辑写进递归的 `_merge_config()`，导致递归到 vehicles 子字典时也执行 `loaded.setdefault("my_beloved", ...)`，给 vehicles 字典加了 my_beloved 键（值是字符串）。`get_vehicle_names_filtered` 遍历到这个键 → `get_vehicle_tags` 调 `.get()` 抛 `AttributeError: 'str' object has no attribute 'get'` → VehicleConfigTab 创建失败。

**修法**：受保护兜底从 `_merge_config` 移到 `load_config` 顶层（合并完成后执行一次）。模块级常量 `_PROTECTED_CONFIG_KEYS = {"my_beloved": "Xiaocheng"}`（base.py）。config.json 磁盘未被污染（污染只在内存），29 passed。

### 用户手册文风讨论（进行中，未动手）

- 参考 KAC 真铁手册中文译制版（KAC_SR25_真铁手册_中文译制版.docx）
- 当前 USER_GUIDE.md 是真铁版（722 行，LF），有真铁的壳但缺魂
- 差距分析（6 维）：安全语气偏软、缺工作原理章节、操作步骤是叙述性散文而非编号 SOP、缺功能检查环节、排错是散文而非表格矩阵、有讨好语言
- 打磨方向（用户已确认方向，待执行）：①安全章硬化 ②加工作原理节（含已知边界）③核心操作改编号 SOP ④排错改表格矩阵 ⑤删讨好语言 ⑥PMCS 表格化
- 用户偏好：通读一遍过、不回看不重看、去人化去误差的纪律性
- 详见 HANDOVER §十一・六

---

## 2026-10-17 角度仪第三轮 + 准星常闭修复 + 定角装填修复

### OverlayRenderer.hide()/show() 不再改 state

**根因**：`OverlayRenderer.hide()` 不只是隐藏窗口，还调 `state.set_overlay_visible(False)`。关闭软件时 `closeEvent` 里调 `overlay.hide()` → state 被改成 False → `save_config()` 保存 False → 下次启动准星常闭。

**修法**：`hide()`/`show()` 只控制窗口显隐（`set_visible`），不改 state。state 由用户操作（按钮/热键）通过 `state.set_overlay_visible()` 改变，再通过 `overlay_toggled` 信号控制窗口。

**影响**：所有调 `overlay.hide()` 的地方（关闭、tab shutdown、角度仪停止使用等）不再改变用户的准星偏好。

### 角度仪微调：短按延迟 + 长按连发

**根因**：使用模式下 `on_pressed` 立刻走一格 + 60ms 后连发，想精确点一次 0.1° 很难（手指停留超过 60ms 就变成连发）。

**修法**：
- 短按（<400ms 松开）：松开时走一格
- 长按（≥400ms）：400ms 时走第一格，之后每 50ms 连发
- 校准时保持原逻辑（立刻走一格，1s 后连发）
- 滚轮直接走一格，不起定时器

### 术语"归零"→"定角装填"

UI 文本和注释全部更名（复选框"启用定角装填"、热键"定角装填热键"、日志"[角度仪] 定角装填"）。config 键名 `auto_reset`、代码变量/函数/信号名全部保留（牵连 12 处，不值得改）。

### 定角装填启用状态不随 profile 切换

**根因**：`_load_profile_params` 切换 profile 时漏了恢复 `auto_reset_check` 的勾选状态和 `hk_reset` 的启用状态。

**修法**：加 4 行恢复代码（blockSignals 防递归）。

### 排版

- 校准设置：灵敏度挪到第一行（精度方案 | 校准状态 | 灵敏度），开始校准按钮单独一行全宽
- 角度仪配置：2 行（最低角 | 最高角 | 启用定角装填 | 提示 | 热键单独一行）

---

## 2026-10-16 B1 清理路径逐项隔离 + 日志门控 + 测试红线

### B1：清理路径逐项隔离

**根因**：AGENTS §2.1「中断即泄漏」——清理方法里任何一行抛异常，后面的清理都不执行。3 处 tab 的关闭路径（角度仪 / 放大镜 / 建队宏）是裸调，第 1 个 `.stop()` 抛异常 → 后面的 `raw.close()`（mss 句柄）永不执行。

**修法**：
- 抽 `core/cleanup.py::safe_call(name, fn)`（5 行纯函数：try/except + logger.warning）
- 3 处 tab 关闭路径改用 safe_call 逐项隔离
- 角度仪 `_shutdown_engine` 顺序重排：`raw.close`（OS 级 mss 句柄）提到最前——越贵的资源越先释放，不依赖异常发生就产生收益
- `_GrabWorker.stop` 的 wait 超时加 warning（**只报告不恢复**：线程真没退出时 mss 句柄依然泄漏，QThread 无安全 terminate）
- `_FineTuner.stop` 不改（单动作，隔离无意义）

**测试边界**：mock 测的是"前一步失败后一步仍执行"（代码路径），不是"OS 资源真的释放了"（靠代码审查）。

### 日志门控

文件 sink 级别从 `INFO（GS_DEBUG 升 DEBUG）` 改成**永远 DEBUG**；控制台 sink 保持 `WARNING（GS_DEBUG 升 DEBUG）`。排错时不需要先设环境变量。

### 测试红线

AGENTS §4 测试红线 20 → 30。原值是直觉值，B1 后契约测试达 29 且都非实现细节测试，据实调整。

---

## 2026-10-14 SSOT 残留 S1/S2/S3 全部修复

### S1：载具页 getter 回落 state

**根因**：`vehicle_config_tab._get_selected_vehicle/_ammo` 从 `list.currentItem()` 取 UserRole，列表空时返回 None。筛选无结果（如 PMC 空标签）时列表空，但 state 保持原值——详情区空白。

**修法**：两个 getter 列表无选中时回落到 `state.current_vehicle` / `state.current_ammo_type`。语义从"读列表"变成"读 state，列表空时回落"。45 处调用点未动。

**设计取舍**：筛选只过滤列表，不改变"当前载具"。筛选无结果时详情区显示 state 的载具（虽然列表里看不到它）。

### S2：hotkey_manager 绕过 state

**根因**：`hotkey_manager.py` 两处 `self.config.get_current_state().get("vehicle")` 绕过 StateMachine 直读 config。

**修法**：改成 `self.state.current_vehicle`。hotkey_manager 已持有 self.state，两行改动。

### S3：放大镜当前 preset 无持有者

**根因**：`config.magnifier` 只有 get/set_magnifier_presets（dict 操作），没有 current_preset 持有者。"当前是哪个 preset"完全靠 UI 列表选中，重启后选中态丢失。

**修法**：
- `config.magnifier` 加 `current_preset` 键 + `get/set_current_magnifier_preset`（默认 `""`）
- `magnifier_tab._on_preset_select` 加幂等短路（值没变不写 config，避免高频搜索触发 request_save）
- `_refresh_preset_list` 改选中恢复逻辑：从 config 读 current，在结果里恢复；不在且非空选第 0 行；空不选
- 删除 / 重命名 preset 时同步处理 current_preset（参照角度仪 `current_profile`）
- 删掉 `refresh()` 里手动调的 `_on_preset_select`（双调冗余）

---

## 2026-10-11 屏幕适配公式修正 + 倍率详情切弹种不更新

### 屏幕适配公式修正

**根因**：`_adapt_factors()` 里用的是 `self._resource_w` / `self._resource_h`（硬编码 2560/1440），而不是 `self._display_w` / `self._display_h`（用户设置的分辨率挡位）。`set_display_resolution()` 设的是 `_display_w` / `_display_h`，但 `_adapt_factors()` 读的是 `_resource_w` / `_resource_h`。所以切换分辨率挡位时，sx/sy 不跟着变。

**第一次修反了方向**：改成 `屏幕宽 / 挡位宽`，用户纠正后改成 `挡位 / 基准`。

**最终公式**：
```python
sx = (self._display_w or self._resource_w) / self._resource_w
sy = (self._display_h or self._resource_h) / self._resource_h
```
- 2K 挡位 = 1.0（不缩放）
- 1K 挡位 = 0.75
- 4K 挡位 = 1.5
- 删掉了 `cur_w` / `cur_h`（屏幕物理宽），纯按「挡位 / 基准」算

### 倍率详情切弹种不更新

**根因**：`on_external_ammo_changed` 里只调了 `_refresh_mag_list()`，没调 `_update_mag_detail()`。倍率继承时索引不变，`_on_mag_user_selected` 里 `idx == state.current_magnification_index` 直接 return，不发信号，所以倍率详情的三个勾选框（独立偏移/叠加载具图片/叠加弹种图片）停留在旧弹种的值。

**修法**：在 `on_external_ammo_changed` 末尾加 `self._update_mag_detail()`。

**双调分析**：倍率索引回退时会双调，但 `_update_mag_detail()` 幂等（读 config + 设 checkbox），无害。

---

## 2026-10-08 SSOT 改造

### 起因

发现两个 bug：
- **bug A**：新增载具时，只有"载具列表"选中了新载具，但弹种列表、倍率列表、状态机、其他 UI 都还停留在旧载具的数据
- **bug B**：删除当前载具时，载具列表删除了，但 state.current_vehicle 还指向被删的载具，所有 UI 也还显示被删载具的信息

排查这两个 bug 时，发现项目里"当前 X"的语义在多处独立存储、靠信号拼凑同步。
归纳出 12 条伪 SSOT。

### 改动

（逐条列，带位置）

* **config 层**：业务方法不再碰 current_state，副作用上移到 state_machine
* **state_machine**：8 个业务方法包装 + 三个 setter 私有化
* **4 列表（vehicle/ammo/mag/quick_ammo_combo）**：选中态由 state 驱动
* **删载具**：清 angle_meter.profiles[*].linked_vehicles
* **删标签**：加 tags_changed 信号，各 tab 的 tag_filter 响应
* **删 profile**：tracker 改 provider 化（_calibration / _min_max 不持缓存）
* **墓碑清理**：angle_meter.current_vehicle / vehicles 加载时 pop
* **角度仪热键重建**：_init_engine 开头无条件 disconnect
* **标定测距暂离同步**：main_window 里同步 ammo_wheel.is_suspended

### 回退与翻车（重要）

* **4 列表改造中，"标签列表空"**：_refresh_tag_list 在新 init 路径里丢了
* **"页面加载失败"**：_pending_vf_signals 从二元组改一元组后没 grep 解包点
* **"标定测距 tab 崩"**：wheel.is_suspended 是 @property，误加括号调用
→ 定位困难，因为 Qt 吞信号槽异常，靠 try/except 包住才拿到 traceback

### 已知问题（不修）

**只留指针**：这两条已登记在 HANDOVER 十三节（同一信息只该有一处）。




---

## 2026-10-08（V155 → V165）

### 配色体系重构

* **删 `ACCENT` 常量**：`colors.py` 不再有 `ACCENT = "#8B6F47"`。强调色出厂默认挪到 config 默认模板 `global_settings.accent_dark/light`（中性值：深主题 `#EBEBEC`、浅主题 `#1D1D1F`）。运行时走 `config.get_accent(theme)`
* **状态色收敛**：`ANGLE_IDLE/ACTIVE/PAUSED/CALIBRATING` 全部改为 `DISTANCE_*` 的别名（灰/绿/橙/橙）；`CAL_HINT` = `DISTANCE_CALIBRATING`
* **主题调色板加 `btn`/`base`**：按钮走 `btn`、输入框走 `base`，以 bg 为基准 ±3 明度（DARK: btn `#202022`/base `#1A1A1C`；LIGHT: btn `#EEEEEF`/base `#E8E8E9`）
* **悬浮窗配色自成体系**：底框 `OVERLAY_BOX_RGB=(20,20,20)` + `OVERLAY_BOX_BG_ALPHA=51`（20%）；文字 `OVERLAY_TEXT="#EBEBEC"` 白字；窗口级 `setWindowOpacity` 全取消
* **滚轮强调项文字跟主题**：横幅/高亮项文字走 `on_accent_text`（与主界面一致），不再固定白

### 悬浮窗三个模块

* **滚轮**：倍率挂件只显示当前倍率（"下一倍率"砍掉）；`FullOverlay(accent)` 构造收 accent；文字全白
* **标定测距**：比例尺、提示文字白字；`set_active()` 退化为兼容空壳
* **角度仪**：悬浮窗底框从"跟主题"改为统一 `OVERLAY_BOX_RGB`；角度示数与主 tab SSOT——正常白、暂离/标定中橙

### 滚轮位置 XY

* `config.get_wheel_offset()` / `set_wheel_offset(x,y)`：`global_settings.wheel_offset_x/y`
* 准星面板加"滚轮位置"组（±2000px）；`AmmoWheelSelector.reposition()`

### 导航调整

* "相关"组顺序：**适配设置 → 资源库 → 信息**（原"资源"改名"相关"，"屏幕适配"改名"适配设置"）

### 修过的 bug

* **角度仪暂离对不上**：`set_suspended()` 用 `getattr(self.tracker, '_paused', False)` 判断暂停态，但 tracker 没有 `_paused` 字段（状态机用 `self.state`）。改成 `tracker.state == STATE_PAUSED`
* **准星面板 tab 创建失败**：`_connect_crosshair_params()` 在滚轮控件创建之前调用。控件创建顺序挪正
* **按钮没变化**：QSS `QPushButton` 没写 `background-color`，Qt 应用 QSS 后背景透明不走 `QPalette.Button`。已补 `background-color: {btn}`

### 回退过的方向

* 悬浮窗文字色曾要求"随当前主题"（上一轮），本轮又要求"固定白字"——以本轮为准
* `get_overlay_text()` / `get_overlay_text_dim()` / `get_overlay_text_suspend()` 加了又删

