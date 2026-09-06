from __future__ import annotations

import argparse
import sys

from src.agent.core import RuleBasedDevAgent
from src.harness.logger import AgentLogger
from src.harness.tracer import ExecutionTrace
from src.llm.config import load_config, build_client
from src.llm.planner import LLMDevAgent
from src.tools import (
    read_file, write_file, list_files, edit_file, search_in_file, grep_files,
    mkdir, mv_file, cp_file, rm_file,
    execute_command, execute_sandbox, execute_python, list_env,
    diff_file, apply_patch, preview_diff,
    create_generate_tests_tool, create_generate_tests_inline_tool,
    git_status, git_init, git_add_commit,
)
from src.loop.feedback import FeedbackLoop, PytestRunner

try:
    import uvicorn
except ImportError:
    uvicorn = None


def build_llm_agent():
    config = load_config("config/default.yaml")
    client = build_client(config["llm"])
    tools = {
        "read_file": read_file,
        "write_file": write_file,
        "list_files": list_files,
        "edit_file": edit_file,
        "search_in_file": search_in_file,
        "grep_files": grep_files,
        "mkdir": mkdir,
        "mv_file": mv_file,
        "cp_file": cp_file,
        "rm_file": rm_file,
        "execute_command": execute_command,
        "execute_sandbox": execute_sandbox,
        "execute_python": execute_python,
        "list_env": list_env,
        "diff_file": diff_file,
        "apply_patch": apply_patch,
        "preview_diff": preview_diff,
        "generate_tests": create_generate_tests_tool(client),
        "generate_tests_inline": create_generate_tests_inline_tool(client),
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
            "edit_file": edit_file,
            "search_in_file": search_in_file,
            "grep_files": grep_files,
            "mkdir": mkdir,
            "mv_file": mv_file,
            "cp_file": cp_file,
            "rm_file": rm_file,
            "execute_command": execute_command,
            "execute_sandbox": execute_sandbox,
            "execute_python": execute_python,
            "list_env": list_env,
            "diff_file": diff_file,
            "apply_patch": apply_patch,
            "preview_diff": preview_diff,
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
    parser.add_argument("--serve", action="store_true", help="Start the web console (uvicorn)")
    parser.add_argument("--eval", action="store_true", help="Run evaluation benchmarks")
    parser.add_argument("--plan", action="store_true", help="Generate and execute a multi-step plan before acting")
    parser.add_argument("--host", default="127.0.0.1", help="Web server host (--serve)")
    parser.add_argument("--port", type=int, default=8000, help="Web server port (--serve)")
    args = parser.parse_args()

    if args.eval:
        from src.eval.runner import run_eval
        results = run_eval()
        passed = sum(1 for r in results if r.success)
        sys.exit(0 if passed == len(results) else 1)

    if args.plan:
        from src.agent.task_planner import run_plan
        config = load_config("config/default.yaml")
        client = build_client(config["llm"])
        tools = {
            "read_file": read_file, "write_file": write_file, "list_files": list_files,
            "edit_file": edit_file, "search_in_file": search_in_file, "grep_files": grep_files,
            "mkdir": mkdir, "mv_file": mv_file, "cp_file": cp_file, "rm_file": rm_file,
            "execute_command": execute_command, "execute_sandbox": execute_sandbox,
            "execute_python": execute_python, "list_env": list_env,
            "diff_file": diff_file, "apply_patch": apply_patch, "preview_diff": preview_diff,
            "git_status": git_status, "git_init": git_init, "git_add_commit": git_add_commit,
        }

        def on_plan(plan):
            print(f"\n  [{'✓' if s.status == 'done' else '✗' if s.status == 'failed' else '→' if s.status == 'running' else '·'}] {s.index+1}. {s.description}")

        def on_step_event(event, idx, info):
            if event == "plan_step_start":
                print(f"  → executing step {idx+1}: {info}")
            elif event == "plan_step_done":
                print(f"  ✓ step {idx+1} done")
            elif event == "plan_step_failed":
                print(f"  ✗ step {idx+1} failed: {info}")
            elif event == "plan_revised":
                print(f"  ↻ plan revised ({info} steps)")

        print(f"\n{'='*60}")
        print(f"TASK PLAN: {args.task}")
        print(f"{'='*60}\n")
        plan, success = run_plan(args.task, tools, client, on_plan=on_plan, on_step_event=on_step_event)

        print(f"\n{'='*60}")
        print(f"RESULT: {'PASS' if success else 'FAIL'} ({plan.completed}/{plan.total_steps} steps)")
        print(f"{'='*60}\n")
        sys.exit(0 if success else 1)

    if args.serve:
        if uvicorn is None:
            print("uvicorn not installed. Run: pip install uvicorn[standard]")
            sys.exit(1)
        print(f"Web console: http://{args.host}:{args.port}")
        uvicorn.run("src.web.app:app", host=args.host, port=args.port)
        return

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
