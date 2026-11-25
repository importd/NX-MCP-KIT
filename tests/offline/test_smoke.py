import json
from pathlib import Path
from types import SimpleNamespace

import nxkit.smoke as smoke
from nxkit.smoke import default_part_path, run

GEOM = {"volume": 60000.0, "bbox": [0, 0, 0, 50, 40, 30]}
REPO = Path(__file__).resolve().parents[2]


class FakeBridge:
    def __init__(self, sessions):
        self._sessions = sessions

    def sessions(self):
        return list(self._sessions)


class FakeRouter:
    def __init__(self, handler, sessions=None):
        self.bridge = FakeBridge(
            sessions
            if sessions is not None
            else [{"pid": 1234, "alive": True, "heartbeat_age_s": 1.0}]
        )
        self.registry = SimpleNamespace(tools={"nx_block": object()})
        self.calls = []
        self._handler = handler

    def call(self, name, args):
        self.calls.append((name, dict(args)))
        return self._handler(name, args)


def _env(ok=True, data=None, facts=None, error=None):
    env = {"ok": ok, "data": data or {}}
    if facts is not None:
        env["verify"] = {"facts": facts}
    if error is not None:
        env["error"] = error
    return env


def _good(name, args):
    if name == "nx_status":
        return _env(data={"connected": True})
    if name == "nx_block":
        return _env(data={"feature": "BLOCK(0)"}, facts=dict(GEOM))
    if name == "nx_measure":
        return _env(data={"body": "BLOCK(0)"}, facts=dict(GEOM))
    return _env(data={})


def _part(workdir):
    return workdir / "smoke" / "p.prt"


def test_run_ok_path(workdir):
    router = FakeRouter(_good)
    result = run(router, workdir, _part(workdir))
    assert result["ok"] is True
    assert result["code"] is None
    assert result["exit_code"] == 0
    assert [s["name"] for s in result["steps"]] == [
        "contract", "io", "session", "status", "part", "block", "measure", "save",
    ]
    assert router.calls[-1][0] == "nx_save"


def test_run_pins_every_call_to_picked_session(workdir):
    sessions = [
        {"pid": 111, "alive": True, "heartbeat_age_s": 1.0},
        {"pid": 222, "alive": True, "heartbeat_age_s": 1.0},
    ]
    router = FakeRouter(_good, sessions=sessions)

    result = run(router, workdir, _part(workdir))

    assert result["ok"] is True
    assert router.calls
    assert all(args.get("pid") == 111 for _, args in router.calls)


def test_run_no_session_is_preflight(workdir):
    router = FakeRouter(_good, sessions=[])
    result = run(router, workdir, _part(workdir))
    assert result["code"] == "NO_SESSION"
    assert result["exit_code"] == 2
    assert router.calls == []


def test_run_missing_io_dir(workdir):
    missing = workdir / "nope"
    result = run(FakeRouter(_good), missing, missing / "smoke" / "p.prt")
    assert result["code"] == "IO_DIR"
    assert result["exit_code"] == 2


def test_measure_without_facts_fails(workdir):
    def handler(name, args):
        if name == "nx_measure":
            return _env(data={"body": "BLOCK(0)"})
        return _good(name, args)

    result = run(FakeRouter(handler), workdir, _part(workdir))
    assert result["code"] == "MEASURE"
    assert result["exit_code"] == 1


def test_measure_rejects_wrong_volume(workdir):
    def handler(name, args):
        if name == "nx_measure":
            return _env(data={"body": "BLOCK(0)"}, facts=dict(GEOM, volume=60010.0))
        return _good(name, args)

    result = run(FakeRouter(handler), workdir, _part(workdir))
    assert result["code"] == "MEASURE"


