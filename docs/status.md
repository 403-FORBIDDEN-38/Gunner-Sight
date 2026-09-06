# 项目状态

> 历史记录见 `docs/archive/`

## 当前版本

V0.0140300088（吉祥物模块集成后发布）

## 最近完成

### BUG-17：get_app_base_dir() 路径错误（2026-09-06）
- 根因：QUALITY-P2 config 拆分后 base.py 从 `core/` 移到 `core/config/`，`Path(__file__).parent.parent` 只到 `core/`，少一层
- 修复：`.parent.parent` → `.parent.parent.parent`
- 附带：修复过程中 PowerShell 编码损坏 base.py，已完全重写（445行41方法，保留所有逻辑）
- 验证：编译全过 / pytest 104 passed / UI冒烟通过，启动无字体报错

### 载具配置页优化（2026-09-06）
- FEATURE-6：切回载具页时恢复当前载具/弹种/倍率选中
- FEATURE-7：级联自动选中（标签→载具→弹种→倍率）
- FEATURE-8：新建后自动选中新项
- REFACTOR-3：删除倍率重命名，删除后自动补位无断层
- PERF-2：资源加载排查——懒加载+缓存策略已合理，无需重大优化

### 代码质量改进 QUALITY-P0~P3（2026-09-06）
- P0：静态扫描 0 ERROR/0 WARN/0 INFO（修 except:pass + 删未使用 import）
- P1：测试文件从 tools/ 移到 tests/，pytest 79→104
- P2：config_manager 拆分为 core/config/ 包（7个mixin，外部API不变）
- P3：rangefinder_tab UI 构建拆分为 8 个子方法（试点）

### 标定测距 + cfg 清理（2026-09-06）
- REFACTOR-4：热键功能名称去括号冗余（记录/测算/组合键）
- REFACTOR-5：cfg 从根源清理（save_config 有序输出 + 自动过滤旧格式 key/trigger）

### 吉祥物模块集成（2026-09-06）
- 独立调试后集成 GS，Q弹+音效+气泡+拖动
- 资源整合：mascot+fonts 移入 resources/assets/，ResourceManager 排除 assets/
- QTimer 性能优化：气泡隐藏时 stop 零开销
- 音效音量 0.225，气泡内容不重复上次文件
- V0.0140300088 已发布

## 验证状态

- 编译：全过
- pytest：104 passed
- UI冒烟：通过
- 静态扫描：0 ERROR / 0 WARN / 0 INFO
