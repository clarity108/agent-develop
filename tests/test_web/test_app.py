import time
import pytest

from fastapi.testclient import TestClient
from src.web.app import app


client = TestClient(app)


class TestIndex:
    def test_returns_html(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "<!DOCTYPE" in r.text

    def test_contains_trace_area(self):
        r = client.get("/")
        assert 'id="trace"' in r.text

    def test_contains_task_form(self):
        r = client.get("/")
        assert 'id="task-form"' in r.text
        assert 'name="task"' in r.text

    def test_contains_tools_list(self):
        r = client.get("/")
        assert "tool-item" in r.text
        assert "read_file" in r.text

    def test_uses_jetbrains_mono(self):
        r = client.get("/")
        assert "JetBrains+Mono" in r.text

    def test_links_static_assets(self):
        r = client.get("/")
        assert "/static/styles.css" in r.text
        assert "/static/app.js" in r.text


class TestRuns:
    def test_post_run_returns_run_id(self):
        r = client.post("/api/runs", data={"task": "test task"})
        assert r.status_code == 200
        data = r.json()
        assert "run_id" in data
        assert len(data["run_id"]) == 8

    def test_post_run_empty_task(self):
        r = client.post("/api/runs", data={"task": ""})
        assert r.json().get("error") == "task is required"

    def test_get_nonexistent_run(self):
        r = client.get("/api/runs/00000000")
        assert r.json().get("error") == "run not found"

    def test_run_produces_events(self):
        r = client.post("/api/runs", data={"task": "create a file", "use_llm": "off"})
        run_id = r.json()["run_id"]

        time.sleep(3)

        r = client.get(f"/api/runs/{run_id}")
        data = r.json()
        assert data["task"] == "create a file"
        assert len(data["events"]) >= 3
        types = [e["type"] for e in data["events"]]
        assert "step_thought" in types
        assert "tool_call" in types or "agent_done" in types

    def test_run_completes(self):
        r = client.post("/api/runs", data={"task": "create a file", "use_llm": "off"})
        run_id = r.json()["run_id"]

        time.sleep(5)

        r = client.get(f"/api/runs/{run_id}")
        data = r.json()
        assert data["done"] is True
        types = [e["type"] for e in data["events"]]
        assert "agent_done" in types

    def test_sse_stream(self):
        r = client.post("/api/runs", data={"task": "create a file", "use_llm": "off"})
        run_id = r.json()["run_id"]

        time.sleep(3)

        r = client.get(f"/api/runs/{run_id}/stream")
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")

    def test_multiple_runs_independent(self):
        r1 = client.post("/api/runs", data={"task": "create file A", "use_llm": "off"})
        r2 = client.post("/api/runs", data={"task": "create file B", "use_llm": "off"})
        assert r1.json()["run_id"] != r2.json()["run_id"]
