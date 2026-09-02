from __future__ import annotations

import time
import uuid


class ExecutionTrace:
    def __init__(self):
        self._traces: dict[str, dict] = {}

    def start(self, task: str) -> str:
        trace_id = uuid.uuid4().hex[:8]
        self._traces[trace_id] = {
            "id": trace_id,
            "task": task,
            "status": "running",
            "steps": [],
            "started_at": time.monotonic(),
        }
        return trace_id

    def step(self, trace_id: str, action: str) -> None:
        if trace_id not in self._traces:
            raise KeyError(f"trace not found: {trace_id}")
        self._traces[trace_id]["steps"].append({
            "action": action,
            "at": time.monotonic(),
        })

    def end(self, trace_id: str, status: str, error: str | None = None) -> None:
        if trace_id not in self._traces:
            raise KeyError(f"trace not found: {trace_id}")
        trace = self._traces[trace_id]
        trace["status"] = status
        trace["duration_ms"] = round((time.monotonic() - trace["started_at"]) * 1000, 1)
        if error:
            trace["error"] = error

    def get_traces(self) -> list[dict]:
        return list(self._traces.values())
