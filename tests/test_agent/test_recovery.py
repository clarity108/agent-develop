import os
import pytest
from src.agent.recovery import RecoveryManager, RecoveryResult


class TestPathSeparatorRecovery:
    def test_forward_slash_on_windows(self):
        if os.sep != "\\":
            pytest.skip("Windows-only test")
        rm = RecoveryManager()
        args = {"path": "src/foo.py"}
        result = rm.try_recover("read_file", args, "file not found: src/foo.py")
        assert result is not None
        assert result.recovered is True
        assert result.modified_args["path"] == "src\\foo.py"

    def test_backslash_on_linux(self):
        if os.sep == "\\":
            pytest.skip("Linux-only test")
        rm = RecoveryManager()
        args = {"path": "src\\foo.py"}
        result = rm.try_recover("read_file", args, "file not found: src\\foo.py")
        assert result is not None
        assert result.recovered is True
        assert result.modified_args["path"] == "src/foo.py"

    def test_same_separator_no_recovery(self):
        if os.sep == "\\":
            path = "src\\foo.py"
        else:
            path = "src/foo.py"
        rm = RecoveryManager()
        result = rm.try_recover("read_file", {"path": path}, "file not found: " + path)
        if result is not None and result.modified_args:
            assert result.modified_args["path"] != path or result.modified_args["path"] == path

    def test_no_recovery_for_non_file_error(self):
        rm = RecoveryManager()
        result = rm.try_recover("read_file", {"path": "src/foo.py"}, "permission denied")
        assert result is None or result.modified_args is None


class TestFileNotFoundSuggestion:
    def test_read_file_suggestion(self):
        rm = RecoveryManager()
        if os.sep == "\\":
            args = {"path": "src/app.py"}
        else:
            args = {"path": "src/app.py"}
        result = rm.try_recover("read_file", args, "file not found: " + args["path"])
        if result is not None and not result.recovered:
            assert "list_files" in result.suggestion

    def test_execute_command_suggestion(self):
        rm = RecoveryManager()
        result = rm.try_recover("execute_command", {"command": "cat src/app.py"}, "no such file or directory: src/app.py")
        assert result is not None
        assert "list_files" in result.suggestion


class TestEditPatternSuggestion:
    def test_edit_pattern_not_found(self):
        rm = RecoveryManager()
        if os.sep == "\\":
            path = "src\\app.py"
        else:
            path = "src/app.py"
        result = rm.try_recover("edit_file", {"path": path, "old_text": "foo", "new_text": "bar"}, f"old_text not found in {path}")
        assert result is not None
        assert result.recovered is False
        assert "read_file" in result.suggestion
        assert path in result.suggestion


class TestNotDirectorySuggestion:
    def test_not_a_directory(self):
        rm = RecoveryManager()
        result = rm.try_recover("list_files", {"directory": "src/app.py"}, "not a directory: src/app.py")
        assert result is not None
        assert "list_files" in result.suggestion
        assert "read_file" in result.suggestion


class TestSourceNotFoundSuggestion:
    def test_mv_file_source_not_found(self):
        rm = RecoveryManager()
        if os.sep == "\\":
            source = "src\\old.py"
        else:
            source = "src/old.py"
        result = rm.try_recover("mv_file", {"source": source, "destination": "src/new.py"}, f"source not found: {source}")
        if result is not None and not result.recovered:
            assert "list_files" in result.suggestion

    def test_cp_file_source_not_found(self):
        rm = RecoveryManager()
        if os.sep == "\\":
            source = "src\\old.py"
        else:
            source = "src/old.py"
        result = rm.try_recover("cp_file", {"source": source, "destination": "src/new.py"}, f"source not found: {source}")
        if result is not None and not result.recovered:
            assert "list_files" in result.suggestion


class TestPermissionSuggestion:
    def test_permission_denied(self):
        rm = RecoveryManager()
        result = rm.try_recover("write_file", {"path": "/etc/passwd", "content": "x"}, "permission denied: /etc/passwd")
        assert result is not None
        assert "execute_command" in result.suggestion


