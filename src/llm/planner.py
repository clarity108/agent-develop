from __future__ import annotations

import json
from .client import DashScopeLLMClient, ChatMessage, ChatResponse

from src.agent.core import _Decision

_SYSTEM_PROMPT = """\
You are an autonomous development agent. You have access to tools.
Given a task and the available tools, decide what to do next.

Respond with a JSON object ONLY (no markdown, no explanation):
{
  "thought": "your reasoning",
  "action": "use_tool_or_answer",
  "tool_name": "tool_name_here or null",
  "tool_args": {"arg": "value"} or {},
  "answer": "final answer text or empty string"
}

If the task is simple and needs no tool, set action to "answer" and put your response in "answer".
If you need a tool, set action to "use_tool", set "tool_name" and "tool_args".
If unsure, prefer "answer" with your best response.
"""


class LLMPlanner:
    def __init__(self, client: DashScopeLLMClient):
        self._client = client

    def plan(self, task: str, step: int, available_tools: list[str], context: str = "") -> _Decision:
        prompt = f"""Task: {task}
Current step: {step}
Available tools: {available_tools}
{f'Previous context: {context}' if context else ''}

Decide what to do this step."""

        messages = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt),
        ]

        resp = self._client.chat(messages)
        if resp.error:
            return _Decision(
                thought=f"LLM error: {resp.error}",
                action="answer",
                answer=f"Sorry, I encountered an error: {resp.error}",
            )

        decision = self._parse_decision(resp.content)
        decision.thought = f"Step {step}: {decision.thought}"
        return decision

    def _parse_decision(self, raw: str) -> _Decision:
        try:
            data = json.loads(raw)
            return _Decision(
                thought=data.get("thought", ""),
                action=data.get("action", "answer"),
                tool_name=data.get("tool_name"),
                tool_args=data.get("tool_args", {}),
                answer=data.get("answer", ""),
            )
        except json.JSONDecodeError:
            return _Decision(
                thought="Failed to parse LLM response",
                action="answer",
                answer=raw[:500],
            )


class LLMDevAgent:
    def __init__(self, client: DashScopeLLMClient, tools: dict | None = None, max_steps: int = 20):
        from src.agent.core import AgentResult, AgentState
        self._client = client
        self._planner = LLMPlanner(client)
        self._tools: dict[str, callable] = tools or {}
        self._max_steps = max_steps
        self._state = AgentState(max_steps=max_steps)
        self._AgentResult = AgentResult
        self._AgentState = AgentState

    def register_tool(self, name: str, fn) -> None:
        self._tools[name] = fn

    def available_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    @property
    def state(self):
        return self._state

    def run(self, task: str):
        self._state = self._AgentState(max_steps=self._max_steps)
        self._state.thought = f"Starting task: {task}"
        context_parts = []

        for step in range(1, self._max_steps + 1):
            self._state.step = step
            decision = self._planner.plan(
                task, step,
                available_tools=self.available_tools(),
                context="\n".join(context_parts) if context_parts else "",
            )
            self._state.thought = decision.thought
            self._state.action = decision.action

            if decision.tool_name is None:
                self._state.result = decision.answer
                self._state.done = True
                break

            if decision.tool_name not in self._tools:
                self._state.result = f"unknown tool: {decision.tool_name}"
                self._state.done = True
                break

            tool_result = self._tools[decision.tool_name](**decision.tool_args)
            self._state.result = tool_result.output
            status = "success" if tool_result.success else f"failed: {tool_result.error}"
            context_parts.append(f"Step {step}: called {decision.tool_name} -> {status} -> {tool_result.output}")

        return self._AgentResult(
            task=task,
            success=self._state.done and "ERROR" not in self._state.result and "unknown tool" not in self._state.result,
            steps=self._state.step,
            final_state=self._state,
        )
