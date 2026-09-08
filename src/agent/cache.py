from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any


class ToolCache:
    def __init__(self, max_entries: int = 100):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_entries = max_entries

    @staticmethod
    def make_key(tool_name: str, args: dict) -> str:
        return f"{tool_name}:{json.dumps(args, sort_keys=True)}"

    def get(self, key: str) -> Any | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            while len(self._cache) >= self._max_entries:
                self._cache.popitem(last=False)
        self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()

    def invalidate_tool(self, tool_name: str) -> None:
        prefix = f"{tool_name}:"
        keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._cache[k]

    def invalidate_path(self, path: str) -> None:
        escaped = path.replace("\\", "\\\\")
        keys_to_remove = [k for k in self._cache if path in k or escaped in k]
        for k in keys_to_remove:
            del self._cache[k]

    @property
    def size(self) -> int:
        return len(self._cache)

    def stats(self) -> dict:
        return {"entries": self.size, "max": self._max_entries}
