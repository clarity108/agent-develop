# API Specification

## Tools

| Function | Params | Returns | Description |
|----------|--------|---------|-------------|
| `read_file(path)` | `path: str` | `ToolResult` | 读取文件内容 |
| `write_file(path, content)` | `path: str, content: str` | `ToolResult` | 写入文件，自动创建父目录 |
| `list_files(directory, recursive)` | `directory: str, recursive: bool = False` | `ToolResult` | 列出文件，newline 分隔 |
| `execute_command(command, timeout, cwd)` | `command: str, timeout: int = 30, cwd: str \| None` | `ToolResult` | 执行 shell 命令 |
| `git_status(cwd)` | `cwd: str` | `ToolResult` | git status --short |
| `git_init(cwd)` | `cwd: str` | `ToolResult` | 初始化 git 仓库 |
| `git_add_commit(cwd, message)` | `cwd: str, message: str` | `ToolResult` | git add . && git commit |

### ToolResult

```python
@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None
```

### Tool Metadata

```python
@dataclass
class ParameterSchema:
    type: str
    description: str = ""
    required: bool = False

@dataclass
class ToolMetadata:
    name: str
    description: str
    parameters: dict[str, ParameterSchema] = field(default_factory=dict)
```

| Function | Params | Returns | Description |
|----------|--------|---------|-------------|
| `@tool(description)` | `description: str` | decorator | 为函数附加 ToolMetadata |
| `get_tool_metadata(fn)` | `fn: callable` | `ToolMetadata \| None` | 获取函数的工具元数据 |

## Memory

### SessionMemory
- `SessionMemory(limit: int | None = None)`
- `add(role, content, metadata=None)` — 添加消息，自动截断
- `get_messages() -> list[dict]`
- `clear()`

### LongTermMemory
- `LongTermMemory(store_dir: str)`
- `save(key, value)` — JSON 持久化
- `load(key)` — 返回 None 或 value
- `delete(key)`
- `list_keys() -> list[str]`

## Agent

### DevAgent
- `DevAgent(tools: dict | None, max_steps: int = 20, session_memory: SessionMemory | None = None)`
- `register_tool(name, fn)`
- `available_tools() -> list[str]`
- `run(task: str) -> AgentResult`
- `session_memory` property — 返回注入的 SessionMemory（可为 None）
- 有 session_memory 时自动记录 user/assistant/tool 消息

### LLMDevAgent
- `LLMDevAgent(client: DashScopeLLMClient, tools: dict | None, max_steps: int = 20)`
- **继承自 DevAgent**，通过 `_plan()` 接入 LLM
- 自动创建 SessionMemory，LLM 可看到完整对话历史
- 与 DevAgent 共享 `run()` 循环

### AgentResult

```python
@dataclass
class AgentResult:
    task: str
    success: bool
    steps: int
    final_state: AgentState
```

### Decision

```python
@dataclass
class Decision:
    thought: str
    action: str
    tool_name: str | None = None
    tool_args: dict = field(default_factory=dict)
    answer: str = ""
```

## LLM

### DashScopeLLMClient
- `DashScopeLLMClient(api_key, model="glm-2.5", base_url=None, temperature=0.7, max_tokens=2048, timeout=60)`
- `chat(messages: list[ChatMessage | AgentMessage]) -> ChatResponse`

### AgentMessage

```python
@dataclass
class AgentMessage:
    role: str          # "system" | "user" | "assistant" | "tool"
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
```

### LLMPlanner
- `LLMPlanner(client: DashScopeLLMClient)`
- `plan(task, step, available_tools=None, session_memory=None, context="") -> Decision`
  - `available_tools` 接受 `dict[name, fn]`（含元数据）或 `list[str]`（仅名称）
  - `session_memory` 提供时，将完整对话历史发送给 LLM

### build_system_prompt
- `build_system_prompt(tools: dict[name, fn]) -> str`
- 根据工具元数据生成包含工具描述的系统提示词

### Config
- `load_config(path: str) -> dict` — 支持 `${ENV_VAR}` 替换，自动从 `.env` / `.env.example` 加载
- `build_client(llm_config: dict) -> DashScopeLLMClient`

## Harness

### AgentLogger
- `AgentLogger(level: str = "DEBUG")`
- `log(level, message, context=None) -> dict`
- `get_entries() -> list[dict]`
- `clear()`

### ExecutionTrace
- `ExecutionTrace()`
- `start(task: str) -> trace_id`
- `step(trace_id, action)`
- `end(trace_id, status, error=None)`
- `get_traces() -> list[dict]`

## Loop

### FeedbackLoop
- `FeedbackLoop(max_retries: int = 3)`
- `run(action, validator) -> FeedbackResult`

### PytestRunner
- `PytestRunner(command, cwd=None, timeout=60)`
- `run() -> ToolResult`
- `passed(result) -> bool`