def test_part_failure_stops_after_part(workdir):
    def handler(name, args):
        if name == "nx_part":
            return _env(ok=False, error={"code": "NX_ERROR", "msg": "boom"})
        return _good(name, args)

    router = FakeRouter(handler)
    result = run(router, workdir, _part(workdir))
    assert result["code"] == "PART"
    assert [name for name, _ in router.calls] == ["nx_status", "nx_part"]


def test_router_exception_becomes_step_failure(workdir):
    def handler(name, args):
        raise RuntimeError("boom")

    result = run(FakeRouter(handler), workdir, _part(workdir))
    assert result["ok"] is False
    assert result["code"] == "STATUS"


def test_no_save_skips_nx_save(workdir):
    router = FakeRouter(_good)
    result = run(router, workdir, _part(workdir), save=False)
    assert result["ok"] is True
    assert all(name != "nx_save" for name, _ in router.calls)
    assert [s for s in result["steps"] if s["name"] == "save"][0]["detail"] == "skipped"


def test_default_part_path_is_unique_and_under_smoke(workdir):
    first = default_part_path(workdir)
    second = default_part_path(workdir)
    assert first != second
    assert first.parent == workdir / "smoke"
    assert first.name.startswith("smoke-") and first.suffix == ".prt"


def _argv(workdir, io, *extra):
    return [
        "--io", str(io),
        "--contract", str(REPO / "contract"),
        "--library", str(workdir / "library"),
        *extra,
    ]


def _dead_session(io, pid=999):
    (io / str(pid)).mkdir(parents=True)
    (io / str(pid) / "status.json").write_text(
        json.dumps({"pid": pid, "alive": True, "updated": 0}), encoding="utf-8"
    )


def test_main_reports_contract_error(workdir, capsys):
    bad = workdir / "bad_contract"
    bad.mkdir()
    rc = smoke.main([
        "--io", str(workdir / "io"),
        "--contract", str(bad),
        "--library", str(workdir / "library"),
    ])
    assert rc == 2
    assert "RESULT: FAIL:CONTRACT" in capsys.readouterr().out


def test_main_reports_no_session(workdir, capsys):
    io = workdir / "io"
    _dead_session(io)
    rc = smoke.main(_argv(workdir, io))
    assert rc == 2
    assert "RESULT: FAIL:NO_SESSION" in capsys.readouterr().out


def test_main_prints_ok_and_returns_zero(workdir, monkeypatch, capsys):
    monkeypatch.setattr(
        smoke, "run",
        lambda *a, **k: {
            "ok": True, "code": None, "exit_code": 0,
            "steps": [{"name": "contract", "ok": True, "detail": "", "error": None}],
        },
    )
    rc = smoke.main(_argv(workdir, workdir))
    out = capsys.readouterr().out
    assert rc == 0
    assert "STEP contract: OK" in out
    assert out.strip().splitlines()[-1] == "RESULT: OK"


def test_main_clean_removes_old_smoke_parts(workdir, monkeypatch, capsys):
    io = workdir / "io"
    old = io / "smoke" / "smoke-old.prt"
    old.parent.mkdir(parents=True)
    old.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        smoke, "run",
        lambda *a, **k: {"ok": True, "code": None, "exit_code": 0, "steps": []},
    )
    rc = smoke.main(_argv(workdir, io, "--clean"))
    assert rc == 0
    assert not old.exists()


def test_main_prints_next_on_failure(workdir, monkeypatch, capsys):
    monkeypatch.setattr(
        smoke, "run",
        lambda *a, **k: {
            "ok": False, "code": "BLOCK", "exit_code": 1,
            "steps": [{
                "name": "block", "ok": False, "detail": "NX_ERROR",
                "error": {"code": "NX_ERROR", "msg": "boom", "next": "check target"},
            }],
        },
    )
    rc = smoke.main(_argv(workdir, workdir))
    out = capsys.readouterr().out
    assert rc == 1
    assert "RESULT: FAIL:BLOCK" in out
    assert "MSG: boom" in out
    assert "NEXT: check target" in out
