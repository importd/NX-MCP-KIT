"""Headless execution: run a plan in a separate NX process via run_journal.exe.

Exit codes are not a verdict: NX journals can swallow exceptions and still
exit 0, and a normal shutdown can return a non-zero code. The verdict comes
from NXKIT_OK / NXKIT_FAIL:<code> markers on stdout plus artifacts measured
after the run.
"""

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_PLAN_DIR = REPO / "io" / "headless"


class HeadlessRunner:
    def __init__(self, nx_root=None, runner_cmd=None, plan_dir=None):
        self.nx_root = Path(nx_root) if nx_root else None
        self.runner_cmd = list(runner_cmd) if runner_cmd else None
        self.plan_dir = Path(plan_dir) if plan_dir else DEFAULT_PLAN_DIR

    def _command(self, plan_path: Path) -> list[str]:
        if self.runner_cmd:
            return self.runner_cmd + [str(plan_path)]
        if self.nx_root is None:
            raise ValueError("HeadlessRunner needs nx_root or runner_cmd")
        run_journal = self.nx_root / "NXBIN" / "run_journal.exe"
        if not run_journal.is_file():
            run_journal = self.nx_root / "UGII" / "run_journal.exe"
        journal = REPO / "bridge" / "headless" / "run.py"
        # NX run_journal accepts one journal file followed by -args; passing the
        # plan path through the environment keeps the call simple and stable.
        return [str(run_journal), str(journal)]

    def run(self, plan: dict, timeout_s: float = 600.0) -> dict:
        self.plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = self.plan_dir / ("plan-%s.json" % uuid.uuid4().hex[:12])
        import json

        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        started = time.monotonic()
        env = dict(os.environ)
        env["NXKIT_PLAN"] = str(plan_path)
        proc = subprocess.Popen(
            self._command(plan_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        try:
            log, _ = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            self._kill(proc)
            log, _ = proc.communicate()
            return {
                "ok": False,
                "markers": [],
                "log": log,
                "artifacts": [],
                "error": "HEADLESS_TIMEOUT",
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
        markers = [
            line.strip()
            for line in log.splitlines()
            if line.strip().startswith("NXKIT_")
        ]
        failed = [marker for marker in markers if marker.startswith("NXKIT_FAIL")]
        ok = ("NXKIT_OK" in markers) and not failed
        artifacts = [str(path) for path in self.plan_dir.glob(plan_path.name + ".result*")]
        return {
            "ok": ok,
            "markers": markers,
            "log": log,
            "artifacts": artifacts,
            "error": None if ok else (failed[0].split(":", 1)[1] if failed else "HEADLESS_NO_OK_MARKER"),
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        except OSError:
            pass
        if proc.poll() is None:
            proc.kill()
