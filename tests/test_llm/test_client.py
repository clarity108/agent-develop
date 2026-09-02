import json
import pytest

from src.llm.client import DashScopeLLMClient, ChatMessage, ChatResponse


class TestDashScopeLLMClient:
    def test_build_request_body(self):
        client = DashScopeLLMClient(api_key="test-key", model="qwen-max", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        messages = [
            ChatMessage(role="system", content="You are helpful."),
            ChatMessage(role="user", content="hello"),
        ]
        body = client._build_body(messages)
        assert body["model"] == "qwen-max"
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "You are helpful."
        assert body["messages"][1]["role"] == "user"

    def test_build_request_headers(self):
        client = DashScopeLLMClient(api_key="sk-test123", model="qwen-plus")
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer sk-test123"
        assert headers["Content-Type"] == "application/json"

    def test_chat_parses_response(self, monkeypatch):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "choices": [{
                        "message": {"role": "assistant", "content": "Hello there!"},
                        "finish_reason": "stop",
                    }],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }

        def fake_post(url, json, headers):
            assert "chat/completions" in url
            return FakeResponse()

        client = DashScopeLLMClient(api_key="test-key", model="qwen-turbo")
        monkeypatch.setattr(client, "_send", fake_post)

        resp = client.chat([
            ChatMessage(role="user", content="hi"),
        ])

        assert isinstance(resp, ChatResponse)
        assert resp.content == "Hello there!"
        assert resp.role == "assistant"
        assert resp.usage.prompt_tokens == 10

    def test_chat_handles_api_error(self, monkeypatch):
        class FakeError:
            status_code = 401

            def json(self):
                return {"error": {"message": "Invalid API key"}}

        def fake_post(url, json, headers):
            return FakeError()

        client = DashScopeLLMClient(api_key="bad-key", model="qwen-turbo")
        monkeypatch.setattr(client, "_send", fake_post)

        resp = client.chat([ChatMessage(role="user", content="hi")])
        assert resp.content == ""
        assert resp.error == "Invalid API key"

    def test_chat_network_error(self, monkeypatch):
        def fake_post(url, json, headers):
            raise ConnectionError("network down")

        client = DashScopeLLMClient(api_key="test-key", model="qwen-turbo")
        monkeypatch.setattr(client, "_send", fake_post)

        resp = client.chat([ChatMessage(role="user", content="hi")])
        assert resp.content == ""
        assert resp.error is not None
        assert "network down" in resp.error

    def test_chat_with_temperature(self):
        client = DashScopeLLMClient(api_key="test-key", model="qwen-max", temperature=0.8)
        body = client._build_body([ChatMessage(role="user", content="test")])
        assert body["temperature"] == 0.8
