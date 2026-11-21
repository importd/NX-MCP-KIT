"""Task drivers.

OracleDriver executes a task's solution_steps through the MCP router and
records every call (GUI/live bridge path). HeadlessDriver runs the same steps
as one run_journal plan in a separate NX process - this is the default for CI
because it needs no GUI session and no bridge startup.

A real model driver only needs to produce the same run.jsonl event stream.
"""

import json
import time
from pathlib import Path


class OracleDriver:
    def __init__(self, router, recorder, parts_dir, save_tool="nx_save"):
        self.router = router
        self.recorder = recorder
        self.parts_dir = Path(parts_dir)
        self.save_tool = save_tool

    def _call(self, tool, args):
        return self.recorder.record(tool, args, self.router.call(tool, args))

    def run_task(self, task, attempt=1):
        self.parts_dir.mkdir(parents=True, exist_ok=True)
        part_path = self.parts_dir / ("%s-a%d.prt" % (task["id"], attempt))
        started = time.monotonic()
        outcome = "error"
        created = self._call("nx_part", {"action": "new", "path": str(part_path)})
        if created.get("ok"):
            outcome = "fail"
            ok = True
            for step in task.get("solution_steps", []):
                args = dict(step.get("args") or {})
                args.setdefault("skip_search", True)  # L1/L2 isolation, gate is measured separately
                envelope = self._call(step["tool"], args)
                if not envelope.get("ok"):
                    ok = False
                    break
            if ok:
                saved = self._call(self.save_tool, {"path": str(part_path)})
                outcome = "pass" if saved.get("ok") else "fail"
        seconds = time.monotonic() - started
        return self.recorder.close(outcome, seconds=seconds, part_path=part_path)


class HeadlessDriver:
    """Run [new_part, *solution_steps, save] in one run_journal plan.

    The recorder is fed from the journal result, so the run.jsonl format is
    identical to the bridge driver and the same scorer/aggregator applies.
    """

    def __init__(self, runner, recorder, parts_dir):
        self.runner = runner
        self.recorder = recorder
        self.parts_dir = Path(parts_dir)

    def _plan(self, task, part_path):
        steps = [{"cmd": "nx_part", "args": {"action": "new", "path": str(part_path)}}]
        for step in task.get("solution_steps", []):
            steps.append({"cmd": step["tool"], "args": dict(step.get("args") or {})})
        steps.append({"cmd": "nx_save", "args": {"path": str(part_path)}})
        return {"steps": steps}

    def run_task(self, task, attempt=1):
        self.parts_dir.mkdir(parents=True, exist_ok=True)
        part_path = self.parts_dir / (
            "%s-%s-a%d.prt" % (task["id"], self.recorder.run_id.split("-")[-1], attempt)
        )
        plan = self._plan(task, part_path)
        started = time.monotonic()
        result = self.runner.run(plan, timeout_s=300)
        payload = None
        if result.get("artifacts"):
            try:
                payload = json.loads(Path(result["artifacts"][0]).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                payload = None
        steps = (payload or {}).get("steps") or []
        ok = bool(result.get("ok")) and bool(steps) and all(
            not (step or {}).get("error") for step in steps
        ) and (payload or {}).get("ok", False)
        plan_steps = plan["steps"]
        for index, step in enumerate(steps):
            entry = plan_steps[index] if index < len(plan_steps) else {}
            error = (step or {}).get("error") or None
            envelope = {
                "ok": error is None,
                "error": error,
                "elapsed_ms": round(float((step or {}).get("elapsed_s") or 0.0) * 1000.0, 1),
            }
            self.recorder.record(entry.get("cmd", ""), entry.get("args") or {}, envelope)
        seconds = time.monotonic() - started
        return self.recorder.close(outcome="pass" if ok else "fail", seconds=seconds, part_path=part_path)
