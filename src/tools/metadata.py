from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParameterSchema:
    type: str
    description: str = ""
    required: bool = False


@dataclass
class ToolMetadata:
    name: str
    description: str
    parameters: dict[str, ParameterSchema] = field(default_factory=dict)


def tool(description: str):
    def decorator(fn):
        fn._tool_metadata = ToolMetadata(name=fn.__name__, description=description)
        return fn
    return decorator


def get_tool_metadata(fn):
    return getattr(fn, "_tool_metadata", None)
