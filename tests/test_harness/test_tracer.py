import pytest

from src.harness.tracer import ExecutionTrace


class TestExecutionTrace:
    def test_start_and_end_trace(self):
        trace = ExecutionTrace()
        trace_id = trace.start("task-1")
        assert trace_id is not None
        trace.end(trace_id, status="completed")
        traces = trace.get_traces()
        assert len(traces) == 1
        assert traces[0]["status"] == "completed"
        assert "duration_ms" in traces[0]

    def test_add_steps(self):
        trace = ExecutionTrace()
        trace_id = trace.start("task-1")
        trace.step(trace_id, "read file")
        trace.step(trace_id, "write file")
        trace.end(trace_id, status="completed")
        t = trace.get_traces()[0]
        assert len(t["steps"]) == 2
        assert t["steps"][0]["action"] == "read file"

    def test_failed_trace(self):
        trace = ExecutionTrace()
        trace_id = trace.start("task-2")
        trace.step(trace_id, "execute command")
        trace.end(trace_id, status="failed", error="timeout")
        t = trace.get_traces()[0]
        assert t["status"] == "failed"
        assert t["error"] == "timeout"

    def test_multiple_traces(self):
        trace = ExecutionTrace()
        t1 = trace.start("task-1")
        trace.end(t1, status="completed")
        t2 = trace.start("task-2")
        trace.end(t2, status="failed", error="crash")
        traces = trace.get_traces()
        assert len(traces) == 2
        assert traces[0]["task"] == "task-1"
        assert traces[1]["task"] == "task-2"

    def test_unknown_trace_id_raises(self):
        trace = ExecutionTrace()
        with pytest.raises(KeyError):
            trace.step("nonexistent", "action")
