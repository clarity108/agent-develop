from __future__ import annotations

import json
import sqlite3

from .file_tools import ToolResult
from .metadata import tool


def _check_db(path: str) -> ToolResult | None:
    if not path:
        return ToolResult(success=False, output="", error="database path is required")
    try:
        conn = sqlite3.connect(path)
        conn.close()
        return None
    except sqlite3.Error as e:
        return ToolResult(success=False, output="", error=f"cannot open database: {e}")


def _rows_to_list(cursor: sqlite3.Cursor) -> list[dict]:
    cols = [desc[0] for desc in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


@tool("Executes a SQL query on a SQLite database and returns results as JSON. Use for SELECT, INSERT, UPDATE, DELETE")
def sqlite_query(db_path: str, sql: str, params: str = "") -> ToolResult:
    err = _check_db(db_path)
    if err:
        return err
    if not sql.strip():
        return ToolResult(success=False, output="", error="sql query is required")

    try:
        query_params: list = []
        if params.strip():
            try:
                parsed = json.loads(params)
                if isinstance(parsed, list):
                    query_params = parsed
                else:
                    query_params = [parsed]
            except json.JSONDecodeError as e:
                return ToolResult(success=False, output="", error=f"invalid params JSON: {e}")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql, query_params)

        is_select = sql.strip().upper().startswith("SELECT")
        if is_select:
            rows = _rows_to_list(cursor)
            result = {"rows": rows, "count": len(rows)}
        else:
            conn.commit()
            result = {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid}

        conn.close()
        return ToolResult(success=True, output=json.dumps(result, indent=2))
    except sqlite3.Error as e:
        return ToolResult(success=False, output="", error=f"sql error: {e}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool("Shows the schema of a SQLite database: tables, columns, types, and indexes")
def sqlite_schema(db_path: str) -> ToolResult:
    err = _check_db(db_path)
    if err:
        return err

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row["name"] for row in cursor.fetchall()]

        schema: dict = {"tables": {}}
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [
                {"name": row["name"], "type": row["type"], "notnull": bool(row["notnull"]), "default": row["dflt_value"]}
                for row in cursor.fetchall()
            ]
            cursor.execute(f"PRAGMA index_list({table})")
            indexes = [row["name"] for row in cursor.fetchall() if row["name"]]
            schema["tables"][table] = {"columns": columns, "indexes": indexes}

        conn.close()
        return ToolResult(success=True, output=json.dumps(schema, indent=2))
    except sqlite3.Error as e:
        return ToolResult(success=False, output="", error=f"schema error: {e}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))
