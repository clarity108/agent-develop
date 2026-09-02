# Standard Development Process

## Workflow

```
[1] Spec     → specs/001-feature.md        需求规格
[2] ADR      → docs/adr/0001-decision.md   架构决策
[3] Design   → 确认 seams（公开接口）        接口设计
[4] TDD      → 测试 Red → 实现 Green        编码
[5] Review   → 自检 + 代码审查               质量门禁
[6] CI       → pytest 全量通过               自动化验证
[7] Docs     → 更新 api_spec / ADR          文档同步
```

## 每步要求

### [1] Spec — 需求规格
- 写到 `specs/{编号}-{功能}.md`
- 格式：用户故事 + 验收标准
- 示例：

```
## 用户故事
作为开发者，我希望 agent 能自动修复测试失败，
以便快速定位并解决问题。

## 验收标准
- 给 agent 一个测试失败的仓库
- agent 能读取失败日志
- agent 能定位到问题代码
- agent 能修改代码使测试通过
```

### [2] ADR — 架构决策记录
- 写到 `docs/adr/{编号}-{主题}.md`
- 每个重大设计选择记录一条
- 格式：背景 / 决策 / 后果

### [3] Design — 确认 seams
- 写测试前先明确公开接口
- 在 spec 中列出 seams 表格

### [4] TDD — Red → Green → Refactor
- Red: 写失败测试
- Green: 写最少代码通过测试
- Refactor: 在 review 阶段进行

### [5] Review
- 自检 checklist
- 无 implementation-coupled 测试
- 无 tautological 测试
- 接口稳定

### [6] CI
```bash
agentenv/python -m pytest tests/ -v --tb=short
```

### [7] Docs
- 更新 `docs/api_spec.md`
- 重大变更更新 ADR

## 目录结构

```
specs/              需求规格文档
docs/
├── adr/            架构决策记录
└── api_spec.md     API 接口规格
```
