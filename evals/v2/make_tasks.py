"""Generate the v2 task suite (T1 = atomic tools, T2 = single-part modeling).

Task files are visible to an agent under test and contain NO expected values.
Expected values live in tasks/hidden/<id>.asserts.json and are only read by the
scorer. Run: python -m evals.v2.make_tasks
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks"
HIDDEN = TASKS / "hidden"

PI = 3.141592653589793
DEFAULT_BUDGET_T1 = {"max_calls": 8, "max_seconds": 180, "max_tokens": None}
DEFAULT_BUDGET_T2 = {"max_calls": 12, "max_seconds": 240, "max_tokens": None}


def rel(measure, expect, tol, ident=None):
    return {"id": ident or measure, "kind": "rel", "measure": measure, "expect": expect, "tol": tol}


def absv(measure, expect, tol=0, ident=None):
    return {"id": ident or measure, "kind": "abs", "measure": measure, "expect": expect, "tol": tol}


def rng(measure, low, high, ident=None):
    return {"id": ident or measure, "kind": "range", "measure": measure, "expect": {"min": low, "max": high}}


TASKS_DEF = [
    # ---------------- T1: atomic tools ----------------
    {
        "id": "T1-block-40x30x20",
        "tier": "T1",
        "goal": "建 40×30×20 的长方体",
        "solution_steps": [{"tool": "nx_block", "args": {"length": 40, "width": 30, "height": 20}}],
        "budget": DEFAULT_BUDGET_T1,
        "tags": ["block"],
        "_asserts": [rel("volume", 24000.0, 0.001), rel("bbox_dx", 40.0, 0.001)],
    },
    {
        "id": "T1-hole-through",
        "tier": "T1",
        "goal": "50×40×30 方块中心打 φ8 通孔",
        "solution_steps": [
            {"tool": "nx_block", "args": {"length": 50, "width": 40, "height": 30}},
            {"tool": "nx_hole", "args": {"target": "last", "position": [25, 20, 30], "diameter": 8}},
        ],
        "budget": DEFAULT_BUDGET_T1,
        "tags": ["hole"],
        "_asserts": [rel("volume", 58492.0355, 0.003), absv("faces", 7, 0)],
    },
    {
        "id": "T1-hole-depth",
        "tier": "T1",
        "goal": "50×40×30 方块打 φ10×15 盲孔",
        "solution_steps": [
            {"tool": "nx_block", "args": {"length": 50, "width": 40, "height": 30}},
            {"tool": "nx_hole", "args": {"target": "last", "position": [25, 20, 30], "diameter": 10, "depth": 15}},
        ],
        "budget": DEFAULT_BUDGET_T1,
        "tags": ["hole"],
        "_asserts": [rel("volume", 58821.9028, 0.005)],
    },
    {
        "id": "T1-fillet-all",
        "tier": "T1",
        "goal": "50×40×30 方块全边倒圆 R3",
        "solution_steps": [
            {"tool": "nx_block", "args": {"length": 50, "width": 40, "height": 30}},
            {"tool": "nx_fillet", "args": {"target": "last", "radius": 3}},
        ],
        "budget": DEFAULT_BUDGET_T1,
        "tags": ["fillet"],
        "_asserts": [rng("volume", 56000.0, 59999.0), rng("faces", 20.0, 70.0)],
    },
    {
        "id": "T1-chamfer-all",
        "tier": "T1",
        "goal": "50×40×30 方块全边倒斜角 C2",
        "solution_steps": [
            {"tool": "nx_block", "args": {"length": 50, "width": 40, "height": 30}},
            {"tool": "nx_chamfer", "args": {"target": "last", "width": 2}},
        ],
        "budget": DEFAULT_BUDGET_T1,
        "tags": ["chamfer"],
        "_asserts": [rng("volume", 56000.0, 59999.0), rng("faces", 20.0, 70.0)],
    },
    {
        "id": "T1-boolean-unite",
        "tier": "T1",
        "goal": "两个相交长方体求和",
        "solution_steps": [
            {"tool": "nx_block", "args": {"length": 50, "width": 40, "height": 20}},
            {"tool": "nx_block", "args": {"x": 10, "length": 20, "width": 20, "height": 20}},
            {"tool": "nx_boolean", "args": {"target": "BLOCK(0)", "tool": "BLOCK(1)", "operation": "unite"}},
        ],
        "budget": DEFAULT_BUDGET_T1,
        "tags": ["boolean"],
        "_asserts": [rel("volume", 40000.0, 0.003), absv("bodies", 1, 0)],
    },
    {
        "id": "T1-shell",
        "tier": "T1",
        "goal": "50×40×30 方块抽壳壁厚 2（顶面开口）",
        "solution_steps": [
            {"tool": "nx_block", "args": {"length": 50, "width": 40, "height": 30}},
            {"tool": "nx_shell", "args": {"target": "last", "thickness": 2, "faces": [[25, 20, 30]]}},
        ],
        "budget": DEFAULT_BUDGET_T1,
        "tags": ["shell"],
        "_asserts": [rel("volume", 13632.0, 0.01), absv("faces", 11, 0)],
    },
    {
        "id": "T1-extrude",
        "tier": "T1",
        "goal": "20×10 矩形轮廓拉伸 5",
        "solution_steps": [
            {"tool": "nx_extrude", "args": {"points": [[0, 0, 0], [20, 0, 0], [20, 10, 0], [0, 10, 0]], "distance": 5}},
        ],
        "budget": DEFAULT_BUDGET_T1,
        "tags": ["extrude"],
        "_asserts": [rel("volume", 1000.0, 0.001), rel("bbox_dz", 5.0, 0.001)],
    },
    # ---------------- T2: single-part modeling ----------------
    {
        "id": "T2-plate-4holes",
        "tier": "T2",
        "goal": "100×60×10 板，四角 4×φ8 通孔",
        "solution_steps": [
            {"tool": "nx_block", "args": {"length": 100, "width": 60, "height": 10}},
            {"tool": "nx_hole", "args": {"target": "last", "position": [20, 15, 10], "diameter": 8}},
            {"tool": "nx_hole", "args": {"target": "last", "position": [80, 15, 10], "diameter": 8}},
            {"tool": "nx_hole", "args": {"target": "last", "position": [20, 45, 10], "diameter": 8}},
            {"tool": "nx_hole", "args": {"target": "last", "position": [80, 45, 10], "diameter": 8}},
        ],
        "budget": DEFAULT_BUDGET_T2,
        "tags": ["plate"],
        "_asserts": [rel("volume", 57989.3805, 0.004), absv("faces", 10, 0)],
    },
    {
        "id": "T2-bushing",
        "tier": "T2",
        "goal": "圆环截面（R20/R10，高 30）绕 Y 轴回转 360°",
        "solution_steps": [
            {
                "tool": "nx_revolve",
                "args": {
                    "points": [[10, -15, 0], [20, -15, 0], [20, 15, 0], [10, 15, 0]],
                    "angle": 360,
                    "axis_dir": [0, 1, 0],
                },
            }
        ],
        "budget": DEFAULT_BUDGET_T2,
        "tags": ["revolve"],
        "_asserts": [rel("volume", 28274.3339, 0.005), rel("bbox_dy", 30.0, 0.002)],
    },
    {
        "id": "T2-three-blocks",
        "tier": "T2",
        "goal": "三个 20 立方体串成一排并求和",
        "solution_steps": [
            {"tool": "nx_block", "args": {"length": 20, "width": 20, "height": 20}},
            {"tool": "nx_block", "args": {"x": 20, "length": 20, "width": 20, "height": 20}},
            {"tool": "nx_boolean", "args": {"target": "BLOCK(0)", "tool": "BLOCK(1)", "operation": "unite"}},
            {"tool": "nx_block", "args": {"x": 40, "length": 20, "width": 20, "height": 20}},
            {"tool": "nx_boolean", "args": {"target": "BLOCK(0)", "tool": "last", "operation": "unite"}},
        ],
        "budget": DEFAULT_BUDGET_T2,
        "tags": ["boolean"],
        "_asserts": [rel("volume", 24000.0, 0.003), absv("bodies", 1, 0)],
    },
    {
        "id": "T2-bracket",
        "tier": "T2",
        "goal": "80×50×15 支架板，打 2×φ10 通孔",
        "solution_steps": [
            {"tool": "nx_block", "args": {"length": 80, "width": 50, "height": 15}},
            {"tool": "nx_hole", "args": {"target": "last", "position": [20, 25, 15], "diameter": 10}},
            {"tool": "nx_hole", "args": {"target": "last", "position": [60, 25, 15], "diameter": 10}},
        ],
        "budget": DEFAULT_BUDGET_T2,
        "tags": ["bracket"],
        "_asserts": [rel("volume", 57642.8, 0.004)],
    },
    {
        "id": "T2-shell-box",
        "tier": "T2",
        "goal": "100×80×40 盒体抽壳壁厚 3（顶面开口）",
        "solution_steps": [
            {"tool": "nx_block", "args": {"length": 100, "width": 80, "height": 40}},
            {"tool": "nx_shell", "args": {"target": "last", "thickness": 3, "faces": [[50, 40, 40]]}},
        ],
        "budget": DEFAULT_BUDGET_T2,
        "tags": ["shell"],
        "_asserts": [rel("volume", 62628.0, 0.01)],
    },
    {
        "id": "T2-extrude-triangle",
        "tier": "T2",
        "goal": "直角三角形（底 40 高 30）拉伸 10",
        "solution_steps": [
            {"tool": "nx_extrude", "args": {"points": [[0, 0, 0], [40, 0, 0], [20, 30, 0]], "distance": 10}},
        ],
        "budget": DEFAULT_BUDGET_T2,
        "tags": ["extrude"],
        "_asserts": [rel("volume", 6000.0, 0.005)],
    },
    {
        "id": "T2-cylinder",
        "tier": "T2",
        "goal": "矩形截面（x0..10，y-5..5）绕 Y 轴回转成圆柱",
        "solution_steps": [
            {
                "tool": "nx_revolve",
                "args": {"points": [[0, -5, 0], [10, -5, 0], [10, 5, 0], [0, 5, 0]], "angle": 360, "axis_dir": [0, 1, 0]},
            }
        ],
        "budget": DEFAULT_BUDGET_T2,
        "tags": ["revolve"],
        "_asserts": [rel("volume", 3141.5927, 0.01)],
    },
    {
        "id": "T2-delete-body",
        "tier": "T2",
        "goal": "建两个分离体，删掉第一个",
        "solution_steps": [
            {"tool": "nx_block", "args": {"length": 20, "width": 20, "height": 10}},
            {"tool": "nx_block", "args": {"x": 50, "length": 10, "width": 10, "height": 10}},
            {"tool": "nx_delete_body", "args": {"target": "BLOCK(0)"}},
        ],
        "budget": DEFAULT_BUDGET_T2,
        "tags": ["delete"],
        "_asserts": [absv("bodies", 1, 0), rel("volume", 1000.0, 0.001)],
    },
]


def main():
    TASKS.mkdir(parents=True, exist_ok=True)
    HIDDEN.mkdir(parents=True, exist_ok=True)
    for task in TASKS_DEF:
        data = dict(task)
        asserts = data.pop("_asserts", [])
        tier_dir = TASKS / data["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        (tier_dir / (data["id"] + ".json")).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (HIDDEN / (data["id"] + ".asserts.json")).write_text(
            json.dumps({"asserts": asserts}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print("wrote %d tasks (%d T1, %d T2)" % (
        len(TASKS_DEF),
        sum(1 for task in TASKS_DEF if task["tier"] == "T1"),
        sum(1 for task in TASKS_DEF if task["tier"] == "T2"),
    ))


if __name__ == "__main__":
    main()
