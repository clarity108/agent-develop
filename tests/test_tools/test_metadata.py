import pytest

from src.tools.metadata import tool, ToolMetadata, ParameterSchema, get_tool_metadata


class TestToolDecorator:
    def test_attaches_metadata_to_function(self):
        @tool("reads a file")
        def read_file(path: str):
            return path

        meta = get_tool_metadata(read_file)
        assert isinstance(meta, ToolMetadata)
        assert meta.name == "read_file"
        assert meta.description == "reads a file"

    def test_preserves_function_behavior(self):
        @tool("adds two numbers")
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_metadata_name_matches_function_name(self):
        @tool("does something")
        def my_custom_tool():
            pass

        meta = get_tool_metadata(my_custom_tool)
        assert meta.name == "my_custom_tool"


class TestToolMetadata:
    def test_default_parameters_is_empty_dict(self):
        meta = ToolMetadata(name="test", description="test desc")
        assert meta.parameters == {}

    def test_parameters_can_be_set(self):
        meta = ToolMetadata(
            name="read_file",
            description="reads a file",
            parameters={
                "path": ParameterSchema(type="str", description="file path", required=True),
            },
        )
        assert meta.parameters["path"].type == "str"
        assert meta.parameters["path"].required is True


class TestGetToolMetadata:
    def test_none_for_plain_function(self):
        def plain_fn():
            pass

        assert get_tool_metadata(plain_fn) is None
