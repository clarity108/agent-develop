from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ToolCall:
    id: str
    type: str
    function_name: str
    function_args: dict


@dataclass
class UsageInfo:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class StreamChunk:
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    done: bool = False


@dataclass
class ChatResponse:
    role: str = "assistant"
    content: str = ""
    error: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: "UsageInfo" = field(default_factory=UsageInfo)
    reasoning_content: str = ""


class DashScopeLLMClient:
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(
        self,
        api_key: str,
        model: str = "glm-5.2",
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = 60,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _message_to_dict(self, msg) -> dict[str, Any]:
        d: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        if hasattr(msg, "tool_name") and msg.tool_name:
            d["tool_name"] = msg.tool_name
        return d

    def _tool_def_to_dict(self, defn: dict) -> dict[str, Any]:
        return {
            "type": "function",
            "function": defn["function"],
        }

    def _build_body(self, messages, tools=None, **extra: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [self._message_to_dict(m) for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            body["tools"] = [self._tool_def_to_dict(d) for d in tools]
        body.update(extra)
        return body

    def _send(self, url: str, body: dict, headers: dict[str, str]) -> httpx.Response:
        with httpx.Client(timeout=self.timeout) as client:
            return client.post(url, json=body, headers=headers)

    def chat(
        self,
        messages,
        tools: list[dict] | None = None,
        **extra: Any,
    ) -> ChatResponse:
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        body = self._build_body(messages, tools=tools, **extra)

        try:
            resp = self._send(url, body, headers)

            if resp.status_code != 200:
                data = resp.json()
                error_msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                return ChatResponse(content="", error=error_msg)

            data = resp.json()
            if isinstance(data, list):
                data = data[0] if data else {}
            choices = data.get("choices", [])
            if not choices:
                content = data.get("output", {}).get("content", "") if isinstance(data, dict) else ""
                if content:
                    return ChatResponse(content=content, role="assistant")
                error_text = data.get("error", {}).get("message", "") if isinstance(data, dict) else ""
                if not error_text:
                    error_text = data.get("message", "") if isinstance(data, dict) else ""
                if not error_text:
                    error_text = f"empty response from API (status {resp.status_code})"
                return ChatResponse(content="", error=error_text)
            choice = choices[0]
            msg = choice.get("message", choice.get("output", {}))
            if isinstance(msg, str):
                return ChatResponse(content=msg, role="assistant")
            if not isinstance(msg, dict):
                msg = {}

            tool_calls = []
            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    type=tc.get("type", "function"),
                    function_name=fn.get("name", ""),
                    function_args=args,
                ))

            usage = data.get("usage", {})
            return ChatResponse(
                role=msg.get("role", "assistant"),
                content=msg.get("content", ""),
                reasoning_content=msg.get("reasoning_content", ""),
                tool_calls=tool_calls,
                usage=UsageInfo(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                ),
            )
        except (httpx.HTTPError, ConnectionError, TimeoutError) as e:
            return ChatResponse(content="", error=str(e))
        except (KeyError, IndexError, ValueError) as e:
            return ChatResponse(content="", error=f"unexpected response format: {e}")

    def stream_chat(self, messages, tools=None, **extra):
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        body = self._build_body(messages, tools=tools, **extra)
        body["stream"] = True

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", url, json=body, headers=headers) as resp:
                    if resp.status_code != 200:
                        data = resp.read().json()
                        error_msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                        yield ChatResponse(content="", error=error_msg)
                        return

                    accumulated_tool_calls: list[ToolCall] = []
                    for line in resp.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            if accumulated_tool_calls:
                                yield StreamChunk(done=True, tool_calls=accumulated_tool_calls)
                            else:
                                yield StreamChunk(done=True)
                            return

                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError:
                            continue

                        choices = data.get("choices", [])
                        if not choices:
                            out = data.get("output", {})
                            content = out.get("content", "") if isinstance(out, dict) else ""
                            if content:
                                yield StreamChunk(content=content, done=True)
                            else:
                                yield StreamChunk(done=True)
                            return
                        choice = choices[0]
                        delta = choice.get("delta", {})
                        content = delta.get("content", "")
                        tool_calls_delta = delta.get("tool_calls", [])

                        if content:
                            yield StreamChunk(content=content)

                        if tool_calls_delta:
                            for tc_delta in tool_calls_delta:
                                tc_id = tc_delta.get("id", "")
                                fn = tc_delta.get("function", {})
                                fn_name = fn.get("name", "")
                                fn_args_str = fn.get("arguments", "")
                                if tc_id and fn_name:
                                    try:
                                        fn_args = json.loads(fn_args_str) if fn_args_str else {}
                                    except (json.JSONDecodeError, TypeError):
                                        fn_args = {}
                                    accumulated_tool_calls.append(ToolCall(
                                        id=tc_id, type="function",
                                        function_name=fn_name, function_args=fn_args,
                                    ))

                    yield StreamChunk(done=True, tool_calls=accumulated_tool_calls or None)
        except (httpx.HTTPError, ConnectionError, TimeoutError) as e:
            yield ChatResponse(content="", error=str(e))
        except (KeyError, IndexError, ValueError) as e:
            yield ChatResponse(content="", error=f"unexpected response format: {e}")
