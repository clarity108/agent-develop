from src.llm.messages import AgentMessage


class TestAgentMessage:
    def test_user_message(self):
        msg = AgentMessage(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.tool_call_id is None
        assert msg.tool_name is None

    def test_tool_result_message(self):
        msg = AgentMessage(role="tool", content="file contents", tool_call_id="call_123")
        assert msg.role == "tool"
        assert msg.tool_call_id == "call_123"
        assert msg.content == "file contents"

    def test_assistant_tool_call_message(self):
        msg = AgentMessage(role="assistant", content='{"tool_name":"read_file"}', tool_name="read_file")
        assert msg.role == "assistant"
        assert msg.tool_name == "read_file"

    def test_system_message(self):
        msg = AgentMessage(role="system", content="You are an agent")
        assert msg.role == "system"
        assert msg.content == "You are an agent"
