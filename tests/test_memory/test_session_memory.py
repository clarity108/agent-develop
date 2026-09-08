import json
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


class MockClient:
    def __init__(self, content="Summary of conversation."):
        self._content = content
        self._error = None
        self.calls = 0

    def chat(self, messages, tools=None, **kwargs):
        self.calls += 1
        from src.llm.client import ChatResponse
        if self._error:
            return ChatResponse(content="", error=self._error)
        return ChatResponse(content=self._content)


class TestCompression:
    def test_no_compression_below_threshold(self):
        mem = SessionMemory(summary_threshold=10)
        for i in range(5):
            mem.add("user", f"msg {i}")
            mem.add("assistant", f"resp {i}")
        client = MockClient()
        compressed = mem.maybe_compress(client)
        assert compressed is False
        assert mem.message_count() == 10
        assert mem.has_summary() is False

    def test_compression_triggers_above_threshold(self):
        mem = SessionMemory(summary_threshold=4, keep_recent=2)
        for i in range(6):
            mem.add("user", f"msg {i}")
            mem.add("assistant", f"resp {i}")
        client = MockClient(content="Summary of first 4 messages.")
        compressed = mem.maybe_compress(client)
        assert compressed is True
        assert mem.has_summary() is True
        assert mem.message_count() == 2

    def test_compression_keeps_recent_messages(self):
        mem = SessionMemory(summary_threshold=4, keep_recent=3)
        for i in range(8):
            mem.add("user", f"msg {i}")
            mem.add("assistant", f"resp {i}")
        client = MockClient(content="summary")
        mem.maybe_compress(client)
        msgs = mem.get_messages()
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "summary"
        recent = msgs[1:]
        assert len(recent) == 3

    def test_compression_appends_to_existing_summary(self):
        mem = SessionMemory(summary_threshold=4, keep_recent=2)
        for i in range(8):
            mem.add("user", f"msg {i}")
        client1 = MockClient(content="First summary.")
        mem.maybe_compress(client1)
        for i in range(10, 16):
            mem.add("user", f"msg {i}")
        client2 = MockClient(content="Second summary.")
        mem.maybe_compress(client2)
        msgs = mem.get_messages()
        assert "First summary." in msgs[0]["content"]
        assert "Second summary." in msgs[0]["content"]

    def test_compression_llm_error_restores_messages(self):
        mem = SessionMemory(summary_threshold=4, keep_recent=2)
        for i in range(8):
            mem.add("user", f"msg {i}")
        client = MockClient()
        client._error = "api timeout"
        compressed = mem.maybe_compress(client)
        assert compressed is False
        assert mem.message_count() == 8

    def test_compression_empty_summary_from_llm(self):
        mem = SessionMemory(summary_threshold=4, keep_recent=2)
        for i in range(8):
            mem.add("user", f"msg {i}")
            mem.add("assistant", f"resp {i}")
        client = MockClient(content="")
        compressed = mem.maybe_compress(client)
        assert compressed is False

    def test_get_messages_with_summary(self):
        mem = SessionMemory(summary_threshold=4, keep_recent=2)
        for i in range(8):
            mem.add("user", f"msg {i}")
            mem.add("assistant", f"resp {i}")
        mem.maybe_compress(MockClient(content="Summary here."))
        msgs = mem.get_messages()
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "Summary here."

    def test_summary_length(self):
        mem = SessionMemory(summary_threshold=4, keep_recent=2)
        for i in range(8):
            mem.add("user", f"msg {i}")
            mem.add("assistant", f"resp {i}")
        mem.maybe_compress(MockClient(content="A summary text."))
        assert mem.summary_length() == len("A summary text.")

    def test_total_count(self):
        mem = SessionMemory(summary_threshold=4, keep_recent=2)
        for i in range(8):
            mem.add("user", f"msg {i}")
        assert mem.total_count() == 8
        mem.maybe_compress(MockClient(content="summary"))
        assert mem.total_count() == mem.message_count() + 1

    def test_save_and_load_with_summary(self, tmp_path):
        mem = SessionMemory(summary_threshold=4, keep_recent=2)
        for i in range(8):
            mem.add("user", f"msg {i}")
            mem.add("assistant", f"resp {i}")
        mem.maybe_compress(MockClient(content="Saved summary."))

        store = str(tmp_path)
        mem.save_to_disk("conv1", store)

        mem2 = SessionMemory()
        loaded = mem2.load_from_disk("conv1", store)
        assert loaded is True
        assert mem2.has_summary() is True
        assert mem2.summary_length() > 0

        msgs = mem2.get_messages()
        assert msgs[0]["role"] == "system"
        assert "Saved summary." in msgs[0]["content"]

    def test_delete_from_disk(self, tmp_path):
        store = str(tmp_path)
        mem = SessionMemory()
        mem.add("user", "hello")
        mem.save_to_disk("conv1", store)
        mem.delete_from_disk("conv1", store)

        mem2 = SessionMemory()
        loaded = mem2.load_from_disk("conv1", store)
        assert loaded is False
