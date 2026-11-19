"""Markdown report + baseline diff for the eval harness."""

import json
from pathlib import Path


def _fmt(value, digits=3):
    if value is None:
        return "—"
    if isinstance(value, float):
        return ("%." + str(digits) + "f") % value
    return str(value)


def to_markdown(result, title="Eval report"):
    lines = ["# " + title, "", "## 指标", "", "| ID | 指标 | 值 |", "|---|---|---|"]
    for item in result.get("metrics", []):
        lines.append("| %s | %s | %s |" % (item["id"], item.get("name") or "", _fmt(item.get("value"))))
    lines += ["", "## 任务", "", "| 任务 | 运行结果 |", "|---|---|"]
    for task_id, outcomes in sorted(result.get("tasks", {}).items()):
        lines.append("| %s | %s |" % (task_id, ", ".join(outcomes)))
    return "\n".join(lines) + "\n"


def diff_against_baseline(result, baseline_path):
    baseline_path = Path(baseline_path)
    if not baseline_path.is_file():
        return {"status": "no_baseline"}
    baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    before = {item["id"]: item.get("value") for item in baseline.get("metrics", [])}
    diffs = []
    for item in result.get("metrics", []):
        old = before.get(item["id"])
        new = item.get("value")
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            diffs.append({"id": item["id"], "baseline": old, "now": new, "delta": round(new - old, 4)})
    return {"status": "compared", "diffs": diffs}


def save_baseline(result, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
