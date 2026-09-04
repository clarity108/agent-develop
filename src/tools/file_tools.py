from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .metadata import tool


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None


@tool("Reads the content of a file at the given path")
def read_file(path: str) -> ToolResult:
    try:
        return ToolResult(success=True, output=Path(path).read_text())
    except FileNotFoundError:
        return ToolResult(success=False, output="", error=f"file not found: {path}")
    except PermissionError:
        return ToolResult(success=False, output="", error=f"permission denied: {path}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool("Writes content to a file, creating parent directories if needed")
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


@tool("Lists files in a directory, optionally recursively")
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


@tool("Edits a file by replacing old_text with new_text. old_text must match exactly (including whitespace and newlines). If old_text appears multiple times, use replace_all=True or provide more surrounding context for a unique match.")
def edit_file(path: str, old_text: str, new_text: str, replace_all: bool = False) -> ToolResult:
    try:
        if not old_text:
            return ToolResult(success=False, output="", error="old_text is empty")

        p = Path(path)
        if not p.exists():
            return ToolResult(success=False, output="", error=f"file not found: {path}")

        content = p.read_text()
        count = content.count(old_text)

        if count == 0:
            return ToolResult(
                success=False,
                output="",
                error=f"old_text not found in {path}. Read the file first and copy the exact text to replace.",
            )

        if count > 1 and not replace_all:
            return ToolResult(
                success=False,
                output="",
                error=f"old_text found {count} times in {path}. Provide more surrounding context for a unique match, or set replace_all=True.",
            )

        new_content = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)
        p.write_text(new_content)

        replacements = count if replace_all else 1
        return ToolResult(success=True, output=f"replaced {replacements} occurrence(s) in {path}")

    except PermissionError:
        return ToolResult(success=False, output="", error=f"permission denied: {path}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))
