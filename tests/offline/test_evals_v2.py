import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from evals.v2 import aggregate, report, scorer  # noqa: E402
from evals.v2.driver import OracleDriver  # noqa: E402
from evals.v2.paths import paths  # noqa: E402
from evals.v2.recorder import RunRecorder  # noqa: E402

P = paths(REPO)


class FakeRouter:
    def __init__(self, fail_tool=None):
        self.calls = []
        self.fail_tool = fail_tool

    def call(self, name, args):
        self.calls.append((name, dict(args)))
        if name == self.fail_tool:
            return {"ok": False, "error": {"code": "NX_FAIL"}, "elapsed_ms": 1.0}
        return {"ok": True, "data": {}, "verify": {"facts": {}}, "elapsed_ms": 1.0}


def _config(**overrides):
    config = {"model": "fake", "skill_version": "v1", "library_state": "n/a",
              "nx_version": "nxfake", "tool_surface": "test"}
    config.update(overrides)
    return config


def test_task_suite_integrity():
    tasks = []
    for path in sorted(P["tasks"].glob("T*/*.json")):
        tasks.append(json.loads(path.read_text(encoding="utf-8-sig")))
    assert len(tasks) == 16
    assert {task["tier"] for task in tasks} == {"T1", "T2"}
    for task in tasks:
        assert {"id", "tier", "goal", "solution_steps", "budget"} <= set(task)
        hidden_path = P["hidden"] / (task["id"] + ".asserts.json")
        assert hidden_path.is_file(), task["id"]
        hidden = json.loads(hidden_path.read_text(encoding="utf-8-sig"))
        assert hidden["asserts"], task["id"]
        task_text = json.dumps(task)
        assert "expect" not in task_text, "task must not leak expected values: " + task["id"]


def test_recorder_writes_run_json(tmp_path):
    recorder = RunRecorder("T1-block-40x30x20", _config(), tmp_path / "runs")
    recorder.record("nx_block", {"length": 40}, {"ok": True, "elapsed_ms": 2.0, "verify": {"facts": {}}})
    path, run = recorder.write(seconds=1.25)
    assert path.is_file()
    assert run["events"][0]["tool"] == "nx_block"
    assert run["events"][0]["has_verify"] is True
    assert run["config"]["tool_surface"] == "test"
    assert run["run_id"] == recorder.run_id


def test_flatten_and_evaluate_asserts():
    measurement = scorer.flatten_measurement(
        {"volume": 24000.5, "area": 100.0, "faces": 6, "edges": 12, "bbox": [0, 0, 0, 40, 30, 20]}
    )
    assert measurement["bbox_dx"] == 40
    results = scorer.evaluate_asserts(
        [
            {"id": "vol", "kind": "rel", "measure": "volume", "expect": 24000.0, "tol": 0.001},
            {"id": "faces", "kind": "abs", "measure": "faces", "expect": 6, "tol": 0},
            {"id": "box", "kind": "range", "measure": "bbox_dz", "expect": {"min": 10, "max": 30}},
        ],
        measurement,
    )
    assert all(item["pass"] for item in results)
    bad = scorer.evaluate_asserts(
        [{"id": "vol", "kind": "rel", "measure": "volume", "expect": 30000.0, "tol": 0.001}],
        measurement,
    )
    assert bad[0]["pass"] is False and bad[0]["rel_err"] > 0.1


def test_driver_runs_steps_and_records(tmp_path):
    task = json.loads((P["tasks"] / "T1" / "T1-block-40x30x20.json").read_text(encoding="utf-8-sig"))
    recorder = RunRecorder(task["id"], _config(), tmp_path / "runs")
    driver = OracleDriver(FakeRouter(), recorder, tmp_path / "parts")
    run = driver.run_task(task)
    assert run["outcome"] == "pass"
    tools = [event["tool"] for event in run["events"]]
    assert tools[0] == "nx_part" and "nx_block" in tools and tools[-1] == "nx_save"
    assert run["artifacts"]["part_path"].endswith(".prt")


def test_driver_fails_on_tool_error(tmp_path):
    task = json.loads((P["tasks"] / "T1" / "T1-block-40x30x20.json").read_text(encoding="utf-8-sig"))
    recorder = RunRecorder(task["id"], _config(), tmp_path / "runs")
    driver = OracleDriver(FakeRouter(fail_tool="nx_block"), recorder, tmp_path / "parts")
    run = driver.run_task(task)
    assert run["outcome"] == "fail"


