from __future__ import annotations

import json
from pathlib import Path


class LongTermMemory:
    def __init__(self, store_dir: str):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, value) -> None:
        path = self._dir / f"{key}.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

    def load(self, key: str):
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def delete(self, key: str) -> None:
        path = self._dir / f"{key}.json"
        if path.exists():
            path.unlink()

    def list_keys(self) -> list[str]:
        return sorted(p.stem for p in self._dir.glob("*.json"))
