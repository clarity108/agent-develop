from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None


def read_file(path: str) -> ToolResult:
    try:
        return ToolResult(success=True, output=Path(path).read_text())
    except FileNotFoundError:
        return ToolResult(success=False, output="", error=f"file not found: {path}")
    except PermissionError:
        return ToolResult(success=False, output="", error=f"permission denied: {path}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def write_file(path: str, content: str) -> ToolResult:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return ToolResult(success=True, output=f"wrote {len(content)} chars to {path}")
    except PermissionError:
        return ToolResult(success=False, output="", error=f"permission denied: {path}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def list_files(directory: str, recursive: bool = False) -> ToolResult:
    try:
        base = Path(directory)
        if not base.is_dir():
            return ToolResult(success=False, output="", error=f"not a directory: {directory}")
        pattern = "**/*" if recursive else "*"
        entries = sorted(base.glob(pattern))
        names = [str(e.relative_to(base)).replace(os.sep, "/") for e in entries]
        return ToolResult(success=True, output="\n".join(names))
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))
