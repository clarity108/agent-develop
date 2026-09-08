from __future__ import annotations

import inspect
import json
import re

from .client import DashScopeLLMClient
from .messages import AgentMessage
from src.agent.core import DevAgent, Decision
from src.tools.metadata import get_tool_metadata, ParameterSchema


def _infer_param_type(default) -> str:
    if isinstance(default, bool):
        return "boolean"
    if isinstance(default, int):
        return "integer"
    return "string"


def build_tools_list(tools: dict) -> list[dict]:
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
            ptype = _infer_param_type(param.default)
            properties[pname] = {"type": ptype}
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


def _type_label(default) -> str:
    if isinstance(default, bool):
        return "bool"
    if isinstance(default, int):
        return "int"
    return "str"


def _tool_signature(fn) -> str:
    sig = inspect.signature(fn)
    parts = []
    for pname, param in sig.parameters.items():
        tl = _type_label(param.default)
        if param.default is inspect.Parameter.empty:
            parts.append(f"{pname}: {tl}")
        else:
            parts.append(f"{pname}: {tl} = {param.default!r}")
    return "(" + ", ".join(parts) + ")"


def _tool_params(fn) -> str:
    sig = inspect.signature(fn)
    lines = []
    for pname, param in sig.parameters.items():
        tl = _type_label(param.default)
        req = "required" if param.default is inspect.Parameter.empty else "optional"
        default = f" = {param.default!r}" if param.default is not inspect.Parameter.empty else ""
        lines.append(f"  - {pname} ({tl}, {req}){default}")
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

## How to respond

You have two ways to respond:

### 1. Call a tool (preferred)
Use the native tool_call mechanism to invoke a tool directly. Fill in the exact
parameter names from the tool's signature. Do NOT produce JSON for tool calls.

### 2. Give a final answer (JSON only)
When no more tools are needed, respond with a single valid JSON object:

  {{
    "thought": "one sentence of reasoning",
    "action": "answer",
    "tool_name": null,
    "tool_args": {{}},
    "answer": "your final answer to the user"
  }}

## Rules
1. For tool calls, use native tool_call — do NOT output JSON for tool invocations.
2. For final answers, output valid JSON with action="answer".
3. If a tool result appears in your conversation history, the tool has already been
   called. Do NOT call the same tool again — process the result and either answer
   or use a different tool.
