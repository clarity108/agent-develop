from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.tools.file_tools import ToolResult


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


class DevAgent:
    def __init__(self, tools: dict[str, ToolFn] | None = None, max_steps: int = 20):
        self._tools: dict[str, ToolFn] = tools or {}
        self._max_steps = max_steps
        self._state = AgentState(max_steps=max_steps)

    @property
    def state(self) -> AgentState:
        return self._state

    def register_tool(self, name: str, fn: ToolFn) -> None:
        self._tools[name] = fn

    def available_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def _plan(self, task: str, step: int) -> _Decision:
        return _Decision(
            thought="No planner configured",
            action="answer",
            answer="No planning strategy available.",
        )

    def run(self, task: str) -> AgentResult:
        self._state = AgentState(max_steps=self._max_steps)
        self._state.thought = f"Starting task: {task}"

        for step in range(1, self._max_steps + 1):
            self._state.step = step
            decision = self._plan(task, step)
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
            if not tool_result.success and tool_result.error:
                self._state.result += f"\nERROR: {tool_result.error}"

        return AgentResult(
            task=task,
            success=self._state.done and "ERROR" not in self._state.result and "unknown tool" not in self._state.result,
            steps=self._state.step,
            final_state=self._state,
        )


@dataclass
class AgentResult:
    task: str
    success: bool
    steps: int
    final_state: AgentState


@dataclass
class _Decision:
    thought: str
    action: str
    tool_name: str | None = None
    tool_args: dict = field(default_factory=dict)
    answer: str = ""


class RuleBasedPlanner:
    """Simple rule-based planner for testing — replaces LLM in dev."""

    def __init__(self, rules: list[dict] | None = None):
        self._rules = rules or []

    def plan(self, task: str, step: int) -> _Decision:
        for rule in self._rules:
            if rule.get("match") in task.lower() and rule.get("step", step) == step:
                if "answer" in rule and "tool" not in rule:
                    return _Decision(
                        thought=f"Rule matched: {rule['match']}",
                        action="answer",
                        answer=rule["answer"],
                    )
                return _Decision(
                    thought=f"Rule matched: {rule['match']}",
                    action=f"Executing rule for step {step}",
                    tool_name=rule.get("tool"),
                    tool_args=rule.get("args", {}),
                    answer=rule.get("answer", ""),
                )
        return _Decision(
            thought="No rule matched, answering directly",
            action="answer",
            answer="I don't have a rule for this task.",
        )


class RuleBasedDevAgent(DevAgent):
    def __init__(self, rules: list[dict] | None = None, tools: dict[str, ToolFn] | None = None, max_steps: int = 20):
        super().__init__(tools=tools, max_steps=max_steps)
        self._planner = RuleBasedPlanner(rules or [])

    def _plan(self, task: str, step: int) -> _Decision:
        return self._planner.plan(task, step)
