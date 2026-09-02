import pytest

from src.memory.session import SessionMemory


class TestSessionMemory:
    def test_add_and_get_messages(self):
        mem = SessionMemory()
        mem.add(role="user", content="hello")
        mem.add(role="assistant", content="hi there")
        msgs = mem.get_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "hi there"

    def test_add_with_metadata(self):
        mem = SessionMemory()
        mem.add(role="user", content="query", metadata={"source": "chat"})
        msgs = mem.get_messages()
        assert msgs[0]["metadata"] == {"source": "chat"}

    def test_clear_removes_all_messages(self):
        mem = SessionMemory()
        mem.add(role="user", content="a")
        mem.add(role="assistant", content="b")
        mem.clear()
        assert mem.get_messages() == []

    def test_limit_enforces_max_size(self):
        mem = SessionMemory(limit=3)
        mem.add(role="user", content="1")
        mem.add(role="assistant", content="2")
        mem.add(role="user", content="3")
        mem.add(role="assistant", content="4")
        msgs = mem.get_messages()
        assert len(msgs) == 3
        assert msgs[0]["content"] == "2"
        assert msgs[-1]["content"] == "4"

    def test_empty_session_returns_empty_list(self):
        mem = SessionMemory()
        assert mem.get_messages() == []
