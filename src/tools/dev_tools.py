from __future__ import annotations

import ast
import io
import json
import re
import subprocess
import sys
from pathlib import Path

from .file_tools import ToolResult
from .metadata import tool


def _signature(node: ast.AST) -> str:
    args = node.args
    params = []
    for a in args.args:
        params.append(a.arg)
    if args.vararg:
        params.append(f"*{args.vararg.arg}")
    for a in args.kwonlyargs:
        params.append(f"{a.arg}: ..." if not a.annotation else "")
    if args.kwarg:
        params.append(f"**{args.kwarg.arg}")
    for d in reversed(args.defaults):
        pass
    defaults = args.defaults
    n_required = len(args.args) - len(defaults)
    for i, a in enumerate(args.args):
        if i >= n_required and i < len(args.args):
            di = i - n_required
            if di < len(defaults):
                pass
    if defaults:
        for i in range(len(args.args)):
            if i >= n_required:
                di = i - n_required
                params[i] = f"{args.args[i].arg} = ..."
    return "(" + ", ".join(params) + ")"


def _extract_docstring(node: ast.AST) -> str:
    body = getattr(node, "body", None)
    if not body:
        return ""
    first = body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first.value.value.split("\n")[0].strip()
    return ""


def _analyze_node(node: ast.AST, depth: int, max_depth: int, in_class: str | None = None) -> dict:
    result: dict = {"classes": [], "functions": [], "docstrings": []}
    for child in node.body:
        if isinstance(child, ast.ClassDef):
            cls_info: dict = {"name": child.name}
            cls_info["methods"] = []
            for method in child.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cls_info["methods"].append(method.name)
            result["classes"].append(cls_info)
            if depth < max_depth:
                nested = _analyze_node(child, depth + 1, max_depth, in_class=child.name)
                for cls in nested["classes"]:
                    result["classes"].append(cls)
            if in_class and _extract_docstring(child):
                doc = _extract_docstring(child)
                result["docstrings"].append(f"class {child.name}: {doc}")

        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["functions"].append(child.name)
            doc = _extract_docstring(child)
            if doc:
                result["docstrings"].append(f"def {child.name}: {doc}")

        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            pass

    return result


