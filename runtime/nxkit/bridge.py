"""File-queue client for the in-NX bridge.

Layout: io/<nx_pid>/inbox/<request_id>.json and io/<nx_pid>/outbox/<request_id>.json.
The bridge ticks on the NX UI thread, drains the inbox and writes one JSON
payload per request. Files (not sockets) keep a crash traceable and need no
firewall entry; UTF-8 is explicit because paths contain Chinese.
"""

import json
import time
import uuid
from pathlib import Path

POLL_INTERVAL_S = 0.04


class BridgeUnavailable(Exception):
    """No io directory or no inbox for the requested NX session."""


class BridgeTimeout(Exception):
    """The bridge did not answer within timeout_s."""


class BridgeClient:
    def __init__(self, io_dir: Path):
        self.io_dir = Path(io_dir)

    def sessions(self) -> list[dict]:
        if not self.io_dir.is_dir():
            raise BridgeUnavailable("io dir not found: %s" % self.io_dir)
        sessions = []
        for entry in sorted(self.io_dir.iterdir()):
            status_path = entry / "status.json"
            if not entry.is_dir() or not status_path.is_file():
                continue
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(status, dict):
                sessions.append(status)
        return sessions

    def submit(self, pid: int, cmd: str, args: dict, timeout_s: float = 120.0) -> dict:
        if not isinstance(cmd, str) or not cmd:
            raise ValueError("cmd must be a non-empty string")
        if not isinstance(args, dict):
            raise ValueError("args must be an object")
        pid_dir = self.io_dir / str(pid)
        inbox = pid_dir / "inbox"
        if not inbox.is_dir():
            raise BridgeUnavailable("no inbox for pid %s: %s" % (pid, pid_dir))
        outbox = pid_dir / "outbox"
        outbox.mkdir(exist_ok=True)

        request_id = uuid.uuid4().hex
        payload = {
            "request_id": request_id,
            "cmd": cmd,
            "args": args,
            "created_at": time.time(),
        }
        pending = inbox / (request_id + ".tmp")
        ready = inbox / (request_id + ".json")
        pending.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        pending.replace(ready)

        response_path = outbox / (request_id + ".json")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if response_path.is_file():
                try:
                    return json.loads(response_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise BridgeUnavailable("bad bridge response: %s" % exc) from exc
            time.sleep(POLL_INTERVAL_S)
        # Withdraw the request so the bridge cannot execute it after we gave up.
        for stale in (ready, pending):
            try:
                stale.unlink()
            except OSError:
                pass
        raise BridgeTimeout(
            "bridge did not answer %s within %.1fs (request_id=%s)" % (cmd, timeout_s, request_id)
        )
