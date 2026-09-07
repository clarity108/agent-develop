from __future__ import annotations

import subprocess
from pathlib import Path

from .file_tools import ToolResult
from .metadata import tool


_REVIEW_PROMPT = """\
You are a senior software engineer performing a code review. Analyze the following
code and provide a structured review.

Source file: {filename}
```python
{source}
```

Review criteria:
1. **Bugs** — logic errors, off-by-one, race conditions, unhandled exceptions, type errors
2. **Security** — injection, path traversal, unsafe deserialization, hardcoded secrets, missing auth
3. **Performance** — O(n²) where O(n) suffices, unnecessary I/O, memory leaks, N+1 queries
4. **Style** — naming, structure, readability, missing type hints, unused imports
5. **Design** — coupling, cohesion, SOLID violations, missing abstractions

Output format (JSON only, no markdown):
{{
  "summary": "one paragraph overall assessment",
  "findings": [
    {{
      "severity": "critical|high|medium|low",
      "category": "bug|security|performance|style|design",
      "line": 42,
      "issue": "description of the problem",
      "fix": "how to fix it"
    }}
  ],
  "score": 7.5
}}

Score 0-10. No findings = 10. Be specific and actionable. Output JSON only.
"""


_DIFF_REVIEW_PROMPT = """\
You are a senior software engineer reviewing a code diff. Analyze the changes and
provide a structured review.

```diff
{diff}
```

Review criteria:
1. **Bugs** — logic errors introduced by changes
2. **Security** — new vulnerabilities, unsafe patterns
3. **Completeness** — missing edge cases, incomplete refactoring
4. **Tests** — missing test coverage for new code
5. **Style** — inconsistent naming, formatting

Output format (JSON only, no markdown):
{{
  "summary": "one paragraph overall assessment of the diff",
  "findings": [
    {{
      "severity": "critical|high|medium|low",
      "category": "bug|security|completeness|tests|style",
      "line": 42,
      "issue": "description of the problem",
      "fix": "how to fix it"
    }}
  ],
  "approved": true
}}

approved=true if no critical/high findings. Output JSON only.
"""


def create_code_review_tool(client):
    @tool("Reviews a Python source file and returns structured findings (bugs, security, performance, style)")
    def code_review(path: str) -> ToolResult:
        p = Path(path)
        if not p.exists():
            return ToolResult(success=False, output="", error=f"file not found: {path}")

        source = p.read_text()
        if len(source) > 15000:
            source = source[:15000] + "\n# [truncated]"

        from src.llm.messages import AgentMessage
        prompt = _REVIEW_PROMPT.format(filename=p.name, source=source)
        resp = client.chat([AgentMessage(role="user", content=prompt)])

        if resp.error:
            return ToolResult(success=False, output="", error=resp.error)

        return ToolResult(success=True, output=resp.content)

    return code_review


def create_diff_review_tool(client):
    @tool("Reviews a unified diff and returns structured findings about the changes")
    def diff_review(patch: str) -> ToolResult:
        from src.llm.messages import AgentMessage
        prompt = _DIFF_REVIEW_PROMPT.format(diff=patch[:10000])
        resp = client.chat([AgentMessage(role="user", content=prompt)])

        if resp.error:
            return ToolResult(success=False, output="", error=resp.error)

        return ToolResult(success=True, output=resp.content)

    return diff_review


def create_git_diff_review_tool(client):
    @tool("Reviews the current git diff (staged + unstaged) and returns structured findings")
    def git_diff_review(cwd: str = ".") -> ToolResult:
        try:
            proc = subprocess.run(
                ["git", "diff"],
                capture_output=True, text=True, timeout=10, cwd=cwd,
            )
            diff = proc.stdout
            if not diff.strip():
                return ToolResult(success=True, output="(no unstaged changes)")
            return ToolResult(success=True, output=_review_diff_with_client(client, diff))
        except FileNotFoundError:
            return ToolResult(success=False, output="", error="not a git repository")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    return git_diff_review


def _review_diff_with_client(client, diff: str) -> str:
    from src.llm.messages import AgentMessage
    prompt = _DIFF_REVIEW_PROMPT.format(diff=diff[:10000])
    resp = client.chat([AgentMessage(role="user", content=prompt)])
    if resp.error:
        return f"Review error: {resp.error}"
    return resp.content
