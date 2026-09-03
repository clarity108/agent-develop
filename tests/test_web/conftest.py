import importlib
import pytest

from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def _db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture(autouse=True)
def _client(_db_path, monkeypatch):
    storage = importlib.import_module("src.web.storage")
    importlib.reload(storage)
    monkeypatch.setattr(storage, "_db_path", lambda: _db_path)

    app_module = importlib.import_module("src.web.app")
    importlib.reload(app_module)

    storage.init_db()
    storage.delete_all_runs()
    return TestClient(app_module.app)


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    import importlib
    storage = importlib.import_module("src.web.storage")
    try:
        storage.delete_all_runs()
    except Exception:
        pass
