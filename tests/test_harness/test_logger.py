import pytest
from io import StringIO

from src.harness.logger import AgentLogger


class TestAgentLogger:
    def test_log_returns_entry(self):
        logger = AgentLogger()
        entry = logger.log("INFO", "hello")
        assert entry["level"] == "INFO"
        assert entry["message"] == "hello"
        assert "timestamp" in entry

    def test_log_with_context(self):
        logger = AgentLogger()
        entry = logger.log("DEBUG", "tool call", context={"tool": "read_file"})
        assert entry["context"] == {"tool": "read_file"}

    def test_filter_by_level(self):
        logger = AgentLogger(level="WARNING")
        entries = logger.get_entries()
        logger.log("DEBUG", "should be filtered")
        logger.log("INFO", "should be filtered")
        logger.log("WARNING", "should appear")
        logger.log("ERROR", "should appear")
        assert len(logger.get_entries()) == 2

    def test_get_entries_returns_all(self):
        logger = AgentLogger()
        logger.log("INFO", "first")
        logger.log("INFO", "second")
        assert len(logger.get_entries()) == 2

    def test_clear_entries(self):
        logger = AgentLogger()
        logger.log("INFO", "a")
        logger.log("INFO", "b")
        logger.clear()
        assert logger.get_entries() == []

    def test_log_levels(self):
        logger = AgentLogger()
        logger.log("INFO", "info msg")
        logger.log("ERROR", "error msg")
        logger.log("WARNING", "warn msg")
        logger.log("DEBUG", "debug msg")
        entries = logger.get_entries()
        assert len(entries) == 4
        levels = [e["level"] for e in entries]
        assert "INFO" in levels
        assert "ERROR" in levels
