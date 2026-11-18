from pathlib import Path

import pytest

from nxkit.gate import Gate
from nxkit.library.store import Library
from nxkit.registry import Registry
from nxkit.router import Router
from nxkit.security import SecurityError, SecurityPolicy


class FakeBridge:
    def __init__(self):
        self.calls = []

    def sessions(self):
        return [{"pid": 8016, "nx": "2512", "alive": True}]

    def submit(self, pid, cmd, args, timeout_s=120.0):
        self.calls.append(cmd)
        return {"data": {"feature": "BLOCK(0)"}, "facts": {"volume": 1.0}}


def _router(workdir, contract_dir, allow_execute=True):
    registry = Registry(contract_dir)
    library = Library(workdir / "library").init()
    gate = Gate(workdir / "workflow.json")
    bridge = FakeBridge()
    policy = SecurityPolicy([workdir], allow_execute=allow_execute)
    return Router(registry, bridge, library, gate, security=policy), bridge


def test_policy_allows_inside_workspace(workdir):
    policy = SecurityPolicy([workdir])
    inside = workdir / "part.prt"
    assert policy.check_path(inside) == inside.resolve()


def test_policy_rejects_outside_workspace(workdir, tmp_path_factory=None):
    policy = SecurityPolicy([workdir])
    with pytest.raises(SecurityError):
        policy.check_path("C:\\Windows\\System32\\config")


def test_router_rejects_outside_path(workdir, contract_dir):
    router, bridge = _router(workdir, contract_dir)
    envelope = router.call(
        "nx_screenshot", {"path": "C:\\Windows\\evil.png", "skip_search": True}
    )
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "PATH_NOT_ALLOWED"
    assert bridge.calls == []


def test_router_blocks_execute_when_disabled(workdir, contract_dir):
    router, bridge = _router(workdir, contract_dir, allow_execute=False)
    envelope = router.call("nx_run_python", {"code": "result = 1", "skip_search": True})
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "EXECUTE_DISABLED"
    assert bridge.calls == []


def test_dry_run_does_not_touch_bridge(workdir, contract_dir):
    router, bridge = _router(workdir, contract_dir)
    envelope = router.call(
        "nx_block",
        {"length": 10, "width": 10, "height": 10, "skip_search": True, "dry_run": True},
    )
    assert envelope["ok"] is True
    assert envelope["data"]["dry_run"] is True
    assert envelope["data"]["cmd"] == "nx_block"
    assert bridge.calls == []
