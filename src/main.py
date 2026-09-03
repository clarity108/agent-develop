from __future__ import annotations

import argparse
import sys

from src.agent.core import RuleBasedDevAgent
from src.harness.logger import AgentLogger
from src.harness.tracer import ExecutionTrace
from src.llm.config import load_config, build_client
from src.llm.planner import LLMDevAgent
from src.tools import (
    read_file, write_file, list_files,
    execute_command, git_status, git_init, git_add_commit,
)
from src.loop.feedback import FeedbackLoop, PytestRunner


def build_llm_agent():
    config = load_config("config/default.yaml")
    client = build_client(config["llm"])
    tools = {
        "read_file": read_file,
        "write_file": write_file,
        "list_files": list_files,
        "execute_command": execute_command,
        "git_status": git_status,
        "git_init": git_init,
        "git_add_commit": git_add_commit,
    }
    return LLMDevAgent(client=client, tools=tools)


def build_rule_agent() -> RuleBasedDevAgent:
    return RuleBasedDevAgent(
        rules=[
            {"match": "read", "step": 1, "tool": "read_file",
             "args": {"path": "output.txt"}},
            {"match": "read", "step": 2, "answer": "File read successfully."},

            {"match": "create", "step": 1, "tool": "write_file",
             "args": {"path": "output.txt", "content": "created by agent"}},
            {"match": "create", "step": 2, "tool": "read_file",
             "args": {"path": "output.txt"}},
            {"match": "create", "step": 3, "answer": "File created and verified."},

            {"match": "commit", "step": 1, "tool": "git_status",
             "args": {"cwd": "."}},
            {"match": "commit", "step": 2, "tool": "git_add_commit",
             "args": {"cwd": ".", "message": "agent auto-commit"}},
            {"match": "commit", "step": 3, "answer": "Committed changes."},

            {"match": "init", "step": 1, "tool": "git_init",
             "args": {"cwd": "."}},
            {"match": "init", "step": 2, "answer": "Git repository initialized."},

            {"match": "list", "step": 1, "tool": "list_files",
             "args": {"directory": "."}},
            {"match": "list", "step": 2, "answer": "Files listed."},
        ],
        tools={
            "read_file": read_file,
            "write_file": write_file,
            "list_files": list_files,
            "execute_command": execute_command,
            "git_status": git_status,
            "git_init": git_init,
            "git_add_commit": git_add_commit,
        },
    )


def run_agent(task: str, cwd: str | None = None, use_llm: bool = True) -> None:
    logger = AgentLogger(level="DEBUG")
    tracer = ExecutionTrace()
    agent = build_llm_agent() if use_llm else build_rule_agent()
    agent_type = "llm" if use_llm else "rule"

    logger.log("INFO", f"Starting agent ({agent_type}) with task: {task}")
    trace_id = tracer.start(task)

    result = agent.run(task)

    tracer.step(trace_id, f"agent ran {result.steps} steps")
    if result.success:
        tracer.end(trace_id, status="completed")
        logger.log("INFO", f"Agent completed in {result.steps} steps")
    else:
        tracer.end(trace_id, status="failed", error=result.final_state.result)
        logger.log("ERROR", f"Agent failed: {result.final_state.result}")

    print(f">> Final: {result.final_state.result}")

    for entry in logger.get_entries():
        print(f"[{entry['level']}] {entry['message']}")

    sys.exit(0 if result.success else 1)


def main():
    parser = argparse.ArgumentParser(description="Autonomous Dev Agent")
    parser.add_argument("task", nargs="?", default="hello", help="Task description")
    parser.add_argument("--cwd", help="Working directory for tools")
    parser.add_argument("--rule", action="store_true", help="Use rule-based agent instead of LLM")
    parser.add_argument("--test", action="store_true", help="Run agent then pytest")
    args = parser.parse_args()

    if args.test:
        run_agent(args.task, cwd=args.cwd, use_llm=not args.rule)
        runner = PytestRunner(cwd=args.cwd)
        feedback = FeedbackLoop(max_retries=3)
        result = feedback.run(runner.run, runner.passed)
        print(f"Pytest: {'PASSED' if result.passed else 'FAILED'} ({result.attempts} attempts)")
        sys.exit(0 if result.passed else 1)

    run_agent(args.task, cwd=args.cwd, use_llm=not args.rule)


if __name__ == "__main__":
    main()