class TestCustomStrategy:
    def test_custom_strategy_first_priority(self):
        rm = RecoveryManager()
        def custom(tool_name, tool_args, error):
            return RecoveryResult(suggestion="custom suggestion")
        rm.register(custom)
        result = rm.try_recover("read_file", {"path": "x"}, "file not found: x")
        assert result is not None
        assert "custom" in result.suggestion

    def test_custom_strategy_no_match(self):
        rm = RecoveryManager()
        def custom(tool_name, tool_args, error):
            return None
        rm.register(custom)
        result = rm.try_recover("read_file", {"path": "x"}, "permission denied: x")
        assert result is not None


class TestEmptyError:
    def test_no_recovery_for_empty_error(self):
        rm = RecoveryManager()
        result = rm.try_recover("read_file", {"path": "x"}, "")
        assert result is None

    def test_no_recovery_for_none_error(self):
        rm = RecoveryManager()
        result = rm.try_recover("read_file", {"path": "x"}, None or "")
        assert result is None


class TestMultipleStrategies:
    def test_first_custom_wins(self):
        rm = RecoveryManager()
        def custom(tool_name, tool_args, error):
            return RecoveryResult(suggestion="custom")
        rm.register(custom)
        result = rm.try_recover("read_file", {"path": "x"}, "permission denied: x")
        assert result is not None
        assert "custom" in result.suggestion


class TestRecoveryInAgent:
    def test_recovery_adds_suggestion_to_error(self):
        from src.agent.core import RuleBasedDevAgent
        from src.tools.file_tools import ToolResult

        captured = []
        def fake_read(path):
            return ToolResult(success=False, output="", error=f"file not found: {path}")

        def on_step(event, step, *args):
            if event == "tool_result":
                captured.append((args[0], args[1]))

        agent = RuleBasedDevAgent(
            tools={"read_file": fake_read},
            rules=[
                {"match": "read", "tool": "read_file", "args": {"path": "src/missing.py"}, "step": 1},
                {"match": "read", "answer": "done", "step": 2},
            ],
        )
        agent.run("read file src/missing.py", on_step=on_step)
        assert len(captured) == 1
        tool_name, tool_result = captured[0]
        assert "SUGGESTION" in (tool_result.error or "")

    def test_recovery_retry_with_modified_args(self):
        from src.agent.core import RuleBasedDevAgent
        from src.tools.file_tools import ToolResult

        calls = []
        def fake_read(path):
            calls.append(path)
            if "CORRECT" in path:
                return ToolResult(success=True, output=f"content of {path}")
            return ToolResult(success=False, output="", error=f"file not found: {path}")

        if os.sep == "\\":
            wrong = "src/WRONG.py"
            correct = "src\\WRONG.py"
        else:
            wrong = "src\\WRONG.py"
            correct = "src/WRONG.py"

        agent = RuleBasedDevAgent(
            tools={"read_file": fake_read},
            rules=[
                {"match": "read", "tool": "read_file", "args": {"path": wrong}, "step": 1},
                {"match": "read", "answer": "done", "step": 2},
            ],
        )
        result = agent.run(f"read file {wrong}")
        assert len(calls) == 2
        assert calls[0] == wrong
        assert calls[1] == correct
        assert result.success

    def test_recovery_retry_failure_keeps_original_error(self):
        from src.agent.core import RuleBasedDevAgent
        from src.tools.file_tools import ToolResult

        def fake_read(path):
            return ToolResult(success=False, output="", error=f"file not found: {path}")

        captured = []
        def on_step(event, step, *args):
            if event == "tool_result":
                captured.append(args[1])

        if os.sep == "\\":
            wrong = "src/WRONG.py"
        else:
            wrong = "src\\WRONG.py"

        agent = RuleBasedDevAgent(
            tools={"read_file": fake_read},
            rules=[
                {"match": "read", "tool": "read_file", "args": {"path": wrong}, "step": 1},
                {"match": "read", "answer": "done", "step": 2},
            ],
        )
        agent.run(f"read file {wrong}", on_step=on_step)
        assert len(captured) == 1
        assert "file not found" in captured[0].error
