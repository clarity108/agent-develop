from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Message:
    role: str
    content: str
    metadata: dict = field(default_factory=dict)


_SUMMARY_PROMPT = """\
You are a conversation summarizer. Given the following conversation history between an AI agent and a developer, produce a concise summary (max 3-4 sentences) capturing:
1. What tasks were requested and performed
2. Key decisions, tool calls, and their results
3. Important file paths, values, or outputs
4. Any ongoing or incomplete work

Conversation:
{transcript}

Output only the summary text. No markdown, no labels, no headers."""


class SessionMemory:
    def __init__(
        self,
        limit: int | None = None,
        summary_threshold: int = 16,
        keep_recent: int = 6,
    ):
        self._messages: list[dict] = []
        self._limit = limit
        self._summary_threshold = summary_threshold
        self._keep_recent = keep_recent
        self._summary = ""

    def add(self, role: str, content: str, metadata: dict | None = None) -> None:
        entry = {"role": role, "content": content}
        if metadata:
            entry["metadata"] = metadata
        self._messages.append(entry)
        if self._limit and len(self._messages) > self._limit:
            self._messages = self._messages[-self._limit:]

    def get_messages(self) -> list[dict]:
        msgs = []
        if self._summary:
            msgs.append({"role": "system", "content": self._summary})
        msgs.extend(self._messages)
        return msgs

    def maybe_compress(self, client) -> bool:
        if len(self._messages) <= self._summary_threshold:
            return False
        split = len(self._messages) - self._keep_recent
        if split <= 0:
            return False
        from src.llm.messages import AgentMessage

        old = self._messages[:split]
        self._messages = self._messages[split:]
        transcript = "\n".join(
            f"[{m['role']}]: {m['content']}" for m in old
        )
        prompt = _SUMMARY_PROMPT.format(transcript=transcript)
        resp = client.chat([AgentMessage(role="user", content=prompt)])
        if resp.error or not resp.content:
            self._messages = old + self._messages
            return False
        if self._summary:
            self._summary += "\n"
        self._summary = (self._summary + resp.content.strip()).strip()
        return True

    def has_summary(self) -> bool:
        return bool(self._summary)

    def summary_length(self) -> int:
        return len(self._summary)

    def message_count(self) -> int:
        return len(self._messages)

    def total_count(self) -> int:
        return (1 if self._summary else 0) + len(self._messages)

    def clear(self) -> None:
        self._messages.clear()
        self._summary = ""

    def save_to_disk(self, conversation_id: str, store_dir: str) -> None:
        data = {
            "messages": self._messages,
            "summary": self._summary,
        }
        path = Path(store_dir) / f"{conversation_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def load_from_disk(self, conversation_id: str, store_dir: str) -> bool:
        path = Path(store_dir) / f"{conversation_id}.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
            self._messages = data.get("messages", [])
            self._summary = data.get("summary", "")
            return True
        except Exception:
            return False

    def delete_from_disk(self, conversation_id: str, store_dir: str) -> None:
        path = Path(store_dir) / f"{conversation_id}.json"
        if path.exists():
            path.unlink()
