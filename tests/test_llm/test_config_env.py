import os
import pytest

from src.llm.config import load_config, _resolve_env_vars


class TestResolveEnvVars:
    def test_resolves_variable(self, monkeypatch):
        monkeypatch.setenv("MY_TEST_KEY", "secret123")
        assert _resolve_env_vars("${MY_TEST_KEY}") == "secret123"

    def test_resolves_in_string(self, monkeypatch):
        monkeypatch.setenv("HOST", "example.com")
        assert _resolve_env_vars("https://${HOST}/api") == "https://example.com/api"

    def test_raises_on_missing_variable(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(ValueError, match="environment variable not set: MISSING_VAR"):
            _resolve_env_vars("${MISSING_VAR}")

    def test_passes_through_non_string(self):
        assert _resolve_env_vars(42) == 42
        assert _resolve_env_vars(True) is True
        assert _resolve_env_vars(None) is None


class TestLoadConfigWithEnv:
    def test_loads_config_with_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-from-env")
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            "llm:\n"
            "  api_key: ${DASHSCOPE_API_KEY}\n"
            "  model: qwen-max\n"
        )
        config = load_config(str(config_file))
        assert config["llm"]["api_key"] == "sk-from-env"
        assert config["llm"]["model"] == "qwen-max"

    def test_raises_on_unset_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("UNSET_VAR", raising=False)
        config_file = tmp_path / "test.yaml"
        config_file.write_text("llm:\n  api_key: ${UNSET_VAR}\n")
        with pytest.raises(ValueError, match="UNSET_VAR"):
            load_config(str(config_file))
