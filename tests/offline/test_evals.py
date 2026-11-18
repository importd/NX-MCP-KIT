import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from evals.run import load_tasks, run_tasks  # noqa: E402


class OkRouter:
    def call(self, name, args):
        return {"ok": True, "data": {}}


class FirstStepFailsRouter:
    def __init__(self):
        self.calls = 0

    def call(self, name, args):
        self.calls += 1
        if self.calls == 1:
            return {"ok": False, "error": {"code": "NX_BOOL_EMPTY"}}
        return {"ok": True, "data": {}}


def test_loads_ten_tasks():
    tasks = load_tasks(REPO / "evals" / "tasks")
    assert len(tasks) == 10
    for task in tasks:
        assert {"id", "goal", "steps"} <= set(task)
        assert task["steps"]


def test_fake_run_reports_metrics():
    report = run_tasks(OkRouter(), load_tasks(REPO / "evals" / "tasks"))
    assert report["success_rate"] == 1.0
    assert report["failures"] == []
    assert report["avg_steps"] > 0
    assert set(report) >= {"success_rate", "avg_steps", "avg_seconds", "rollback_rate", "failures"}


def test_failure_is_counted():
    report = run_tasks(FirstStepFailsRouter(), load_tasks(REPO / "evals" / "tasks"))
    assert report["success_rate"] < 1.0
    assert report["failures"]
    assert report["failures"][0]["failure"]["code"] == "NX_BOOL_EMPTY"
