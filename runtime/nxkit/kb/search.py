"""Query the local NXOpen API index."""

import sqlite3

from ..library.index import tokens


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
        sql += " ORDER BY rank LIMIT ?"
        params.append(int(k))
        rows = self.conn.execute(sql, params).fetchall()
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
