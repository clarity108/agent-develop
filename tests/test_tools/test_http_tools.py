import pytest

from src.tools.http_tools import http_get, http_post, http_request


class TestHttpGet:
    def test_invalid_url_format(self):
        result = http_get("not-a-url")
        assert result.success is False


class TestHttpPost:
    def test_invalid_json_body(self):
        result = http_post("http://example.com", json_body="{invalid")
        assert result.success is False
        assert "invalid JSON" in result.error


class TestHttpRequest:
    def test_unsupported_method(self):
        result = http_request("TRACE", "http://example.com")
        assert result.success is False
        assert "unsupported method" in result.error

    def test_invalid_json_body(self):
        result = http_request("POST", "http://example.com", json_body="{invalid")
        assert result.success is False
        assert "invalid JSON" in result.error
