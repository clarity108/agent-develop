from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from src.agent.cache import ToolCache

from src.tools.file_tools import ToolResult
from src.memory.session import SessionMemory


@dataclass
class AgentState:
    step: int = 0
    max_steps: int = 20
    thought: str = ""
    action: str = ""
    result: str = ""
    done: bool = False


class ToolFn(Protocol):
    def __call__(self, *args, **kwargs) -> ToolResult: ...


@dataclass
class Decision:
    thought: str
    action: str
    tool_name: str | None = None
    tool_args: dict = field(default_factory=dict)
    answer: str = ""
    tool_call_id: str | None = None


_RETRYABLE_PATTERNS = (
    "not found", "no such file", "permission denied", "connection refused",
    "timeout", "timed out", "temporarily unavailable", "broken pipe",
    "connection reset", "network error", "rate limit", "too many requests",
)

_DANGEROUS_TOOLS = {"rm_file", "execute_command"}

_FILE_MOD_TOOLS = {
    "write_file": "path",
    "edit_file": "path",
    "rm_file": "path",
    "mv_file": "source",
    "apply_patch": "path",
}


def _is_retryable(error: str) -> bool:
    if not error:
        return False
    err_lower = error.lower()
    return any(p in err_lower for p in _RETRYABLE_PATTERNS)


def _is_dangerous(tool_name: str) -> bool:
    return tool_name in _DANGEROUS_TOOLS


def _args_key(tool_name: str, tool_args: dict) -> str:
    return f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"


class DevAgent:
    def __init__(
        self,
        tools: dict[str, ToolFn] | None = None,
        max_steps: int = 20,
        session_memory: SessionMemory | None = None,
        max_tool_retries: int = 2,
        undo_manager=None,
        tool_cache: ToolCache | None = None,
    ):
        self._tools: dict[str, ToolFn] = tools or {}
        self._max_steps = max_steps
        self._max_tool_retries = max_tool_retries
        self._retry_counts: dict[str, int] = {}
        self._state = AgentState(max_steps=max_steps)
        self._session_memory = session_memory
        self._undo_manager = undo_manager
        self._tool_cache = tool_cache or ToolCache()

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def session_memory(self) -> SessionMemory | None:
        return self._session_memory

    @property
    def undo_manager(self):
        return self._undo_manager

    @property
    def tool_cache(self) -> ToolCache:
        return self._tool_cache

    def register_tool(self, name: str, fn: ToolFn) -> None:
        self._tools[name] = fn

    def available_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def _plan(self, task: str, step: int, on_compression=None, on_token=None, on_usage=None) -> Decision:
        return Decision(
            thought="No planner configured",
            action="answer",
            answer="No planning strategy available.",
        )

    def run(self, task: str, on_step=None, cancel_check=None, on_compression=None, confirmation_check=None, on_token=None, on_usage=None) -> AgentResult:
        self._state = AgentState(max_steps=self._max_steps)
        self._state.thought = f"Starting task: {task}"

        if self._session_memory:
            self._session_memory.add("user", task)

        for step in range(1, self._max_steps + 1):
            if cancel_check and cancel_check():
                self._state.result = "Cancelled by user"
                self._state.done = True
                break
            self._state.step = step
            decision = self._plan(task, step, on_compression=on_compression, on_token=on_token, on_usage=on_usage)
            self._state.thought = decision.thought
            self._state.action = decision.action

            if on_step:
                on_step("decision", step, decision)

            if decision.tool_name is None:
                self._state.result = decision.answer
                self._state.done = True
                if self._session_memory:
                    self._session_memory.add("assistant", decision.answer)
                break

            if decision.tool_name not in self._tools:
                self._state.result = f"unknown tool: {decision.tool_name}"
                self._state.done = True
                if on_step:
                    on_step("error", step, f"unknown tool: {decision.tool_name}")
                break

            if _is_dangerous(decision.tool_name) and confirmation_check:
                approved = confirmation_check(decision.tool_name, decision.tool_args)
                if not approved:
                    tool_result = ToolResult(
                        success=False,
                        output="",
                        error=f"action rejected by user: {decision.tool_name}",
                    )
                    self._state.result = tool_result.output
                    if on_step:
                        on_step("tool_result", step, decision.tool_name, tool_result)
                    if self._session_memory:
                        meta = {"tool_name": decision.tool_name}
                        if decision.tool_call_id:
                            meta["tool_call_id"] = decision.tool_call_id
                        self._session_memory.add("assistant", decision.thought, metadata=meta)
                        self._session_memory.add("tool", f"rejected: user denied {decision.tool_name}", metadata=meta)
                    continue

            args_key = _args_key(decision.tool_name, decision.tool_args)
            cache_key = ToolCache.make_key(decision.tool_name, decision.tool_args)

            cached = self._tool_cache.get(cache_key)
            if cached is not None:
                tool_result = cached
                if on_step:
                    on_step("tool_cache_hit", step, decision.tool_name, tool_result)
                self._state.result = tool_result.output
                if not tool_result.success and tool_result.error:
                    self._state.result += f"\nERROR: {tool_result.error}"
                if self._session_memory:
                    meta = {"tool_name": decision.tool_name, "cache": "hit"}
                    if decision.tool_call_id:
                        meta["tool_call_id"] = decision.tool_call_id
                    self._session_memory.add("assistant", decision.thought, metadata=meta)
                    status = "success" if tool_result.success else f"error: {tool_result.error}"
                    self._session_memory.add("tool", f"{status} [cached]: {tool_result.output}", metadata=meta)
                continue

            undo_path = None
            mod_path = None
            if decision.tool_name in _FILE_MOD_TOOLS:
                path_arg = _FILE_MOD_TOOLS[decision.tool_name]
                if path_arg in decision.tool_args:
                    mod_path = decision.tool_args[path_arg]
                    if self._undo_manager:
                        undo_path = mod_path
                        self._undo_manager.before_change(undo_path)

            max_attempts = self._max_tool_retries + 1
            tool_result = None
            for attempt in range(1, max_attempts + 1):
                try:
                    tool_result = self._tools[decision.tool_name](**decision.tool_args)
                except TypeError as e:
                    tool_result = ToolResult(success=False, output="", error=f"invalid arguments: {e}")
                except Exception as e:
                    tool_result = ToolResult(success=False, output="", error=str(e))

                if tool_result.success or not _is_retryable(tool_result.error or ""):
                    break
                if attempt < max_attempts:
                    if on_step:
                        on_step("tool_retry", step, decision.tool_name, attempt, max_attempts, tool_result.error)
                    self._retry_counts[args_key] = attempt

            if tool_result.success:
                self._tool_cache.set(cache_key, tool_result)
                if mod_path:
                    self._tool_cache.invalidate_path(str(mod_path))

            if undo_path and tool_result.success:
                self._undo_manager.after_change(undo_path)

            self._state.result = tool_result.output
            if not tool_result.success and tool_result.error:
                self._state.result += f"\nERROR: {tool_result.error}"

            if on_step:
                on_step("tool_result", step, decision.tool_name, tool_result)

            if self._session_memory:
                meta = {"tool_name": decision.tool_name}
                if decision.tool_call_id:
                    meta["tool_call_id"] = decision.tool_call_id
                self._session_memory.add("assistant", decision.thought, metadata=meta)
                status = "success" if tool_result.success else f"error: {tool_result.error}"
                self._session_memory.add(
                    "tool",
                    f"{status}: {tool_result.output}",
                    metadata=meta,
                )

        return AgentResult(
            task=task,
            success=(
                self._state.done
                and "ERROR" not in self._state.result
                and "unknown tool" not in self._state.result
                and "Cancelled" not in self._state.result
            ),
            steps=self._state.step,
            final_state=self._state,
        )