@tool("Analyzes a Python source file using AST and returns imports, classes, functions, and docstrings")
def analyze_code(path: str, max_depth: int = 1) -> ToolResult:
    p = Path(path)
    if not p.exists():
        return ToolResult(success=False, output="", error=f"file not found: {path}")
    if not p.suffix == ".py":
        return ToolResult(success=False, output="", error=f"not a Python file: {path}")

    try:
        source = p.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(p))
    except SyntaxError as e:
        return ToolResult(success=False, output="", error=f"syntax error: {e}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))

    imports: list[str] = []
    classes: list[dict] = []
    functions: list[str] = []
    docstrings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if alias.asname:
                    name = f"{name} as {alias.asname}"
                imports.append(name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                name = alias.name
                if alias.asname:
                    name = f"{name} as {alias.asname}"
                imports.append(f"{module}.{name}")

    def analyze_body(body: list, depth: int):
        for node in body:
            if isinstance(node, ast.ClassDef):
                methods = []
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(child.name)
                classes.append({"name": node.name, "methods": methods})
                if depth < max_depth:
                    analyze_body(node.body, depth + 1)
                doc = _extract_docstring(node)
                if doc:
                    docstrings.append(f"class {node.name}: {doc}")

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
                doc = _extract_docstring(node)
                if doc:
                    docstrings.append(f"def {node.name}: {doc}")

    analyze_body(tree.body, 0)

    result = {
        "file": str(p),
        "imports": imports,
        "classes": classes,
        "functions": functions,
        "docstrings": docstrings,
    }
    return ToolResult(success=True, output=json.dumps(result, indent=2))


@tool("Runs pytest on the specified paths and returns structured pass/fail/error counts and failure details")
def run_tests(paths: str = ".", timeout: int = 120) -> ToolResult:
    try:
        cmd = [sys.executable, "-m", "pytest", paths, "--tb=short", "--no-header", "-q"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        combined = output + "\n" + stderr if stderr else output

        passed = 0
        failed = 0
        errors = 0
        skipped = 0
        failures: list[dict] = []

        for line in combined.split("\n"):
            if " passed" in line and " failed" in line:
                nums = re.findall(r"(\d+)", line.split("failed")[0])
                if nums:
                    passed = int(nums[0])
            m = re.search(r"(\d+) passed", line)
            if m:
                passed = int(m.group(1))
            m = re.search(r"(\d+) failed", line)
            if m:
                failed = int(m.group(1))
            m = re.search(r"(\d+) error", line)
            if m:
                errors = int(m.group(1))
            m = re.search(r"(\d+) skipped", line)
            if m:
                skipped = int(m.group(1))

        if failed > 0 or errors > 0:
            lines = combined.split("\n")
            current_test = ""
            current_error = ""
            in_failure = False
            for line in lines:
                m = re.match(r"(tests/.*?::.*)$", line.strip())
                if m and ("FAIL" in line or "ERROR" in line or line.startswith("FAILED")):
                    if current_test:
                        failures.append({"test": current_test, "error": current_error[:200]})
                    current_test = m.group(1)
                    current_error = ""
                    in_failure = True
                    continue
                if in_failure and current_test:
                    if line.strip().startswith("_"):
                        in_failure = False
                        failures.append({"test": current_test, "error": current_error[:200]})
                        current_test = ""
                        current_error = ""
                    elif line.strip() and not line.startswith(" "):
                        in_failure = False
                        failures.append({"test": current_test, "error": current_error[:200]})
                        current_test = ""
                        current_error = ""
                    else:
                        current_error += line.strip() + " "
            if current_test:
                failures.append({"test": current_test, "error": current_error[:200]})

        result = {
            "exit_code": proc.returncode,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "failures": failures[:20],
        }

        if proc.returncode == 0:
            return ToolResult(success=True, output=json.dumps(result, indent=2))
        return ToolResult(success=False, output=json.dumps(result, indent=2), error=f"tests failed: {failed} failures, {errors} errors")
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error=f"timeout: pytest exceeded {timeout}s")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool("Installs Python packages via pip. Supports multiple packages and version constraints")
def pip_install(packages: str, extra_args: str = "") -> ToolResult:
    if not packages or not packages.strip():
        return ToolResult(success=False, output="", error="packages argument is required")

    try:
        cmd = [sys.executable, "-m", "pip", "install"]
        if extra_args.strip():
            cmd.extend(extra_args.strip().split())
        cmd.extend(packages.strip().split())

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        combined = output
        if stderr:
            combined += "\n" + stderr

        if proc.returncode == 0:
            installed = []
            for line in output.split("\n"):
                m = re.search(r"Successfully installed (.+)", line)
                if m:
                    installed = m.group(1).split(" ")
                    break
            return ToolResult(success=True, output=f"Installed: {', '.join(installed) if installed else packages}")
        return ToolResult(success=False, output=combined, error=f"pip install failed (exit code {proc.returncode})")
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error="timeout: pip install exceeded 120s")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool("Lists installed Python packages, optionally filtered by name substring")
def pip_list(filter_name: str = "") -> ToolResult:
    try:
        cmd = [sys.executable, "-m", "pip", "list", "--format=columns"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (proc.stdout or "").strip()

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            return ToolResult(success=False, output=output, error=f"pip list failed: {stderr}")

        lines = output.split("\n")
        packages: list[dict] = []
        header_skipped = False
        for line in lines:
            if not header_skipped:
                if "Package" in line and "Version" in line:
                    header_skipped = True
                continue
            if not line.strip() or line.startswith("---"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                pkg = {"name": parts[0], "version": parts[1]}
                if filter_name and filter_name.lower() not in pkg["name"].lower():
                    continue
                packages.append(pkg)

        result = {
            "count": len(packages),
            "packages": packages,
        }
        return ToolResult(success=True, output=json.dumps(result, indent=2))
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error="timeout: pip list exceeded 30s")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))
