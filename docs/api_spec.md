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
- `DevAgent(tools: dict | None, max_steps: int = 20)`
- `register_tool(name, fn)`
- `available_tools() -> list[str]`
- `run(task: str) -> AgentResult`

### LLMDevAgent
- `LLMDevAgent(client: DashScopeLLMClient, tools: dict | None, max_steps: int = 20)`
- 同上接口，由 LLM 驱动规划决策
- 历史结果自动作为 context 回传 LLM

### AgentResult

```python
@dataclass
class AgentResult:
    task: str
    success: bool
    steps: int
    final_state: AgentState
```

## LLM

### DashScopeLLMClient
- `DashScopeLLMClient(api_key, model="glm-2.5", base_url=None, temperature=0.7, max_tokens=2048, timeout=60)`
- `chat(messages: list[ChatMessage]) -> ChatResponse`

### LLMPlanner
- `LLMPlanner(client: DashScopeLLMClient)`
- `plan(task, step, available_tools, context="") -> _Decision`

### Config
- `load_config(path: str) -> dict` — 支持 `${ENV_VAR}` 替换
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
