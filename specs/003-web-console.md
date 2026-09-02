# Spec: Agent Console Web 前端

## 用户故事
作为开发者，我希望通过浏览器访问 agent 控制台，
以便提交开发任务、实时观看 agent 的执行过程（思考/工具调用/结果），并管理历史会话。

## 验收标准

### AC1: 页面渲染
- `GET /` 返回 HTML 页面，包含执行追踪面板
- 页面使用 JetBrains Mono 等宽字体，深色主题
- 左侧：任务输入表单 + 会话历史
- 中间：执行追踪（execution trace）主区域
- 右侧：工具列表 + 实时指标 + agent 状态

### AC2: 任务提交
- `POST /api/runs` 接受表单 `task` 参数
- 返回 `{"run_id": "..."}` 
- agent 在后台线程执行，不阻塞 HTTP 响应

### AC3: 实时执行流
- `GET /api/runs/{run_id}/stream` 返回 Server-Sent Events
- 事件类型：`agent_start`, `step_thought`, `tool_call`, `tool_result`, `step_end`, `agent_done`, `agent_error`
- 前端收到事件后实时更新执行追踪界面
- 完成后发送 `done` 事件关闭连接

### AC4: 历史会话
- 已完成的任务自动出现在左侧会话历史中
- 点击历史条目可加载并展示该次执行的完整追踪

### AC5: 设计系统
- 等宽字体（JetBrains Mono）作为页面主字体
- 颜色：深板岩灰底 `#1a1f2e`，暖白文字 `#e4e6e8`，琥珀色信号 `#d4a030`，钢蓝色结构 `#5b7a99`
- 执行追踪为垂直时间线，每步显示：思考（琥珀色斜体）→ 工具调用（钢蓝色代码块）→ 结果（等宽输出）
- 所有边框为 1px 发丝线，无边角半径

## Seams（公开接口）

| Route | Method | Returns | Description |
|-------|--------|---------|-------------|
| `/` | GET | HTML | Agent Console 主页 |
| `/api/runs` | POST | `{"run_id": str}` | 提交任务，启动 agent 执行 |
| `/api/runs/{id}` | GET | `{"run_id", "task", "done", "elapsed", "events"}` | 查询执行状态 |
| `/api/runs/{id}/stream` | GET | SSE stream | 实时流式执行事件 |

## 非目标
- 暂不支持多 agent 并行
- 暂不支持认证/权限
- 暂不支持文件上传
- 暂不支持 LLM agent 模式（默认 rule-based）
