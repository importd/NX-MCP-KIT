"""Independent scorer: measures a saved .prt in a separate NX process.

The被测 MCP never participates in scoring. Preferred path is run_journal
(headless, independent); if no NX root is given, the caller may pass a
measurement function (tests) or a bridge-backed measurer, and the score is
marked independent=false.
"""

import json
from pathlib import Path

from . import paths as v2paths


def flatten_measurement(facts):
    facts = facts or {}
    bbox = facts.get("bbox") or [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    return {
        "volume": facts.get("volume"),
        "area": facts.get("area"),
        "faces": facts.get("faces"),
        "edges": facts.get("edges"),
        "bbox_dx": round(float(bbox[3]) - float(bbox[0]), 6),
        "bbox_dy": round(float(bbox[4]) - float(bbox[1]), 6),
        "bbox_dz": round(float(bbox[5]) - float(bbox[2]), 6),
    }


def _rel_err(got, expect):
    try:
        expect = float(expect)
        if expect == 0:
            return None
        return abs(float(got) - expect) / abs(expect)
    except (TypeError, ValueError):
        return None


def evaluate_asserts(asserts, measurements):
    results = []
    for item in asserts:
        measure = item["measure"]
        got = measurements.get(measure)
        expect = item.get("expect")
        kind = item.get("kind", "abs")
        passed = False
        if got is None:
            pass
        elif kind == "range":
            low, high = expect.get("min"), expect.get("max")
            passed = (low is None or float(got) >= float(low)) and (
                high is None or float(got) <= float(high)
            )
        elif kind == "rel":
            err = _rel_err(got, expect)
            passed = err is not None and err <= float(item.get("tol", 0.0))
        else:
            passed = abs(float(got) - float(expect)) <= float(item.get("tol", 0.0))
        results.append(
            {
                "id": item.get("id", measure),
                "kind": kind,
                "measure": measure,
                "expect": expect,
                "got": got,
                "rel_err": _rel_err(got, expect) if got is not None and kind != "range" else None,
                "pass": bool(passed),
            }
        )
    return results


class HeadlessMeasurer:
    """Measure a saved part through run_journal (independent process)."""

    def __init__(self, nx_root, plan_dir):
        self.nx_root = Path(nx_root)
        self.plan_dir = Path(plan_dir)
        self.independent = True

    def measure(self, part_path):
        from nxkit.headless import HeadlessRunner

        runner = HeadlessRunner(self.nx_root, plan_dir=self.plan_dir)
        plan = {
            "steps": [
                {"cmd": "nx_part", "args": {"action": "open", "path": str(part_path)}},
                {"cmd": "nx_measure", "args": {"target": "last"}},
                {"cmd": "nx_inspect", "args": {}},
            ]
        }
        result = runner.run(plan, timeout_s=300)
        if not result.get("ok") or not result.get("artifacts"):
            raise RuntimeError("independent measure failed: %s" % (result.get("markers"),))
        payload = json.loads(Path(result["artifacts"][0]).read_text(encoding="utf-8"))
        facts = payload["steps"][1].get("facts") or {}
        data = flatten_measurement(facts)
        data["bodies"] = len((payload["steps"][2].get("data") or {}).get("bodies") or [])
        return data


def score_run(run, task, hidden_asserts, measurement, independent=True):
    assert_results = evaluate_asserts(hidden_asserts.get("asserts", []), measurement)
    budgets = task.get("budget", {})
    calls = len(run.get("events", []))
    seconds = run.get("seconds") or 0.0
    tokens = run.get("tokens")
    budget_ok = calls <= budgets.get("max_calls", 10**9) and seconds <= budgets.get(
        "max_seconds", 10**9
    )
    if budgets.get("max_tokens") is not None and tokens is not None:
        budget_ok = budget_ok and tokens <= budgets["max_tokens"]
    outcome = "pass" if all(item["pass"] for item in assert_results) and budget_ok else "fail"
    return {
        "run_id": run.get("run_id"),
        "task_id": task.get("id"),
        "outcome": outcome,
        "independent": bool(independent),
        "measurement": measurement,
        "asserts": assert_results,
        "budgets": {"calls": calls, "seconds": seconds, "tokens": tokens, "ok": budget_ok},
        "error": None,
    }


def default_paths(repo_root):
    return v2paths(repo_root)
