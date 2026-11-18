"""Experience gate: block geometry changes until the library was searched.

State is per part; switching parts resets `searched`. Modes are hard (default),
soft and off; `skip_search=1` is the explicit escape hatch.
"""

import json
from pathlib import Path


class Gate:
    def __init__(self, path):
        self.path = Path(path)
        self.state = {"part": "current", "searched": False, "done": []}
        if self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.state.update(loaded)
            except (OSError, ValueError):
                pass

    @property
    def part(self) -> str:
        return self.state.get("part", "current")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")

    def _ensure_part(self, part: str) -> None:
        if self.state.get("part") != part:
            self.state = {"part": part, "searched": False, "done": []}
            self._save()

    def check(self, tool, part: str, library) -> dict | None:
        self._ensure_part(part)
        if self.state.get("searched"):
            return None
        query_terms = list(tool.k) or [tool.name]
        hits = []
        for term in query_terms:
            hits = [
                hit
                for hit in library.search(term, limit=5)
                if hit.get("c") in ("招式", "方案", "模板")
            ]
            if hits:
                break
        if not hits:
            return None
        ids = ",".join(hit["id"] for hit in hits[:3])
        return {
            "msg": "经验库里已有可复用的 %s；先 exp_search（0 命中也算），或传 skip_search=1" % ids,
            "next": "exp_search q=<短词>",
        }

    def mark_searched(self, part: str | None = None) -> None:
        self._ensure_part(part or self.part)
        self.state["searched"] = True
        self._save()
