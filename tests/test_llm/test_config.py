import pytest

from src.llm.config import load_config, build_client


class TestLoadConfig:
    def test_load_yaml_config(self, tmp_path):
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            "llm:\n"
            "  provider: dashscope\n"
            "  api_key: sk-test123\n"
            "  model: qwen-max\n"
            "  base_url: https://example.com/v1\n"
        )
        config = load_config(str(config_file))
        assert config["llm"]["provider"] == "dashscope"
        assert config["llm"]["api_key"] == "sk-test123"
        assert config["llm"]["model"] == "qwen-max"
        assert config["llm"]["base_url"] == "https://example.com/v1"

    def test_load_default_config(self):
        config = load_config("config/default.yaml")
        assert "llm" in config
        assert "api_key" in config["llm"]

    def test_load_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path.yaml")


class TestBuildClient:
    def test_builds_dashscope_client(self, tmp_path):
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            "llm:\n"
            "  provider: dashscope\n"
            "  api_key: sk-test456\n"
            "  model: glm-2.5\n"
            "  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1\n"
            "  temperature: 0.5\n"
            "  max_tokens: 1024\n"
        )
        config = load_config(str(config_file))
        client = build_client(config["llm"])

        assert client.api_key == "sk-test456"
        assert client.model == "glm-2.5"
        assert client.temperature == 0.5
        assert client.max_tokens == 1024
        assert "dashscope" in client.base_url
