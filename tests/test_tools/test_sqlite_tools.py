import json
import sqlite3

import pytest

from src.tools.sqlite_tools import sqlite_query, sqlite_schema


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE)")
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, FOREIGN KEY(user_id) REFERENCES users(id))")
    conn.execute("CREATE INDEX idx_orders_user ON orders(user_id)")
    conn.execute("INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com')")
    conn.execute("INSERT INTO users (name, email) VALUES ('Bob', 'bob@example.com')")
    conn.execute("INSERT INTO orders (user_id, amount) VALUES (1, 99.50)")
    conn.execute("INSERT INTO orders (user_id, amount) VALUES (2, 250.00)")
    conn.commit()
    conn.close()
    return str(path)


class TestSqliteQuery:
    def test_select(self, db):
        result = sqlite_query(db, "SELECT * FROM users WHERE id = 1")
        assert result.success
        data = json.loads(result.output)
        assert data["count"] == 1
        assert data["rows"][0]["name"] == "Alice"

    def test_select_no_params(self, db):
        result = sqlite_query(db, "SELECT name FROM users ORDER BY id")
        assert result.success
        data = json.loads(result.output)
        assert data["count"] == 2

    def test_insert(self, db):
        result = sqlite_query(db, "INSERT INTO users (name, email) VALUES (?, ?)", '["Charlie", "charlie@example.com"]')
        assert result.success
        data = json.loads(result.output)
        assert data["rowcount"] == 1
        assert data["lastrowid"] == 3

    def test_update(self, db):
        result = sqlite_query(db, "UPDATE users SET email = ? WHERE id = 1", '["alice2@example.com"]')
        assert result.success
        data = json.loads(result.output)
        assert data["rowcount"] == 1

    def test_delete(self, db):
        result = sqlite_query(db, "DELETE FROM orders WHERE id = 1")
        assert result.success
        data = json.loads(result.output)
        assert data["rowcount"] == 1

    def test_params_json_list(self, db):
        result = sqlite_query(db, "SELECT * FROM users WHERE name = ?", '["Alice"]')
        assert result.success
        data = json.loads(result.output)
        assert data["count"] == 1

    def test_params_json_single_value(self, db):
        result = sqlite_query(db, "SELECT * FROM users WHERE id = ?", "1")
        assert result.success
        data = json.loads(result.output)
        assert data["count"] == 1

    def test_invalid_params_json(self, db):
        result = sqlite_query(db, "SELECT 1", "not json")
        assert not result.success
        assert "invalid params" in result.error

    def test_missing_db_path(self):
        result = sqlite_query("", "SELECT 1")
        assert not result.success
        assert "required" in result.error

    def test_missing_sql(self, db):
        result = sqlite_query(db, "")
        assert not result.success
        assert "required" in result.error

    def test_sql_error(self, db):
        result = sqlite_query(db, "SELECT * FROM nonexistent")
        assert not result.success
        assert "sql error" in result.error

    def test_bad_db_path(self, tmp_path):
        path = str(tmp_path / "bad" / "file.db")
        result = sqlite_query(path, "SELECT 1")
        assert not result.success
        assert "cannot open" in result.error

    def test_json_types(self, db):
        result = sqlite_query(db, "SELECT ? AS val", '["hello", 42, true, null]')
        assert not result.success


class TestSqliteSchema:
    def test_tables_listed(self, db):
        result = sqlite_schema(db)
        assert result.success
        schema = json.loads(result.output)
        assert "users" in schema["tables"]
        assert "orders" in schema["tables"]

    def test_columns(self, db):
        result = sqlite_schema(db)
        schema = json.loads(result.output)
        cols = {c["name"]: c for c in schema["tables"]["users"]["columns"]}
        assert cols["name"]["type"] == "TEXT"
        assert cols["name"]["notnull"] is True

    def test_indexes(self, db):
        result = sqlite_schema(db)
        schema = json.loads(result.output)
        assert "idx_orders_user" in schema["tables"]["orders"]["indexes"]

    def test_missing_db_path(self):
        result = sqlite_schema("")
        assert not result.success

    def test_bad_db_path(self, tmp_path):
        path = str(tmp_path / "nonexistent" / "db.sqlite")
        result = sqlite_schema(path)
        assert not result.success
        assert "cannot open" in result.error
