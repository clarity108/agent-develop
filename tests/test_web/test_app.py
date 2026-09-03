import time
import pytest


class TestIndex:
    def test_returns_html(self, _client):
        r = _client.get("/")
        assert r.status_code == 200
        assert "<!DOCTYPE" in r.text

    def test_contains_trace_area(self, _client):
        r = _client.get("/")
        assert 'id="trace"' in r.text

    def test_contains_task_form(self, _client):
        r = _client.get("/")
        assert 'id="task-form"' in r.text
        assert 'name="task"' in r.text

    def test_contains_tools_list(self, _client):
        r = _client.get("/")
        assert "tool-item" in r.text
        assert "read_file" in r.text

    def test_uses_jetbrains_mono(self, _client):
        r = _client.get("/")
        assert "JetBrains+Mono" in r.text

    def test_links_static_assets(self, _client):
        r = _client.get("/")
        assert "/static/styles.css" in r.text
        assert "/static/app.js" in r.text


class TestRuns:
    def test_post_run_returns_run_id(self, _client):
        r = _client.post("/api/runs", data={"task": "test task"})
        assert r.status_code == 200
        data = r.json()
        assert "run_id" in data
        assert len(data["run_id"]) == 8

    def test_post_run_empty_task(self, _client):
        r = _client.post("/api/runs", data={"task": ""})
        assert r.json().get("error") == "task is required"

    def test_get_nonexistent_run(self, _client):
        r = _client.get("/api/runs/00000000")
        assert r.json().get("error") == "run not found"

    def test_cancel_nonexistent_run(self, _client):
        r = _client.post("/api/runs/00000000/cancel")
        assert r.json().get("error") == "run not found"

    def test_run_produces_events(self, _client):
        r = _client.post("/api/runs", data={"task": "create a file", "use_llm": "off"})
        run_id = r.json()["run_id"]

        time.sleep(3)

        r = _client.get(f"/api/runs/{run_id}")
        data = r.json()
        assert data["task"] == "create a file"
        assert len(data["events"]) >= 3
        types = [e["type"] for e in data["events"]]
        assert "step_thought" in types
        assert "tool_call" in types or "agent_done" in types

    def test_run_completes(self, _client):
        r = _client.post("/api/runs", data={"task": "create a file", "use_llm": "off"})
        run_id = r.json()["run_id"]

        time.sleep(5)

        r = _client.get(f"/api/runs/{run_id}")
        data = r.json()
        assert data["done"] is True
        types = [e["type"] for e in data["events"]]
        assert "agent_done" in types

    def test_cancel_run(self, _client):
        r = _client.post("/api/runs", data={"task": "create a file", "use_llm": "off"})
        run_id = r.json()["run_id"]

        time.sleep(2)

        r = _client.post(f"/api/runs/{run_id}/cancel")
        assert r.json()["status"] in ("cancelled", "already_done")

    def test_sse_stream(self, _client):
        r = _client.post("/api/runs", data={"task": "create a file", "use_llm": "off"})
        run_id = r.json()["run_id"]

        time.sleep(3)

        r = _client.get(f"/api/runs/{run_id}/stream")
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")

    def test_multiple_runs_independent(self, _client):
        r1 = _client.post("/api/runs", data={"task": "create file A", "use_llm": "off"})
        r2 = _client.post("/api/runs", data={"task": "create file B", "use_llm": "off"})
        assert r1.json()["run_id"] != r2.json()["run_id"]


class TestHistory:
    def test_history_empty_on_start(self, _client):
        r = _client.get("/api/history")
        assert r.status_code == 200
        assert r.json() == []

    def test_history_records_completed_run(self, _client):
        r = _client.post("/api/runs", data={"task": "create a file", "use_llm": "off"})
        run_id = r.json()["run_id"]
        time.sleep(5)

        r = _client.get("/api/history")
        data = r.json()
        entry = next(e for e in data if e["run_id"] == run_id)
        assert entry["task"] == "create a file"
        assert entry["success"] is True

    def test_history_shows_use_llm(self, _client):
        r = _client.post("/api/runs", data={"task": "create a file", "use_llm": "off"})
        run_id = r.json()["run_id"]
        time.sleep(5)

        r = _client.get("/api/history")
        data = r.json()
        entry = next(e for e in data if e["run_id"] == run_id)
        assert entry["use_llm"] is False

    def test_clear_history(self, _client):
        r = _client.post("/api/runs", data={"task": "hello", "use_llm": "off"})
        time.sleep(4)

        r = _client.delete("/api/history")
        assert r.json()["deleted"] >= 1

        r = _client.get("/api/history")
        assert r.json() == []

    def test_history_order_newest_first(self, _client):
        r = _client.post("/api/runs", data={"task": "first", "use_llm": "off"})
        run_id_1 = r.json()["run_id"]
        time.sleep(4)
        r = _client.post("/api/runs", data={"task": "second", "use_llm": "off"})
        run_id_2 = r.json()["run_id"]
        time.sleep(5)

        r = _client.get("/api/history")
        data = r.json()
        ours = [e for e in data if e["run_id"] in (run_id_1, run_id_2)]
        assert len(ours) == 2
        assert ours[0]["run_id"] == run_id_2
        assert ours[1]["run_id"] == run_id_1
