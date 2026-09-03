import os
import importlib
import pytest


class TestStorage:
    @pytest.fixture(autouse=True)
    def _storage(self, monkeypatch, tmp_path):
        db = str(tmp_path / "storage.db")
        monkeypatch.setenv("AGENT_HISTORY_DB", db)
        storage = importlib.import_module("src.web.storage")
        importlib.reload(storage)
        return storage

    def test_init_creates_table(self, _storage, tmp_path):
        _storage.init_db()
        db = tmp_path / "storage.db"
        assert db.exists()

    def test_save_and_list(self, _storage):
        _storage.init_db()
        _storage.save_run(
            run_id="abc123",
            task="create a file",
            use_llm=True,
            success=True,
            steps=3,
            elapsed=2.5,
            cancelled=False,
        )
        _storage.save_run(
            run_id="def456",
            task="hello",
            use_llm=False,
            success=False,
            steps=1,
            elapsed=0.5,
            cancelled=True,
        )
        runs = _storage.list_runs()
        assert len(runs) == 2
        first = runs[0]
        assert first["run_id"] == "def456"
        assert first["cancelled"] is True
        assert first["use_llm"] is False

    def test_list_respects_limit(self, _storage):
        _storage.init_db()
        for i in range(10):
            _storage.save_run(
                run_id=f"run-{i:04d}",
                task=f"task {i}",
                use_llm=True,
                success=True,
                steps=1,
                elapsed=0.1,
                cancelled=False,
            )
        assert len(_storage.list_runs(limit=5)) == 5

    def test_delete_all(self, _storage):
        _storage.init_db()
        _storage.save_run("a", "t", True, True, 1, 0.1, False)
        _storage.save_run("b", "t", True, True, 1, 0.1, False)
        assert _storage.delete_all_runs() == 2
        assert _storage.list_runs() == []

    def test_delete_run(self, _storage):
        _storage.init_db()
        _storage.save_run("a", "t", True, True, 1, 0.1, False)
        _storage.save_run("b", "t", True, True, 1, 0.1, False)
        _storage.delete_run("a")
        assert len(_storage.list_runs()) == 1
        assert _storage.list_runs()[0]["run_id"] == "b"

    def test_delete_run_not_found(self, _storage):
        _storage.init_db()
        assert _storage.delete_run("nonexistent") == 0

    def test_insert_or_replace_upsert(self, _storage):
        _storage.init_db()
        _storage.save_run("a", "t1", True, True, 1, 0.1, False)
        _storage.save_run("a", "t2", False, False, 5, 1.0, True)
        runs = _storage.list_runs()
        assert len(runs) == 1
        assert runs[0]["task"] == "t2"
        assert runs[0]["cancelled"] is True

    def test_save_and_list_with_conversation_id(self, _storage):
        _storage.init_db()
        _storage.save_run(
            run_id="a", task="first", use_llm=True, success=True,
            steps=1, elapsed=0.5, cancelled=False, conversation_id="conv1",
        )
        _storage.save_run(
            run_id="b", task="second", use_llm=True, success=True,
            steps=2, elapsed=1.0, cancelled=False, conversation_id="conv1",
        )
        _storage.save_run(
            run_id="c", task="other", use_llm=False, success=True,
            steps=1, elapsed=0.2, cancelled=False,
        )
        runs = _storage.list_runs()
        assert len(runs) == 3
        conv1_runs = [r for r in runs if r["conversation_id"] == "conv1"]
        assert len(conv1_runs) == 2
        assert conv1_runs[0]["task"] == "second"
        assert conv1_runs[1]["task"] == "first"
        standalone = [r for r in runs if not r["conversation_id"]]
        assert len(standalone) == 1
        assert standalone[0]["run_id"] == "c"
