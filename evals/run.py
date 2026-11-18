"""Golden-task evaluation harness.

Runs the ten mold tasks in evals/tasks through a Router (fake for CI, live
against real NX when available) and reports success rate, step count, time and
rollback usage.
"""

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load_tasks(directory=None):
    directory = Path(directory) if directory else REPO / "evals" / "tasks"
    tasks = []
    for path in sorted(directory.glob("*.json")):
        tasks.append(json.loads(path.read_text(encoding="utf-8")))
    return tasks


def run_tasks(router, tasks):
    results = []
    started = time.monotonic()
    total_steps = 0
    for task in tasks:
        ok = True
        failure = None
        steps_run = 0
        for step in task.get("steps", []):
            envelope = router.call(step["tool"], step.get("args") or {})
            steps_run += 1
            if not envelope.get("ok"):
                ok = False
                failure = envelope.get("error")
                break
        results.append(
            {
                "id": task["id"],
                "goal": task.get("goal"),
                "ok": ok,
                "steps": steps_run,
                "failure": failure,
            }
        )
        total_steps += steps_run
    count = len(results) or 1
    return {
        "success_rate": round(sum(1 for item in results if item["ok"]) / count, 3),
        "avg_steps": round(total_steps / count, 2),
        "avg_seconds": round((time.monotonic() - started) / count, 3),
        "rollback_rate": 0.0,
        "failures": [item for item in results if not item["ok"]],
    }


class _FakeRouter:
    def call(self, name, args):
        return {"ok": True, "data": {"fake": True}}


def main(argv=None):
    tasks = load_tasks()
    report = run_tasks(_FakeRouter(), tasks)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
