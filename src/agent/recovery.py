from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable


@dataclass
class RecoveryResult:
    recovered: bool = False
    modified_args: dict | None = None
    suggestion: str = ""


StrategyFn = Callable[[str, dict, str], RecoveryResult | None]


class RecoveryManager:
    def __init__(self):
        self._custom: list[StrategyFn] = []
        self._default: list[StrategyFn] = [
            _path_separator_recovery,
            _file_not_found_suggestion,
            _edit_pattern_suggestion,
            _not_directory_suggestion,
            _source_not_found_suggestion,
            _permission_suggestion,
        ]

    def register(self, fn: StrategyFn) -> None:
        self._custom.insert(0, fn)

    def try_recover(self, tool_name: str, tool_args: dict, error: str) -> RecoveryResult | None:
        if not error:
            return None
        for strategy in self._custom:
            try:
                result = strategy(tool_name, tool_args, error)
            except Exception:
                continue
            if result is not None:
                return result
        for strategy in self._default:
            try:
                result = strategy(tool_name, tool_args, error)
            except Exception:
                continue
            if result is not None:
                return result
        return None


_FILE_TOOLS = {"read_file", "write_file", "edit_file", "search_in_file", "grep_files", "mkdir", "mv_file", "cp_file", "rm_file", "list_files"}

_PATH_ARG_MAP = {
    "read_file": "path",
    "write_file": "path",
    "edit_file": "path",
    "search_in_file": "path",
    "grep_files": "directory",
    "mkdir": "path",
    "mv_file": "source",
    "cp_file": "source",
    "rm_file": "path",
    "list_files": "directory",
}


def _get_path(tool_name: str, tool_args: dict) -> str | None:
    key = _PATH_ARG_MAP.get(tool_name)
    if key:
        return tool_args.get(key)
    return None


def _has_wrong_separator(path: str) -> bool:
    if os.sep == "\\":
        return "/" in path and "\\" not in path
    return "\\" in path and "/" not in path


def _path_separator_recovery(tool_name: str, tool_args: dict, error: str) -> RecoveryResult | None:
    if "not found" not in error.lower() and "no such file" not in error.lower():
        return None
    path = _get_path(tool_name, tool_args)
    if not path or not _has_wrong_separator(path):
        return None

    if os.sep == "\\":
        alt = path.replace("/", "\\")
    else:
        alt = path.replace("\\", "/")

    return RecoveryResult(
        recovered=True,
        modified_args={**tool_args, **{_PATH_ARG_MAP[tool_name]: alt}},
        suggestion=f"Path '{path}' may need '{alt}' on this OS.",
    )


def _file_not_found_suggestion(tool_name: str, tool_args: dict, error: str) -> RecoveryResult | None:
    if "not found" not in error.lower() and "no such file" not in error.lower():
        return None
    if tool_name not in _FILE_TOOLS and tool_name != "execute_command":
        return None
    if tool_name == "execute_command":
        return RecoveryResult(suggestion="Use list_files(\".\") to check available files, or read_file() to verify the path exists.")
    path = _get_path(tool_name, tool_args)
    if not path:
        return None
    parent = os.path.dirname(path) or "."
    return RecoveryResult(suggestion=f"Use list_files(\"{parent}\") to check available files, or read_file(\"{path}\") to verify the path exists.")


def _edit_pattern_suggestion(tool_name: str, tool_args: dict, error: str) -> RecoveryResult | None:
    if tool_name != "edit_file":
        return None
    if "old_text not found" not in error:
        return None
    path = tool_args.get("path", "")
    return RecoveryResult(suggestion=f"Read the file with read_file(\"{path}\") first to see the exact content, then retry with matching text.")


def _not_directory_suggestion(tool_name: str, tool_args: dict, error: str) -> RecoveryResult | None:
    if "not a directory" not in error:
        return None
    path = tool_args.get("directory") or tool_args.get("path", "")
    if not path:
        return None
    parent = os.path.dirname(path) or "."
    return RecoveryResult(suggestion=f"Path '{path}' is not a directory. Use list_files(\"{parent}\") to check, or read_file(\"{path}\") if it's a file.")


def _source_not_found_suggestion(tool_name: str, tool_args: dict, error: str) -> RecoveryResult | None:
    if tool_name not in ("mv_file", "cp_file"):
        return None
    if "source not found" not in error:
        return None
    source = tool_args.get("source", "")
    parent = os.path.dirname(source) or "."
    return RecoveryResult(suggestion=f"Source '{source}' not found. Use list_files(\"{parent}\") to find the correct path.")


def _permission_suggestion(tool_name: str, tool_args: dict, error: str) -> RecoveryResult | None:
    if "permission denied" not in error.lower():
        return None
    return RecoveryResult(suggestion="Try using execute_command() to run the operation with elevated privileges, or check if the path is writable.")
