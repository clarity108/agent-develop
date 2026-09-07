import pytest
import tempfile
from pathlib import Path

from src.agent.undo import UndoManager, FileSnapshot
from src.agent.core import DevAgent, Decision
from src.tools.file_tools import write_file


class TestUndoManagerBasics:
    def test_empty_undo_returns_error(self):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        result = mgr.undo()
        assert result is not None
        assert result["success"] is False
        assert "No undo available" in result["message"]

    def test_empty_redo_returns_error(self):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        result = mgr.redo()
        assert result is not None
        assert result["success"] is False
        assert "No redo available" in result["message"]

    def test_undo_count_empty(self):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        assert mgr.undo_count == 0

    def test_redo_count_empty(self):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        assert mgr.redo_count == 0

    def test_stack_info_empty(self):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        info = mgr.stack_info()
        assert info == {"undo": 0, "redo": 0}

    def test_clear_resets_all(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        f = tmp_path / "test.txt"
        f.write_text("original")
        mgr.before_change(str(f))
        f.write_text("modified")
        mgr.after_change(str(f))
        assert mgr.undo_count == 1
        mgr.clear()
        assert mgr.undo_count == 0
        assert mgr.redo_count == 0


class TestUndoModify:
    def test_undo_restores_original_content(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        f = tmp_path / "test.txt"
        f.write_text("original content")

        mgr.before_change(str(f))
        f.write_text("modified content")
        mgr.after_change(str(f))

        result = mgr.undo()
        assert result["success"] is True
        assert f.read_text() == "original content"

    def test_redo_restores_modified_content(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        f = tmp_path / "test.txt"
        f.write_text("original content")

        mgr.before_change(str(f))
        f.write_text("modified content")
        mgr.after_change(str(f))

        mgr.undo()
        result = mgr.redo()
        assert result["success"] is True
        assert f.read_text() == "modified content"

    def test_multiple_undo_redo(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        f = tmp_path / "test.txt"
        f.write_text("v1")

        # Change to v2
        mgr.before_change(str(f))
        f.write_text("v2")
        mgr.after_change(str(f))

        # Change to v3
        mgr.before_change(str(f))
        f.write_text("v3")
        mgr.after_change(str(f))

        assert mgr.undo_count == 2

        # Undo v3 → v2
        result = mgr.undo()
        assert result["success"] is True
        assert f.read_text() == "v2"

        # Undo v2 → v1
        result = mgr.undo()
        assert result["success"] is True
        assert f.read_text() == "v1"

        assert mgr.undo_count == 0
        assert mgr.redo_count == 2

        # Redo v1 → v2
        result = mgr.redo()
        assert result["success"] is True
        assert f.read_text() == "v2"

        # Redo v2 → v3
        result = mgr.redo()
        assert result["success"] is True
        assert f.read_text() == "v3"

        assert mgr.undo_count == 2
        assert mgr.redo_count == 0


class TestUndoCreate:
    def test_undo_newly_created_file(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        f = tmp_path / "newfile.txt"
        assert not f.exists()

        mgr.before_change(str(f))
        f.write_text("brand new content")
        mgr.after_change(str(f))

        result = mgr.undo()
        assert result["success"] is True
        assert not f.exists()

    def test_redo_newly_created_file(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        f = tmp_path / "newfile.txt"

        mgr.before_change(str(f))
        f.write_text("brand new content")
        mgr.after_change(str(f))

        mgr.undo()
        assert not f.exists()

        result = mgr.redo()
        assert result["success"] is True
        assert f.exists()
        assert f.read_text() == "brand new content"


class TestUndoDelete:
    def test_undo_deleted_file(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        f = tmp_path / "todelete.txt"
        f.write_text("content before delete")

        mgr.before_change(str(f))
        f.unlink()
        mgr.after_change(str(f))

        result = mgr.undo()
        assert result["success"] is True
        assert f.exists()
        assert f.read_text() == "content before delete"

    def test_redo_deleted_file(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        f = tmp_path / "todelete.txt"
        f.write_text("content before delete")

        mgr.before_change(str(f))
        f.unlink()
        mgr.after_change(str(f))

        mgr.undo()
        assert f.exists()

        result = mgr.redo()
        assert result["success"] is True
        assert not f.exists()


class TestUndoNewChangeClearsRedo:
    def test_new_change_clears_redo_stack(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        f = tmp_path / "test.txt"
        f.write_text("v1")

        mgr.before_change(str(f))
        f.write_text("v2")
        mgr.after_change(str(f))

        mgr.undo()
        assert mgr.redo_count == 1

        # New change clears redo
        f.write_text("v3")
        mgr.before_change(str(f))
        f.write_text("v4")
        mgr.after_change(str(f))

        assert mgr.redo_count == 0


class TestUndoFileSnapshot:
    def test_size_property(self):
        snap = FileSnapshot(path="test.txt", before=b"hello", after=b"world", exists_before=True)
        assert snap.size == 5

    def test_size_zero_when_none(self):
        snap = FileSnapshot(path="test.txt", before=None, after=b"world", exists_before=True)
        assert snap.size == 0

    def test_is_dir_default_false(self):
        snap = FileSnapshot(path="/tmp/dir", before=None, after=None, exists_before=True)
        assert snap.is_dir is False

    def test_is_dir_true(self):
        snap = FileSnapshot(path="/tmp/dir", before=None, after=None, exists_before=True, is_dir=True)
        assert snap.is_dir is True


class TestUndoDirectoryHandling:
    def test_undo_recreates_deleted_directory(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        d = tmp_path / "testdir"
        d.mkdir()

        mgr.before_change(str(d))
        import shutil
        shutil.rmtree(d)
        mgr.after_change(str(d))

        result = mgr.undo()
        assert result["success"] is True
        assert d.exists()
        assert d.is_dir()


class TestUndoIntegrationWithAgent:
    def test_agent_tracks_file_changes(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        target = tmp_path / "agent_test.txt"

        # Step 1: write file
        target.write_text("initial")

        calls = []
        def plan(task, step, **kwargs):
            if step == 1:
                return Decision(
                    thought="write file", action="use_tool",
                    tool_name="write_file",
                    tool_args={"path": str(target), "content": "step1"},
                )
            if step == 2:
                return Decision(
                    thought="edit file", action="use_tool",
                    tool_name="write_file",
                    tool_args={"path": str(target), "content": "step2"},
                )
            return Decision(thought="done", action="answer", answer="ok")

        agent = DevAgent(
            tools={"write_file": write_file},
            undo_manager=mgr,
            max_steps=3,
        )
        agent._plan = plan

        agent.run("test task")

        assert mgr.undo_count == 2
        result = mgr.undo()
        assert result["success"] is True
        assert target.read_text() == "step1"

        result = mgr.undo()
        assert result["success"] is True
        assert target.read_text() == "initial"

    def test_before_change_alone_does_not_add_to_undo_stack(self, tmp_path):
        mgr = UndoManager(snapshot_dir=tempfile.mkdtemp())
        f = tmp_path / "test.txt"
        f.write_text("content")

        # before_change alone doesn't add to undo stack
        mgr.before_change(str(f))
        assert mgr.undo_count == 0

        # Only after_change finalizes the snapshot
        f.write_text("changed")
        mgr.after_change(str(f))
        assert mgr.undo_count == 1
