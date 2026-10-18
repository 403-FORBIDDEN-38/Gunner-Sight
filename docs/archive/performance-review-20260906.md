# GunnerSight 性能审查报告

## 审查范围
启动流程、关闭流程、核心模块初始化、UI创建、资源加载

## 审查方法
静态代码分析（main.py / main_window.py / config_manager.py / hotkey_manager.py / overlay.py），结合模块依赖关系和已知开销特征

---

## 一、启动性能瓶颈

### 瓶颈1：字体加载阻塞窗口显示（高优先级）

**位置**：`main.py` `load_custom_fonts(app)`，第202行，在 `window.show()` 之前同步执行

**问题**：
- 加载两个字体文件：`NORWESTER.ttf`（英文）+ `SYHT_BOLD.otf`（中文思源黑体Bold）
- 中文字体文件通常 5~15MB，`QFontDatabase.addApplicationFont` 需要解析整个字体文件
- 预计耗时 100~500ms，直接阻塞窗口出现
- 字体加载在窗口显示前，用户看到的是"启动慢"

**优化方案**：
- 把 `load_custom_fonts(app)` 移到 `window.show()` 之后，用 `QTimer.singleShot(0, lambda: load_custom_fonts(app))` 延迟加载
- 窗口先用系统默认字体显示，字体加载完成后自动切换
- 用户感知：窗口立即出现，字体在几百毫秒后切换（几乎不可察觉）

### 瓶颈2：ConfigManager 每次启动都执行7个迁移函数（高优先级）

**位置**：`config_manager.py` `__init__` 第83-96行

**问题**：
- 每次启动无条件执行7个迁移函数：`_migrate_crosshair_paths` / `_migrate_ammo_hotkeys` / `_migrate_xcj_to_rangefinder` / `_migrate_angle_meter_hotkeys` / `_migrate_angle_meter_calibration` / `_migrate_ammo_hotkeys_vehicle_scope`
- 没有配置版本号判断，即使配置已经是最新格式，仍然每次遍历所有数据
- `_migrate_crosshair_paths` 中对每个准星图片调用 `os.path.exists`，如果有很多载具/弹种/倍率，IO 开销累积
- 7次独立遍历，每次都检查所有配置项，累积开销

**优化方案**：
- ConfigManager 增加 `config_version` 字段（如 `"config_version": 3`）
- 每个迁移函数对应一个版本号，只在当前版本 < 目标版本时执行
- 迁移完成后更新版本号
- 7个迁移函数合并为一次遍历（在同一个循环中检查所有迁移条件），减少重复遍历
- `_migrate_crosshair_paths` 的文件存在性检查可以缓存结果或延迟到实际使用时

### 瓶颈3：9个Tab启动时一次性创建（中优先级）

**位置**：`main_window.py` `_create_ui` 第266-276行

**问题**：
- 启动时一次性创建全部9个tab：概览、载具配置、热键、信息数显、角度仪、建队宏、资源库、信息
- 每个tab的 `__init__` 创建大量UI控件、信号连接、数据加载
- `vehicle_config_tab` 和 `angle_meter_tab` 控件最多（各有数百个控件）
- 用户可能很少用建队宏、资源库等tab，但启动时仍然创建
- 预计总耗时 200~500ms（取决于控件数量）

**优化方案**：
- Tab懒加载：启动时只创建第一页（概览页），其他tab用占位符
- 用户第一次点击某个tab时才创建该tab的真实UI
- 实现方式：`QStackedWidget` 中先放 `QLabel("加载中...")`，`nav_list.currentRowChanged` 时检查是否已创建，未创建则创建并替换
- 预计启动时间减少 150~400ms

### 瓶颈4：HotkeyManager.initialize 全局键盘钩子（中优先级）

**位置**：`hotkey_manager.py` `initialize()` 第83-87行，`main.py` 第222行延迟调用

**问题**：
- 虽然用 `QTimer.singleShot(0, hotkey.initialize)` 延迟到窗口显示后，但用户启动后热键不可用的时间变长
- `keyboard.hook()` 安装全局键盘钩子，需要管理员权限，预计 200~500ms
- `_register_all_hotkeys` 遍历所有热键配置逐个注册
- 模块顶部第16行已经 `import keyboard`，`initialize()` 第86行又 `import keyboard`（重复，no-op但说明代码混乱）

**优化方案**：
- 短期：保持延迟初始化，但在窗口显示后立即执行（已经是这样），可接受
- 长期：考虑用 `ctypes.windll.user32.RegisterHotKey` 直接注册Windows热键，比keyboard库轻量（不需要全局钩子，只注册指定按键）
- 清理重复import

### 瓶颈5：OverlayRenderer 初始化（低优先级）

**位置**：`overlay.py` `OverlayRenderer.__init__` 第252行

**问题**：
- 启动时创建overlay透明窗口，即使准星未启用
- 设置窗口穿透样式（`apply_click_through`），`QTimer.singleShot` 延迟应用
- 可能加载准星图片

**优化方案**：
- Overlay窗口延迟创建：用户启用准星时才创建窗口
- 启动时只初始化数据，不创建窗口
- 预计减少 50~100ms

---

## 二、关闭性能瓶颈

