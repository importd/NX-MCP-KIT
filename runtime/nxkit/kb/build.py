"""NXOpen API knowledge base builder.

Parses the licensed NX installation's own documentation:
- NXOpen*.xml (managed .NET docs; NX10 has it under UGII/managed)
- UGOPEN/pythonStubs/NXOpen/*.pyi (NX2512+)

The index is a private SQLite FTS5 file and must not be redistributed
(the docs are Siemens content).
"""

import re
import sqlite3
from pathlib import Path

from ..library.index import tokens

_MEMBER = re.compile(r'<member name="([A-Z]):([^"]+)">')
_LICENSE = re.compile(r"License requirements:\s*([^<]+)")
_LICENSE_QUOTED = re.compile(r'\("([^"]+)"\)')
_TAG = re.compile(r"<[^>]+>")
_CLASS = re.compile(r"^class\s+(\w+)")
_DEF = re.compile(r"^\s*def\s+(\w+)")


class KbBuilder:
    def __init__(self, nx_root):
        self.root = Path(nx_root)

    def _xml_paths(self):
        found = []
        for rel in ("NXBIN/managed", "UGII/managed"):
            folder = self.root / rel
            if folder.is_dir():
                found.extend(sorted(folder.glob("NXOpen*.xml")))
        return found

    def _pyi_paths(self):
        folder = self.root / "UGOPEN" / "pythonStubs" / "NXOpen"
        if not folder.is_dir():
            return []
        return sorted(folder.glob("*.pyi"))

    def build(self, db_path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.is_file():
            db_path.unlink()
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE VIRTUAL TABLE api_fts USING fts5("
            "body, name UNINDEXED, short UNINDEXED, summary UNINDEXED, "
            "source UNINDEXED, lic UNINDEXED, py UNINDEXED, kind UNINDEXED)"
        )
        members = 0
        for xml_path in self._xml_paths():
            members += self._index_xml(conn, xml_path)
        py_members = 0
        for pyi_path in self._pyi_paths():
            py_members += self._index_pyi(conn, pyi_path)
        conn.commit()
        conn.close()
        return {"members": members + py_members, "indexed_py": py_members}

    def _insert(self, conn, name, summary, source, lic, py, kind):
        short = name.rsplit(".", 1)[-1]
        raw = "%s %s %s" % (name, summary or "", lic or "")
        body = tokens(raw) + " " + raw.lower().replace("_", " ")
        conn.execute(
            "INSERT INTO api_fts(body, name, short, summary, source, lic, py, kind) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (body, name, short, (summary or "")[:500], source, lic or "", py or "", kind),
        )

    def _index_xml(self, conn, path):
        text = path.read_text(encoding="utf-8", errors="replace")
        count = 0
        for block in text.split("<member name=")[1:]:
            match = _MEMBER.match("<member name=" + block[:200])
            if not match:
                continue
            kind, full = match.group(1), match.group(2)
            body = block.split("</member>", 1)[0]
            summary = " ".join(_TAG.sub(" ", body).split())
            summary = re.sub(r"License requirements:.*", "", summary).strip()
            licence = ""
            licence_match = _LICENSE.search(body)
            if licence_match:
                quoted = _LICENSE_QUOTED.search(licence_match.group(1))
                licence = quoted.group(1) if quoted else licence_match.group(1).strip()
            py = None
            if kind == "T":
                py = full
            elif kind == "M":
                py = re.sub(r"\(.*", "", full)
            self._insert(conn, full, summary, "xml", licence, py, kind)
            count += 1
        return count

    def _index_pyi(self, conn, path):
        module = path.stem
        current = None
        count = 0
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            class_match = _CLASS.match(line)
            if class_match:
                current = class_match.group(1)
                full = "NXOpen.%s.%s" % (module, current)
                self._insert(conn, full, "", "pyi", "", full, "T")
                count += 1
                continue
            def_match = _DEF.match(line)
            if def_match and current:
                full = "NXOpen.%s.%s.%s" % (module, current, def_match.group(1))
                py = "NXOpen.%s.%s" % (module, current)
                self._insert(conn, full, line.strip(), "pyi", "", py, "M")
                count += 1
        return count
