import json
from pathlib import Path

import pytest

from nxkit.gate import Gate
from nxkit.ingest import candidates, ingest, signature, verify_drafts, write_drafts
from nxkit.library.store import Library
from nxkit.oplog import OperationLog, sanitize_args
from nxkit.registry import Registry
from nxkit.router import Router


class FakeBridge:
    def __init__(self, facts=None):
        self.calls = []
        self.facts = facts or {"volume": 60000.0, "faces": 6}

    def sessions(self):
        return [{"pid": 8016, "nx": "2512", "alive": True}]

    def submit(self, pid, cmd, args, timeout_s=120.0):
        self.calls.append(cmd)
        if cmd == "nx_bad":
            return {"error": {"code": "NX_FAIL", "msg": "boom"}}
        return {"data": {"feature": "BLOCK(0)"}, "facts": self.facts}


def _router(workdir, contract_dir, oplog=None, bridge=None):
    registry = Registry(contract_dir)
    library = Library(workdir / "library").init()
    gate = Gate(workdir / "workflow.json")
    return Router(
        registry, bridge or FakeBridge(), library, gate,
        precheck=None, security=None, oplog=oplog,
    )


def test_sanitize_args_strips_paths():
    clean = sanitize_args(
        {"path": r"D:\客户资料\模架\A-0021.prt", "x": 1, "nested": {"to": "C:/tmp/out.prt"}}
    )
    assert clean["path"] == "<path:A-0021.prt>"
    assert clean["nested"]["to"] == "<path:out.prt>"
    assert clean["x"] == 1


def test_operation_log_roundtrip(tmp_path):
    log = OperationLog(tmp_path / "oplog.jsonl")
    log.append({"tool": "nx_block", "ok": True, "args": {"length": 10}})
    log.append({"tool": "nx_hole", "ok": False, "error_code": "NX_FAIL"})
    events = log.read()
    assert [event["tool"] for event in events] == ["nx_block", "nx_hole"]
    assert events[0]["event_id"].startswith("op-")
    assert log.size() == 2


def test_router_writes_every_call_to_oplog(workdir, contract_dir):
    log = OperationLog(workdir / "oplog.jsonl")
    router = _router(workdir, contract_dir, oplog=log)
    ok = router.call("nx_block", {"length": 50, "width": 40, "height": 30, "skip_search": True})
    assert ok["ok"] is True
    router.call("nx_screenshot", {"path": r"D:\私有目录\x.png"})
    missing = router.call("nx_nope", {})
    assert missing["ok"] is False
    events = log.read()
    by_tool = {event["tool"]: event for event in events}
    assert by_tool["nx_block"]["ok"] is True
    assert by_tool["nx_block"]["verify"]["facts"]["volume"] == 60000.0
    assert by_tool["nx_screenshot"]["args"]["path"] == "<path:x.png>"
    assert by_tool["nx_nope"]["ok"] is False
    assert by_tool["nx_nope"]["error_code"] == "TOOL_NOT_FOUND"


def _event(ok=True, volume=60000.0, tool="nx_block", args=None):
    return {
        "tool": tool,
        "args": args or {"length": 50, "width": 40, "height": 30},
        "ok": ok,
        "error_code": None if ok else "NX_FAIL",
        "verify": {"facts": {"volume": volume, "faces": 6}} if ok else None,
    }


def test_candidates_need_repeat_success_and_low_failure_rate():
    events = [
        _event(), _event(), _event(), _event(), _event(),
        _event(ok=False),
        _event(tool="nx_inspect", args={}),
    ]
    items = candidates(events, min_success=2)
    assert len(items) == 1
    assert items[0]["tool"] == "nx_block"
    assert items[0]["success"] == 5 and items[0]["failure"] == 1
    assert candidates(events, min_success=6) == []
    noisy = [_event(), _event(), _event(ok=False), _event(ok=False)]
    assert candidates(noisy, min_success=2) == []


def test_ingest_writes_drafts_not_indexed(tmp_path):
    log = OperationLog(tmp_path / "io" / "oplog.jsonl")
    for _ in range(3):
        log.append(_event())
    library = Library(tmp_path / "library").init()
    result = ingest(tmp_path / "io" / "oplog.jsonl", library)
    assert result["candidates"] == 1
    assert result["drafts"][0]["result"].startswith("draft:")
    draft_path = library.root / "_drafts" / (result["drafts"][0]["id"] + ".json")
    assert draft_path.is_file()
    assert library.search("block") == []


def test_replay_promotes_only_matching_draft(tmp_path):
    events = [_event(), _event(), _event()]
    log = OperationLog(tmp_path / "io" / "oplog.jsonl")
    for event in events:
        log.append(event)
    library = Library(tmp_path / "library").init()
    result = ingest(tmp_path / "io" / "oplog.jsonl", library)
    entry_id = result["drafts"][0]["id"]

    good = verify_drafts(library, lambda entry: {"ok": True, "facts": {"volume": 60010.0, "faces": 6}})
    assert good[0]["promoted"] is True
    assert [hit["id"] for hit in library.search("block")] == [entry_id]
    promoted = library.get(entry_id)
    assert promoted["v"] == 1
    assert promoted["evidence"]["what"] == "volume"
    assert promoted["evidence"]["got"] == 60010.0
    assert "auto" not in promoted


def test_replay_with_router_promotes_entry(tmp_path):
    from nxkit.ingest import replay_with_router

    class ReplayRouter:
        def __init__(self):
            self.calls = []

        def call(self, name, args):
            self.calls.append(name)
            if name == "nx_part":
                return {"ok": True, "data": {"part": args["path"]}}
            if name == "nx_measure":
                return {"ok": True, "verify": {"facts": {"volume": 60000.0, "faces": 6}}}
            return {"ok": True, "verify": {"facts": {"volume": 60000.0}}}

    log = OperationLog(tmp_path / "io" / "oplog.jsonl")
    for _ in range(3):
        log.append(_event())
    library = Library(tmp_path / "library").init()
    result = ingest(tmp_path / "io" / "oplog.jsonl", library)
    entry_id = result["drafts"][0]["id"]
    router = ReplayRouter()
    verify = verify_drafts(
        library,
        lambda entry: replay_with_router(router, entry, tmp_path / "parts"),
    )
    assert verify[0]["promoted"] is True
    assert "nx_part" in router.calls and "nx_measure" in router.calls
    assert [hit["id"] for hit in library.search("block")] == [entry_id]


def test_replay_mismatch_keeps_draft(tmp_path):
    log = OperationLog(tmp_path / "io" / "oplog.jsonl")
    for _ in range(3):
        log.append(_event())
    library = Library(tmp_path / "library").init()
    result = ingest(tmp_path / "io" / "oplog.jsonl", library)
    entry_id = result["drafts"][0]["id"]
    bad = verify_drafts(library, lambda entry: {"ok": True, "facts": {"volume": 12000.0}})
    assert bad[0]["promoted"] is False
    assert "mismatch" in bad[0]["reason"]
    assert library.search("block") == []
    assert library.get(entry_id)["v"] == 0
