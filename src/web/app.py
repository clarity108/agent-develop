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
from fastapi.responses import HTMLResponse, StreamingResponse
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

PROJECT_ROOT = Path(__file__).parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "web"
STATIC_DIR = PROJECT_ROOT / "web" / "src"

app = FastAPI(title="Autonomous Dev Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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


def _run_agent_in_thread(run: AgentRun) -> None:
    try:
        agent = _build_agent(False)
        run.emit("agent_start", {"task": run.task, "tools": agent.available_tools()})

        original_run = agent.run

        def instrumented_run(task: str):
            run.emit("agent_start", {"task": task, "tools": agent.available_tools()})
            state = agent._state
            max_steps = agent._max_steps

            if agent.session_memory:
                agent.session_memory.add("user", task)

            result = None
            for step in range(1, max_steps + 1):
                state.step = step
                decision = agent._plan(task, step)
                state.thought = decision.thought
                state.action = decision.action

                run.emit("step_thought", {
                    "step": step,
                    "thought": decision.thought,
                    "action": decision.action,
                })

                if decision.tool_name is None:
                    state.result = decision.answer
                    state.done = True
                    if agent.session_memory:
                        agent.session_memory.add("assistant", decision.answer)
                    run.emit("step_end", {"step": step, "answer": decision.answer})
                    result = type("R", (), {
                        "task": task,
                        "success": True,
                        "steps": step,
                        "final_state": state,
                    })()
                    break

                if decision.tool_name not in agent._tools:
                    state.result = f"unknown tool: {decision.tool_name}"
                    state.done = True
                    run.emit("step_error", {
                        "step": step,
                        "error": f"unknown tool: {decision.tool_name}",
                    })
                    result = type("R", (), {
                        "task": task,
                        "success": False,
                        "steps": step,
                        "final_state": state,
                    })()
                    break

                run.emit("tool_call", {
                    "step": step,
                    "tool_name": decision.tool_name,
                    "tool_args": decision.tool_args,
                    "thought": decision.thought,
                })

                tool_result = agent._tools[decision.tool_name](**decision.tool_args)
                state.result = tool_result.output
                if not tool_result.success and tool_result.error:
                    state.result += f"\nERROR: {tool_result.error}"

                if agent.session_memory:
                    agent.session_memory.add(
                        "assistant", decision.thought,
                        metadata={"tool_name": decision.tool_name},
                    )
                    status = "success" if tool_result.success else f"error: {tool_result.error}"
                    agent.session_memory.add(
                        "tool",
                        f"{status}: {tool_result.output}",
                        metadata={"tool_name": decision.tool_name},
                    )

                run.emit("tool_result", {
                    "step": step,
                    "tool_name": decision.tool_name,
                    "success": tool_result.success,
                    "output": tool_result.output,
                    "error": tool_result.error,
                })

                time.sleep(0.6)

            run.emit("agent_done", {
                "success": bool(result.success),
                "steps": result.steps,
                "result": result.final_state.result,
            })
            run.final_result = result
            run.done = True

        agent.run = instrumented_run  # type: ignore[assignment]
        agent.run(run.task)
    except Exception as e:
        run.emit("agent_error", {"error": str(e)})
        run.done = True


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
    return templates.TemplateResponse(
        request,
        "execute.html",
        {"tools": tools_list},
    )


@app.post("/api/runs")
async def start_run(request: Request):
    form = await request.form()
    task = form.get("task", "").strip()
    if not task:
        return {"error": "task is required"}

    run_id = uuid.uuid4().hex[:8]
    run = AgentRun(run_id=run_id, task=task)
    _ACTIVE_RUNS[run_id] = run

    threading.Thread(target=_run_agent_in_thread, args=(run, ), daemon=True).start()
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
        "elapsed": run.elapsed(),
        "events": events,
    }
