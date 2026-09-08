from __future__ import annotations

import json

import httpx

from .file_tools import ToolResult
from .metadata import tool

_MAX_BODY = 50_000


def _truncate(text: str, limit: int = _MAX_BODY) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} total chars]"


def _format_response(resp: httpx.Response) -> str:
    status_line = f"HTTP {resp.status_code} {resp.reason_phrase}"
    headers = dict(resp.headers)
    content_type = headers.get("content-type", "")

    body = resp.text
    if "json" in content_type:
        try:
            body = json.dumps(json.loads(body), indent=2)
        except (json.JSONDecodeError, ValueError):
            pass
    body = _truncate(body)

    parts = [status_line]
    if content_type:
        parts.append(f"Content-Type: {content_type}")
    parts.append(f"\n{body}")
    return "\n".join(parts)


@tool("Sends an HTTP GET request and returns the response with status, headers, and body")
def http_get(url: str, headers: str = "", timeout: int = 30) -> ToolResult:
    try:
        header_dict: dict[str, str] = {}
        if headers.strip():
            for line in headers.strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    header_dict[k.strip()] = v.strip()

        resp = httpx.get(url, headers=header_dict, timeout=timeout, follow_redirects=True)
        return ToolResult(success=True, output=_format_response(resp))
    except httpx.TimeoutException:
        return ToolResult(success=False, output="", error=f"timeout: exceeded {timeout}s")
    except httpx.ConnectError as e:
        return ToolResult(success=False, output="", error=f"connection error: {e}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool("Sends an HTTP POST request with optional JSON body and returns the response")
def http_post(url: str, json_body: str = "", headers: str = "", timeout: int = 30) -> ToolResult:
    try:
        header_dict: dict[str, str] = {}
        if headers.strip():
            for line in headers.strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    header_dict[k.strip()] = v.strip()

        post_json: dict | None = None
        if json_body.strip():
            try:
                post_json = json.loads(json_body)
            except json.JSONDecodeError as e:
                return ToolResult(success=False, output="", error=f"invalid JSON body: {e}")

        resp = httpx.post(url, json=post_json, headers=header_dict, timeout=timeout, follow_redirects=True)
        return ToolResult(success=True, output=_format_response(resp))
    except httpx.TimeoutException:
        return ToolResult(success=False, output="", error=f"timeout: exceeded {timeout}s")
    except httpx.ConnectError as e:
        return ToolResult(success=False, output="", error=f"connection error: {e}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool("Sends an HTTP request with a custom method (PUT, DELETE, PATCH, HEAD) and returns the response")
def http_request(method: str, url: str, json_body: str = "", headers: str = "", timeout: int = 30) -> ToolResult:
    method = method.upper()
    if method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}:
        return ToolResult(success=False, output="", error=f"unsupported method: {method}")

    try:
        header_dict: dict[str, str] = {}
        if headers.strip():
            for line in headers.strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    header_dict[k.strip()] = v.strip()

        post_json: dict | None = None
        if json_body.strip():
            try:
                post_json = json.loads(json_body)
            except json.JSONDecodeError as e:
                return ToolResult(success=False, output="", error=f"invalid JSON body: {e}")

        resp = httpx.request(method, url, json=post_json, headers=header_dict, timeout=timeout, follow_redirects=True)
        return ToolResult(success=True, output=_format_response(resp))
    except httpx.TimeoutException:
        return ToolResult(success=False, output="", error=f"timeout: exceeded {timeout}s")
    except httpx.ConnectError as e:
        return ToolResult(success=False, output="", error=f"connection error: {e}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))
