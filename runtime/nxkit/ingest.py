"""Auto-ingestion: operation log -> repeatable signatures -> drafts -> verified.

The pipeline is deliberately conservative:

1. `candidates(events)` groups successful/failed geometry calls by signature
   (tool + sanitized args). A signature becomes a candidate only after
   `min_success` successes and a low failure rate.
2. `write_drafts` stores candidates as library drafts (v=0). They are NOT
   searchable yet - "returned ok" is not proof the model calls were right.
3. `verify_drafts` replays a draft in a fresh part (caller supplies the replay
   function) and only promotes to v=1 when the measured facts match the
   recorded ones. Failed replays stay drafts with a reason.

Usage:
  python -m nxkit.ingest --oplog io/oplog.jsonl --library library
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

GEOMETRY_TOOLS = (
    "nx_block",
    "nx_hole",
    "nx_fillet",
    "nx_chamfer",
    "nx_boolean",
    "nx_move_face",
    "nx_shell",
    "nx_delete_body",
    "nx_extrude",
    "nx_revolve",
)

FACT_KEYS = ("volume", "area", "faces", "edges")


def signature(event):
    payload = json.dumps(
        {"tool": event.get("tool"), "args": event.get("args") or {}},
        ensure_ascii=False,
        sort_keys=True,
    )
    return "%s:%s" % (event.get("tool"), hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12])


def _facts_of(event):
    verify = event.get("verify") or {}
    facts = verify.get("facts") or {}
    return {key: facts.get(key) for key in FACT_KEYS if facts.get(key) is not None}


def candidates(events, min_success=2, max_failure_rate=0.2):
    stats = {}
    for event in events:
        if event.get("tool") not in GEOMETRY_TOOLS:
            continue
        sig = signature(event)
        item = stats.setdefault(
            sig,
            {
                "signature": sig,
                "tool": event.get("tool"),
                "args": event.get("args") or {},
                "success": 0,
                "failure": 0,
                "facts": None,
                "error_codes": {},
                "parts": set(),
            },
        )
        item["parts"].add(event.get("part"))
        if event.get("ok"):
            item["success"] += 1
            facts = _facts_of(event)
            if facts:
                item["facts"] = facts
        else:
            item["failure"] += 1
            code = ((event.get("error") or {}).get("code")) or "UNKNOWN"
            item["error_codes"][code] = item["error_codes"].get(code, 0) + 1
    result = []
    for item in stats.values():
        total = item["success"] + item["failure"]
        failure_rate = item["failure"] / total if total else 1.0
        item["failure_rate"] = round(failure_rate, 3)
        item.pop("parts", None)
        if item["success"] >= min_success and failure_rate <= max_failure_rate and item["facts"]:
            result.append(item)
    return result


def _entry_id(item):
    return "AUTO-" + item["signature"].split(":")[-1][:8].upper()


def _title(item):
    args = " ".join("%s=%s" % (key, value) for key, value in sorted(item["args"].items()))
    return "自动沉淀：%s %s" % (item["tool"], args)[:80]


def write_drafts(library, items):
    written = []
    for item in items:
        entry = {
            "id": _entry_id(item),
            "c": "招式",
            "t": _title(item),
            "k": [item["tool"].replace("nx_", "")],
            "general": "自动沉淀的成功操作（%d 次成功 / 失败率 %.0f%%），需复测后才可复用"
            % (item["success"], item["failure_rate"] * 100),
            "impl": [{"tool": item["tool"], "params": item["args"]}],
            "evidence": {"expect": item["facts"], "got": item["facts"], "tol": 0.01},
            "source": "auto",
            "auto": {
                "signature": item["signature"],
                "success": item["success"],
                "failure": item["failure"],
                "error_codes": item["error_codes"],
            },
        }
        result = library.save(entry, force_draft=True)
        written.append({"id": entry["id"], "result": result})
    return written


def verify_drafts(library, replay, tol=0.01, limit=20):
    drafts = []
    draft_dir = library.root / "_drafts"
    for path in sorted(draft_dir.glob("*.json"))[:limit]:
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if entry.get("source") == "auto":
            drafts.append(entry)
    results = []
    for entry in drafts:
        expected = (entry.get("evidence") or {}).get("expect") or {}
        try:
            outcome = replay(entry)
        except Exception as exc:
            outcome = {"ok": False, "error": repr(exc)}
        if not outcome.get("ok"):
            results.append({"id": entry["id"], "promoted": False, "reason": outcome.get("error") or "replay failed"})
            continue
        got = outcome.get("facts") or {}
        primary = None
        for key in ("volume", "area", "faces", "edges"):
            if expected.get(key) is not None and got.get(key) is not None:
                primary = key
                break
        if primary is None:
            results.append({"id": entry["id"], "promoted": False, "reason": "no comparable fact"})
            continue
        expected_value = float(expected[primary])
        got_value = float(got[primary])
        mismatch = abs(got_value - expected_value) > tol * max(1.0, abs(expected_value))
        if mismatch:
            results.append({"id": entry["id"], "promoted": False,
                            "reason": "mismatch: %s %.4f vs %.4f" % (primary, got_value, expected_value)})
            continue
        verified = dict(entry)
        # library evidence is scalar: |got - expect| <= tol
        verified["evidence"] = {
            "what": primary,
            "expect": expected_value,
            "got": got_value,
            "tol": round(abs(expected_value) * tol + 1e-9, 6),
        }
        verified["facts"] = got
        verified.pop("auto", None)
        library.save(verified)
        results.append({"id": entry["id"], "promoted": True})
    return results


def replay_with_router(router, entry, parts_dir, name=None):
    """Real replay: fresh part -> impl steps -> measure. Returns {ok, facts}."""
    part = Path(parts_dir) / (
        "%s-%d.prt" % (name or entry.get("id", "auto"), int(time.time() * 1000))
    )
    created = router.call("nx_part", {"action": "new", "path": str(part)})
    if not created.get("ok"):
        return {"ok": False, "error": "new part failed: %r" % (created.get("error"),)}
    for step in entry.get("impl") or []:
        args = dict(step.get("params") or {})
        args["skip_search"] = True
        envelope = router.call(step["tool"], args)
        if not envelope.get("ok"):
            return {"ok": False, "error": envelope.get("error")}
    measured = router.call("nx_measure", {"target": "last", "what": "volume"})
    if not measured.get("ok"):
        return {"ok": False, "error": measured.get("error")}
    facts = (measured.get("verify") or {}).get("facts") or {}
    return {"ok": True, "facts": facts}


def ingest(oplog_path, library, min_success=2, replay=None):
    from .library.store import Library

    events = []
    path = Path(oplog_path)
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    items = candidates(events, min_success=min_success)
    drafts = write_drafts(library, items)
    promoted = verify_drafts(library, replay) if replay is not None else []
    return {"events": len(events), "candidates": len(items), "drafts": drafts, "verify": promoted}


def main(argv=None):
    from .library.store import Library

    parser = argparse.ArgumentParser()
    parser.add_argument("--oplog", default=os.environ.get("NXKIT_OPLOG", "io/oplog.jsonl"))
    parser.add_argument("--library", default=os.environ.get("NXKIT_LIBRARY", "library"))
    parser.add_argument("--min-success", type=int, default=2)
    args = parser.parse_args(argv)
    library = Library(args.library).init()
    result = ingest(args.oplog, library, min_success=args.min_success)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
