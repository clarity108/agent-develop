from __future__ import annotations

import inspect
import json

from .client import DashScopeLLMClient
from .messages import AgentMessage
from src.agent.core import DevAgent, Decision
from src.tools.metadata import get_tool_metadata, ParameterSchema


def build_tools_list(tools: dict) -> list[dict]:
    """Builds the tools array for the OpenAI-compatible tool_use API."""
    tool_defs = []
    for name, fn in tools.items():
        meta = get_tool_metadata(fn) if fn else None
        if not fn:
            continue

        properties = {}
        required = []
        sig = inspect.signature(fn)
        for pname, param in sig.parameters.items():
            is_required = param.default is inspect.Parameter.empty
            properties[pname] = {"type": "string"}
            if is_required:
                required.append(pname)

        desc = meta.description if meta else "No description available."
        tool_defs.append({
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        })
    return tool_defs


def _tool_signature(fn) -> str:
    sig = inspect.signature(fn)
    parts = []
    for pname, param in sig.parameters.items():
        if param.default is inspect.Parameter.empty:
            parts.append(f"{pname}: str")
        else:
            parts.append(f"{pname}: str = {param.default!r}")
    return "(" + ", ".join(parts) + ")"


def _tool_params(fn) -> str:
    sig = inspect.signature(fn)
    lines = []
    for pname, param in sig.parameters.items():
        req = "required" if param.default is inspect.Parameter.empty else "optional"
        default = f" = {param.default!r}" if param.default is not inspect.Parameter.empty else ""
        lines.append(f"  - {pname} (str, {req}){default}")
    return "\n".join(lines) if lines else "  (none)"


def build_tools_section(tools: dict) -> str:
    sections = []
    for name, fn in sorted(tools.items()):
        meta = get_tool_metadata(fn) if fn else None
        desc = meta.description if meta else "No description available."
        sig = _tool_signature(fn) if fn else f"({name})"
        params = _tool_params(fn) if fn else "  (none)"
        sections.append(
            f"### {meta.name if meta else name}{sig}\n{desc}\n"
            f"Parameters:\n{params}"
        )
    return "\n\n".join(sections) if sections else "No tools available."


def build_system_prompt(tools: dict) -> str:
    return f"""\
You are an autonomous development agent. You have access to tools.
Given a task and the available tools, decide what to do next.

Available tools:
{build_tools_section(tools)}

RESPONSE FORMAT (strict):
You MUST respond with a single valid JSON object. No markdown, no prose, no explanation — JSON only.

Schema:
  {{
    "thought": "one sentence of reasoning",
    "action": "use_tool" | "answer",
    "tool_name": "exact tool name or null",
    "tool_args": {{}},
    "answer": ""
  }}

RULES:
1. Always output valid JSON. Invalid JSON causes an error.
2. When action is "use_tool", you MUST fill "tool_args" with the exact parameter names
   from the tool's function signature. E.g. read_file(path) requires tool_args: {{"path": "output.txt"}}.
3. When action is "use_tool", leave "answer" as an empty string.
4. When action is "answer", leave "tool_name" as null and "tool_args" as empty object.
5. If a tool result message appears in your conversation history, the tool has already been
   called. Do NOT call the same tool again — process the result and either answer or use a
   different tool.

You also support native tool calls. When using a tool, you may call it directly
via the tool interface instead of producing JSON.

EXAMPLE 1 — JSON response calling a tool:
  {{
    "thought": "The task requires reading a file, use read_file",
    "action": "use_tool",
    "tool_name": "read_file",
    "tool_args": {{"path": "output.txt"}},
    "answer": ""
  }}

EXAMPLE 2 — JSON response giving a final answer:
  {{
    "thought": "The file content is known, respond to the user",
    "action": "answer",
    "tool_name": null,
    "tool_args": {{}},
    "answer": "The file contains 'created by agent'."
  }}

Do not deviate from this format. Output JSON only.
"""


class LLMPlanner:
    def __init__(self, client: DashScopeLLMClient, long_term_memory=None):
        self._client = client
        self._ltm = long_term_memory

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

        system_prompt = build_system_prompt(tools)
        if self._ltm:
            memories = self._ltm.list_keys()
            if memories:
                past_lines = ["\n\nPAST EXPERIENCES (from previous tasks):"]
                for key in memories:
                    mem = self._ltm.load(key)
                    if mem:
                        past_lines.append(
                            f"- [{mem.get('task', key)}] "
                            f"result: {mem.get('result', 'N/A')}"
                        )
                system_prompt += "\n".join(past_lines)

        messages = [AgentMessage(role="system", content=system_prompt)]

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

        tool_defs = build_tools_list(tools)
        resp = self._client.chat(messages, tools=tool_defs)

        if resp.error:
            return Decision(
                thought=f"LLM error: {resp.error}",
                action="answer",
                answer=f"Sorry, I encountered an error: {resp.error}",
            )

        if resp.tool_calls:
            tc = resp.tool_calls[0]
            decision = Decision(
                thought=f"Native tool call: {tc.function_name}",
                action="use_tool",
                tool_name=tc.function_name,
                tool_args=tc.function_args,
                answer="",
            )
            decision.thought = f"Step {step}: {decision.thought}"
            return decision

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
        session_memory: "SessionMemory" | None = None,
        long_term_memory=None,
    ):
        from src.memory.session import SessionMemory
        if session_memory is None:
            session_memory = SessionMemory()
        super().__init__(
            tools=tools,
            max_steps=max_steps,
            session_memory=session_memory,
        )
        self._client = client
        self._planner = LLMPlanner(client, long_term_memory=long_term_memory)

    def _plan(self, task: str, step: int) -> Decision:
        return self._planner.plan(
            task,
            step,
            available_tools=self._tools,
            session_memory=self._session_memory,
        )
