"""Live-bridge deployment self-check.

Runs a fixed sequence against an already-open NX session: contract, io root,
live session, status, new part, block, measure, save. The verdict is the
measured geometry, not the exit code of NX (same rule as headless runs).

This module only talks to a Router, so offline tests inject a fake one.
"""

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .bridge import BridgeClient
from .gate import Gate
from .library.store import Library
from .registry import ContractError, Registry
from .router import Router

PREFLIGHT_CODES = frozenset({"CONTRACT", "IO_DIR", "NO_SESSION"})

CONTRACT = "CONTRACT"
IO_DIR = "IO_DIR"
NO_SESSION = "NO_SESSION"
STATUS = "STATUS"
PART = "PART"
BLOCK = "BLOCK"
MEASURE = "MEASURE"
SAVE = "SAVE"

EXPECTED_VOLUME = 60000.0
VOLUME_TOLERANCE = 1.0
EXPECTED_BBOX = [0.0, 0.0, 0.0, 50.0, 40.0, 30.0]

_FAILURE_CODES = {
    "contract": CONTRACT,
    "io": IO_DIR,
    "session": NO_SESSION,
    "status": STATUS,
    "part": PART,
    "block": BLOCK,
    "measure": MEASURE,
    "save": SAVE,
}


def _step(name, ok, detail="", error=None):
    return {"name": name, "ok": bool(ok), "detail": detail, "error": error}


def _finish(steps):
    for step in steps:
        if not step["ok"]:
            code = _FAILURE_CODES[step["name"]]
            exit_code = 2 if code in PREFLIGHT_CODES else 1
            return {"ok": False, "code": code, "exit_code": exit_code, "steps": steps}
    return {"ok": True, "code": None, "exit_code": 0, "steps": steps}


def _pick_session(sessions):
    """Same preference as Router._pick_session, kept local to avoid a cycle."""
    alive = [session for session in sessions if session.get("alive")]
    fresh = [
        session
        for session in alive
        if session.get("heartbeat_age_s") is None or session.get("heartbeat_age_s") < 300
    ]
    pool = fresh or alive
    return pool[0] if pool else None


def _call_step(router, name, tool, args):
    try:
        envelope = router.call(tool, args)
    except Exception as exc:
        return _step(name, False, "EXCEPTION", {"code": "EXCEPTION", "msg": repr(exc)}), None
    if not envelope.get("ok"):
        error = envelope.get("error") or {}
        return _step(name, False, error.get("code", "ERROR"), error), None
    return _step(name, True), envelope


def default_part_path(io_dir, now=None):
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return Path(io_dir) / "smoke" / ("smoke-%s-%s.prt" % (stamp, uuid.uuid4().hex[:6]))


