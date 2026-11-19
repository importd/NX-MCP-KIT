"""Aggregation of runs + scores into the metric dictionary.

Input: run dicts (recorder format) and score dicts. Output: metric values with
their IDs from metrics.json, plus per-task rows for the report.
"""

import json
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
    "nx_run_python",
)


def load_metrics(metrics_path):
    data = json.loads(Path(metrics_path).read_text(encoding="utf-8-sig"))
    return {item["id"]: item for item in data["metrics"]}, data.get("metrics_version", "dev")


def _mean(values):
    values = [value for value in values if value is not None]
    return round(sum(values) / len(values), 3) if values else None


def _ratio(num, den):
    return round(num / den, 3) if den else None


def gate_compliance(run):
    geometry_seen = False
    searched = False
    for event in run.get("events", []):
        tool = event.get("tool")
        if tool == "exp_search":
            searched = True
        elif tool in GEOMETRY_TOOLS:
            geometry_seen = True
            if not searched:
                return False
    return True if geometry_seen else None


def precheck_compliance(run):
    have_check = False
    calls = 0
    ok = 0
    for event in run.get("events", []):
        tool = event.get("tool")
        if tool == "nx_run_python":
            calls += 1
            if have_check:
                ok += 1
        elif tool == "nx_check":
            have_check = True
    return _ratio(ok, calls) if calls else None


def aggregate(runs, scores, metrics):
    score_by_run = {score["run_id"]: score for score in scores}
    rows = []
    for run in runs:
        score = score_by_run.get(run.get("run_id"))
        if score is None:
            continue
        rows.append({"run": run, "score": score})

    passed = [row for row in rows if row["score"]["outcome"] == "pass"]
    task_outcomes = {}
    for row in rows:
        task_outcomes.setdefault(row["run"]["task_id"], []).append(row["score"]["outcome"])

    geo_errors = []
    assert_ok = assert_total = 0
    for row in rows:
        for item in row["score"].get("asserts", []):
            assert_total += 1
            if item["pass"]:
                assert_ok += 1
            if item.get("rel_err") is not None:
                geo_errors.append(item["rel_err"])

    passed_calls = [len(row["run"]["events"]) for row in passed]
    passed_seconds = [row["run"].get("seconds") for row in passed]
    passed_tokens = [row["run"].get("tokens") for row in passed]

    gate_values = [gate_compliance(row["run"]) for row in rows]
    gate_values = [value for value in gate_values if value is not None]
    precheck_values = [precheck_compliance(row["run"]) for row in rows]
    precheck_values = [value for value in precheck_values if value is not None]

    exp_reuse = sum(
        1
        for row in rows
        if any(event.get("tool") in ("exp_replay", "nx_exp") for event in row["run"]["events"])
    )
    cold = [len(row["run"]["events"]) for row in rows if row["run"]["config"]["library_state"] == "cold"]
    warm = [len(row["run"]["events"]) for row in rows if row["run"]["config"]["library_state"] == "warm"]

    version_pairs = {}
    for row in rows:
        task_id = row["run"]["task_id"]
        version = row["run"]["config"]["nx_version"]
        version_pairs.setdefault(task_id, {})[version] = row["score"]["outcome"]
    equivalent = comparable = 0
    for outcomes in version_pairs.values():
        if len(outcomes) >= 2:
            comparable += 1
            if len(set(outcomes.values())) == 1:
                equivalent += 1

    def metric(metric_id, value):
        return {"id": metric_id, "value": value, "name": metrics.get(metric_id, {}).get("name")}

    return {
        "metrics_version": None,
        "rows": rows,
        "tasks": task_outcomes,
        "metrics": [
            metric("M-TASK-01", _ratio(len(passed), len(rows))),
            metric("M-TASK-02", _ratio(sum(1 for outcomes in task_outcomes.values() if "pass" in outcomes), len(task_outcomes))),
            metric("M-GEO-01", round(max(geo_errors), 6) if geo_errors else None),
            metric("M-EFF-01", _mean(passed_calls)),
            metric("M-EFF-02", _mean(passed_seconds)),
            metric("M-EFF-03", _mean(passed_tokens)),
            metric("M-CMP-01", _mean(gate_values)),
            metric("M-CMP-02", _mean(precheck_values)),
            metric("M-VER-01", _ratio(assert_ok, assert_total)),
            metric("M-VER-02", None),
            metric("M-EXP-01", _ratio(exp_reuse, len(rows))),
            metric("M-EXP-02", (round(_mean(cold) - _mean(warm), 3) if cold and warm else None)),
            metric("M-VER-03", _ratio(equivalent, comparable)),
            metric("M-QUA-01", _ratio(len(rows), len(runs))),
        ],
    }
