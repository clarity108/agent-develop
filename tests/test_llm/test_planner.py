import json
import pytest

from src.llm.client import DashScopeLLMClient, ChatMessage, ChatResponse, UsageInfo
from src.llm.planner import LLMPlanner, LLMDevAgent


class TestLLMPlanner:
    def _make_client_with_response(self, response_text: str) -> DashScopeLLMClient:
        client = DashScopeLLMClient(api_key="test-key", model="test-model")

        class FakeResp:
            status_code = 200

            def json(self):
                return {
                    "choices": [{"message": {"role": "assistant", "content": response_text}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                }

        client._send = lambda url, body, headers: FakeResp()
        return client

    def test_plan_returns_decision_with_tool(self):
        response = json.dumps({
            "thought": "Need to read a file",
            "action": "use_tool",
            "tool_name": "read_file",
            "tool_args": {"path": "/tmp/foo.txt"},
            "answer": "",
        })
        client = self._make_client_with_response(response)
        planner = LLMPlanner(client)

        decision = planner.plan("read the config file", step=1, available_tools=["read_file", "write_file"])

        assert decision.tool_name == "read_file"
        assert decision.tool_args == {"path": "/tmp/foo.txt"}
        assert decision.action == "use_tool"

    def test_plan_returns_direct_answer(self):
        response = json.dumps({
            "thought": "Simple question",
            "action": "answer",
            "tool_name": None,
            "tool_args": {},
            "answer": "The answer is 42.",
        })
        client = self._make_client_with_response(response)
        planner = LLMPlanner(client)

        decision = planner.plan("what is the answer", step=1, available_tools=[])

        assert decision.tool_name is None
        assert decision.answer == "The answer is 42."

    def test_plan_handles_llm_error(self):
        client = DashScopeLLMClient(api_key="test-key", model="test-model")

        class FakeError:
            status_code = 500

            def json(self):
                return {"error": {"message": "rate limited"}}

        client._send = lambda url, body, headers: FakeError()
        planner = LLMPlanner(client)

        decision = planner.plan("do something", step=1, available_tools=["read_file"])
        assert "rate limited" in decision.thought
        assert "error" in decision.answer

    def test_plan_handles_invalid_json(self):
        client = self._make_client_with_response("not valid json at all")
        planner = LLMPlanner(client)

        decision = planner.plan("do something", step=1, available_tools=[])
        assert "Failed to parse" in decision.thought


class TestLLMDevAgent:
    def test_agent_uses_llm_to_choose_tool(self, tmp_path):
        from src.tools.file_tools import write_file

        target = tmp_path / "result.txt"
        step_counter = {"n": 0}

        client = DashScopeLLMClient(api_key="test-key", model="test-model")

        class FakeResp:
            status_code = 200

            def json(self):
                step_counter["n"] += 1
                if step_counter["n"] == 1:
                    content = json.dumps({
                        "thought": "Write a file",
                        "action": "use_tool",
                        "tool_name": "write_file",
                        "tool_args": {"path": str(target), "content": "llm generated"},
                        "answer": "",
                    })
                else:
                    content = json.dumps({
                        "thought": "Done",
                        "action": "answer",
                        "tool_name": None,
                        "tool_args": {},
                        "answer": "File written successfully.",
                    })
                return {
                    "choices": [{"message": {"role": "assistant", "content": content}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }

        client._send = lambda url, body, headers: FakeResp()
        agent = LLMDevAgent(client, tools={"write_file": write_file}, max_steps=5)

        result = agent.run("write something")
        assert result.success is True
        assert result.final_state.done is True
        assert target.read_text() == "llm generated"

    def test_agent_available_tools(self):
        client = DashScopeLLMClient(api_key="test-key", model="test-model")
        agent = LLMDevAgent(client, tools={})
        agent.register_tool("read", lambda **kw: None)
        assert "read" in agent.available_tools()
