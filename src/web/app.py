from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.agent.core import RuleBasedDevAgent, DevAgent, AgentResult
from src.agent.delegation import create_delegate_task_tool
from src.agent.undo import UndoManager
from src.llm.config import load_config, build_client
from src.llm.planner import LLMDevAgent
from src.tools import (
    read_file, write_file, list_files, edit_file,
    search_in_file, grep_files,
    mkdir, mv_file, cp_file, rm_file,
    execute_command, execute_sandbox, execute_python, list_env,
    diff_file, apply_patch, preview_diff,
    batch_replace, batch_rename, batch_move, batch_delete, find_in_files, batch_format,
    create_code_review_tool, create_diff_review_tool, create_git_diff_review_tool,
    create_generate_tests_tool, create_generate_tests_inline_tool,
    git_status, git_init, git_add_commit, git_log, git_branch, git_diff, git_blame,
    analyze_code, run_tests, pip_install, pip_list,
    http_get, http_post, http_request,
    sqlite_query, sqlite_schema,
    get_tool_metadata, tool,
)
from src.tools.metadata import ToolMetadata
from src.memory.session import SessionMemory
from src.memory.long_term import LongTermMemory
from src.web.storage import init_db, save_run, list_runs, delete_all_runs, delete_run

PROJECT_ROOT = Path(__file__).parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "web"
STATIC_DIR = PROJECT_ROOT / "web" / "src"

