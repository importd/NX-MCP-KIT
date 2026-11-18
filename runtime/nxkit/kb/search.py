"""Query the local NXOpen API index."""

import sqlite3

from ..library.index import tokens


def _normalize(text):
    return (text or "").lower().replace("_", "")


class Kb:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(str(db_path))
        self.tables = self._tables()

    def _tables(self):
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {row[0] for row in rows}

    def search(self, query, src="all", k=8):
        query_tokens = tokens(query or "")
        if not query_tokens:
            return []
        sql = (
            "SELECT name, short, summary, source, lic, py, kind "
            "FROM api_fts WHERE api_fts MATCH ?"
        )
        params = [query_tokens]
        if src in ("xml", "pyi"):
            sql += " AND source = ?"
            params.append(src)
        elif src != "all":
            return []
        sql += " LIMIT ?"
        params.append(max(int(k) * 5, 20))
        rows = self.conn.execute(sql, params).fetchall()

        wanted = _normalize(query)

        def rank(row):
            name, short = row[0], row[1]
            score = 0
            if _normalize(short) == wanted:
                score += 10
            elif _normalize(name).endswith(wanted):
                score += 5
            elif wanted in _normalize(name):
                score += 2
            if row[6] == "T":
                score += 2
            if row[3] == "pyi":
                score += 1
            return -score

        rows = sorted(rows, key=rank)[: int(k)]
        return [
            {
                "name": row[0],
                "short": row[1],
                "summary": row[2],
                "source": row[3],
                "lic": row[4],
                "py": row[5],
                "kind": row[6],
            }
            for row in rows
        ]
