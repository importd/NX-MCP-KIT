"""Append-only operation log (JSONL).

Every tool call that goes through the Router is written here, regardless of
whether the model later calls exp_save. This is the production-side source of
truth for auto-ingestion; evals have their own recorder for benchmarking.

Paths in args are reduced to a basename marker so the log can be shared without
leaking private directories.
"""

import json
import os
import time
from pathlib import Path

_PATH_KEYS = ("path", "to", "part", "file", "out", "source")


def sanitize_args(args, depth=0):
    if depth > 4 or not isinstance(args, dict):
        return args
    clean = {}
    for key, value in args.items():
        if isinstance(value, dict):
            clean[key] = sanitize_args(value, depth + 1)
        elif isinstance(value, str) and key in _PATH_KEYS and (
            "\\" in value or "/" in value or value.lower().endswith(".prt")
        ):
            clean[key] = "<path:%s>" % os.path.basename(value.replace("/", "\\"))
        else:
            clean[key] = value
    return clean


class OperationLog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event):
        record = dict(event)
        record.setdefault("ts", round(time.time(), 3))
        record.setdefault("event_id", "op-%d-%d" % (int(time.time() * 1000), len(self.read()) + 1))
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return record

    def read(self):
        if not self.path.is_file():
            return []
        events = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        return events

    def size(self):
        return len(self.read())
