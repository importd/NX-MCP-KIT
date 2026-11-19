"""Run recorder: turns MCP tool calls into an auditable event stream.

One run = one task attempt with a fixed config tuple (model, skill_version,
library_state, nx_version, tool_surface). Everything the metrics layer uses is
derived from these events; nothing is reconstructed after the fact.
"""

import hashlib
import json
import time
import uuid
from pathlib import Path

GEOMETRY_TOOLS = ("nx_block", "nx_hole", "nx_fillet", "nx_chamfer", "nx_boolean",
                  "nx_move_face", "nx_shell", "nx_delete_body", "nx_extrude",
                  "nx_revolve", "nx_run_python")


class RunRecorder:
    def __init__(self, task_id, config, runs_dir):
        self.task_id = task_id
        self.config = dict(config)
        self.runs_dir = Path(runs_dir)
        self.run_id = "%s-%s-%s" % (task_id, time.strftime("%Y%m%d%H%M%S"), uuid.uuid4().hex[:6])
        self.started = time.time()
        self.events = []
        self.outcome = "error"
        self.tokens = None
        self.prompt_tokens = None
        self.part_path = None
        self._closed = False

    def record(self, tool, args, envelope):
        digest = hashlib.sha256(
            json.dumps(args or {}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        verify = envelope.get("verify") if isinstance(envelope, dict) else None
        error = (envelope or {}).get("error") or {}
        self.events.append(
            {
                "seq": len(self.events) + 1,
                "tool": tool,
                "ok": bool((envelope or {}).get("ok")),
                "error_code": error.get("code"),
                "duration_ms": (envelope or {}).get("elapsed_ms"),
                "args_digest": "sha256:" + digest,
                "has_verify": bool(verify),
            }
        )
        return envelope

    def close(self, outcome, seconds=None, part_path=None, tokens=None, prompt_tokens=None):
        self.outcome = outcome
        self.part_path = str(part_path) if part_path else None
        self.tokens = tokens
        self.prompt_tokens = prompt_tokens
        self._closed = True
        return self.to_dict(seconds)

    def to_dict(self, seconds=None):
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "config": self.config,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.started)),
            "seconds": round(seconds if seconds is not None else (time.time() - self.started), 3),
            "tokens": self.tokens,
            "prompt_tokens": self.prompt_tokens,
            "events": self.events,
            "outcome": self.outcome,
            "artifacts": {"part_path": self.part_path} if self.part_path else {},
        }

    def write(self, seconds=None):
        data = self.to_dict(seconds)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self.runs_dir / (self.run_id + ".json")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path, data