app = FastAPI(title="Autonomous Dev Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
init_db()

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(content="", media_type="image/x-icon")

_ACTIVE_RUNS: dict[str, "AgentRun"] = {}
_CONVERSATIONS: dict[str, SessionMemory] = {}
_CONVERSATIONS_DIR = str(PROJECT_ROOT / "conversations")
_LONG_TERM_MEMORY = LongTermMemory(store_dir=str(PROJECT_ROOT / "memories"))
_UNDO_MANAGER = UndoManager()


@dataclass
class TraceEvent:
    type: str
    data: dict
    ts: float = field(default_factory=time.time)


class _ApprovalGate:
    def __init__(self):
        self._event = threading.Event()
        self._approved = False
        self._pending = False

    @property
    def pending(self) -> bool:
        return self._pending

    def wait(self, timeout: float = 120) -> bool:
        self._pending = True
        result = self._event.wait(timeout)
        self._pending = False
        if not result:
            self._approved = False
            return False
        return self._approved

    def resolve(self, approved: bool) -> None:
        self._approved = approved
        self._event.set()


@dataclass
class AgentRun:
    run_id: str
    task: str
    events: deque = field(default_factory=lambda: deque(maxlen=500))
    done: bool = False
    cancelled: bool = False
    start_time: float = field(default_factory=time.time)
    final_result: AgentResult | None = None
    approval_gate: _ApprovalGate = field(default_factory=_ApprovalGate)

    def emit(self, event_type: str, data: dict) -> None:
        self.events.append(TraceEvent(type=event_type, data=data))

    def elapsed(self) -> float:
        return round(time.time() - self.start_time, 1)


def _base_tools() -> dict:
    return {
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
        "batch_replace": batch_replace,
        "batch_rename": batch_rename,
        "batch_move": batch_move,
        "batch_delete": batch_delete,
        "find_in_files": find_in_files,
        "batch_format": batch_format,
        "git_status": git_status,
        "git_init": git_init,
        "git_add_commit": git_add_commit,
        "git_log": git_log,
        "git_branch": git_branch,
        "git_diff": git_diff,
        "git_blame": git_blame,
        "analyze_code": analyze_code,
        "run_tests": run_tests,
        "pip_install": pip_install,
        "pip_list": pip_list,
        "http_get": http_get,
        "http_post": http_post,
        "http_request": http_request,
        "sqlite_query": sqlite_query,
        "sqlite_schema": sqlite_schema,
    }


def _build_agent(use_llm: bool, session_memory: SessionMemory | None = None) -> DevAgent:
    tools = _base_tools()
    if use_llm:
        config = load_config(str(PROJECT_ROOT / "config" / "default.yaml"))
        client = build_client(config["llm"])
        delegate_fn = create_delegate_task_tool(
            client=client, tools=tools, long_term_memory=_LONG_TERM_MEMORY,
        )
        tools["delegate_task"] = delegate_fn
        tools["generate_tests"] = create_generate_tests_tool(client)
        tools["generate_tests_inline"] = create_generate_tests_inline_tool(client)
        tools["code_review"] = create_code_review_tool(client)
        tools["diff_review"] = create_diff_review_tool(client)
        tools["git_diff_review"] = create_git_diff_review_tool(client)
        return LLMDevAgent(
            client=client, tools=tools, session_memory=session_memory,
            long_term_memory=_LONG_TERM_MEMORY,
            undo_manager=_UNDO_MANAGER,
        )
    return RuleBasedDevAgent(
        rules=[
            {"match": "create", "step": 1, "tool": "write_file",
             "args": {"path": "output.txt", "content": "created by agent"}},
            {"match": "create", "step": 2, "tool": "read_file",
             "args": {"path": "output.txt"}},
            {"match": "create", "step": 3, "answer": "File created and verified."},
        ],
        tools=tools,
        session_memory=session_memory,
        undo_manager=_UNDO_MANAGER,
    )


def _get_conversation(conversation_id: str) -> SessionMemory:
    if conversation_id in _CONVERSATIONS:
        return _CONVERSATIONS[conversation_id]
    memory = SessionMemory()
    if memory.load_from_disk(conversation_id, _CONVERSATIONS_DIR):
        _CONVERSATIONS[conversation_id] = memory
        return memory
    memory = SessionMemory()
    _CONVERSATIONS[conversation_id] = memory
    return memory


def _save_conversation(conversation_id: str) -> None:
    memory = _CONVERSATIONS.get(conversation_id)
    if memory:
        memory.save_to_disk(conversation_id, _CONVERSATIONS_DIR)


def _run_agent_in_thread(run: AgentRun, use_llm: bool = True, conversation_id: str | None = None, use_plan: bool = False) -> None:
    try:
        session_memory = _get_conversation(conversation_id) if conversation_id else None
        run.emit("agent_start", {"task": run.task, "use_llm": use_llm, "use_plan": use_plan, "conversation_id": conversation_id})

        if use_plan:
            from src.agent.task_planner import run_plan
            config = load_config(str(PROJECT_ROOT / "config" / "default.yaml"))
            client = build_client(config["llm"])
            delegate_fn = create_delegate_task_tool(client=client, tools=_base_tools(), long_term_memory=_LONG_TERM_MEMORY)
            all_tools = {**_base_tools(), "delegate_task": delegate_fn}

            def on_plan(plan):
                run.emit("plan_update", plan.to_dict())

            def on_step_event(event, idx, info):
                if event == "plan_step_start":
                    run.emit("plan_step_start", {"index": idx, "description": info})
                elif event == "plan_step_done":
                    run.emit("plan_step_done", {"index": idx, "result": info})
                elif event == "plan_step_failed":
                    run.emit("plan_step_failed", {"index": idx, "error": info})
                elif event == "plan_revised":
                    run.emit("plan_revised", {"total_steps": info})

            plan, success = run_plan(
                run.task, all_tools, client,
                long_term_memory=_LONG_TERM_MEMORY,
                on_plan=on_plan,
                on_step_event=on_step_event,
                cancel_check=lambda: run.cancelled,
            )

            result_text = plan.to_dict()["steps"][-1]["result"] if plan.steps else ""
            run.emit("agent_done", {
                "success": success and not run.cancelled,
                "steps": plan.total_steps,
                "task": run.task,
                "result": result_text,
                "cancelled": run.cancelled,
            })
            save_run(run_id=run.run_id, task=run.task, use_llm=True,
                     success=success and not run.cancelled,
                     steps=plan.total_steps, elapsed=run.elapsed(),
                     cancelled=run.cancelled, conversation_id=conversation_id)
            _LONG_TERM_MEMORY.save(run.run_id, {
                "timestamp": time.time(), "task": run.task,
                "success": success and not run.cancelled,
                "steps": plan.total_steps, "result": result_text,
                "conversation_id": conversation_id,
            })
            if conversation_id:
                _save_conversation(conversation_id)
            run.done = True
            return

        agent = _build_agent(use_llm, session_memory=session_memory)
        run.emit("agent_start", {"task": run.task, "tools": agent.available_tools(), "use_llm": use_llm, "conversation_id": conversation_id})

        def on_step(event: str, step: int, *args):
            if event == "decision":
                decision = args[0]
                run.emit("step_thought", {
                    "step": step,
                    "thought": decision.thought,
                    "action": decision.action,
                    "tool_name": decision.tool_name,
                    "tool_args": decision.tool_args,
                })
                if decision.tool_name is not None:
                    run.emit("tool_call", {
                        "step": step,
                        "tool_name": decision.tool_name,
                        "tool_args": decision.tool_args,
                    })
                else:
                    run.emit("step_end", {"step": step, "answer": decision.answer})
            elif event == "tool_result":
                tool_name = args[0]
                result = args[1]
                run.emit("tool_result", {
                    "step": step,
                    "tool_name": tool_name,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                })
                time.sleep(0.3)
            elif event == "tool_retry":
                tool_name, attempt, max_attempts, error = args
                run.emit("tool_retry", {
                    "step": step,
                    "tool_name": tool_name,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error": error,
                })
            elif event == "tool_cache_hit":
                tool_name, result = args
                run.emit("tool_cache_hit", {
                    "step": step,
                    "tool_name": tool_name,
                    "success": result.success,
                    "output": result.output[:200] if result.output else "",
                })
            elif event == "tool_recovery":
                tool_name, action, new_args = args
                run.emit("tool_recovery", {
                    "step": step,
                    "tool_name": tool_name,
                    "action": action,
                    "new_args": new_args,
                })
            elif event == "error":
                run.emit("step_error", {"step": step, "error": args[0]})

        def confirmation_check(tool_name, tool_args):
            run.emit("approval_requested", {"tool_name": tool_name, "tool_args": tool_args})
            approved = run.approval_gate.wait(timeout=120)
            run.emit("approval_resolved", {"approved": approved, "tool_name": tool_name})
            return approved

        def on_token(token: str):
            run.emit("token", {"text": token})

        def on_usage(prompt_tokens: int, completion_tokens: int):
            run.emit("usage", {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            })

        result = agent.run(
            run.task,
            on_step=on_step,
            cancel_check=lambda: run.cancelled,
            on_compression=lambda msgs, slen: run.emit("context_compressed", {
                "messages": msgs, "summary_length": slen,
            }),
            confirmation_check=confirmation_check,
            on_token=on_token,
            on_usage=on_usage,
        )

        run.emit("agent_done", {
            "success": result.success if not run.cancelled else False,
            "steps": result.steps,
            "task": run.task,
            "result": result.final_state.result,
            "cancelled": run.cancelled,
        })
        save_run(
            run_id=run.run_id,
            task=run.task,
            use_llm=use_llm,
            success=result.success and not run.cancelled,
            steps=result.steps,
            elapsed=run.elapsed(),
            cancelled=run.cancelled,
            conversation_id=conversation_id,
        )
        _LONG_TERM_MEMORY.save(run.run_id, {
            "timestamp": time.time(),
            "task": run.task,
            "success": result.success and not run.cancelled,
            "steps": result.steps,
            "result": result.final_state.result,
            "conversation_id": conversation_id,
        })
        if conversation_id:
            _save_conversation(conversation_id)
        run.final_result = result
        run.done = True
    except Exception as e:
        run.emit("agent_error", {"error": str(e)})
        run.done = True
        save_run(
            run_id=run.run_id,
            task=run.task,
            use_llm=use_llm,
            success=False,
            steps=0,
            elapsed=run.elapsed(),
            cancelled=False,
            conversation_id=conversation_id,
        )
        _LONG_TERM_MEMORY.save(run.run_id, {
            "timestamp": time.time(),
            "task": run.task,
            "success": False,
            "steps": 0,
            "result": f"Error: {e}",
            "conversation_id": conversation_id,
        })
        if conversation_id:
            _save_conversation(conversation_id)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    tools_list = []
    base_tools = _base_tools()
    for name in list(base_tools.keys()):
        fn = base_tools[name]
        meta = get_tool_metadata(fn)
        tools_list.append({
            "name": meta.name if meta else name,
            "description": meta.description if meta else "No description available.",
        })
    tools_list.append({
        "name": "delegate_task",
        "description": "Delegates a sub-task to a sub-agent that runs independently with a fresh context",
    })
    tools_list.append({
        "name": "generate_tests",
        "description": "Generates pytest test cases for a Python source file using LLM analysis",
    })
    tools_list.append({
        "name": "generate_tests_inline",
        "description": "Generates pytest test code from inline source code using LLM analysis",
    })
    tools_list.append({
        "name": "code_review",
        "description": "Reviews a Python source file and returns structured findings (bugs, security, performance, style)",
    })
    tools_list.append({
        "name": "diff_review",
        "description": "Reviews a unified diff and returns structured findings about the changes",
    })
    tools_list.append({
        "name": "git_diff_review",
        "description": "Reviews the current git diff (staged + unstaged) and returns structured findings",
    })

    _rules = _build_agent(False).rules
    rule_matches = sorted({r.get("match", "") for r in _rules if r.get("match")})

    return templates.TemplateResponse(
        request,
        "execute.html",
        {"tools": tools_list, "rule_matches": rule_matches},
    )


@app.post("/api/runs")
async def start_run(request: Request):
    form = await request.form()
    task = form.get("task", "").strip()
    if not task:
        return {"error": "task is required"}

    use_llm = form.get("use_llm", "on") == "on"
    use_plan = form.get("use_plan", "off") == "on"
    conversation_id = form.get("conversation_id", "").strip() or None
    if not conversation_id:
        conversation_id = uuid.uuid4().hex[:8]
    run_id = uuid.uuid4().hex[:8]
    run = AgentRun(run_id=run_id, task=task)
    _ACTIVE_RUNS[run_id] = run

    threading.Thread(
        target=_run_agent_in_thread,
        args=(run, use_llm, conversation_id, use_plan),
        daemon=True,
    ).start()
    return {"run_id": run_id, "conversation_id": conversation_id}


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str):
    if run_id not in _ACTIVE_RUNS:
        return {"error": "run not found"}

    run = _ACTIVE_RUNS[run_id]

    async def event_stream() -> AsyncGenerator[bytes, None]:
        seen = 0
        while True:
            while len(run.events) > seen:
                event = run.events[seen]
                payload = json.dumps({"type": event.type, "data": event.data})
                seen += 1
                yield f"data: {payload}\n\n".encode()
            if run.done:
                yield "data: {\"type\": \"done\"}\n\n".encode()
                break
            await asyncio.sleep(0.15)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    run = _ACTIVE_RUNS.get(run_id)
    if not run:
        return {"error": "run not found"}
    events = [asdict(e) for e in run.events]
    return {
        "run_id": run.run_id,
        "task": run.task,
        "done": run.done,
        "cancelled": run.cancelled,
        "elapsed": run.elapsed(),
        "events": events,
    }


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    run = _ACTIVE_RUNS.get(run_id)
    if not run:
        return {"error": "run not found"}
    if run.done:
        return {"status": "already_done"}
    run.cancelled = True
    run.done = True
    run.emit("cancelled", {})
    return {"status": "cancelled"}


