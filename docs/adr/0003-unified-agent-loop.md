# ADR-0003: 统一 Agent 循环与 Tool-Augmented Conversation

## 日期
2026-09-02

## 背景
项目初始架构中 `LLMDevAgent` 与 `DevAgent` 是两套平行的实现，`run()` 逻辑完全重复。LLM 只能看到工具名（字符串列表）和累积的上下文字符串，无法感知工具描述，也无法看到结构化的对话历史。这与 Claude Code 等成熟 agent 的 architecture 存在差距。

## 决策
重构 agent 核心，采用 tool-augmented conversation loop：

1. **统一循环** — `LLMDevAgent` 继承自 `DevAgent`，通过 Template Method `_plan()` 接入 LLM。`DevAgent.run()` 是唯一的循环实现。

2. **工具元数据** — 通过 `@tool(description)` 装饰器为每个工具附带描述。`LLMPlanner` 在构建系统提示词时自动收集已注册工具的元数据，格式化为 LLM 可读的工具定义。

3. **AgentMessage 协议** — 定义 `AgentMessage(role, content, tool_call_id, tool_name)` 替代简单的 `ChatMessage`。支持 system/user/assistant/tool 四种角色，tool 角色用于将工具结果回注对话。

4. **Session Memory 集成** — `DevAgent` 接受可选的 `SessionMemory` 参数。有 session_memory 时，agent 自动记录 user 任务、assistant 决策、tool 结果。`LLMPlanner` 读取完整对话历史发送给 LLM。

5. **Decision 公开化** — `_Decision` 重命名为 `Decision`，作为 planner 与 agent 之间的公开接口。

## 后果

### 正面
- `LLMDevAgent` 和 `RuleBasedDevAgent` 共享同一个循环，bug fix 只写一次
- LLM 能看到工具描述，减少工具调用错误
- 完整对话历史让 LLM 了解之前的工具调用结果，可自主判断何时终止
- `isinstance(LLMDevAgent, DevAgent)` 为 True，类型系统正确
- Session memory 可选，不破坏现有无记忆的用法

### 负面
- `LLMPlanner.plan()` 的参数从 `available_tools: list[str]` 扩展为 `available_tools: dict | list`，有轻微的类型变化
- Session memory 的引入增加了 `DevAgent` 的依赖（需要 `src.memory.session`）
- 系统提示词长度随工具数量增长，可能增加 token 消耗

## 相关文件
- `src/agent/core.py` — DevAgent, Decision, session_memory
- `src/llm/planner.py` — LLMPlanner, LLMDevAgent(DevAgent), build_system_prompt
- `src/llm/client.py` — AgentMessage 支持
- `src/llm/messages.py` — AgentMessage
- `src/tools/metadata.py` — ToolMetadata, @tool, get_tool_metadata