4. Be concise in thoughts and answers.
"""


_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "and", "or", "but", "not", "so", "if", "then", "than", "that", "this",
    "these", "those", "it", "its", "he", "she", "they", "we", "you", "i",
    "me", "my", "our", "your", "his", "her", "their", "what", "which",
    "who", "when", "where", "why", "how", "all", "each", "every", "both",
    "few", "more", "most", "other", "some", "such", "no", "nor", "only",
    "own", "same", "too", "very", "just", "also", "here", "there",
}


def _extract_keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z_][a-z0-9_]+", text.lower())
    return {w for w in words if len(w) > 1 and w not in _STOPWORDS}


def _find_relevant_memories(task: str, memories: list[dict], max_results: int = 5) -> list[dict]:
    task_kw = _extract_keywords(task)
    if not task_kw:
        return memories[:max_results]
    scored = []
    for mem in memories:
        mem_text = f"{mem.get('task', '')} {mem.get('result', '')}"
        mem_kw = _extract_keywords(mem_text)
        overlap = len(task_kw & mem_kw)
        if overlap > 0:
            scored.append((overlap, mem))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:max_results]]


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
        on_compression=None,
        on_token=None,
        on_usage=None,
    ) -> Decision:
        tools: dict = {}
        if isinstance(available_tools, dict):
            tools = available_tools
        elif available_tools:
            tools = {name: None for name in available_tools}

        system_prompt = build_system_prompt(tools)
        if self._ltm:
            keys = self._ltm.list_keys()
            if keys:
                all_mems = [m for m in (self._ltm.load(k) for k in keys) if m]
                relevant = _find_relevant_memories(task, all_mems)
                if relevant:
                    past_lines = ["\n\nRELEVANT PAST EXPERIENCES:"]
                    for mem in relevant:
                        past_lines.append(
                            f"- [{mem.get('task', '?')}] "
                            f"result: {mem.get('result', 'N/A')}"
                        )
                    system_prompt += "\n".join(past_lines)

        if session_memory:
            if session_memory.maybe_compress(self._client) and on_compression:
                on_compression(
                    session_memory.message_count(),
                    session_memory.summary_length(),
                )

        messages = [AgentMessage(role="system", content=system_prompt)]

        if session_memory:
            for entry in session_memory.get_messages():
                meta = entry.get("metadata", {})
                messages.append(AgentMessage(
                    role=entry["role"],
                    content=entry["content"],
                    tool_call_id=meta.get("tool_call_id"),
                    tool_name=meta.get("tool_name"),
                ))

        user_content = f"Task: {task}\nCurrent step: {step}"
        if context:
            user_content += f"\n{context}"
        messages.append(AgentMessage(role="user", content=user_content))

        tool_defs = build_tools_list(tools)

        if on_token:
            return self._plan_stream(
                messages, tool_defs, step, on_token, on_usage,
            )

        resp = self._client.chat(messages, tools=tool_defs)

        if resp.error:
            return Decision(
                thought=f"LLM error: {resp.error}",
                action="answer",
                answer=f"Sorry, I encountered an error: {resp.error}",
            )

        if on_usage and resp.usage:
            on_usage(resp.usage.prompt_tokens, resp.usage.completion_tokens)

        if resp.tool_calls:
            tc = resp.tool_calls[0]
            decision = Decision(
                thought=f"Native tool call: {tc.function_name}",
                action="use_tool",
                tool_name=tc.function_name,
                tool_args=tc.function_args,
                answer="",
                tool_call_id=tc.id,
            )
            decision.thought = f"Step {step}: {decision.thought}"
            return decision

        decision = self._parse_decision(resp.content)
        decision.thought = f"Step {step}: {decision.thought}"
        return decision

    def _plan_stream(self, messages, tool_defs, step, on_token, on_usage=None) -> Decision:
        from .client import StreamChunk, ChatResponse
        full_content = ""
        tool_calls = []
        error = None

        for chunk in self._client.stream_chat(messages, tools=tool_defs):
            if isinstance(chunk, ChatResponse):
                error = chunk.error
                break
            if isinstance(chunk, StreamChunk):
                if chunk.content:
                    full_content += chunk.content
                    on_token(chunk.content)
                if chunk.tool_calls:
                    tool_calls = chunk.tool_calls
                if chunk.done:
                    break

        if error:
            return Decision(
                thought=f"LLM error: {error}",
                action="answer",
                answer=f"Sorry, I encountered an error: {error}",
            )

        if tool_calls:
            tc = tool_calls[0]
            decision = Decision(
                thought=f"Native tool call: {tc.function_name}",
                action="use_tool",
                tool_name=tc.function_name,
                tool_args=tc.function_args,
                answer="",
                tool_call_id=tc.id,
            )
            decision.thought = f"Step {step}: {decision.thought}"
            return decision

        decision = self._parse_decision(full_content)
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
        max_tool_retries: int = 2,
        undo_manager=None,
        tool_cache=None,
    ):
        from src.memory.session import SessionMemory
        if session_memory is None:
            session_memory = SessionMemory()
        super().__init__(
            tools=tools,
            max_steps=max_steps,
            session_memory=session_memory,
            max_tool_retries=max_tool_retries,
            undo_manager=undo_manager,
            tool_cache=tool_cache,
        )
        self._client = client
        self._planner = LLMPlanner(client, long_term_memory=long_term_memory)

    def _plan(self, task: str, step: int, on_compression=None, on_token=None, on_usage=None) -> Decision:
        return self._planner.plan(
            task,
            step,
            available_tools=self._tools,
            session_memory=self._session_memory,
            on_compression=on_compression,
            on_token=on_token,
            on_usage=on_usage,
        )