@app.post("/api/runs/{run_id}/approve")
async def approve_run(run_id: str):
    run = _ACTIVE_RUNS.get(run_id)
    if not run:
        return {"error": "run not found"}
    if not run.approval_gate.pending:
        return {"error": "no pending approval"}
    run.approval_gate.resolve(True)
    return {"status": "approved"}


@app.post("/api/runs/{run_id}/reject")
async def reject_run(run_id: str):
    run = _ACTIVE_RUNS.get(run_id)
    if not run:
        return {"error": "run not found"}
    if not run.approval_gate.pending:
        return {"error": "no pending approval"}
    run.approval_gate.resolve(False)
    return {"status": "rejected"}


@app.get("/api/undo/stack")
async def get_undo_stack():
    return _UNDO_MANAGER.stack_info()


@app.post("/api/undo/undo")
async def do_undo():
    return _UNDO_MANAGER.undo()


@app.post("/api/undo/redo")
async def do_redo():
    return _UNDO_MANAGER.redo()


@app.get("/api/history")
async def get_history():
    return list_runs()


@app.delete("/api/history")
async def clear_history():
    count = delete_all_runs()
    return {"deleted": count}


@app.delete("/api/history/{run_id}")
async def delete_history_run(run_id: str):
    count = delete_run(run_id)
    return {"deleted": count}


