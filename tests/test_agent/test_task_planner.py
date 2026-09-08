import json
import pytest
from dataclasses import dataclass, field
from typing import Any

from src.agent.task_planner import TaskPlan, PlanStep, TaskPlanner, run_plan
from src.llm.client import ChatResponse, ToolCall, UsageInfo
from src.llm.messages import AgentMessage
from src.tools.file_tools import ToolResult


class MockClient:
    def __init__(self, responses: list[ChatResponse] | None = None):
        self._responses = responses or []
        self._index = 0
        self.messages_log: list = []

    def chat(self, messages, tools=None, **kwargs) -> ChatResponse:
        self.messages_log.append(messages)
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp
        return ChatResponse(content="", error="no more responses")

    def stream_chat(self, messages, tools=None, **kwargs):
        yield self.chat(messages)


def _plan_response(steps: list[str]) -> ChatResponse:
    data = {"plan": [{"description": s} for s in steps]}
    return ChatResponse(content=json.dumps(data))


def _answer_response(answer: str) -> ChatResponse:
    return ChatResponse(content=f"Action: answer\nAnswer: {answer}")


def _tool_call_response(tool_name: str, args: dict) -> ChatResponse:
    tc = ToolCall(id="call_1", type="function", function_name=tool_name, function_args=args)
    return ChatResponse(content="", tool_calls=[tc])


def _error_response(error: str) -> ChatResponse:
    return ChatResponse(content="", error=error)


def _revised_plan_response(steps: list[dict]) -> ChatResponse:
    data = {"plan": steps}
    return ChatResponse(content=json.dumps(data))


class TestTaskPlan:
    def test_empty_plan(self):
        plan = TaskPlan(task="test")
        assert plan.total_steps == 0
        assert plan.completed == 0
        assert plan.current is None

    def test_plan_with_steps(self):
        plan = TaskPlan(task="test", steps=[
            PlanStep(0, "step 1", "pending"),
            PlanStep(1, "step 2", "done"),
            PlanStep(2, "step 3", "failed"),
        ])
        assert plan.total_steps == 3
        assert plan.completed == 1
        assert plan.current is not None
        assert plan.current.index == 0

    def test_current_running(self):
        plan = TaskPlan(task="test", steps=[
            PlanStep(0, "step 1", "done"),
            PlanStep(1, "step 2", "running"),
            PlanStep(2, "step 3", "pending"),
        ])
        assert plan.current.index == 1

    def test_to_dict(self):
        plan = TaskPlan(task="test", steps=[PlanStep(0, "step 1", "done", "result1")])
        d = plan.to_dict()
        assert d["task"] == "test"
        assert d["total"] == 1
        assert d["completed"] == 1
        assert d["steps"][0]["result"] == "result1"


