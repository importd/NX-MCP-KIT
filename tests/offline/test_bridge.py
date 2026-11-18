import json
import threading
import time
from pathlib import Path

import pytest

from nxkit.bridge import BridgeClient, BridgeTimeout, BridgeUnavailable


def _fake_bridge(io_dir: Path, pid: int = 8016):
    """Thread that answers inbox files by writing outbox files."""
    pid_dir = io_dir / str(pid)
    inbox = pid_dir / "inbox"
    outbox = pid_dir / "outbox"
    inbox.mkdir(parents=True)
    outbox.mkdir()
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            for path in sorted(inbox.glob("*.json")):
                try:
                    req = json.loads(path.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                path.unlink()
                resp = {"data": {"echo": req["cmd"]}, "facts": {}}
                (outbox / (req["request_id"] + ".json")).write_text(
                    json.dumps(resp, ensure_ascii=False), encoding="utf-8"
                )
            time.sleep(0.01)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return stop


def test_submit_roundtrip_with_chinese_path(workdir):
    io_dir = workdir / "零件库" / "io"
    io_dir.mkdir(parents=True)
    stop = _fake_bridge(io_dir)
    try:
        client = BridgeClient(io_dir)
        res = client.submit(8016, "nx_block", {"x": 0}, timeout_s=3.0)
        assert res["data"]["echo"] == "nx_block"
    finally:
        stop.set()


def test_sessions_reads_status_files(workdir):
    io_dir = workdir / "io"
    pid_dir = io_dir / "8016"
    pid_dir.mkdir(parents=True)
    (pid_dir / "status.json").write_text(
        json.dumps({"pid": 8016, "nx": "2512", "py": "3.12", "alive": True, "heartbeat_age_s": 1.5}),
        encoding="utf-8",
    )
    sessions = BridgeClient(io_dir).sessions()
    assert [s["pid"] for s in sessions] == [8016]
    assert sessions[0]["nx"] == "2512"


def test_sessions_skips_corrupt_status(workdir):
    io_dir = workdir / "io"
    (io_dir / "1").mkdir(parents=True)
    (io_dir / "1" / "status.json").write_text("{not json", encoding="utf-8")
    assert BridgeClient(io_dir).sessions() == []


def test_missing_io_dir_raises_unavailable(workdir):
    with pytest.raises(BridgeUnavailable):
        BridgeClient(workdir / "nope").sessions()


def test_timeout_raises(workdir):
    io_dir = workdir / "io"
    (io_dir / "8016" / "inbox").mkdir(parents=True)
    with pytest.raises(BridgeTimeout):
        BridgeClient(io_dir).submit(8016, "nx_block", {}, timeout_s=0.2)


def test_timeout_withdraws_request(workdir):
    io_dir = workdir / "io"
    pid_dir = io_dir / "8016"
    (pid_dir / "inbox").mkdir(parents=True)
    with pytest.raises(BridgeTimeout):
        BridgeClient(io_dir).submit(8016, "nx_block", {}, timeout_s=0.2)
    assert list((pid_dir / "inbox").glob("*.json")) == []


def test_sessions_marks_stale_heartbeat_dead(workdir):
    import time

    io_dir = workdir / "io"
    pid_dir = io_dir / "8016"
    pid_dir.mkdir(parents=True)
    (pid_dir / "status.json").write_text(
        json.dumps({"pid": 8016, "alive": True, "updated": time.time() - 3600}),
        encoding="utf-8",
    )
    sessions = BridgeClient(io_dir).sessions()
    assert sessions[0]["alive"] is False
    assert sessions[0]["heartbeat_age_s"] > 60


def test_sessions_keeps_fresh_heartbeat_alive(workdir):
    import time

    io_dir = workdir / "io"
    pid_dir = io_dir / "8017"
    pid_dir.mkdir(parents=True)
    (pid_dir / "status.json").write_text(
        json.dumps({"pid": 8017, "alive": True, "updated": time.time() - 1}),
        encoding="utf-8",
    )
    sessions = BridgeClient(io_dir).sessions()
    assert sessions[0]["alive"] is True
    assert sessions[0]["heartbeat_age_s"] < 10


def test_stale_outbox_not_reused(workdir):
    io_dir = workdir / "io"
    stop = _fake_bridge(io_dir)
    try:
        outbox = io_dir / "8016" / "outbox"
        (outbox / "old-request.json").write_text(
            json.dumps({"data": {"echo": "stale"}}), encoding="utf-8"
        )
        res = BridgeClient(io_dir).submit(8016, "nx_hole", {}, timeout_s=3.0)
        assert res["data"]["echo"] == "nx_hole"
    finally:
        stop.set()
