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


def _try_compile(pattern: str):
    import re
    try:
        return re.compile(pattern)
    except re.error:
        return re.compile(re.escape(pattern))


@tool("Searches for a pattern in a file and returns matching lines with line numbers. Pattern is treated as regex; if invalid regex, falls back to literal search. context shows surrounding lines.")
def search_in_file(path: str, pattern: str, context: int = 2, max_results: int = 50) -> ToolResult:
    try:
        p = Path(path)
        if not p.exists():
            return ToolResult(success=False, output="", error=f"file not found: {path}")

        lines = p.read_text().splitlines()
        rx = _try_compile(pattern)
        results = []

        for i, line in enumerate(lines):
            if len(results) >= max_results:
                break
            if rx.search(line):
                start = max(0, i - context)
                end = min(len(lines), i + context + 1)
                block_lines = []
                for j in range(start, end):
                    marker = ">>>" if j == i else "   "
                    block_lines.append(f"{marker} {j+1:>4}: {lines[j]}")
                results.append("\n".join(block_lines))

        if not results:
            return ToolResult(success=True, output=f"no matches for pattern: {pattern}")

        output = f"{len(results)} match(es) in {path}:\n\n" + "\n---\n".join(results)
        return ToolResult(success=True, output=output)

    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool("Searches for a pattern across files in a directory tree. Returns matching file paths and lines. Skips binary files and large files (>1MB).")
def grep_files(directory: str, pattern: str, recursive: bool = True, max_results: int = 50) -> ToolResult:
    try:
        base = Path(directory)
        if not base.is_dir():
            return ToolResult(success=False, output="", error=f"not a directory: {directory}")

        rx = _try_compile(pattern)
        results = []
        total_matches = 0

        pattern_glob = "**/*" if recursive else "*"
        for fpath in sorted(base.glob(pattern_glob)):
            if not fpath.is_file() or total_matches >= max_results:
                continue
            if fpath.stat().st_size > 1_000_000:
                continue

            try:
                lines = fpath.read_text(errors="replace").splitlines()
            except Exception:
                continue

            file_matches = []
            for i, line in enumerate(lines):
                if len(results) + len(file_matches) >= max_results:
                    break
                if rx.search(line):
                    file_matches.append(f"{fpath.relative_to(base)}:{i+1}: {line.strip()}")
                    total_matches += 1

            if file_matches:
                results.extend(file_matches)

        if not results:
            return ToolResult(success=True, output=f"no matches for pattern: {pattern} in {directory}")

        output = f"{len(results)} match(es) in {directory}:\n" + "\n".join(results)
        return ToolResult(success=True, output=output)

    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))
