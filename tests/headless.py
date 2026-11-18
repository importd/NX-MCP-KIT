"""Headless acceptance against a real NX install (run_journal).

Run with: NXKIT_NX_ROOT="D:\\Program Files\\Siemens\\NX 10.0" pytest tests/headless.py -v
Skips entirely when NXKIT_NX_ROOT is not set.
"""

import json
import os
from pathlib import Path

import pytest

from nxkit.headless import HeadlessRunner

NX_ROOT = os.environ.get("NXKIT_NX_ROOT")
pytestmark = pytest.mark.skipif(not NX_ROOT, reason="NXKIT_NX_ROOT not set")
REPO = Path(__file__).resolve().parents[1]


def test_headless_block_then_hole():
    part = REPO / "io" / "live" / "headless_accept.prt"
    plan = {
        "steps": [
            {"cmd": "nx_part", "args": {"action": "new", "path": str(part)}},
            {"cmd": "nx_block", "args": {"length": 50, "width": 40, "height": 30}},
            {"cmd": "nx_hole", "args": {"target": "last", "position": [25, 20, 30], "diameter": 8}},
            {"cmd": "nx_inspect", "args": {}},
            {"cmd": "nx_measure", "args": {"target": "last"}},
        ]
    }
    runner = HeadlessRunner(Path(NX_ROOT), plan_dir=REPO / "io" / "headless")
    result = runner.run(plan, timeout_s=300)

    assert result["ok"] is True, result["markers"]
    assert "NXKIT_OK" in result["markers"]
    payload = json.loads(Path(result["artifacts"][0]).read_text(encoding="utf-8"))
    assert payload["ok"] is True

    block = payload["steps"][1]["facts"]
    assert block["volume"] == pytest.approx(60000.0, abs=1.0)
    assert block["bbox"] == [0.0, 0.0, 0.0, 50.0, 40.0, 30.0]

    hole = payload["steps"][2]["facts"]
    assert hole["volume"] == pytest.approx(58492.04, abs=10.0)
    assert hole["faces"] == 7

    inspect = payload["steps"][3]["data"]
    assert inspect["bodies"][0]["id"] == "BLOCK(0)"
