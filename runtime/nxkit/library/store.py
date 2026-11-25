"""Experience library v2: moves / pits / recipes / templates + drafts.

Only entries whose evidence is an NX measurement within tolerance are indexed
(v=1); anything else lands in _drafts and stays out of search. Entries carry
usage counters so repeated wins can be ranked later.
"""

import json
import zipfile
from pathlib import Path

from .index import Index

CATEGORY_DIRS = {
    "招式": "moves",
    "坑": "pits",
    "方案": "recipes",
    "模板": "templates",
}
SEARCH_DIRS = ("moves", "pits", "recipes", "templates")


class LibraryError(Exception):
    pass


def _evidence_ok(evidence) -> bool:
    if not isinstance(evidence, dict):
        return False
    try:
        expect = float(evidence["expect"])
        got = float(evidence["got"])
        tol = float(evidence["tol"])
    except (KeyError, TypeError, ValueError):
        return False
    return abs(got - expect) <= tol


class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.index = None

    def init(self) -> "Library":
        self.root.mkdir(parents=True, exist_ok=True)
        for name in SEARCH_DIRS + ("_drafts",):
            (self.root / name).mkdir(exist_ok=True)
        self.index = Index(self.root / "index.db")
        # Rebuild the index from files so external edits stay searchable.
        for name in SEARCH_DIRS:
            for path in sorted((self.root / name).glob("*.json")):
                try:
                    entry = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(entry, dict) and entry.get("v") == 1:
                    self.index.upsert(entry)
        return self

    def _require_init(self) -> None:
        if self.index is None:
            raise LibraryError("call init() first")

    def _category_dir(self, entry: dict) -> str:
        category = entry.get("c")
        if category not in CATEGORY_DIRS:
            raise LibraryError("unknown category c=%r" % category)
        return CATEGORY_DIRS[category]

    def save(self, entry: dict, force_draft: bool = False) -> str:
        self._require_init()
        if not isinstance(entry, dict):
            raise LibraryError("entry must be an object")
        entry_id = entry.get("id")
        if not entry_id:
            raise LibraryError("entry needs id")
        directory = self._category_dir(entry)
        stored = dict(entry)
        stored.setdefault("usage", {"count": 0, "success": 0, "fail": 0, "last": None})
        verified = _evidence_ok(stored.get("evidence")) and not force_draft
        stored["v"] = 1 if verified else 0

        target_dir = self.root / directory if verified else self.root / "_drafts"
        path = target_dir / (entry_id + ".json")
        path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        if verified:
            self.index.upsert(stored)
            # A draft promoted to verified must not linger in _drafts.
            draft = self.root / "_drafts" / (entry_id + ".json")
            if draft.is_file():
                draft.unlink()
            return entry_id
        self.index.delete(entry_id)
        return "draft:" + entry_id

    def get(self, entry_id: str) -> dict | None:
        self._require_init()
        for name in SEARCH_DIRS:
            path = self.root / name / (entry_id + ".json")
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        draft = self.root / "_drafts" / (entry_id + ".json")
        if draft.is_file():
            return json.loads(draft.read_text(encoding="utf-8"))
        return None

    def search(self, query: str, limit: int = 10) -> list[dict]:
        self._require_init()
        results = []
        for entry_id in self.index.search(query, limit):
            entry = self.get(entry_id)
            if entry is not None:
                results.append(entry)
        return results

    def bump_usage(self, entry_id: str, ok=None) -> None:
        entry = self.get(entry_id)
        if entry is None:
            raise LibraryError("unknown entry: %s" % entry_id)
        directory = CATEGORY_DIRS.get(entry.get("c"))
        if directory is None:
            raise LibraryError("entry has no category: %s" % entry_id)
        usage = entry.setdefault("usage", {"count": 0, "success": 0, "fail": 0, "last": None})
        usage["count"] = int(usage.get("count", 0)) + 1
        if ok is True:
            usage["success"] = int(usage.get("success", 0)) + 1
        elif ok is False:
            usage["fail"] = int(usage.get("fail", 0)) + 1
        import datetime

        usage["last"] = datetime.date.today().isoformat()
        path = self.root / directory / (entry_id + ".json")
        path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

    def export_pack(self, dst) -> int:
        self._require_init()
        exported = 0
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in SEARCH_DIRS:
                for path in sorted((self.root / name).glob("*.json")):
                    entry = json.loads(path.read_text(encoding="utf-8"))
                    if entry.get("v") != 1:
                        continue
                    zf.writestr("%s/%s" % (name, path.name), json.dumps(entry, ensure_ascii=False))
                    exported += 1
        return exported

    def import_pack(self, src) -> int:
        self._require_init()
        imported = 0
        with zipfile.ZipFile(src) as zf:
            for name in sorted(zf.namelist()):
                if not name.endswith(".json"):
                    continue
                entry = json.loads(zf.read(name).decode("utf-8"))
                if self.save(entry).startswith("draft:"):
                    continue
                imported += 1
        return imported
