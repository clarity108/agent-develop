from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

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


class DevAgent:
    def __init__(
        self,
        tools: dict[str, ToolFn] | None = None,
        max_steps: int = 20,
        session_memory: SessionMemory | None = None,
    ):
        self._tools: dict[str, ToolFn] = tools or {}
        self._max_steps = max_steps
        self._state = AgentState(max_steps=max_steps)
        self._session_memory = session_memory

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def session_memory(self) -> SessionMemory | None:
        return self._session_memory

    def register_tool(self, name: str, fn: ToolFn) -> None:
        self._tools[name] = fn

    def available_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def _plan(self, task: str, step: int) -> Decision:
        return Decision(
            thought="No planner configured",
            action="answer",
            answer="No planning strategy available.",
        )

    def run(self, task: str, on_step=None) -> AgentResult:
        self._state = AgentState(max_steps=self._max_steps)
        self._state.thought = f"Starting task: {task}"

        if self._session_memory:
            self._session_memory.add("user", task)

        for step in range(1, self._max_steps + 1):
            self._state.step = step
            decision = self._plan(task, step)
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

            tool_result = self._tools[decision.tool_name](**decision.tool_args)
            self._state.result = tool_result.output
            if not tool_result.success and tool_result.error:
                self._state.result += f"\nERROR: {tool_result.error}"

            if on_step:
                on_step("tool_result", step, decision.tool_name, tool_result)

            if self._session_memory:
                self._session_memory.add(
                    "assistant",
                    decision.thought,
                    metadata={"tool_name": decision.tool_name},
                )
                status = "success" if tool_result.success else f"error: {tool_result.error}"
                self._session_memory.add(
                    "tool",
                    f"{status}: {tool_result.output}",
                    metadata={"tool_name": decision.tool_name},
                )

        return AgentResult(
            task=task,
            success=(
                self._state.done
                and "ERROR" not in self._state.result
                and "unknown tool" not in self._state.result
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
    ):
        super().__init__(tools=tools, max_steps=max_steps, session_memory=session_memory)
        self._planner = RuleBasedPlanner(rules or [])

    def _plan(self, task: str, step: int) -> Decision:
        return self._planner.plan(task, step)
