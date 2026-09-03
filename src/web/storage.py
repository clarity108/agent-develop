from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

_DEFAULT_DB = str(Path(__file__).parent.parent.parent / "history.db")


def _db_path() -> str:
    return os.environ.get("AGENT_HISTORY_DB", _DEFAULT_DB)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS runs ("
        "  id TEXT PRIMARY KEY,"
        "  task TEXT NOT NULL,"
        "  use_llm INTEGER NOT NULL,"
        "  success INTEGER NOT NULL,"
        "  steps INTEGER NOT NULL,"
        "  elapsed REAL NOT NULL,"
        "  cancelled INTEGER NOT NULL,"
        "  finished_at TEXT NOT NULL"
        ")"
    )
    return conn


def init_db() -> None:
    conn = _get_conn()
    conn.commit()
    conn.close()


def save_run(
    run_id: str,
    task: str,
    use_llm: bool,
    success: bool,
    steps: int,
    elapsed: float,
    cancelled: bool,
) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO runs "
            "(id, task, use_llm, success, steps, elapsed, cancelled, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                task,
                1 if use_llm else 0,
                1 if success else 0,
                steps,
                elapsed,
                1 if cancelled else 0,
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_runs(limit: int = 50) -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, task, use_llm, success, steps, elapsed, cancelled, finished_at, ROWID "
            "FROM runs ORDER BY finished_at DESC, ROWID DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "run_id": r[0],
                "task": r[1],
                "use_llm": bool(r[2]),
                "success": bool(r[3]),
                "steps": r[4],
                "elapsed": r[5],
                "cancelled": bool(r[6]),
                "finished_at": r[7],
            }
            for r in rows
        ]
    finally:
        conn.close()


def delete_all_runs() -> int:
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM runs")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def delete_run(run_id: str) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