@app.get("/api/memory")
async def list_memories():
    keys = _LONG_TERM_MEMORY.list_keys()
    memories = []
    for key in keys:
        mem = _LONG_TERM_MEMORY.load(key)
        if mem:
            memories.append({"key": key, **mem})
    return memories


@app.get("/api/memory/{key}")
async def get_memory(key: str):
    mem = _LONG_TERM_MEMORY.load(key)
    if mem is None:
        return {"error": "memory not found"}
    return {"key": key, **mem}


@app.delete("/api/memory/{key}")
async def delete_memory(key: str):
    if key not in _LONG_TERM_MEMORY.list_keys():
        return {"error": "memory not found"}
    _LONG_TERM_MEMORY.delete(key)
    return {"deleted": key}


@app.delete("/api/memory")
async def clear_memories():
    keys = _LONG_TERM_MEMORY.list_keys()
    for key in keys:
        _LONG_TERM_MEMORY.delete(key)
    return {"deleted": len(keys)}


@app.get("/api/conversations")
async def list_conversations():
    store = Path(_CONVERSATIONS_DIR)
    if not store.exists():
        return []
    convs = []
    for f in sorted(store.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            msgs = data.get("messages", [])
            first_user = next((m["content"] for m in msgs if m.get("role") == "user"), "")
            convs.append({
                "id": f.stem,
                "messages": len(msgs),
                "has_summary": bool(data.get("summary")),
                "first_task": first_user[:80],
                "updated": f.stat().st_mtime,
            })
        except Exception:
            continue
    return convs


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    _CONVERSATIONS.pop(conv_id, None)
    path = Path(_CONVERSATIONS_DIR) / f"{conv_id}.json"
    if not path.exists():
        return {"error": "conversation not found"}
    path.unlink()
    return {"deleted": conv_id}


@app.delete("/api/conversations")
async def clear_conversations():
    store = Path(_CONVERSATIONS_DIR)
    if not store.exists():
        return {"deleted": 0}
    count = 0
    for f in store.glob("*.json"):
        conv_id = f.stem
        _CONVERSATIONS.pop(conv_id, None)
        f.unlink()
        count += 1
    return {"deleted": count}