### 瓶颈1：热键注销重复操作（高优先级）

**位置**：`hotkey_manager.py` `_unregister_all_keyboard_hotkeys` 第103-115行

**问题**：
```python
if self._keyboard_global_hook:
    keyboard.unhook(self._keyboard_global_hook)  # 先unhook单个
    self._keyboard_global_hook = None
keyboard.unhook_all()  # 再unhook_all（重复，unhook_all已经包含所有钩子）
```
- 先 `unhook` 单个全局钩子，再 `unhook_all`，后者已经包含前者
- `unhook_all` 遍历所有已注册钩子逐个注销，如果热键数量多，可能需要 100~300ms
- `MouseHook.release()` 可能也需要时间

**优化方案**：
- 直接 `keyboard.unhook_all()`，不需要先unhook单个
- 或者：只unhook单个全局钩子（因为所有热键都走这个全局钩子回调），不需要unhook_all
- 二选一，不要都做

### 瓶颈2：各Tab的shutdown可能等待（中优先级）

**位置**：`main_window.py` `closeEvent` 第438-441行

**问题**：
- 依次调用 `rangefinder_tab.shutdown()` / `angle_meter_tab.shutdown()` / `squad_macro_tab.shutdown()`
- 如果某个tab有定时器未停止、线程未退出，可能等待超时
- `angle_meter_tab.shutdown()` 需要停止RawInput、定时器、AngleTracker
- 串行执行，总时间是各tab shutdown时间之和

**优化方案**：
- 确保所有shutdown是幂等的、非阻塞的（不等待线程join，只设置退出标志）
- 可以并行触发shutdown（设置标志后立即返回），不需要等待完成
- RawInput注销可以延迟到进程退出时由系统自动清理

### 瓶颈3：QApplication.quit() 清理大量UI控件（中优先级）

**位置**：`main_window.py` `closeEvent` 第444行

**问题**：
- 9个tab的所有UI控件在 `QApplication.quit()` 时由Qt统一析构
- 控件数量多（可能上千个），析构需要时间
- 用户感知：窗口已经隐藏，但进程还在后台运行，任务管理器中还能看到

**优化方案**：
- `closeEvent` 中先 `self.tab_stack.deleteLater()` 删除所有tab，再 `QApplication.quit()`
- 主动删除控件比Qt自动析构更快
- 或者：设置 `Qt.WA_DeleteOnClose` 属性，关闭时自动删除

---

## 三、优化实施计划

### P0（立即实施，高收益低风险）

| 编号 | 优化项 | 预计收益 | 风险 |
|---|---|---|---|
| P0-1 | 字体加载延迟到窗口显示后 | 启动快100~500ms | 低（字体加载后自动切换，几乎不可察觉） |
| P0-2 | ConfigManager加配置版本号，迁移函数只在版本变化时执行 | 启动快50~200ms | 低（版本号逻辑简单） |
| P0-3 | 关闭时热键注销简化（直接unhook_all，不重复） | 关闭快50~200ms | 低 |

### P1（后续实施，中等收益）

| 编号 | 优化项 | 预计收益 | 风险 |
|---|---|---|---|
| P1-1 | Tab懒加载（第一次点击时创建） | 启动快150~400ms | 中（需要处理tab间信号依赖） |
| P1-2 | 7个迁移函数合并为一次遍历 | 启动快20~50ms | 低 |
| P1-3 | Overlay窗口延迟创建 | 启动快50~100ms | 中（需要处理启用/禁用逻辑） |
| P1-4 | 关闭前主动删除所有tab | 关闭快50~150ms | 低 |

### P2（长期优化，高复杂度）

| 编号 | 优化项 | 预计收益 | 风险 |
|---|---|---|---|
| P2-1 | 用ctypes RegisterHotKey替换keyboard库 | 启动快200~500ms，关闭快100~300ms | 高（需要重写热键系统，处理组合键、鼠标键等） |
| P2-2 | ResourceManager图片懒加载 | 启动快（取决于图片数量） | 中 |
| P2-3 | 关闭时非阻塞shutdown（只设标志不等待） | 关闭快（取决于线程数量） | 中（需要确保资源正确释放） |

---

## 四、验证方法

1. **启动时间测量**：在 `main.py` 各关键节点加 `time.time()` 打印，测量：
   - QApplication创建 → 字体加载 → ConfigManager → 各模块初始化 → MainWindow创建 → window.show → 热键初始化
   - 优化前后对比

2. **关闭时间测量**：在 `closeEvent` 各节点加 `time.time()` 打印，测量：
   - hide → 各tab shutdown → hotkey.shutdown → save_config → quit

3. **功能验证**：优化后确认所有功能正常（热键、准星、角度仪、载具配置等）

---

## 五、结论

当前启动延迟的主要原因是**字体加载阻塞**和**9个tab一次性创建**，关闭延迟的主要原因是**热键注销重复操作**和**Qt自动析构大量控件**。

P0三项优化（字体延迟、版本号、热键注销简化）风险低、收益明确，建议立即实施，预计启动快150~700ms，关闭快50~200ms。

P1的Tab懒加载收益最大（150~400ms），但需要处理tab间信号依赖，建议在P0完成后实施。