def test_score_run_budget_and_outcome():
    task = {"id": "T1-x", "budget": {"max_calls": 2, "max_seconds": 10}}
    hidden = {"asserts": [{"id": "vol", "kind": "rel", "measure": "volume", "expect": 100.0, "tol": 0.01}]}
    run_ok = {"run_id": "r1", "events": [{"tool": "nx_block"}], "seconds": 1.0, "tokens": None}
    score = scorer.score_run(run_ok, task, hidden, {"volume": 100.5}, independent=True)
    assert score["outcome"] == "pass" and score["independent"] is True
    run_slow = {"run_id": "r2", "events": [{"tool": "nx_block"}] * 3, "seconds": 20.0, "tokens": None}
    score = scorer.score_run(run_slow, task, hidden, {"volume": 100.5})
    assert score["outcome"] == "fail" and score["budgets"]["ok"] is False


def _run(tool, ok=True, error=None):
    return {"tool": tool, "ok": ok, "error_code": error}


def _build_run(task_id, tools, nx="nx10", library="n/a", seconds=5.0, tokens=1000, idx=0):
    return {
        "run_id": "%s-%s-%s-%d" % (task_id, nx, library, idx),
        "task_id": task_id,
        "config": _config(nx_version=nx, library_state=library),
        "seconds": seconds,
        "tokens": tokens,
        "events": [{"seq": i + 1, **_run(tool)} for i, tool in enumerate(tools)],
    }


def test_aggregate_metrics():
    runs = [
        _build_run("T1-a", ["nx_part", "exp_search", "exp_replay", "nx_block", "nx_save"], idx=1),
        _build_run("T1-a", ["nx_part", "nx_block", "nx_save"], idx=2),
        _build_run("T1-b", ["nx_part", "exp_search", "exp_replay", "nx_check", "nx_run_python", "nx_save"], idx=3),
        _build_run("T1-b", ["nx_part", "exp_search", "exp_replay", "nx_block"], nx="nx2512", idx=4),
    ]
    scores = [
        {"run_id": runs[0]["run_id"], "task_id": "T1-a", "outcome": "pass", "asserts": [{"id": "v", "pass": True, "rel_err": 0.001}]},
        {"run_id": runs[1]["run_id"], "task_id": "T1-a", "outcome": "fail", "asserts": [{"id": "v", "pass": False, "rel_err": 0.1}]},
        {"run_id": runs[2]["run_id"], "task_id": "T1-b", "outcome": "pass", "asserts": [{"id": "v", "pass": True, "rel_err": 0.0}]},
        {"run_id": runs[3]["run_id"], "task_id": "T1-b", "outcome": "pass", "asserts": [{"id": "v", "pass": True, "rel_err": 0.0}]},
    ]
    metrics, version = aggregate.load_metrics(P["root"] / "metrics.json")
    result = aggregate.aggregate(runs, scores, metrics)
    values = {item["id"]: item["value"] for item in result["metrics"]}
    assert values["M-TASK-01"] == 0.75
    assert values["M-TASK-02"] == 1.0
    assert values["M-GEO-01"] == 0.1
    assert values["M-EFF-01"] == 5.0
    assert values["M-EXP-01"] == 0.75
    assert values["M-VER-03"] == 1.0
    assert version


def test_headless_driver_records_events(tmp_path):
    from evals.v2.driver import HeadlessDriver

    task = json.loads((P["tasks"] / "T1" / "T1-block-40x30x20.json").read_text(encoding="utf-8-sig"))

    class FakeRunner:
        def run(self, plan, timeout_s=300):
            result_file = tmp_path / "result.json"
            steps = [{"cmd": step["cmd"], "data": {}, "facts": {}} for step in plan["steps"]]
            result_file.write_text(json.dumps({"ok": True, "steps": steps}), encoding="utf-8")
            return {"ok": True, "artifacts": [str(result_file)], "markers": ["NXKIT_OK"]}

    recorder = RunRecorder(task["id"], _config(), tmp_path / "runs")
    driver = HeadlessDriver(FakeRunner(), recorder, tmp_path / "parts")
    run = driver.run_task(task)
    assert run["outcome"] == "pass"
    tools = [event["tool"] for event in run["events"]]
    assert tools == ["nx_part", "nx_block", "nx_save"]
    assert run["artifacts"]["part_path"].endswith(".prt")


def test_report_markdown_and_baseline(tmp_path):
    result = {"metrics": [{"id": "M-TASK-01", "name": "TSR", "value": 0.5}], "tasks": {"T1-a": ["pass", "fail"]}}
    markdown = report.to_markdown(result)
    assert "M-TASK-01" in markdown and "T1-a" in markdown
    baseline_path = report.save_baseline(result, tmp_path / "baseline.json")
    assert baseline_path.is_file()
    diff = report.diff_against_baseline(result, baseline_path)
    assert diff["status"] == "compared" and diff["diffs"][0]["delta"] == 0
