# Spec: Claude Code 风格 Agent 内部架构

## 用户故事
作为 agent 开发者，我希望 agent 内部采用 Claude Code 风格的 tool-augmented conversation loop，
以便 LLM 能看到完整的对话历史（含工具描述、工具调用、工具结果），做出更准确的决策。

## 验收标准

### AC1: 工具元数据（Tool Metadata）
- 每个工具可通过 `@tool(description)` 装饰器附带描述信息
- `ToolMetadata` 包含 name / description / parameters
- LLM 的系统提示词包含所有已注册工具的元数据
- 未装饰的工具仍可用，但显示 "No description available"

### AC2: 统一消息协议（AgentMessage）
- `AgentMessage` 支持 system / user / assistant / tool 四种角色
- tool 角色消息携带 `tool_call_id` 用于关联调用与结果
- `DashScopeLLMClient.chat()` 同时接受 `ChatMessage` 和 `AgentMessage`

### AC3: 统一 Agent 循环
- `LLMDevAgent` 继承自 `DevAgent`（`isinstance` 返回 True）
- `LLMDevAgent` 不再重写 `run()`，通过重写 `_plan()` 接入 LLM
- `DevAgent.run()` 是唯一的循环实现，规则版和 LLM 版共享

### AC4: 会话记忆（Session Memory）
- `DevAgent` 支持传入 `SessionMemory`，自动记录 user/assistant/tool 消息
- `LLMPlanner.plan()` 读取会话历史，将完整对话发送给 LLM
- 工具执行结果作为 tool 角色消息回注对话历史
- 不传入 session_memory 时行为不变（向后兼容）

### AC5: Decision 公开化
- `_Decision` 重命名为 `Decision`，作为公开接口
- `src.agent.core` 导出 `Decision`

## Seams（公开接口）

| Module | Seam |
|--------|------|
| `ToolMetadata` | `name`, `description`, `parameters` |
| `@tool(description)` | decorator returning original function |
| `get_tool_metadata(fn)` | `-> ToolMetadata \| None` |
| `AgentMessage` | `role`, `content`, `tool_call_id`, `tool_name` |
| `Decision` | `thought`, `action`, `tool_name`, `tool_args`, `answer` |
| `DevAgent(session_memory=)` | 新增可选参数 |
| `LLMDevAgent` | 继承自 `DevAgent` |
| `LLMPlanner.plan(session_memory=)` | 新增可选参数 |
| `build_system_prompt(tools)` | `-> str`，生成含工具描述的系统提示 |

## 非目标
- 暂不支持工具参数自动校验（schema validation）
- 暂不支持 tool_call_id 在 LLM 响应中的自动生成
- 暂不支持并行工具调用
