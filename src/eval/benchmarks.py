from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Benchmark:
    name: str
    task: str
    check: Callable[[str], bool]
    max_steps: int = 10
    max_time: float = 30.0
    use_llm: bool = True


def _has_word(word: str) -> Callable[[str], bool]:
    return lambda result: word.lower() in result.lower()


def get_benchmarks() -> list[Benchmark]:
    return [
        Benchmark(
            name="create_file",
            task="create a file",
            check=_has_word("created"),
            use_llm=False,
        ),
        Benchmark(
            name="read_file",
            task="read output.txt",
            check=lambda r: len(r) > 0,
            use_llm=False,
        ),
        Benchmark(
            name="git_init",
            task="init git",
            check=_has_word("initialized"),
            use_llm=False,
        ),
        Benchmark(
            name="git_commit",
            task="commit changes",
            check=_has_word("committed"),
            use_llm=False,
        ),
        Benchmark(
            name="list_files",
            task="list files",
            check=lambda r: len(r) > 0,
            use_llm=False,
        ),
        Benchmark(
            name="llm_read",
            task="read the file output.txt and tell me its content",
            check=lambda r: len(r) > 5,
            use_llm=True,
        ),
        Benchmark(
            name="llm_create",
            task="create a file named test.txt with content hello",
            check=_has_word("created"),
            use_llm=True,
        ),
    ]
