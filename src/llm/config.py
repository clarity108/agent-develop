from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from .client import DashScopeLLMClient


_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value) -> str:
    if not isinstance(value, str):
        return value
    def _replace(match):
        var_name = match.group(1)
        resolved = os.environ.get(var_name)
        if resolved is None:
            raise ValueError(f"environment variable not set: {var_name}")
        return resolved
    return _ENV_VAR_PATTERN.sub(_replace, value)


def _resolve_dict(obj) -> dict:
    if isinstance(obj, dict):
        return {k: _resolve_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_dict(item) for item in obj]
    return _resolve_env_vars(obj)


def load_config(path: str) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with open(file_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _resolve_dict(raw)


def build_client(llm_config: dict) -> DashScopeLLMClient:
    return DashScopeLLMClient(
        api_key=llm_config["api_key"],
        model=llm_config.get("model", "glm-2.5"),
        base_url=llm_config.get("base_url"),
        temperature=llm_config.get("temperature", 0.7),
        max_tokens=llm_config.get("max_tokens", 2048),
        timeout=llm_config.get("timeout", 60),
    )
