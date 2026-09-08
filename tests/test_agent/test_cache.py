import pytest

from src.agent.cache import ToolCache
from src.agent.core import DevAgent, RuleBasedDevAgent, Decision
from src.tools.file_tools import write_file


class TestToolCache:
    def test_make_key(self):
        key = ToolCache.make_key("read_file", {"path": "test.txt"})
        assert key == "read_file:{\"path\": \"test.txt\"}"

    def test_make_key_sorted(self):
        key1 = ToolCache.make_key("read_file", {"b": 1, "a": 2})
        key2 = ToolCache.make_key("read_file", {"a": 2, "b": 1})
        assert key1 == key2

    def test_set_and_get(self):
        cache = ToolCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing(self):
        cache = ToolCache()
        assert cache.get("missing") is None

    def test_eviction_lru(self):
        cache = ToolCache(max_entries=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # move a to end
        cache.set("c", 3)  # should evict b (LRU)
        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3
        assert cache.size == 2

    def test_clear(self):
        cache = ToolCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size == 0
        assert cache.get("a") is None

    def test_invalidate_tool(self):
        cache = ToolCache()
        cache.set("read_file:{\"path\": \"a.txt\"}", "content_a")
        cache.set("read_file:{\"path\": \"b.txt\"}", "content_b")
        cache.set("write_file:{\"path\": \"c.txt\"}", "ok")
        cache.invalidate_tool("read_file")
        assert cache.get("read_file:{\"path\": \"a.txt\"}") is None
        assert cache.get("read_file:{\"path\": \"b.txt\"}") is None
        assert cache.get("write_file:{\"path\": \"c.txt\"}") == "ok"

    def test_invalidate_path(self):
        cache = ToolCache()
        cache.set("read_file:{\"path\": \"/tmp/test.txt\"}", "content")
        cache.set("read_file:{\"path\": \"/tmp/other.txt\"}", "other")
        cache.invalidate_path("/tmp/test.txt")
        assert cache.get("read_file:{\"path\": \"/tmp/test.txt\"}") is None
        assert cache.get("read_file:{\"path\": \"/tmp/other.txt\"}") == "other"

    def test_stats(self):
        cache = ToolCache(max_entries=50)
        cache.set("a", 1)
        cache.set("b", 2)
        stats = cache.stats()
        assert stats == {"entries": 2, "max": 50}


class TestCacheIntegrationWithAgent:
    def test_cache_hit_on_repeated_read(self, tmp_path):
        target = tmp_path / "cache_test.txt"
        target.write_text("cached content")

        calls = []
        def fake_read_file(path):
            calls.append(path)
            from src.tools.file_tools import read_file
            return read_file(path)

        cache = ToolCache()
        agent = DevAgent(
            tools={"read_file": fake_read_file},
            tool_cache=cache,
            max_steps=5,
        )

        step = [0]
        def plan(task, step_num, **kwargs):
            if step[0] == 0:
                step[0] = 1
                return Decision(thought="read", action="use_tool",
                                tool_name="read_file", tool_args={"path": str(target)})
            if step[0] == 1:
                step[0] = 2
                return Decision(thought="read again", action="use_tool",
                                tool_name="read_file", tool_args={"path": str(target)})
            return Decision(thought="done", action="answer", answer="ok")

        agent._plan = plan
        agent.run("test")

        assert len(calls) == 1  # second call hit cache
        assert cache.size == 1

    def test_file_mod_invalidates_cache(self, tmp_path):
        target = tmp_path / "mod_test.txt"
        target.write_text("original")

        calls = []
        def fake_read_file(path):
            calls.append(("read", path))
            from src.tools.file_tools import read_file
            return read_file(path)

        def fake_write_file(path, content):
            calls.append(("write", path))
            return write_file(path, content)

        cache = ToolCache()
        agent = DevAgent(
            tools={"read_file": fake_read_file, "write_file": fake_write_file},
            tool_cache=cache,
            max_steps=5,
        )

        step = [0]
        def plan(task, step_num, **kwargs):
            s = step[0]
            step[0] = s + 1
            if s == 0:
                return Decision(thought="read", action="use_tool",
                                tool_name="read_file", tool_args={"path": str(target)})
            if s == 1:
                return Decision(thought="write", action="use_tool",
                                tool_name="write_file", tool_args={"path": str(target), "content": "new"})
            if s == 2:
                return Decision(thought="read again", action="use_tool",
                                tool_name="read_file", tool_args={"path": str(target)})
            return Decision(thought="done", action="answer", answer="ok")

        agent._plan = plan
        agent.run("test")

        # First read: cache miss, execute
        # Write: cache miss, execute, invalidate path
        # Second read: cache miss again (invalidated), execute
        assert len(calls) == 3
