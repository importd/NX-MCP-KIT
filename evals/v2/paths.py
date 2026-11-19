"""Paths for the eval harness (tasks, hidden asserts, runs, scores, baselines)."""

from pathlib import Path


def paths(repo_root):
    root = Path(repo_root) / "evals" / "v2"
    return {
        "root": root,
        "tasks": root / "tasks",
        "hidden": root / "tasks" / "hidden",
        "runs": root / "runs",
        "scores": root / "scores",
        "baselines": root / "baselines",
    }
