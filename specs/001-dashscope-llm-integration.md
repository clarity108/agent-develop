# Spec: 接入阿里云百炼（DashScope）LLM

## 用户故事
作为开发者，我希望 agent 能通过阿里云百炼 API 驱动规划决策，
以便让 agent 理解自然语言任务并自主执行开发操作。

## 验收标准

### AC1: LLM Client 封装
- 支持 DashScope OpenAI 兼容 API 端点
- 支持配置 model / temperature / max_tokens / timeout
- API 错误和网络错误正确返回 ChatResponse(error=...)
- 不依赖额外 SDK，仅用 httpx 发 HTTP 请求

### AC2: 配置管理
- 配置文件使用 YAML 格式
- API Key 通过 `${ENV_VAR}` 语法引用环境变量
- 环境变量未设置时抛出明确错误
- 默认配置文件位于 `config/default.yaml`

### AC3: LLM 规划器
- LLMPlanner 将 LLM 的 JSON 输出解析为 _Decision
- 非 JSON 响应时降级为 answer（不回崩）
- LLM 返回错误时，agent 记录错误并终止

### AC4: LLM Agent
- LLMDevAgent 继承 AgentResult/AgentState 接口
- 每步将历史 tool 结果作为 context 回传 LLM
- 工具执行成功后，LLM 可决定下一步或终止
- max_steps 限制防止无限循环

## Seams（公开接口）

| Module | Seam |
|--------|------|
| `DashScopeLLMClient` | `chat(messages) -> ChatResponse` |
| `LLMPlanner` | `plan(task, step, available_tools, context) -> _Decision` |
| `LLMDevAgent` | `run(task) -> AgentResult` |
| `load_config` | `load_config(path) -> dict` |
| `build_client` | `build_client(llm_config) -> DashScopeLLMClient` |

## 非目标
- 暂不支持流式输出（SSE）
- 暂不支持多模型切换
- 暂不支持 prompt 模板管理
