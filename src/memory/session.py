from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Message:
    role: str
    content: str
    metadata: dict = field(default_factory=dict)


class SessionMemory:
    def __init__(self, limit: int | None = None):
        self._messages: list[dict] = []
        self._limit = limit

    def add(self, role: str, content: str, metadata: dict | None = None) -> None:
        entry = {"role": role, "content": content}
        if metadata:
            entry["metadata"] = metadata
        self._messages.append(entry)
        if self._limit and len(self._messages) > self._limit:
            self._messages = self._messages[-self._limit:]

    def get_messages(self) -> list[dict]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()
