from __future__ import annotations

import argparse
import sys

from src.agent.core import RuleBasedDevAgent
from src.harness.logger import AgentLogger
from src.harness.tracer import ExecutionTrace
from src.tools import read_file, write_file, execute_command, git_status, git_add_commit
from src.loop.feedback import FeedbackLoop, PytestRunner


def build_default_agent() -> RuleBasedDevAgent:
    return RuleBasedDevAgent(
        tools={
            "read_file": read_file,
            "write_file": write_file,
            "execute_command": execute_command,
            "git_status": git_status,
            "git_add_commit": git_add_commit,
        },
    )


def run_agent(task: str, cwd: str | None = None) -> None:
    logger = AgentLogger(level="DEBUG")
    tracer = ExecutionTrace()
    agent = build_default_agent()

    logger.log("INFO", f"Starting agent with task: {task}")
    trace_id = tracer.start(task)

    result = agent.run(task)

    tracer.step(trace_id, f"agent ran {result.steps} steps")
    if result.success:
        tracer.end(trace_id, status="completed")
        logger.log("INFO", f"Agent completed in {result.steps} steps")
    else:
        tracer.end(trace_id, status="failed", error=result.final_state.result)
        logger.log("ERROR", f"Agent failed: {result.final_state.result}")

    for entry in logger.get_entries():
        print(f"[{entry['level']}] {entry['message']}")

    sys.exit(0 if result.success else 1)


def main():
    parser = argparse.ArgumentParser(description="Autonomous Dev Agent")
    parser.add_argument("task", nargs="?", default="hello", help="Task description")
    parser.add_argument("--cwd", help="Working directory for tools")
    parser.add_argument("--test", action="store_true", help="Run agent then pytest")
    args = parser.parse_args()

    if args.test:
        agent = build_default_agent()
        agent.run(args.task)
        runner = PytestRunner(cwd=args.cwd)
        feedback = FeedbackLoop(max_retries=3)
        result = feedback.run(runner.run, runner.passed)
        print(f"Pytest: {'PASSED' if result.passed else 'FAILED'} ({result.attempts} attempts)")
        sys.exit(0 if result.passed else 1)

    run_agent(args.task, cwd=args.cwd)


if __name__ == "__main__":
    main()
