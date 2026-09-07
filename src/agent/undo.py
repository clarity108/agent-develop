from __future__ import annotations

import os
import shutil
import tempfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FileSnapshot:
    path: str
    before: Optional[bytes]
    after: Optional[bytes]
    exists_before: bool
    is_dir: bool = False

    @property
    def size(self) -> int:
        if self.before is None:
            return 0
        return len(self.before)


_SNAPSHOT_DIR = Path(os.environ.get("AGENT_UNDO_DIR", tempfile.mkdtemp(prefix="agent_undo_")))


class UndoManager:
    def __init__(self, snapshot_dir: Path | None = None):
        self._undo_stack: deque[FileSnapshot] = deque()
        self._redo_stack: deque[FileSnapshot] = deque()
        self._before_map: dict[str, tuple[bool, Optional[bytes]]] = {}
        self._snapshot_dir = snapshot_dir or _SNAPSHOT_DIR
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)

    def before_change(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            self._before_map[path] = (False, None)
        elif p.is_dir():
            self._before_map[path] = (True, None)
        else:
            try:
                self._before_map[path] = (True, p.read_bytes())
            except Exception:
                self._before_map[path] = (False, None)

    def after_change(self, path: str) -> bool:
        if path not in self._before_map:
            return False
        exists_before, before = self._before_map.pop(path)
        p = Path(path)

        if p.is_dir():
            self._undo_stack.append(FileSnapshot(
                path=str(p), before=None, after=None,
                exists_before=True, is_dir=True,
            ))
        else:
            after = p.read_bytes() if p.exists() else None
            self._undo_stack.append(FileSnapshot(
                path=str(p), before=before, after=after,
                exists_before=exists_before,
            ))

        self._redo_stack.clear()
        return True

    def backup_file(self, path: str) -> bool:
        self.before_change(path)
        self.after_change(path)
        return True

    def undo(self) -> Optional[dict]:
        if not self._undo_stack:
            return {"success": False, "message": "No undo available"}

        snap = self._undo_stack.pop()
        p = Path(snap.path)

        if snap.exists_before and snap.is_dir:
            if p.exists():
                shutil.rmtree(p)
            p.mkdir(parents=True, exist_ok=True)
        elif snap.exists_before and snap.before is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(snap.before)
        else:
            if p.exists():
                p.unlink()

        self._redo_stack.append(snap)
        return {"success": True, "path": snap.path, "message": f"Restored: {snap.path}"}

    def redo(self) -> Optional[dict]:
        if not self._redo_stack:
            return {"success": False, "message": "No redo available"}

        snap = self._redo_stack.pop()
        p = Path(snap.path)

        if snap.is_dir:
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
        elif snap.after is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(snap.after)
        elif snap.exists_before:
            if p.exists():
                p.unlink()

        self._undo_stack.append(snap)
        return {"success": True, "path": snap.path, "message": f"Redone: {snap.path}"}

    @property
    def undo_count(self) -> int:
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        return len(self._redo_stack)

    def stack_info(self) -> dict:
        return {"undo": self.undo_count, "redo": self.redo_count}

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._before_map.clear()
