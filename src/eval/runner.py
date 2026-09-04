from __future__ import annotations

import time
from dataclasses import dataclass

from src.agent.core import DevAgent, AgentResult
from src.eval.benchmarks import Benchmark, get_benchmarks


@dataclass
class EvalResult:
    name: str
    success: bool
    steps: int
    elapsed: float
    result: str
    error: str | None = None


def _build_eval_agent(benchmark: Benchmark):
    from src.llm.config import load_config, build_client
    from src.llm.planner import LLMDevAgent
    from src.agent.core import RuleBasedDevAgent
    from src.tools import (
        read_file, write_file, list_files, edit_file,
        search_in_file, grep_files, mkdir, mv_file, cp_file, rm_file,
        execute_command, git_status, git_init, git_add_commit,
    )

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
        "git_status": git_status,
        "git_init": git_init,
        "git_add_commit": git_add_commit,
    }

    if benchmark.use_llm:
        config = load_config("config/default.yaml")
        client = build_client(config["llm"])
        return LLMDevAgent(client=client, tools=tools, max_steps=benchmark.max_steps)

    return RuleBasedDevAgent(
        rules=[
            {"match": "create", "step": 1, "tool": "write_file",
             "args": {"path": "output.txt", "content": "created by agent"}},
            {"match": "create", "step": 2, "tool": "read_file",
             "args": {"path": "output.txt"}},
            {"match": "create", "step": 3, "answer": "File created and verified."},
            {"match": "read", "step": 1, "tool": "read_file",
             "args": {"path": "output.txt"}},
            {"match": "read", "step": 2, "answer": "File read successfully."},
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
        tools=tools,
        max_steps=benchmark.max_steps,
    )


def run_eval(benchmarks: list[Benchmark] | None = None) -> list[EvalResult]:
    if benchmarks is None:
        benchmarks = get_benchmarks()

    results = []
    total_start = time.time()

    print(f"\n{'='*60}")
    print(f"AGENT EVALUATION — {len(benchmarks)} benchmark(s)")
    print(f"{'='*60}\n")

    for bm in benchmarks:
        agent_type = "LLM" if bm.use_llm else "RULE"
        print(f"  [{agent_type}] {bm.name}...", end=" ", flush=True)

        agent = _build_eval_agent(bm)
        start = time.time()
        try:
            result = agent.run(bm.task)
            elapsed = time.time() - start
            passed = bm.check(result.final_state.result)
            success = result.success and passed and elapsed <= bm.max_time

            if success:
                print(f"OK  ({result.steps} steps, {elapsed:.1f}s)")
            else:
                print(f"FAIL  ({result.steps} steps, {elapsed:.1f}s)")
                if not result.success:
                    print(f"        error: {result.final_state.result[:100]}")
                elif not passed:
                    print(f"        check failed: {result.final_state.result[:100]}")
                elif elapsed > bm.max_time:
                    print(f"        timeout: {elapsed:.1f}s > {bm.max_time:.1f}s")

            results.append(EvalResult(
                name=bm.name,
                success=success,
                steps=result.steps,
                elapsed=elapsed,
                result=result.final_state.result,
            ))
        except Exception as e:
            elapsed = time.time() - start
            print(f"ERROR  ({elapsed:.1f}s)")
            print(f"        exception: {e}")
            results.append(EvalResult(
                name=bm.name,
                success=False,
                steps=0,
                elapsed=elapsed,
                result="",
                error=str(e),
            ))

    total_elapsed = time.time() - total_start
    passed = sum(1 for r in results if r.success)

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{len(results)} passed ({passed/len(results)*100:.0f}%)")
    print(f"Total time: {total_elapsed:.1f}s")
    print(f"{'='*60}\n")

    return results
