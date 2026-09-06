from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .file_tools import ToolResult
from .metadata import tool

_MAX_OUTPUT = 100_000
_FORBIDDEN = ("rm -rf /", "rm -rf ~", "mkfs", "dd if=", ":(){", "shutdown", "reboot", "halt")


def _check_forbidden(cmd: str) -> str | None:
    cmd_lower = cmd.lower().strip()
    for pattern in _FORBIDDEN:
        if pattern in cmd_lower:
            return f"forbidden command: {pattern}"
    return None


def _truncate(text: str) -> str:
    if len(text) > _MAX_OUTPUT:
        return text[:_MAX_OUTPUT] + f"\n... [truncated, {len(text)} total chars]"
    return text


@tool("Executes a shell command in a sandboxed environment with output limits and safety checks")
def execute_sandbox(command: str, timeout: int = 30, cwd: str | None = None) -> ToolResult:
    forbidden = _check_forbidden(command)
    if forbidden:
        return ToolResult(success=False, output="", error=forbidden)

    try:
        shell = sys.platform == "win32"
        proc = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        stdout = _truncate(proc.stdout or "")
        stderr = _truncate(proc.stderr or "")
        if proc.returncode == 0:
            return ToolResult(success=True, output=stdout)
        error = f"exit code {proc.returncode}"
        if stderr:
            error += f": {stderr}"
        return ToolResult(success=False, output=stdout, error=error)
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error=f"timeout: exceeded {timeout}s")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool("Executes Python code in a sandboxed temporary directory, returns stdout/stderr")
def execute_python(code: str, timeout: int = 30) -> ToolResult:
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "_agent_script.py"
            script_path.write_text(code)
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
            stdout = _truncate(proc.stdout or "")
            stderr = _truncate(proc.stderr or "")
            if proc.returncode == 0:
                return ToolResult(success=True, output=stdout)
            error = f"exit code {proc.returncode}"
            if stderr:
                error += f": {stderr}"
            return ToolResult(success=False, output=stdout, error=error)
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error=f"timeout: exceeded {timeout}s")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool("Reads the environment variables available to the agent")
def list_env() -> ToolResult:
    try:
        safe_env = {k: v for k, v in os.environ.items()
                    if k not in ("PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP", "HOMEPATH", "USERPROFILE", "APPDATA", "LOCALAPPDATA")}
        return ToolResult(success=True, output="\n".join(f"{k}={v}" for k, v in sorted(safe_env.items())))
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))
