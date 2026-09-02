from __future__ import annotations

import subprocess
import sys
from .file_tools import ToolResult


def execute_command(command: str, timeout: int = 30, cwd: str | None = None) -> ToolResult:
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
        output = proc.stdout.strip()
        if proc.returncode == 0:
            return ToolResult(success=True, output=output)
        stderr = (proc.stderr or "").strip()
        error = f"exit code {proc.returncode}"
        if stderr:
            error += f": {stderr}"
        return ToolResult(success=False, output=output, error=error)
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error=f"timeout: command exceeded {timeout}s")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))
