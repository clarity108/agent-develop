import pytest
import sys
from pathlib import Path

from src.tools.file_tools import ToolResult
from src.tools.command_tool import execute_command


class TestExecuteCommand:
    def test_successful_command(self):
        cmd = "python --version" if sys.platform != "win32" else "python --version"
        result = execute_command(cmd, timeout=10)
        assert result.success is True
        assert "Python" in result.output

    def test_command_stderr_on_failure(self):
        result = execute_command("python -c \"print(1/0)\"", timeout=10)
        assert result.success is False
        assert result.error is not None
        assert "zero" in result.error.lower() or "error" in result.error.lower()

    def test_command_timeout(self):
        if sys.platform == "win32":
            cmd = "ping -n 30 127.0.0.1"
        else:
            cmd = "sleep 30"
        result = execute_command(cmd, timeout=2)
        assert result.success is False
        assert "timeout" in result.error.lower()

    def test_command_with_working_directory(self, tmp_path: Path):
        (tmp_path / "marker.txt").write_text("here")
        result = execute_command("type marker.txt" if sys.platform == "win32" else "cat marker.txt",
                                 cwd=str(tmp_path), timeout=5)
        assert result.success is True
        assert "here" in result.output

    def test_command_returns_exit_code_info(self):
        if sys.platform == "win32":
            result = execute_command("cmd /c exit 42", timeout=5)
        else:
            result = execute_command("bash -c 'exit 42'", timeout=5)
        assert result.success is False
        assert "exit" in result.error.lower() or "42" in result.error or "error" in result.error.lower()
