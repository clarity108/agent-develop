import pytest
from src.agent.delegation import create_delegate_task_tool
from src.tools.file_tools import ToolResult


class MockClient:
    def __init__(self):
        self._responses = []

    def add_response(self, response):
        self._responses.append(response)

    def chat(self, messages, tools=None, **kwargs):
        from src.llm.client import ChatResponse, ToolCall
        if self._responses:
            return self._responses.pop(0)
        return ChatResponse(content="", error="no response")

    def stream_chat(self, messages, tools=None, **kwargs):
        yield self.chat(messages)


class TestDelegateTaskTool:
    def test_creates_tool_function(self):
        client = MockClient()
        tools = {"read_file": lambda path: ToolResult(success=True, output="content")}
        tool_fn = create_delegate_task_tool(client, tools, max_sub_steps=5)
        assert tool_fn is not None
        assert callable(tool_fn)

    def test_tool_has_metadata(self):
        from src.tools.metadata import get_tool_metadata
        client = MockClient()
        tools = {}
        tool_fn = create_delegate_task_tool(client, tools, max_sub_steps=5)
        meta = get_tool_metadata(tool_fn)
        assert meta is not None
        assert "delegate" in meta.description.lower() or "sub" in meta.description.lower()

    def test_delegate_excludes_itself(self):
        client = MockClient()
        delegate_tool = create_delegate_task_tool(client, {}, max_sub_steps=3)
        result = delegate_tool("do something")
        assert isinstance(result, ToolResult)

    def test_delegate_success(self):
        client = MockClient()
        from src.llm.client import ChatResponse, ToolCall

        client.add_response(ChatResponse(content="", tool_calls=[
            ToolCall(id="c1", type="function", function_name="read_file", function_args={"path": "src/test.py"})
        ]))
        client.add_response(ChatResponse(content="I read the file. Content: hello world.", tool_calls=[]))

        tools = {"read_file": lambda path: ToolResult(success=True, output="hello world")}
        tool_fn = create_delegate_task_tool(client, tools, max_sub_steps=5)
        result = tool_fn("read src/test.py and report back")
        assert result.success
        assert "hello world" in result.output or "complete" in result.output.lower()

    def test_delegate_error_handling(self):
        client = MockClient()
        from src.llm.client import ChatResponse

        client.add_response(ChatResponse(content="", error="api timeout"))

        tools = {"read_file": lambda path: ToolResult(success=True, output="content")}
        tool_fn = create_delegate_task_tool(client, tools, max_sub_steps=2)
        result = tool_fn("read a file")
        assert isinstance(result, ToolResult)

    def test_custom_max_sub_steps(self):
        client = MockClient()
        tool_fn = create_delegate_task_tool(client, {}, max_sub_steps=1)
        result = tool_fn("do nothing")
        assert isinstance(result, ToolResult)
