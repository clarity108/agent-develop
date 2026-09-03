from __future__ import annotations

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
from src.llm.config import load_config, build_client
from src.llm.planner import LLMDevAgent
from src.tools import (
    read_file, write_file, list_files,
    execute_command, git_status, git_init, git_add_commit,
    get_tool_metadata, tool,
)
from src.tools.metadata import ToolMetadata
from src.web.storage import init_db, save_run, list_runs, delete_all_runs

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


@dataclass
class TraceEvent:
    type: str
    data: dict
    ts: float = field(default_factory=time.time)


@dataclass
class AgentRun:
    run_id: str
    task: str
    events: deque = field(default_factory=lambda: deque(maxlen=500))
    done: bool = False
    cancelled: bool = False
    start_time: float = field(default_factory=time.time)
    final_result: AgentResult | None = None

    def emit(self, event_type: str, data: dict) -> None:
        self.events.append(TraceEvent(type=event_type, data=data))

    def elapsed(self) -> float:
        return round(time.time() - self.start_time, 1)


def _build_agent(use_llm: bool) -> DevAgent:
    tools = {
        "read_file": read_file,
        "write_file": write_file,
        "list_files": list_files,
        "execute_command": execute_command,
        "git_status": git_status,
        "git_init": git_init,
        "git_add_commit": git_add_commit,
    }
    if use_llm:
        config = load_config(str(PROJECT_ROOT / "config" / "default.yaml"))
        client = build_client(config["llm"])
        return LLMDevAgent(client=client, tools=tools)
    return RuleBasedDevAgent(
        rules=[
            {"match": "create", "step": 1, "tool": "write_file",
             "args": {"path": "output.txt", "content": "created by agent"}},
            {"match": "create", "step": 2, "tool": "read_file",
             "args": {"path": "output.txt"}},
            {"match": "create", "step": 3, "answer": "File created and verified."},
        ],
        tools=tools,
    )


def _run_agent_in_thread(run: AgentRun, use_llm: bool = True) -> None:
    try:
        agent = _build_agent(use_llm)
        run.emit("agent_start", {"task": run.task, "tools": agent.available_tools(), "use_llm": use_llm})

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
            elif event == "error":
                run.emit("step_error", {"step": step, "error": args[0]})

        result = agent.run(run.task, on_step=on_step, cancel_check=lambda: run.cancelled)

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
        )
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
        )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    tools_list = []
    for name in ["read_file", "write_file", "list_files",
                  "execute_command", "git_status", "git_init", "git_add_commit"]:
        fn = {"read_file": read_file, "write_file": write_file, "list_files": list_files,
              "execute_command": execute_command, "git_status": git_status,
              "git_init": git_init, "git_add_commit": git_add_commit}[name]
        meta = get_tool_metadata(fn)
        tools_list.append({
            "name": meta.name if meta else name,
            "description": meta.description if meta else "No description available.",
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
    run_id = uuid.uuid4().hex[:8]
    run = AgentRun(run_id=run_id, task=task)
    _ACTIVE_RUNS[run_id] = run

    threading.Thread(target=_run_agent_in_thread, args=(run, use_llm), daemon=True).start()
    return {"run_id": run_id}


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


import asyncio


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


@app.get("/api/history")
async def get_history():
    return list_runs()


@app.delete("/api/history")
async def clear_history():
    count = delete_all_runs()
    return {"deleted": count}
