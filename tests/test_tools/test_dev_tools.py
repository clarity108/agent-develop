import json
import pytest
from pathlib import Path

from src.tools.dev_tools import analyze_code, run_tests, pip_install, pip_list


class TestAnalyzeCode:
    def test_basic_functions(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("""\
import os
from pathlib import Path
from typing import Optional

def hello(name: str) -> str:
    \"\"\"Say hello.\"\"\"
    return f"hello {name}"

def world():
    pass

class Foo:
    \"\"\"A test class.\"\"\"
    def __init__(self, x):
        pass
    def bar(self, y):
        pass
""")
        result = analyze_code(str(f))
        assert result.success is True
        data = json.loads(result.output)
        assert "os" in data["imports"]
        assert "pathlib.Path" in data["imports"]
        assert "hello" in data["functions"]
        assert "world" in data["functions"]
        assert len(data["classes"]) == 1
        assert data["classes"][0]["name"] == "Foo"
        assert "bar" in data["classes"][0]["methods"]
        assert any("Say hello" in d for d in data["docstrings"])

    def test_nonexistent_file(self):
        result = analyze_code("/nonexistent/file.py")
        assert result.success is False
        assert "not found" in result.error

    def test_not_python_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = analyze_code(str(f))
        assert result.success is False
        assert "not a Python file" in result.error

    def test_syntax_error(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(:")
        result = analyze_code(str(f))
        assert result.success is False
        assert "syntax error" in result.error

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        result = analyze_code(str(f))
        assert result.success is True
        data = json.loads(result.output)
        assert data["imports"] == []
        assert data["classes"] == []
        assert data["functions"] == []

    def test_nested_classes(self, tmp_path):
        f = tmp_path / "nested.py"
        f.write_text("""\
class Outer:
    def method1(self):
        pass
    class Inner:
        def method2(self):
            pass
""")
        result = analyze_code(str(f))
        assert result.success is True
        data = json.loads(result.output)
        names = [c["name"] for c in data["classes"]]
        assert "Outer" in names
        assert "Inner" in names

    def test_async_functions(self, tmp_path):
        f = tmp_path / "async.py"
        f.write_text("""\
async def fetch_data():
    \"\"\"Fetch data.\"\"\"
    pass
""")
        result = analyze_code(str(f))
        assert result.success is True
        data = json.loads(result.output)
        assert "fetch_data" in data["functions"]

    def test_import_as(self, tmp_path):
        f = tmp_path / "alias.py"
        f.write_text("import numpy as np\nfrom os.path import join")
        result = analyze_code(str(f))
        assert result.success is True
        data = json.loads(result.output)
        assert "numpy as np" in data["imports"]
        assert "os.path.join" in data["imports"]


class TestRunTests:
    def test_nonexistent_path(self):
        result = run_tests("/nonexistent/tests/path")
        assert result.success is False
        data = json.loads(result.output)
        assert data["exit_code"] != 0

    def test_output_is_json(self, tmp_path):
        test_file = tmp_path / "test_simple.py"
        test_file.write_text("def test_pass():\n    assert True\n\ndef test_fail():\n    assert False\n")
        result = run_tests(str(test_file))
        data = json.loads(result.output)
        assert "passed" in data
        assert "failed" in data
        assert "exit_code" in data
        assert data["failed"] >= 1
        assert data["passed"] >= 1


class TestPipInstall:
    def test_empty_packages(self):
        result = pip_install("")
        assert result.success is False
        assert "required" in result.error

    def test_invalid_package(self):
        result = pip_install("nonexistent-package-xyz-12345")
        assert result.success is False


class TestPipList:
    def test_basic_list(self):
        result = pip_list()
        assert result.success is True
        data = json.loads(result.output)
        assert data["count"] > 0
        assert len(data["packages"]) > 0
        assert data["packages"][0]["name"]
        assert data["packages"][0]["version"]

    def test_filter(self):
        result = pip_list("pytest")
        assert result.success is True
        data = json.loads(result.output)
        for pkg in data["packages"]:
            assert "pytest" in pkg["name"].lower()

    def test_filter_no_match(self):
        result = pip_list("zzznonexistentzzz")
        assert result.success is True
        data = json.loads(result.output)
        assert data["count"] == 0
