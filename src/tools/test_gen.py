from __future__ import annotations

from pathlib import Path

from .file_tools import ToolResult
from .metadata import tool


_GENERATE_PROMPT = """\
You are a senior Python test engineer. Analyze the following source code and generate
comprehensive pytest test cases.

Source file: {filename}
```python
{source}
```

Requirements:
1. Cover all public functions and classes
2. Include edge cases: None inputs, empty inputs, boundary values, error conditions
3. Use descriptive test names: test_function_name_condition
4. Use pytest fixtures where appropriate
5. Mock external dependencies
6. Include both happy path and failure scenarios
7. Keep tests independent (no shared state between tests)
8. Use parametrization for multiple input/output pairs

Output ONLY the test code as a Python file. No markdown, no explanation.

Start with:
```python
"""Tests for {filename}."""
import pytest
```
"""


def _extract_code(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines)
        for i, line in enumerate(lines):
            if i > 0 and line.strip() == "```":
                end = i
                break
        return "\n".join(lines[start:end])
    return text


def create_generate_tests_tool(client):
    @tool("Generates pytest test cases for a Python source file using LLM analysis")
    def generate_tests(source_path: str, test_path: str | None = None) -> ToolResult:
        p = Path(source_path)
        if not p.exists():
            return ToolResult(success=False, output="", error=f"file not found: {source_path}")

        source = p.read_text()
        if len(source) > 15000:
            source = source[:15000] + "\n# [truncated]"

        from src.llm.messages import AgentMessage
        prompt = _GENERATE_PROMPT.format(filename=p.name, source=source)
        resp = client.chat([AgentMessage(role="user", content=prompt)])

        if resp.error:
            return ToolResult(success=False, output="", error=resp.error)

        content = _extract_code(resp.content)
        tp = Path(test_path or _default_test_path(source_path))
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(content)

        return ToolResult(success=True, output=f"Tests generated: {test_path}\n\n{content}")

    return generate_tests


def create_generate_tests_inline_tool(client):
    @tool("Generates pytest test code from inline source code using LLM analysis")
    def generate_tests_inline(source_code: str, filename: str = "module.py") -> ToolResult:
        if len(source_code) > 15000:
            source_code = source_code[:15000] + "\n# [truncated]"

        from src.llm.messages import AgentMessage
        prompt = _GENERATE_PROMPT.format(filename=filename, source=source_code)
        resp = client.chat([AgentMessage(role="user", content=prompt)])

        if resp.error:
            return ToolResult(success=False, output="", error=resp.error)

        content = _extract_code(resp.content)
        return ToolResult(success=True, output=content)

    return generate_tests_inline


def _default_test_path(source_path: str) -> str:
    p = Path(source_path)
    return str(p.parent / f"test_{p.stem}.py")
