# 审查-修复工作流

## 流程

1. 主 Agent 审查 → 写入 docs/code-review.md（唯一审查文档）
2. 执行 Agent 按 code-review.md 修复 → 每项修复对应一个 git commit
3. 执行 Agent 交付：修改文件清单 + commit hash + 测试运行结果
4. 主 Agent 复审：读 diff + 跑测试 + 手动验收核心功能
5. 通过则关闭该轮，不通过则回到第2步

## 沟通文件

- docs/code-review.md — 当前轮审查意见（唯一）
- docs/status.md — 当前项目状态（唯一）
- docs/archive/ — 历史轮次产物（只读，不再修改）

## 硬性要求

- 每次代码修改后必须运行现有测试套件
- 审查编号不写入代码注释，用 git commit message 追踪
- 交付必须包含测试运行结果，不允许只说"已修复"
