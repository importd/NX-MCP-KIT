from pathlib import Path

from nxkit.gate import Gate
from nxkit.library.store import Library
from nxkit.registry import Registry, ToolDef
from nxkit.router import Router

REPO = Path(__file__).resolve().parents[2]


class FakeBridge:
    def __init__(self):
        self.calls = []

    def sessions(self):
        return [{"pid": 8016, "nx": "2512", "alive": True}]

    def submit(self, pid, cmd, args, timeout_s=120.0):
        self.calls.append((cmd, args))
        return {"data": {"feature": "BLOCK(0)"}, "facts": {"volume": 1000.0}}


def _router(workdir, contract_dir):
    registry = Registry(contract_dir)
    registry.tools["nx_block"] = ToolDef(
        name="nx_block",
        group="model",
        s="方块",
        k=("方块", "block"),
        desc="建块",
        route={"kind": "nx", "cmd": "nx_block"},
        flags={"gate": True},
        schema={"type": "object", "properties": {}},
        next="",
        matrix={},
    )
    library = Library(workdir / "library")
    library.init()
    library.save(
        {
            "id": "M0001",
            "c": "招式",
            "t": "用方块建基体",
            "k": ["方块"],
            "evidence": {"expect": 1.0, "got": 1.0, "tol": 0.01},
        }
    )
    gate = Gate(workdir / "workflow.json")
    return Router(registry, FakeBridge(), library, gate)


def test_find_returns_cards(workdir, contract_dir):
    router = _router(workdir, contract_dir)
    envelope = router.call("nx_find", {"q": "状态"})
    assert envelope["ok"] is True
    card = envelope["data"]["items"][0]
    assert card["t"] == "nx_status"
    assert card["g"] == "meta"
    assert card["need"] == []


def test_help_returns_full_schema(workdir, contract_dir):
    router = _router(workdir, contract_dir)
    envelope = router.call("nx_help", {"t": "nx_does_not_exist"})
    assert envelope["ok"] is False  # unknown tool
    envelope = router.call("nx_help", {"t": "nx_status"})
    assert envelope["ok"] is True
    assert envelope["data"]["inputSchema"]["type"] == "object"


def test_gate_blocks_until_search(workdir, contract_dir):
    router = _router(workdir, contract_dir)
    blocked = router.call("nx_block", {"x": 1})
    assert blocked["ok"] is False
    assert blocked["error"]["code"] == "SEARCH_REQUIRED"
    router.call("exp_search", {"q": "方块"})
    passed = router.call("nx_block", {"x": 1})
    assert passed["ok"] is True
    assert passed["data"]["feature"] == "BLOCK(0)"


def test_skip_search_escape(workdir, contract_dir):
    router = _router(workdir, contract_dir)
    envelope = router.call("nx_block", {"x": 1, "skip_search": True})
    assert envelope["ok"] is True


def test_nx_call_equivalent(workdir, contract_dir):
    router = _router(workdir, contract_dir)
    router.call("exp_search", {"q": "方块"})
    envelope = router.call("nx_call", {"t": "nx_block", "args": {"x": 1}})
    assert envelope["ok"] is True
    assert envelope["data"]["feature"] == "BLOCK(0)"


def test_unknown_tool_reports_not_found(workdir, contract_dir):
    router = _router(workdir, contract_dir)
    envelope = router.call("nx_nope", {})
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "TOOL_NOT_FOUND"


def test_exp_search_marks_gate_searched(workdir, contract_dir):
    router = _router(workdir, contract_dir)
    router.call("exp_search", {"q": "方块"})
    assert router.gate.state["searched"] is True
