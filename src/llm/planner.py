from __future__ import annotations

import json

from .client import DashScopeLLMClient
from .messages import AgentMessage
from src.agent.core import DevAgent, Decision
from src.tools.metadata import get_tool_metadata


def build_tools_section(tools: dict) -> str:
    sections = []
    for name, fn in sorted(tools.items()):
        meta = get_tool_metadata(fn) if fn else None
        if meta:
            params_lines = []
            for pname, pschema in meta.parameters.items():
                req = "required" if pschema.required else "optional"
                params_lines.append(
                    f"  - {pname} ({pschema.type}, {req}): {pschema.description}"
                )
            params = ("\nParameters:\n" + "\n".join(params_lines)) if params_lines else ""
            sections.append(f"### {meta.name}\n{meta.description}.{params}")
        else:
            sections.append(f"### {name}\nNo description available.")
    return "\n\n".join(sections) if sections else "No tools available."


def build_system_prompt(tools: dict) -> str:
    return f"""\
You are an autonomous development agent. You have access to tools.
Given a task and the available tools, decide what to do next.

Available tools:
{build_tools_section(tools)}

Respond with a JSON object ONLY (no markdown, no explanation):
{{
  "thought": "your reasoning",
  "action": "use_tool_or_answer",
  "tool_name": "tool_name_here or null",
  "tool_args": {{"arg": "value"}} or {{}},
  "answer": "final answer text or empty string"
}}

If the task is simple and needs no tool, set action to "answer" and put your response in "answer".
If you need a tool, set action to "use_tool", set "tool_name" and "tool_args".
If unsure, prefer "answer" with your best response.
"""


class LLMPlanner:
    def __init__(self, client: DashScopeLLMClient):
        self._client = client

    def plan(
        self,
        task: str,
        step: int,
        available_tools=None,
        session_memory=None,
        context: str = "",
    ) -> Decision:
        tools: dict = {}
        if isinstance(available_tools, dict):
            tools = available_tools
        elif available_tools:
            tools = {name: None for name in available_tools}

        messages = [AgentMessage(role="system", content=build_system_prompt(tools))]

        if session_memory:
            for entry in session_memory.get_messages():
                messages.append(AgentMessage(
                    role=entry["role"],
                    content=entry["content"],
                ))

        user_content = f"Task: {task}\nCurrent step: {step}"
        if context:
            user_content += f"\n{context}"
        messages.append(AgentMessage(role="user", content=user_content))

        resp = self._client.chat(messages)
        if resp.error:
            return Decision(
                thought=f"LLM error: {resp.error}",
                action="answer",
                answer=f"Sorry, I encountered an error: {resp.error}",
            )

        decision = self._parse_decision(resp.content)
        decision.thought = f"Step {step}: {decision.thought}"
        return decision

    def _parse_decision(self, raw: str) -> Decision:
        try:
            data = json.loads(raw)
            return Decision(
                thought=data.get("thought", ""),
                action=data.get("action", "answer"),
                tool_name=data.get("tool_name"),
                tool_args=data.get("tool_args", {}),
                answer=data.get("answer", ""),
            )
        except json.JSONDecodeError:
            return Decision(
                thought="Failed to parse LLM response",
                action="answer",
                answer=raw[:500],
            )


class LLMDevAgent(DevAgent):
    def __init__(
        self,
        client: DashScopeLLMClient,
        tools: dict | None = None,
        max_steps: int = 20,
    ):
        from src.memory.session import SessionMemory
        super().__init__(
            tools=tools,
            max_steps=max_steps,
            session_memory=SessionMemory(),
        )
        self._client = client
        self._planner = LLMPlanner(client)

    def _plan(self, task: str, step: int) -> Decision:
        return self._planner.plan(
            task,
            step,
            available_tools=self._tools,
            session_memory=self._session_memory,
        )
