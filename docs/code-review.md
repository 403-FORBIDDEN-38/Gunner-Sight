# 当前待办

> 已完成任务见 `docs/archive/code-review-archive-20260906.md`

---

## BUG-17：get_app_base_dir() 路径错误（P0）

**根因**：`core/config/base.py` 的 `get_app_base_dir()` 开发环境返回 `Path(__file__).parent.parent`，但 base.py 在 `core/config/` 下，上溯两层只到 `core/`，少了一层到项目根目录。这是 QUALITY-P2 config 拆分引入的回归。

**表现**：所有外置资源路径多了 `core/` 前缀，字体/配置/资源都读不到。日志显示 `[Main] Norwester 字体文件不存在`。

**修复**：`core/config/base.py` 第26行 `.parent.parent` → `.parent.parent.parent`

**验证**：启动日志无"字体文件不存在"报错，中文显示 Noto Sans SC Light 细体，配置正常读写。

**字体文件已就位**：`resources/assets/fonts/NORWESTER.ttf`（20KB）+ `NotoSansSC-Light.ttf`（10.6MB，静态 Light 字重）。main.py 加载逻辑已改好，只需修路径。

---

## T0-降险：base.py 重写后加强测试覆盖（P0）

**背景**：BUG-17 修复过程中 PowerShell 编码损坏 base.py，执行Agent完全重写了该文件（445行41方法）。重写版编译+测试+冒烟通过，但可能丢失原始版本的某些边界处理。需加强测试覆盖确认行为一致。

**任务**：
1. **旧配置迁移测试**：构造旧格式 cfg（含 key/trigger 热键、xcj 段、旧角度仪校准格式），验证 load_config 后所有迁移正确执行
2. **损坏配置恢复测试**：构造语法错误的 config.json，验证启动后自动备份为 .corrupt 并回退最小骨架
3. **空配置初始化测试**：删除 config.json 后启动，验证最小骨架正确生成、所有列表为空、程序正常运行
4. **保存有序+过滤冗余字段测试**：保存后验证 cfg 顶层键按固定顺序、热键无 key/trigger 旧字段
5. **防抖保存测试**：连续 request_save 10 次，验证只执行一次实际写入

**验证**：新增测试全部通过 + 原有 104 测试无回归

---

## FEATURE-6：载具页进入时恢复当前使用的载具/弹种/倍率选中

`vehicle_config_tab.py` 的 `showEvent` 中读取 state_machine 当前状态，依次选中标签→载具→弹种→倍率。注意在列表数据加载完成后执行。

---

## FEATURE-7：级联自动选中（标签→载具→弹种→倍率）

选中标签→载具列表自动选中第一辆→弹种自动选中第一个→倍率自动选中第一倍率。空列表不崩溃，用 blockSignals 防循环。

---

## FEATURE-8：新建载具/弹种/倍率时自动选中新项

新建后 `setCurrentRow` 选中新项（通常最后一行），触发级联。

---

## REFACTOR-3：删除倍率重命名 + 删除倍率时自动补位

- 删除倍率重命名按钮和方法（倍率名是自动序号，无意义）
- 倍率名称不持久化，UI 动态生成"倍率{idx+1}"，从根源消除断层
- 载具/弹种重命名保留

---

## PERF-2：资源加载性能优化

排查点：overlay 是否预加载所有准星图片（应只加载当前使用的）、资源库缓存上限是否合理、图片是否预缩放、切换时旧 QPixmap 是否释放。优先懒加载。

---

## QUALITY-P3：大tab拆分子组件（持续优化）

angle_meter_tab(772行)、rangefinder_tab(708行)、vehicle_config_tab(668行) 拆分为主tab + 子组件，单文件≤400行。
