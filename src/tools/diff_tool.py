from __future__ import annotations

import difflib
from pathlib import Path

from .file_tools import ToolResult
from .metadata import tool


def _read_lines(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    return p.read_text().splitlines(keepends=True)


def _compute_diff(old_lines: list[str], new_lines: list[str],
                  from_label: str = "a", to_label: str = "b") -> str:
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=from_label, tofile=to_label,
        lineterm="",
    )
    return "".join(diff)


@tool("Computes a unified diff between two files or between a file and new content")
def diff_file(path: str, new_content: str = "") -> ToolResult:
    p = Path(path)
    if not p.exists():
        return ToolResult(success=False, output="", error=f"file not found: {path}")

    old_lines = _read_lines(path)
    if new_content:
        new_lines = new_content.splitlines(keepends=True)
        if not new_lines or new_lines[-1] != "":
            if new_lines:
                new_lines[-1] += "\n"
    else:
        return ToolResult(success=False, output="", error="new_content is required")

    diff = _compute_diff(old_lines, new_lines, path, path)
    if not diff:
        return ToolResult(success=True, output="(no changes)")
    return ToolResult(success=True, output=diff)


@tool("Applies a unified diff patch to a file")
def apply_patch(path: str, patch: str) -> ToolResult:
    p = Path(path)
    if not p.exists():
        return ToolResult(success=False, output="", error=f"file not found: {path}")

    old_content = p.read_text()
    old_lines = old_content.splitlines(keepends=True)

    patch_lines = patch.splitlines(keepends=True)
    if not patch_lines or not patch_lines[0].startswith("---"):
        return ToolResult(success=False, output="", error="invalid patch format: expected unified diff")

    new_lines = list(old_lines)
    for line in patch_lines[2:]:
        if line.startswith("@@"):
            continue
        if line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith("-"):
            if new_lines:
                new_lines.pop()
        elif line.startswith(" "):
            if new_lines:
                new_lines.pop()
                new_lines.append(line[1:])

    p.write_text("".join(new_lines))
    return ToolResult(success=True, output=f"patch applied to {path}")


@tool("Shows the diff between current file content and what it would look like after applying changes")
def preview_diff(path: str, old_text: str, new_text: str) -> ToolResult:
    p = Path(path)
    if not p.exists():
        return ToolResult(success=False, output="", error=f"file not found: {path}")

    content = p.read_text()
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    if old_lines:
        old_lines[-1] = old_lines[-1] if old_lines[-1].endswith("\n") else old_lines[-1] + "\n"
    if new_lines:
        new_lines[-1] = new_lines[-1] if new_lines[-1].endswith("\n") else new_lines[-1] + "\n"

    diff = _compute_diff(old_lines, new_lines, path, path)
    return ToolResult(success=True, output=diff)
