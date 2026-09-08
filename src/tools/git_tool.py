from __future__ import annotations

import json

from .command_tool import execute_command
from .file_tools import ToolResult
from .metadata import tool


def _not_git_repo(error: str) -> ToolResult:
    return ToolResult(success=False, output="", error="not a git repository")


@tool("Shows the git status of a repository in short format")
def git_status(cwd: str) -> ToolResult:
    result = execute_command("git status --short", cwd=cwd, timeout=10)
    if not result.success and "not a git repository" in (result.error or "").lower():
        return _not_git_repo(result.error or "")
    if not result.success and "fatal" in (result.error or "").lower():
        return _not_git_repo(result.error or "")
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
    combined = (result.output or "") + (result.error or "")
    if "nothing to commit" in combined.lower():
        return ToolResult(success=True, output="no changes to commit")
    return result


@tool("Shows commit history with hash, author, date, and message for the last N commits")
def git_log(cwd: str, count: int = 10) -> ToolResult:
    count = max(1, min(count, 100))
    result = execute_command(f"git log --oneline -{count}", cwd=cwd, timeout=10)
    if not result.success:
        return _not_git_repo(result.error or "")
    return result


@tool("Lists all branches in the repository, showing the current branch")
def git_branch(cwd: str) -> ToolResult:
    result = execute_command("git branch -a", cwd=cwd, timeout=10)
    if not result.success:
        return _not_git_repo(result.error or "")
    return result


@tool("Shows the diff between two git refs or the working tree. Use 'git diff <ref>' to compare with a commit")
def git_diff(cwd: str, ref: str = "") -> ToolResult:
    if ref:
        cmd = f"git diff {ref} --stat && echo '---' && git diff {ref}"
    else:
        cmd = "git diff --stat && echo '---' && git diff"
    result = execute_command(cmd, cwd=cwd, timeout=30)
    if not result.success:
        return _not_git_repo(result.error or "")
    return result


@tool("Shows who wrote each line of a file (git blame)")
def git_blame(cwd: str, file_path: str) -> ToolResult:
    result = execute_command(f"git blame {file_path}", cwd=cwd, timeout=10)
    if not result.success:
        return _not_git_repo(result.error or "")
    return result
