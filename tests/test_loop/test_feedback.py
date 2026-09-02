import pytest

from src.loop.feedback import FeedbackLoop, PytestRunner, RetryConfig


class TestFeedbackLoop:
    def test_passes_on_first_try(self):
        loop = FeedbackLoop(max_retries=3)
        counter = {"n": 0}

        def action():
            counter["n"] += 1
            return "result"

        def validator(r):
            return r == "result"

        result = loop.run(action, validator)
        assert result.passed is True
        assert result.attempts == 1
        assert counter["n"] == 1

    def test_retries_then_passes(self):
        loop = FeedbackLoop(max_retries=3)
        counter = {"n": 0}

        def action():
            counter["n"] += 1
            return "good" if counter["n"] >= 2 else "bad"

        def validator(r):
            return r == "good"

        result = loop.run(action, validator)
        assert result.passed is True
        assert result.attempts == 2
        assert counter["n"] == 2

    def test_fails_after_max_retries(self):
        loop = FeedbackLoop(max_retries=2)
        counter = {"n": 0}

        def action():
            counter["n"] += 1
            return "always_bad"

        def validator(r):
            return False

        result = loop.run(action, validator)
        assert result.passed is False
        assert result.attempts == 2
        assert counter["n"] == 2


class TestPytestRunner:
    def test_passed_with_success(self):
        runner = PytestRunner(command="python --version")
        result = runner.run()
        assert runner.passed(result) is True

    def test_passed_with_failure(self):
        runner = PytestRunner(command="python -c \"import sys; sys.exit(1)\"")
        result = runner.run()
        assert runner.passed(result) is False


class TestRetryConfig:
    def test_defaults(self):
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.backoff_factor == 1.0

    def test_custom_values(self):
        config = RetryConfig(max_retries=5, backoff_factor=2.0)
        assert config.max_retries == 5
        assert config.backoff_factor == 2.0
