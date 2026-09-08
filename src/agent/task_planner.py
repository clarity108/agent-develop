from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from src.llm.messages import AgentMessage
from src.tools.file_tools import ToolResult


@dataclass
class PlanStep:
    index: int
    description: str
    status: str = "pending"
    result: str = ""


@dataclass
class TaskPlan:
    task: str
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed(self) -> int:
        return sum(1 for s in self.steps if s.status in ("done", "skipped"))

    @property
    def current(self) -> PlanStep | None:
        for s in self.steps:
            if s.status == "running":
                return s
        for s in self.steps:
            if s.status == "pending":
                return s
        return None

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "steps": [{"index": s.index, "description": s.description,
                       "status": s.status, "result": s.result} for s in self.steps],
            "total": self.total_steps,
            "completed": self.completed,
        }


_PLAN_PROMPT = """\
You are an autonomous development agent planning a multi-step task.

Given the following task, generate a detailed step-by-step plan.
Each step should be a single atomic action using one of the available tools, or a final answer.

Available tools:
{tools_section}

Task: {task}

Output a JSON object with this exact schema:
{{
  "plan": [
    {{"description": "what to do in step 1"}},
    {{"description": "what to do in step 2"}},
    ...
  ]
}}

Rules:
- 2-8 steps, each describing one atomic action
- Steps must be ordered and executable sequentially
- Last step should be a verification or final answer
- Do NOT include tool names — describe the action in plain language
- Output JSON only, no markdown
"""

_REVISE_PROMPT = """\
You are an autonomous development agent. A step in your plan failed.

Original plan:
{plan_json}

Failed step: {failed_index} — {failed_description}
Error: {error}

Revise the plan to fix or work around this failure. Keep successful steps unchanged.
You may remove, modify, or add steps as needed.

Output a JSON object:
{{
  "plan": [
    {{"description": "...", "status": "done|pending|running"}},
    ...
  ]
}}

Output JSON only, no markdown.
"""


class TaskPlanner:
    def __init__(self, client, tools: dict, long_term_memory=None):
        self._client = client
        self._tools = tools
        self._ltm = long_term_memory

    def generate_plan(self, task: str) -> TaskPlan:
        from src.llm.planner import build_tools_section
        tools_section = build_tools_section(self._tools)
        prompt = _PLAN_PROMPT.format(tools_section=tools_section, task=task)
        resp = self._client.chat([AgentMessage(role="user", content=prompt)])

        if resp.error or not resp.content:
            return TaskPlan(task=task, steps=[PlanStep(0, task, "failed", resp.error or "LLM error")])

        try:
            data = json.loads(resp.content)
            steps_data = data.get("plan", [])
        except json.JSONDecodeError:
            steps_data = [{"description": task}]

        steps = [PlanStep(i, d.get("description", ""), "pending") for i, d in enumerate(steps_data)]
        return TaskPlan(task=task, steps=steps)

    def execute_step(self, task: str, step: PlanStep, agent) -> ToolResult:
        from src.llm.planner import LLMPlanner
        planner = LLMPlanner(self._client, long_term_memory=self._ltm)
        decision = planner.plan(
            step.description,
            step.index + 1,
            available_tools=self._tools,
        )
        if decision.tool_name and decision.tool_name in self._tools:
            try:
                return self._tools[decision.tool_name](**decision.tool_args)
            except TypeError as e:
                return ToolResult(success=False, output="", error=f"invalid arguments: {e}")
            except Exception as e:
                return ToolResult(success=False, output="", error=str(e))
        if decision.answer:
            return ToolResult(success=True, output=decision.answer, error=None)
        return ToolResult(success=False, output="", error="no action taken")

    def revise_plan(self, plan: TaskPlan, failed_index: int, error: str) -> TaskPlan:
        plan_json = json.dumps([{"index": s.index, "description": s.description, "status": s.status}
                                for s in plan.steps], indent=2)
        failed_step = plan.steps[failed_index] if failed_index < len(plan.steps) else None
        failed_desc = failed_step.description if failed_step else "unknown"

        prompt = _REVISE_PROMPT.format(
            plan_json=plan_json,
            failed_index=failed_index,
            failed_description=failed_desc,
            error=error,
        )
        resp = self._client.chat([AgentMessage(role="user", content=prompt)])

        if resp.error or not resp.content:
            return plan

        try:
            data = json.loads(resp.content)
            steps_data = data.get("plan", [])
        except json.JSONDecodeError:
            return plan

        steps = []
        for d in steps_data:
            idx = d.get("index", len(steps))
            steps.append(PlanStep(
                idx,
                d.get("description", ""),
                d.get("status", "pending"),
                d.get("result", ""),
            ))
        return TaskPlan(task=plan.task, steps=steps)


def run_plan(
    task: str,
    tools: dict,
    client,
    long_term_memory=None,
    on_plan=None,
    on_step_event: Callable | None = None,
    cancel_check: Callable | None = None,
) -> tuple[TaskPlan, bool]:
    planner = TaskPlanner(client, tools, long_term_memory=long_term_memory)
    plan = planner.generate_plan(task)

    if on_plan:
        on_plan(plan)

    agent = None
    if tools:
        from src.llm.planner import LLMDevAgent
        agent = LLMDevAgent(client=client, tools=tools)

    all_steps_done = True
    for step in plan.steps:
        if cancel_check and cancel_check():
            step.status = "skipped"
            step.result = "cancelled"
            all_steps_done = False
            if on_plan:
                on_plan(plan)
            continue

        if step.status in ("done", "skipped"):
            continue

        step.status = "running"
        if on_plan:
            on_plan(plan)
        if on_step_event:
            on_step_event("plan_step_start", step.index, step.description)

        result = planner.execute_step(task, step, agent)

        if result.success:
            step.status = "done"
            step.result = result.output[:500]
            if on_step_event:
                on_step_event("plan_step_done", step.index, result.output[:200])
        else:
            step.status = "failed"
            step.result = result.error or "unknown error"
            all_steps_done = False
            if on_step_event:
                on_step_event("plan_step_failed", step.index, result.error)

            revised = planner.revise_plan(plan, step.index, result.error)
            if revised != plan:
                if on_step_event:
                    on_step_event("plan_revised", revised.total_steps)
                plan = revised
                if on_plan:
                    on_plan(plan)

        if on_plan:
            on_plan(plan)

    success = all_steps_done
    return plan, success
