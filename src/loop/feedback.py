from __future__ import annotations

from dataclasses import dataclass
from src.tools.file_tools import ToolResult


@dataclass
class FeedbackResult:
    passed: bool
    feedback: str
    attempts: int


class FeedbackLoop:
    def __init__(self, max_retries: int = 3):
        self._max_retries = max_retries

    def run(self, action, validator):
        attempts = 0
        last_error = ""

        while attempts < self._max_retries:
            attempts += 1
            result = action()

            if validator(result):
                return FeedbackResult(passed=True, feedback="validated", attempts=attempts)

            last_error = f"attempt {attempts} failed"

        return FeedbackResult(passed=False, feedback=last_error, attempts=attempts)


class PytestRunner:
    def __init__(self, command: str = "python -m pytest", cwd: str | None = None, timeout: int = 60):
        self._command = command
        self._cwd = cwd
        self._timeout = timeout

    def run(self):
        from src.tools.command_tool import execute_command
        return execute_command(self._command, cwd=self._cwd, timeout=self._timeout)

    def passed(self, result: ToolResult) -> bool:
        return result.success


class RetryConfig:
    def __init__(self, max_retries: int = 3, backoff_factor: float = 1.0):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
