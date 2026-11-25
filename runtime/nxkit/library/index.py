"""Full-text index over experience entries.

SQLite FTS5's unicode61 tokenizer splits Chinese poorly, so every Chinese run
is expanded into character bigrams before indexing and querying. ASCII words
are lowercased and matched as-is.
"""

import re
import sqlite3

_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")


def tokens(text: str) -> str:
    if not text:
        return ""
    parts: list[str] = []
    for match in _CJK_RUN.finditer(text):
        run = match.group(0)
        # Single characters give recall for one-character queries (孔 → 钻孔);
        # bigrams give precision for longer runs.
        parts.extend(run)
        if len(run) > 1:
            parts.extend(run[i : i + 2] for i in range(len(run) - 1))
    parts.extend(word.lower() for word in _ASCII_WORD.findall(text))
    return " ".join(sorted(set(parts)))


class Index:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts "
            "USING fts5(id UNINDEXED, tokens, title)"
        )

    def upsert(self, entry: dict) -> None:
        entry_id = entry["id"]
        self.delete(entry_id)
        body = " ".join(
            [
                entry.get("t", ""),
                " ".join(entry.get("k", [])),
                entry.get("general", ""),
            ]
        )
        self.conn.execute(
            "INSERT INTO entries_fts(id, tokens, title) VALUES (?, ?, ?)",
            (entry_id, tokens(body), entry.get("t", "")),
        )
        self.conn.commit()

    def delete(self, entry_id: str) -> None:
        self.conn.execute("DELETE FROM entries_fts WHERE id = ?", (entry_id,))
        self.conn.commit()

    def search(self, query: str, limit: int = 10) -> list[str]:
        query_tokens = tokens(query)
        if not query_tokens:
            return []
        try:
            rows = self.conn.execute(
                "SELECT id FROM entries_fts WHERE entries_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (query_tokens, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [row[0] for row in rows]
