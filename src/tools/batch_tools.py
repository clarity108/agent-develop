from __future__ import annotations

import shutil
from pathlib import Path

from .file_tools import ToolResult
from .metadata import tool


def _glob_safe(pattern: str, root: str = ".") -> list[Path]:
    root_p = Path(root)
    if not root_p.exists():
        return []
    return sorted(root_p.glob(pattern))


@tool("Find and replace text across multiple files matching a glob pattern")
def batch_replace(pattern: str, old_text: str, new_text: str, root: str = ".") -> ToolResult:
    files = _glob_safe(pattern, root)
    if not files:
        return ToolResult(success=False, output="", error=f"no files match pattern: {pattern}")

    results = []
    for f in files:
        if not f.is_file():
            continue
        content = f.read_text()
        count = content.count(old_text)
        if count == 0:
            continue
        new_content = content.replace(old_text, new_text)
        f.write_text(new_content)
        results.append(f"{f.name}: {count} replacement(s)")

    if not results:
        return ToolResult(success=True, output="no matches found in any file")
    return ToolResult(success=True, output=f"updated {len(results)} file(s):\n" + "\n".join(results))


@tool("Rename files matching a glob pattern using a search/replace pattern on filenames")
def batch_rename(pattern: str, old_name_part: str, new_name_part: str, root: str = ".") -> ToolResult:
    files = _glob_safe(pattern, root)
    if not files:
        return ToolResult(success=False, output="", error=f"no files match pattern: {pattern}")

    results = []
    for f in files:
        if not f.is_file():
            continue
        if old_name_part not in f.name:
            continue
        new_name = f.name.replace(old_name_part, new_name_part)
        new_path = f.parent / new_name
        if new_path.exists():
            results.append(f"{f.name}: SKIPPED (target exists)")
            continue
        f.rename(new_path)
        results.append(f"{f.name} -> {new_name}")

    if not results:
        return ToolResult(success=True, output="no files matched rename criteria")
    return ToolResult(success=True, output=f"renamed {len(results)} file(s):\n" + "\n".join(results))


@tool("Move multiple files matching a glob pattern to a target directory")
def batch_move(pattern: str, dest_dir: str, root: str = ".") -> ToolResult:
    files = _glob_safe(pattern, root)
    if not files:
        return ToolResult(success=False, output="", error=f"no files match pattern: {pattern}")

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    results = []
    for f in files:
        if not f.is_file():
            continue
        dest_path = dest / f.name
        if dest_path.exists():
            results.append(f"{f.name}: SKIPPED (target exists)")
            continue
        shutil.move(str(f), str(dest_path))
        results.append(f"{f.name} -> {dest}/")

    if not results:
        return ToolResult(success=True, output="no files to move")
    return ToolResult(success=True, output=f"moved {len(results)} file(s):\n" + "\n".join(results))


@tool("Delete multiple files matching a glob pattern")
def batch_delete(pattern: str, root: str = ".") -> ToolResult:
    files = _glob_safe(pattern, root)
    if not files:
        return ToolResult(success=False, output="", error=f"no files match pattern: {pattern}")

    results = []
    for f in files:
        if not f.is_file():
            continue
        f.unlink()
        results.append(f"deleted: {f.name}")

    if not results:
        return ToolResult(success=True, output="no files to delete")
    return ToolResult(success=True, output=f"deleted {len(results)} file(s):\n" + "\n".join(results))


@tool("Find text in files matching a glob pattern, reports filename and line numbers")
def find_in_files(pattern: str, search_text: str, root: str = ".") -> ToolResult:
    files = _glob_safe(pattern, root)
    if not files:
        return ToolResult(success=False, output="", error=f"no files match pattern: {pattern}")

    matches = []
    for f in files:
        if not f.is_file():
            continue
        try:
            lines = f.read_text().splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            if search_text in line:
                matches.append(f"{f.name}:{i}: {line.strip()[:100]}")

    if not matches:
        return ToolResult(success=True, output=f"no matches for '{search_text}' in {len(files)} file(s)")
    return ToolResult(success=True, output=f"found {len(matches)} match(es):\n" + "\n".join(matches))


@tool("Format Python files matching a glob pattern using black-style formatting")
def batch_format(pattern: str, root: str = ".") -> ToolResult:
    import subprocess
    import sys

    files = [f for f in _glob_safe(pattern, root) if f.suffix == ".py"]
    if not files:
        return ToolResult(success=False, output="", error=f"no .py files match pattern: {pattern}")

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "black", "--quiet", "--check", "--diff"] + [str(f) for f in files],
            capture_output=True, text=True, timeout=30,
        )
        diff = proc.stdout or ""
        if proc.returncode == 0:
            return ToolResult(success=True, output="all files already formatted")
        if not diff:
            return ToolResult(success=True, output="formatting needed but no diff output")
        return ToolResult(success=True, output=diff)
    except FileNotFoundError:
        return ToolResult(success=False, output="", error="black not installed — run: pip install black")
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error="timeout: formatting exceeded 30s")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))
