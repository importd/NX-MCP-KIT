import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nxkit.auto_ingest import main as auto_main, run_once
from nxkit.gate import Gate
from nxkit.ingest import ingest, pit_candidates
from nxkit.library.store import Library
from nxkit.oplog import OperationLog
from nxkit.registry import Registry
from nxkit.router import Router

REPO = Path(__file__).resolve().parents[2]
PWSH = shutil.which("pwsh") or shutil.which("powershell")


def _event(ok=True, code=None, tool="nx_block", args=None):
    return {
        "tool": tool,
        "args": args or {"length": 50, "width": 40, "height": 30},
        "ok": ok,
        "error": {"code": code} if code else None,
        "verify": {"facts": {"volume": 60000.0, "faces": 6}} if ok else None,
    }


def test_pit_candidates_and_drafts(tmp_path):
    log = OperationLog(tmp_path / "io" / "oplog.jsonl")
    for _ in range(3):
        log.append(_event(ok=False, code="NX_BOOL_EMPTY"))
    log.append(_event(ok=True))
    events = [json.loads(line) for line in (tmp_path / "io" / "oplog.jsonl").read_text(encoding="utf-8").splitlines()]
    pits = pit_candidates(events, min_failures=2)
    assert len(pits) == 1
    assert pits[0]["error_codes"] == {"NX_BOOL_EMPTY": 3}

    library = Library(tmp_path / "library").init()
    result = ingest(tmp_path / "io" / "oplog.jsonl", library)
    assert result["pits"], "failure signature should become a pit draft"
    pit_path = library.root / "_drafts" / (result["pits"][0]["id"] + ".json")
    assert pit_path.is_file()
    pit = json.loads(pit_path.read_text(encoding="utf-8"))
    assert pit["c"] == "坑" and pit["source"] == "auto"
    assert library.search("block") == []


def test_bump_usage_without_success_flag(tmp_path):
    library = Library(tmp_path / "library").init()
    library.save({"id": "M0001", "c": "招式", "t": "测试", "evidence": {"expect": 1.0, "got": 1.0, "tol": 0.01}})
    library.bump_usage("M0001", None)
    usage = library.get("M0001")["usage"]
    assert usage["count"] == 1 and usage["success"] == 0 and usage["fail"] == 0


class FakeBridge:
    def sessions(self):
        return [{"pid": 1, "alive": True}]

    def submit(self, pid, cmd, args, timeout_s=120.0):
        return {"data": {"feature": "BLOCK(0)"}, "facts": {"volume": 60000.0, "faces": 6}}


def test_nx_exp_get_bumps_usage(tmp_path, contract_dir):
    library = Library(tmp_path / "library").init()
    library.save({"id": "M0001", "c": "招式", "t": "测试", "evidence": {"expect": 1.0, "got": 1.0, "tol": 0.01}})
    router = Router(Registry(contract_dir), FakeBridge(), library, Gate(tmp_path / "workflow.json"))
    envelope = router.call("nx_exp", {"action": "get", "id": "M0001"})
    assert envelope["ok"] is True
    assert library.get("M0001")["usage"]["count"] == 1


class FakeReplayRouter:
    def call(self, name, args):
        if name == "nx_part":
            return {"ok": True, "data": {"part": args["path"]}}
        if name == "nx_measure":
            return {"ok": True, "verify": {"facts": {"volume": 60000.0, "faces": 6}}}
        return {"ok": True, "verify": {"facts": {"volume": 60000.0}}}


def test_run_once_promotes_via_live_replay(tmp_path):
    log = OperationLog(tmp_path / "io" / "oplog.jsonl")
    for _ in range(3):
        log.append(_event(ok=True))
    result = run_once(
        tmp_path / "io" / "oplog.jsonl",
        tmp_path / "library",
        router=FakeReplayRouter(),
        parts_dir=tmp_path / "parts",
    )
    assert result["drafts"] and result["verify"][0]["promoted"] is True
    library = Library(tmp_path / "library").init()
    assert library.search("block")


def test_auto_ingest_cli_without_session(tmp_path, contract_dir):
    io_dir = tmp_path / "io"
    io_dir.mkdir()
    code = auto_main(
        ["--io", str(io_dir), "--library", str(tmp_path / "library"), "--contract", str(contract_dir)]
    )
    assert code == 3


def test_install_ingest_task_prints_schtasks(tmp_path):
    assert PWSH, "no PowerShell found"
    script = REPO / "deploy" / "install_ingest_task.ps1"
    result = subprocess.run(
        [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-RuntimeHome", str(tmp_path / "runtime"), "-PrintOnly"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert "schtasks /Create" in result.stdout
    assert "NXAgentKit-AutoIngest" in result.stdout
    remove = subprocess.run(
        [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-RuntimeHome", str(tmp_path / "runtime"), "-Remove", "-PrintOnly"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert "schtasks /Delete" in remove.stdout