@dataclass
class AgentResult:
    task: str
    success: bool
    steps: int
    final_state: AgentState


class RuleBasedPlanner:
    def __init__(self, rules: list[dict] | None = None):
        self._rules = rules or []

    @property
    def rules(self) -> list[dict]:
        return self._rules

    def plan(self, task: str, step: int) -> Decision:
        for rule in self._rules:
            if rule.get("match") in task.lower() and rule.get("step", step) == step:
                if "answer" in rule and "tool" not in rule:
                    return Decision(
                        thought=f"Rule matched: {rule['match']}",
                        action="answer",
                        answer=rule["answer"],
                    )
                return Decision(
                    thought=f"Rule matched: {rule['match']}",
                    action=f"Executing rule for step {step}",
                    tool_name=rule.get("tool"),
                    tool_args=rule.get("args", {}),
                    answer=rule.get("answer", ""),
                )
        return Decision(
            thought="No rule matched, answering directly",
            action="answer",
            answer="I don't have a rule for this task.",
        )


class RuleBasedDevAgent(DevAgent):
    def __init__(
        self,
        rules: list[dict] | None = None,
        tools: dict[str, ToolFn] | None = None,
        max_steps: int = 20,
        session_memory: SessionMemory | None = None,
        max_tool_retries: int = 2,
        undo_manager=None,
        tool_cache: ToolCache | None = None,
    ):
        super().__init__(tools=tools, max_steps=max_steps, session_memory=session_memory, max_tool_retries=max_tool_retries, undo_manager=undo_manager, tool_cache=tool_cache)
        self._planner = RuleBasedPlanner(rules or [])

    @property
    def rules(self) -> list[dict]:
        return self._planner.rules

    def _plan(self, task: str, step: int, on_compression=None, on_token=None, on_usage=None) -> Decision:
        return self._planner.plan(task, step)
