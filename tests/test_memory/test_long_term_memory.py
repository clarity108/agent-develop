import pytest

from src.memory.long_term import LongTermMemory


class TestLongTermMemory:
    def test_save_and_load_string(self, tmp_path):
        store = LongTermMemory(str(tmp_path))
        store.save("user_name", "Alice")
        assert store.load("user_name") == "Alice"

    def test_save_and_load_dict(self, tmp_path):
        store = LongTermMemory(str(tmp_path))
        data = {"project": "agent", "language": "python"}
        store.save("project_info", data)
        assert store.load("project_info") == data

    def test_load_missing_key_returns_none(self, tmp_path):
        store = LongTermMemory(str(tmp_path))
        assert store.load("nonexistent") is None

    def test_list_keys(self, tmp_path):
        store = LongTermMemory(str(tmp_path))
        store.save("a", 1)
        store.save("b", 2)
        store.save("c", 3)
        keys = store.list_keys()
        assert set(keys) == {"a", "b", "c"}

    def test_delete_key(self, tmp_path):
        store = LongTermMemory(str(tmp_path))
        store.save("temp", "value")
        assert store.load("temp") == "value"
        store.delete("temp")
        assert store.load("temp") is None

    def test_overwrite_existing_key(self, tmp_path):
        store = LongTermMemory(str(tmp_path))
        store.save("key", "old")
        store.save("key", "new")
        assert store.load("key") == "new"
