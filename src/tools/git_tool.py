from __future__ import annotations

from .command_tool import execute_command
from .file_tools import ToolResult
from .metadata import tool


@tool("Shows the git status of a repository in short format")
def git_status(cwd: str) -> ToolResult:
    result = execute_command("git status --short", cwd=cwd, timeout=10)
    if not result.success and "not a git repository" in (result.error or "").lower():
        return ToolResult(success=False, output="", error="not a git repository")
    if not result.success and "fatal" in (result.error or "").lower():
        return ToolResult(success=False, output="", error="not a git repository")
    return result


@tool("Initializes a new git repository in the given directory")
def git_init(cwd: str) -> ToolResult:
    result = execute_command("git init", cwd=cwd, timeout=10)
    if result.success:
        return ToolResult(success=True, output="initialized git repository")
    if "already exists" in (result.output + result.error).lower():
        return ToolResult(success=True, output="git repository already initialized")
    return result


@tool("Stages all changes and commits them with the given message")
def git_add_commit(cwd: str, message: str) -> ToolResult:
    add = execute_command("git add .", cwd=cwd, timeout=10)
    if not add.success:
        return add
    result = execute_command(f'git commit -m "{message}"', cwd=cwd, timeout=30)
    if result.success:
        return ToolResult(success=True, output=f"committed: {message}")
    if "nothing to commit" in (result.error or "").lower():
        return ToolResult(success=True, output="no changes to commit")
    return result
