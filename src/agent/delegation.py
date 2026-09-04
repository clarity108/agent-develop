from __future__ import annotations

from src.tools.file_tools import ToolResult
from src.tools.metadata import tool


def create_delegate_task_tool(client, tools: dict, long_term_memory=None, max_sub_steps: int = 10):
    @tool("Delegates a sub-task to a sub-agent that runs independently with a fresh context. The sub-agent has access to all standard tools (read_file, write_file, edit_file, list_files, execute_command, git_*). Use this for complex sub-tasks that would clutter the main conversation. The sub-agent will complete the task and return its result.")
    def delegate_task(description: str) -> ToolResult:
        from src.llm.planner import LLMDevAgent

        sub_tools = {k: v for k, v in tools.items() if k != "delegate_task"}
        sub_agent = LLMDevAgent(
            client=client,
            tools=sub_tools,
            max_steps=max_sub_steps,
            long_term_memory=long_term_memory,
        )
        try:
            result = sub_agent.run(description)
            return ToolResult(
                success=result.success,
                output=result.final_state.result,
                error=None if result.success else f"sub-agent failed after {result.steps} steps",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"sub-agent error: {e}")

    return delegate_task
