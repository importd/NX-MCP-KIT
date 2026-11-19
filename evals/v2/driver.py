"""Task drivers.

OracleDriver executes a task's solution_steps through the MCP router and
records every call. It is the L1/L2 harness validator: it answers "does the
tool surface + scoring pipeline work", not "is an LLM smart". A real model
driver only needs to produce the same run.jsonl event stream.
"""

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
