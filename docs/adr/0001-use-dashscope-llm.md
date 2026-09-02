# ADR-0001: 使用 DashScope（百炼）作为 LLM 后端

## 日期
2026-09-02

## 背景
agent 需要 LLM 来驱动规划决策（plan-tool-answer 循环）。需要选择一个 LLM 后端。

## 决策
使用阿里云百炼（DashScope）的 OpenAI 兼容 API 端点：
`https://dashscope.aliyuncs.com/compatible-mode/v1`

模型默认 `glm-2.5`，可配置替换为 `qwen-max` / `qwen-plus` 等。

## 后果

### 正面
- OpenAI 兼容 API，`httpx` 直接调用，无需额外 SDK
- 支持国内网络环境
- 模型可选（glm / qwen 系列）

### 负面
- API Key 管理需要额外处理（已实现 `${ENV_VAR}` 环境变量替换）
- 不同模型的能力差异需在实际使用中评估
- 依赖外部服务，网络故障需有降级策略

## 相关文件
- `src/llm/client.py` — DashScopeLLMClient
- `src/llm/planner.py` — LLMPlanner / LLMDevAgent
- `src/llm/config.py` — 配置加载与环境变量解析
- `config/default.yaml` — 默认配置
