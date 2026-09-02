import pytest

from src.agent.core import DevAgent, RuleBasedDevAgent, AgentResult
from src.tools.file_tools import ToolResult, read_file, write_file


class TestDevAgent:
    def test_register_and_list_tools(self):
        agent = DevAgent()
        agent.register_tool("read", read_file)
        agent.register_tool("write", write_file)
        assert agent.available_tools() == ["read", "write"]

    def test_run_unknown_tool(self):
        agent = RuleBasedDevAgent(
            rules=[{"match": "use", "tool": "nonexistent_tool", "args": {}}],
            tools={"read": read_file},
            max_steps=3,
        )
        result = agent.run("use nonexistent tool")
        assert result.success is False
        assert "unknown tool" in result.final_state.result

    def test_run_no_tools_terminates(self):
        agent = DevAgent(max_steps=3)
        result = agent.run("do something")
        assert result.steps > 0


class TestRuleBasedDevAgent:
    def test_run_with_matching_rule(self, tmp_path):
        target = tmp_path / "output.txt"
        agent = RuleBasedDevAgent(
            rules=[
                {"match": "write", "step": 1, "tool": "write_file", "args": {"path": str(target), "content": "hello"}},
                {"match": "write", "step": 2, "answer": "File written successfully."},
            ],
            tools={"write_file": write_file},
        )
        result = agent.run("write a file")
        assert result.success is True
        assert target.read_text() == "hello"

    def test_run_with_no_matching_rule(self):
        agent = RuleBasedDevAgent(
            rules=[],
            tools={},
        )
        result = agent.run("unknown task")
        assert result.success is True
        assert "don't have a rule" in result.final_state.result

    def test_state_has_step_count(self):
        agent = RuleBasedDevAgent(rules=[], tools={})
        agent.run("anything")
        assert agent.state.step >= 1

    def test_max_steps_respected(self):
        agent = RuleBasedDevAgent(
            rules=[
                {"match": "loop", "tool": "unknown_tool", "args": {}},
            ],
            tools={},
            max_steps=5,
        )
        result = agent.run("loop forever")
        assert result.steps <= 5

    def test_result_type_is_agent_result(self):
        agent = RuleBasedDevAgent(rules=[], tools={})
        result = agent.run("test")
        assert isinstance(result, AgentResult)
        assert hasattr(result, "task")
        assert hasattr(result, "success")
        assert hasattr(result, "steps")