class TestTaskPlanner:
    def test_generate_plan(self):
        client = MockClient([_plan_response(["step 1", "step 2", "step 3"])])
        planner = TaskPlanner(client, {})
        plan = planner.generate_plan("do something")
        assert plan.total_steps == 3
        assert plan.steps[0].description == "step 1"
        assert all(s.status == "pending" for s in plan.steps)

    def test_generate_plan_empty_response(self):
        client = MockClient([_error_response("api error")])
        planner = TaskPlanner(client, {})
        plan = planner.generate_plan("do something")
        assert plan.total_steps == 1
        assert plan.steps[0].status == "failed"

    def test_generate_plan_invalid_json(self):
        client = MockClient([ChatResponse(content="not json")])
        planner = TaskPlanner(client, {})
        plan = planner.generate_plan("do something")
        assert plan.total_steps == 1

    def test_execute_step_with_tool(self):
        tools_called = []
        def fake_tool(path):
            tools_called.append(("read_file", path))
            return ToolResult(success=True, output="file content")

        client = MockClient([_tool_call_response("read_file", {"path": "src/test.py"})])
        planner = TaskPlanner(client, {"read_file": fake_tool})
        step = PlanStep(0, "read a file", "running")
        result = planner.execute_step("task", step, None)
        assert result.success
        assert result.output == "file content"
        assert tools_called == [("read_file", "src/test.py")]

    def test_execute_step_with_answer(self):
        client = MockClient([_answer_response("The answer is 42")])
        planner = TaskPlanner(client, {})
        step = PlanStep(0, "answer the question", "running")
        result = planner.execute_step("task", step, None)
        assert result.success
        assert "42" in result.output

    def test_execute_step_invalid_args(self):
        def fake_tool(path):
            raise TypeError("missing required argument: 'content'")

        client = MockClient([_tool_call_response("write_file", {"path": "x"})])
        planner = TaskPlanner(client, {"write_file": fake_tool})
        step = PlanStep(0, "write a file", "running")
        result = planner.execute_step("task", step, None)
        assert not result.success
        assert "invalid arguments" in result.error

    def test_execute_step_unknown_tool(self):
        client = MockClient([_tool_call_response("unknown_tool", {})])
        planner = TaskPlanner(client, {})
        step = PlanStep(0, "do something", "running")
        result = planner.execute_step("task", step, None)
        assert not result.success

    def test_revise_plan(self):
        client = MockClient([_revised_plan_response([
            {"index": 0, "description": "step 1", "status": "done"},
            {"index": 1, "description": "fixed step 2", "status": "pending"},
        ])])
        planner = TaskPlanner(client, {})
        plan = TaskPlan(task="test", steps=[
            PlanStep(0, "step 1", "done"),
            PlanStep(1, "step 2", "failed"),
        ])
        revised = planner.revise_plan(plan, 1, "some error")
        assert revised.total_steps == 2
        assert revised.steps[1].description == "fixed step 2"

    def test_revise_plan_llm_error(self):
        client = MockClient([_error_response("api error")])
        planner = TaskPlanner(client, {})
        plan = TaskPlan(task="test", steps=[PlanStep(0, "step 1", "failed")])
        revised = planner.revise_plan(plan, 0, "error")
        assert revised == plan


class TestRunPlan:
    def test_successful_run(self):
        client = MockClient([
            _plan_response(["step 1", "step 2"]),
            _tool_call_response("read_file", {"path": "src/test.py"}),
            _tool_call_response("write_file", {"path": "src/output.py", "content": "done"}),
        ])

        tools_called = []
        def fake_read(path):
            tools_called.append(("read_file", path))
            return ToolResult(success=True, output="file content")
        def fake_write(path, content):
            tools_called.append(("write_file", path))
            return ToolResult(success=True, output=f"wrote to {path}")

        plan, success = run_plan(
            "process a file",
            {"read_file": fake_read, "write_file": fake_write},
            client,
        )
        assert success
        assert plan.completed == 2
        assert len(tools_called) == 2

    def test_run_with_failure_and_revision(self):
        client = MockClient([
            _plan_response(["step 1", "step 2"]),
            _tool_call_response("read_file", {"path": "missing.py"}),
            _revised_plan_response([
                {"index": 0, "description": "step 1", "status": "done"},
                {"index": 1, "description": "step 2 revised", "status": "pending"},
            ]),
            _tool_call_response("write_file", {"path": "src/out.py", "content": "ok"}),
        ])

        def fake_read(path):
            return ToolResult(success=False, output="", error="file not found: " + path)
        def fake_write(path, content):
            return ToolResult(success=True, output=f"wrote to {path}")

        events = []
        plan, success = run_plan(
            "process",
            {"read_file": fake_read, "write_file": fake_write},
            client,
            on_step_event=lambda e, *a: events.append(e),
        )
        assert "plan_step_failed" in events
        assert "plan_revised" in events

    def test_run_with_cancel(self):
        client = MockClient([
            _plan_response(["step 1", "step 2", "step 3"]),
            _tool_call_response("read_file", {"path": "x"}),
        ])

        cancel = [False, True]
        def cancel_check():
            return cancel[0]

        call_count = [0]
        def fake_read(path):
            call_count[0] += 1
            cancel[0] = True
            return ToolResult(success=True, output="ok")

        plan, success = run_plan(
            "task",
            {"read_file": fake_read},
            client,
            cancel_check=cancel_check,
        )
        assert not success

    def test_run_with_on_plan_callback(self):
        client = MockClient([
            _plan_response(["step 1"]),
            _tool_call_response("read_file", {"path": "x"}),
        ])

        def fake_read(path):
            return ToolResult(success=True, output="ok")

        plans_seen = []
        plan, success = run_plan(
            "task",
            {"read_file": fake_read},
            client,
            on_plan=lambda p: plans_seen.append(p.total_steps),
        )
        assert len(plans_seen) >= 2
        assert plans_seen[0] == 1
