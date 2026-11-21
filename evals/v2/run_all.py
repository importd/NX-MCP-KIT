"""Run the v2 eval suite (oracle driver) against a live NX session + headless scorer.

Usage (repo root, PYTHONPATH=repo/runtime):
  python -m evals.v2.run_all --tier T1 --attempts 1 --nx-root "D:\\Program Files\\Siemens\\NX 10.0"
  python -m evals.v2.run_all --tier all --nx-root ... --baseline nx10
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _repo_root():
    return REPO


def _tool_surface():
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def load_tasks_v2(tier="all"):
    tasks = []
    root = REPO / "evals" / "v2" / "tasks"
    for path in sorted(root.glob("T*/*.json")):
        if tier != "all" and path.parent.name != tier:
            continue
        tasks.append(json.loads(path.read_text(encoding="utf-8-sig")))
    return tasks


def load_hidden(task_id):
    path = REPO / "evals" / "v2" / "tasks" / "hidden" / (task_id + ".asserts.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_router(io_dir):
    from nxkit.bridge import BridgeClient
    from nxkit.gate import Gate
    from nxkit.library.store import Library
    from nxkit.precheck import Precheck
    from nxkit.registry import Registry
    from nxkit.router import Router
    from nxkit.snapshot import SnapshotStore
    from nxkit.templates import TemplateStore

    io_dir = Path(io_dir)
    return Router(
        Registry(REPO / "contract"),
        BridgeClient(io_dir),
        Library(REPO / "library").init(),
        Gate(io_dir / "workflow.json"),
        precheck=Precheck(REPO / "contract"),
        snapshots=SnapshotStore(REPO / "snapshots"),
        templates=TemplateStore(REPO / "contract"),
    )


def nx_version_of(io_dir):
    from nxkit.bridge import BridgeClient

    sessions = [s for s in BridgeClient(Path(io_dir)).sessions() if s.get("alive")]
    if not sessions:
        return "none"
    py = str(sessions[0].get("python", ""))
    return "nx10" if py.startswith("3.3") else "nx2512"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", default="all")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--io-dir", default=r"E:\Code\CAD-Agent-Hub\MCP\UG\io")
    parser.add_argument("--nx-root", default=os.environ.get("NXKIT_NX_ROOT", ""))
    parser.add_argument("--baseline", default="")
    parser.add_argument("--mode", default="auto", choices=["auto", "headless", "bridge"])
    parser.add_argument("--skip-score", action="store_true")
    args = parser.parse_args(argv)

    from evals.v2 import aggregate, report, scorer
    from evals.v2.driver import HeadlessDriver, OracleDriver
    from evals.v2.paths import paths
    from evals.v2.recorder import RunRecorder

    p = paths(REPO)
    live_version = nx_version_of(args.io_dir) if Path(args.io_dir).is_dir() else "none"
    headless = args.mode == "headless" or (
        args.mode == "auto" and live_version == "none"
    )
    if headless and not args.nx_root:
        print("headless mode needs --nx-root", file=sys.stderr)
        return 2
    if not headless and live_version == "none":
        print("bridge mode needs a live NX session in %s" % args.io_dir, file=sys.stderr)
        return 2
    version = live_version if not headless else (
        "nx10" if "NX 10" in args.nx_root else "nx2512"
    )
    config = {
        "model": "oracle",
        "skill_version": "n/a",
        "library_state": "n/a",
        "nx_version": version,
        "tool_surface": _tool_surface(),
    }
    measurer = None
    if not args.skip_score and args.nx_root:
        measurer = scorer.HeadlessMeasurer(args.nx_root, REPO / "io" / "headless")
    router = None if headless else build_router(args.io_dir)

    runs, scores = [], []
    for task in load_tasks_v2(args.tier):
        hidden = load_hidden(task["id"])
        for attempt in range(1, args.attempts + 1):
            recorder = RunRecorder(task["id"], config, p["runs"])
            if headless:
                from nxkit.headless import HeadlessRunner

                runner = HeadlessRunner(Path(args.nx_root), plan_dir=REPO / "io" / "headless")
                driver = HeadlessDriver(runner, recorder, REPO / "io" / "eval_parts_headless")
            else:
                driver = OracleDriver(router, recorder, REPO / "io" / "eval_parts")
            run = driver.run_task(task, attempt)
            path, run = recorder.write()
            runs.append(run)
            if measurer is None:
                score = {"run_id": run["run_id"], "task_id": task["id"], "outcome": "not_scored",
                         "asserts": [], "measurement": {}, "independent": False, "error": "no nx-root"}
            else:
                try:
                    measurement = measurer.measure(run["artifacts"]["part_path"])
                    score = scorer.score_run(run, task, hidden, measurement, independent=True)
                except Exception as exc:
                    score = {"run_id": run["run_id"], "task_id": task["id"], "outcome": "error",
                             "asserts": [], "measurement": {}, "independent": True, "error": repr(exc)}
            p["scores"].mkdir(parents=True, exist_ok=True)
            (p["scores"] / (run["run_id"] + ".json")).write_text(
                json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            scores.append(score)
            print("%-22s attempt %d -> %-10s %s" % (task["id"], attempt, score["outcome"],
                                                    "" if score["outcome"] == "pass" else str(score.get("error") or "")[:120]))

    metrics, metrics_version = aggregate.load_metrics(p["root"] / "metrics.json")
    result = aggregate.aggregate(runs, scores, metrics)
    result["metrics_version"] = metrics_version
    result["config"] = config
    markdown = report.to_markdown(result, "Eval v2 — %s / %s" % (version, config["tool_surface"]))
    print(markdown)
    if args.baseline:
        path = report.save_baseline(result, p["baselines"] / (args.baseline + ".json"))
        print("baseline saved:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
