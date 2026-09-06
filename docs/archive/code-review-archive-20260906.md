# 已归档任务（2026-09-06 清理）

以下任务已完成，从 code-review.md 移除以保持一线文档精简。

---

## REFACTOR-2：资源目录整合（mascot + fonts 归入 assets/，资源库排除）✅

- 创建 `resources/assets/`，fonts/ 和 mascot/ 移入
- `ResourceManager.list_resources()` 排除 `assets/` 目录
- 所有引用路径更新

## PERF-1：吉祥物 QTimer 性能优化 ✅

- 用 `chat_bubble.visibility_changed` 信号控制 `_follow_timer` 启停
- 气泡隐藏时 QTimer 停止（零开销），显示时启动

## FEATURE-5：气泡内容抓取不重复上次文件 ✅

- `_last_content_file` 机制，连续点击不重复
- 单文件时不重试死循环

## CONFIG-1：音效音量再减半 ✅

- 0.45 → 0.225

## REFACTOR-4：标定测距热键功能名称去冗余 ✅

- "记录（标定）" → "记录"
- "测算（测距）" → "测算"
- "组合键（修饰）" → "组合键"

## REFACTOR-5：cfg 配置结构从根源清理 ✅

- `save_config` 构造有序 dict 按固定分区顺序输出
- 自动过滤旧格式 `key`/`trigger` 冗余字段
- 读取兼容旧格式，内存中迁移到 `key1`

## QUALITY-P0：静态扫描WARN修复 + 未使用import清理 ✅

- distance_meter.py:183 except Exception: pass 加日志
- 删除 widgets.py / test_config.py 未使用 import

## QUALITY-P1：测试文件位置修正（tools/ → tests/）✅

- tools/test_distance_meter_logic.py → tests/

## QUALITY-P2：config_manager.py 拆分 ✅（引入 BUG-17）

- 拆分为 core/config/ 包（base/vehicle/angle_meter/distance/squad_macro/mascot）
- 外部 API 不变
- **回归 bug**：`get_app_base_dir()` 路径上溯层数错误（见 code-review.md BUG-17）

## BUG-17（旧）：中文字体未生效 ✅（根因即路径错误）

- 从系统可变字体提取静态 Light 字体 `NotoSansSC-Light.ttf`（10.6MB）
- main.py 加载逻辑已改好
- 根因是 `get_app_base_dir()` 路径错误导致字体文件读不到（见 BUG-17）
