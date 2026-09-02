import json
import pytest

from src.agent.core import DevAgent
from src.llm.client import DashScopeLLMClient, ChatMessage, ChatResponse, UsageInfo
from src.llm.planner import LLMPlanner, LLMDevAgent, build_system_prompt, build_tools_section
from src.tools.metadata import tool, ParameterSchema


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

    def test_llm_dev_agent_is_subclass_of_dev_agent(self):
        client = DashScopeLLMClient(api_key="test-key", model="test-model")
        agent = LLMDevAgent(client, tools={})
        assert isinstance(agent, DevAgent)

    def test_llm_dev_agent_has_session_memory(self):
        client = DashScopeLLMClient(api_key="test-key", model="test-model")
        agent = LLMDevAgent(client, tools={})
        assert agent.session_memory is not None

    def test_session_memory_receives_tool_results(self, tmp_path):
        from src.tools.file_tools import write_file

        target = tmp_path / "out.txt"
        step_counter = {"n": 0}
        client = DashScopeLLMClient(api_key="test-key", model="test-model")

        class FakeResp:
            status_code = 200

            def json(self):
                step_counter["n"] += 1
                if step_counter["n"] == 1:
                    content = json.dumps({
                        "thought": "Write",
                        "action": "use_tool",
                        "tool_name": "write_file",
                        "tool_args": {"path": str(target), "content": "hello"},
                        "answer": "",
                    })
                else:
                    content = json.dumps({
                        "thought": "Done",
                        "action": "answer",
                        "tool_name": None,
                        "tool_args": {},
                        "answer": "OK",
                    })
                return {
                    "choices": [{"message": {"role": "assistant", "content": content}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }

        client._send = lambda url, body, headers: FakeResp()
        agent = LLMDevAgent(client, tools={"write_file": write_file}, max_steps=5)
        agent.run("write file")

        messages = agent.session_memory.get_messages()
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles
        assert "tool" in roles


class TestBuildSystemPrompt:
    def test_prompt_contains_tool_descriptions(self):
        @tool("reads a file")
        def my_read(path: str):
            pass

        prompt = build_system_prompt({"my_read": my_read})
        assert "reads a file" in prompt
        assert "my_read" in prompt

    def test_prompt_contains_no_tools_message(self):
        prompt = build_system_prompt({})
        assert "No tools available" in prompt

    def test_prompt_contains_tool_name_for_undecorated(self):
        def plain_fn():
            pass

        prompt = build_system_prompt({"plain_fn": plain_fn})
        assert "plain_fn" in prompt
        assert "No description available" in prompt
