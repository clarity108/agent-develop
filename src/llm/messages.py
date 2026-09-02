from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentMessage:
    role: str
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
