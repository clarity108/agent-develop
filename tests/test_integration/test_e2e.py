import pytest

from src.agent.core import RuleBasedDevAgent, AgentResult
from src.tools import read_file, write_file, execute_command, git_init
from src.memory.session import SessionMemory
from src.memory.long_term import LongTermMemory
from src.harness.logger import AgentLogger
from src.harness.tracer import ExecutionTrace
from src.loop.feedback import FeedbackLoop, PytestRunner


class TestEndToEnd:
    def test_agent_writes_and_reads_file(self, tmp_path):
        target = tmp_path / "agent_output.txt"
        agent = RuleBasedDevAgent(
            rules=[
                {"match": "create", "step": 1, "tool": "write_file",
                 "args": {"path": str(target), "content": "created by agent"}},
                {"match": "create", "step": 2, "tool": "read_file",
                 "args": {"path": str(target)}},
                {"match": "create", "step": 3, "answer": "Done."},
            ],
            tools={"write_file": write_file, "read_file": read_file},
        )
        result = agent.run("create a file")
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert target.read_text() == "created by agent"

    def test_full_pipeline_with_all_components(self, tmp_path):
        session = SessionMemory(limit=10)
        long_term = LongTermMemory(str(tmp_path / "memory"))
        logger = AgentLogger(level="DEBUG")
        tracer = ExecutionTrace()

        session.add("user", "create file")
        long_term.save("task", "create file")

        target = tmp_path / "output.txt"
        agent = RuleBasedDevAgent(
            rules=[
                {"match": "create", "step": 1, "tool": "write_file",
                 "args": {"path": str(target), "content": "hello"}},
                {"match": "create", "step": 2, "answer": "Done."},
            ],
            tools={"write_file": write_file},
        )

        logger.log("INFO", "pipeline start")
        trace_id = tracer.start("e2e-test")
        tracer.step(trace_id, "agent execution")

        result = agent.run("create file")

        tracer.step(trace_id, f"agent steps: {result.steps}")
        tracer.end(trace_id, status="completed")
        logger.log("INFO", "pipeline complete")

        assert result.success is True
        assert target.read_text() == "hello"
        assert long_term.load("task") == "create file"
        assert len(session.get_messages()) == 1
        assert len(logger.get_entries()) == 2
        assert tracer.get_traces()[0]["status"] == "completed"

    def test_feedback_loop_with_agent(self, tmp_path):
        target = tmp_path / "will_fail.txt"
        attempts = {"n": 0}

        def agent_action():
            attempts["n"] += 1
            if attempts["n"] >= 2:
                return write_file(str(target), f"attempt {attempts['n']}")
            return write_file(str(target), "bad")

        def validator(result):
            if not result.success:
                return False
            content = target.read_text() if target.exists() else ""
            return "attempt 2" in content

        loop = FeedbackLoop(max_retries=3)
        feedback = loop.run(agent_action, validator)
        assert feedback.passed is True
        assert feedback.attempts == 2
        assert target.read_text() == "attempt 2"

    def test_agent_state_exposed_via_harness(self):
        agent = RuleBasedDevAgent(rules=[], tools={})
        logger = AgentLogger()
        tracer = ExecutionTrace()

        trace_id = tracer.start("state-check")
        tracer.step(trace_id, "run agent")

        result = agent.run("anything")

        logger.log("INFO", f"steps: {result.steps}", context={"steps": result.steps})
        tracer.end(trace_id, status="completed")

        assert agent.state.step >= 1
        assert logger.get_entries()[0]["context"]["steps"] == result.steps
