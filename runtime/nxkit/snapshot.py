"""Binary .prt snapshots. Files are not under git, so a big edit needs a copy.

Backups live under <root>/backups; the index is append-only JSONL so a crash
never loses earlier entries. Restoring over the source path is refused by the
caller when NX has that part open (Windows file lock raises OSError here).
"""

import json
import shutil
import time
from pathlib import Path


class SnapshotError(Exception):
    pass


class SnapshotStore:
    def __init__(self, root):
        self.root = Path(root)
        self.backups = self.root / "backups"
        self.index = self.root / "index.jsonl"

    def _ensure(self):
        self.backups.mkdir(parents=True, exist_ok=True)

    def _entries(self):
        if not self.index.is_file():
            return []
        entries = []
        for line in self.index.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
        return entries

    def save(self, part_path, note="") -> str:
        part = Path(part_path)
        if not part.is_file():
            raise SnapshotError("part not found: %s" % part)
        self._ensure()
        existing = self._entries()
        snapshot_id = str(max([int(entry["id"]) for entry in existing], default=0) + 1)
        backup = self.backups / (snapshot_id + part.suffix)
        shutil.copy2(part, backup)
        entry = {
            "id": snapshot_id,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": str(part),
            "backup": str(backup),
            "note": note,
        }
        with self.index.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return snapshot_id

    def list(self) -> list[dict]:
        return list(reversed(self._entries()))

    def restore(self, snapshot_id, to=None) -> Path:
        by_id = {entry["id"]: entry for entry in self._entries()}
        entry = by_id.get(str(snapshot_id))
        if entry is None:
            raise SnapshotError("unknown snapshot: %s" % snapshot_id)
        target = Path(to) if to else Path(entry["source"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry["backup"], target)
        return target
