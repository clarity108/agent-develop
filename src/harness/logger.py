from __future__ import annotations

from datetime import datetime, timezone


_LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}


class AgentLogger:
    def __init__(self, level: str = "DEBUG"):
        self._min_level = _LEVEL_ORDER.get(level, 0)
        self._entries: list[dict] = []

    def log(self, level: str, message: str, context: dict | None = None) -> dict:
        if _LEVEL_ORDER.get(level, 0) < self._min_level:
            return {}
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        }
        if context:
            entry["context"] = context
        self._entries.append(entry)
        return entry

    def get_entries(self) -> list[dict]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()