def run(router, io_dir, part_path, *, save=True, timeout_s=120.0):
    """Run every smoke step in order; stop at the first failure."""
    io_path = Path(io_dir)
    part_path = Path(part_path)
    steps = []

    registry = getattr(router, "registry", None)
    if registry is None or not getattr(registry, "tools", None):
        steps.append(_step("contract", False, "no contract tools"))
        return _finish(steps)
    steps.append(_step("contract", True))

    if not io_path.is_dir():
        steps.append(_step("io", False, "io dir not found: %s" % io_path))
        return _finish(steps)
    steps.append(_step("io", True))

    try:
        sessions = router.bridge.sessions()
    except Exception as exc:
        steps.append(_step("session", False, "EXCEPTION", {"code": "EXCEPTION", "msg": repr(exc)}))
        return _finish(steps)
    session = _pick_session(sessions)
    if session is None:
        steps.append(_step("session", False, "no alive NX session"))
        return _finish(steps)
    steps.append(_step("session", True, "pid=%s" % session.get("pid")))

    step, envelope = _call_step(router, "status", "nx_status", {})
    if step["ok"] and not (envelope.get("data") or {}).get("connected"):
        step = _step("status", False, "not connected")
    steps.append(step)
    if not step["ok"]:
        return _finish(steps)

    try:
        part_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        steps.append(_step("part", False, "cannot create %s" % part_path.parent, {"code": "OS_ERROR", "msg": str(exc)}))
        return _finish(steps)

    step, _ = _call_step(
        router,
        "part",
        "nx_part",
        {"action": "new", "path": str(part_path), "timeout_s": timeout_s},
    )
    steps.append(step)
    if not step["ok"]:
        return _finish(steps)

    step, _ = _call_step(
        router,
        "block",
        "nx_block",
        {
            "length": 50,
            "width": 40,
            "height": 30,
            "skip_search": True,
            "timeout_s": timeout_s,
        },
    )
    steps.append(step)
    if not step["ok"]:
        return _finish(steps)

    step, envelope = _call_step(
        router,
        "measure",
        "nx_measure",
        {"target": "last", "skip_search": True, "timeout_s": timeout_s},
    )
    if step["ok"]:
        facts = (envelope.get("verify") or {}).get("facts") or {}
        volume = facts.get("volume")
        bbox = facts.get("bbox")
        if volume is None or bbox is None:
            step = _step("measure", False, "no facts returned")
        elif abs(float(volume) - EXPECTED_VOLUME) > VOLUME_TOLERANCE:
            step = _step("measure", False, "volume=%s" % volume)
        elif list(bbox) != EXPECTED_BBOX:
            step = _step("measure", False, "bbox=%s" % (bbox,))
        else:
            step = _step("measure", True, "volume=%s" % volume)
    steps.append(step)
    if not step["ok"]:
        return _finish(steps)

    if not save:
        steps.append(_step("save", True, "skipped"))
        return _finish(steps)

    step, _ = _call_step(
        router,
        "save",
        "nx_save",
        {"path": str(part_path), "timeout_s": timeout_s},
    )
    steps.append(step)
    return _finish(steps)


def _print_step(step):
    line = "STEP %s: %s" % (step["name"], "OK" if step["ok"] else "FAIL")
    if step["detail"]:
        line += " " + step["detail"]
    print(line)
    if not step["ok"]:
        error = step.get("error") or {}
        if error.get("msg"):
            print("MSG: " + str(error["msg"]))
        if error.get("next"):
            print("NEXT: " + str(error["next"]))


def _clean_old_parts(io_path):
    folder = Path(io_path) / "smoke"
    if not folder.is_dir():
        return
    for path in folder.glob("smoke-*.prt"):
        try:
            path.unlink()
        except OSError:
            pass


def _parser():
    parser = argparse.ArgumentParser(
        prog="nxkit.smoke", description="Live NX bridge deployment self-check"
    )
    parser.add_argument("--io", required=True, help="bridge io root (holds <pid>/ dirs)")
    parser.add_argument("--contract", help="contract dir (default: repo/contract)")
    parser.add_argument("--library", help="experience library root (default: <io>/../library)")
    parser.add_argument("--part", help="smoke part path (default: <io>/smoke/smoke-<ts>.prt)")
    parser.add_argument("--no-save", action="store_true", help="skip the save step")
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--clean", action="store_true", help="delete old <io>/smoke/smoke-*.prt first")
    return parser


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    io_path = Path(args.io)
    contract = Path(args.contract) if args.contract else Path(__file__).resolve().parents[2] / "contract"
    library_root = Path(args.library) if args.library else io_path.parent / "library"

    if args.clean:
        _clean_old_parts(io_path)

    try:
        registry = Registry(contract)
    except ContractError as exc:
        print("STEP contract: FAIL %s" % exc)
        print("RESULT: FAIL:CONTRACT")
        return 2

    try:
        bridge = BridgeClient(io_path)
        library = Library(library_root).init()
        gate = Gate(io_path / "workflow.json")
        router = Router(registry, bridge, library, gate, expose="all")
        part_path = Path(args.part) if args.part else default_part_path(io_path)
        print("SMOKE io=%s contract=%s part=%s" % (io_path, contract, part_path))
        result = run(
            router,
            io_path,
            part_path,
            save=not args.no_save,
            timeout_s=args.timeout_s,
        )
    except Exception as exc:
        print("RESULT: FAIL:INTERNAL")
        print("NEXT: %r" % (exc,))
        return 1

    for step in result["steps"]:
        _print_step(step)
    if result["ok"]:
        print("RESULT: OK")
    else:
        print("RESULT: FAIL:%s" % result["code"])
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
