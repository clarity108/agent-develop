# ADR-0002: Agent 核心架构

## 日期
2026-09-02

## 背景
需要实现一个可自主执行开发任务的 agent，包含规划、工具调用、反馈循环。

## 决策
采用 **planner-tool loop** 架构：

```
DevAgent (抽象基类)
  ├── RuleBasedDevAgent  — 规则驱动，用于测试/开发
  └── LLMDevAgent        — LLM 驱动，用于生产
```

每步循环：
1. Planner 根据 task + step + context 产出 _Decision
2. 如果是 tool call → 执行工具 → 结果回传
3. 如果是 answer → 终止循环
4. 历史结果作为 context 回传下一步的 planner

## 后果

### 正面
- 规则版和 LLM 版共享 AgentResult/AgentState，测试可覆盖两者
- Planner 是独立组件，可替换（规则 / LLM / 混合）
- LLMDevAgent 自带 context 回传，解决循环终止问题

### 负面
- LLMDevAgent 内部循环与 DevAgent 有重复逻辑（未来可统一）
- 目前 LLM 输出格式依赖 JSON，需要 prompt engineering

## 相关文件
- `src/agent/core.py`
- `src/llm/planner.py`
