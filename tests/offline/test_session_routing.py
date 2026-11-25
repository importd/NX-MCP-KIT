"""Multi-session routing: explicit pid, ambiguity, and session_id reporting."""

from nxkit.gate import Gate
from nxkit.library.store import Library
from nxkit.registry import Registry
from nxkit.router import Router

ALIVE_TWO = [
    {"pid": 111, "alive": True, "python": "3.3.2"},
    {"pid": 222, "alive": True, "python": "3.3.2"},
]


class RecordingBridge:
    def __init__(self, sessions):
        self._sessions = sessions
        self.calls = []

    def sessions(self):
        return list(self._sessions)

    def submit(self, pid, cmd, args, timeout_s=120.0):
        self.calls.append({"pid": pid, "cmd": cmd, "args": args})
        return {"data": {"feature": "BLOCK(0)"}, "facts": {"volume": 1.0}}


def _router(workdir, contract_dir, sessions):
    registry = Registry(contract_dir)
    library = Library(workdir / "library").init()
    gate = Gate(workdir / "workflow.json")
    bridge = RecordingBridge(sessions)
    return Router(registry, bridge, library, gate), bridge


def test_two_alive_sessions_without_pid_is_ambiguous(workdir, contract_dir):
    router, bridge = _router(workdir, contract_dir, ALIVE_TWO)

    envelope = router.call("nx_block", {"x": 1, "skip_search": True})

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "AMBIGUOUS_SESSION"
    assert envelope["error"]["sessions"] == [
        {"pid": 111, "python": "3.3.2"},
        {"pid": 222, "python": "3.3.2"},
    ]
    assert bridge.calls == []


def test_explicit_pid_selects_session(workdir, contract_dir):
    router, bridge = _router(workdir, contract_dir, ALIVE_TWO)

    envelope = router.call("nx_block", {"x": 1, "pid": 222, "skip_search": True})

    assert envelope["ok"] is True
    assert [call["pid"] for call in bridge.calls] == [222]
    assert envelope["session_pid"] == 222


def test_single_alive_session_is_auto_selected(workdir, contract_dir):
    sessions = [ALIVE_TWO[0], {"pid": 333, "alive": False, "python": "3.3.2"}]
    router, bridge = _router(workdir, contract_dir, sessions)

    envelope = router.call("nx_block", {"x": 1, "skip_search": True})

    assert envelope["ok"] is True
    assert [call["pid"] for call in bridge.calls] == [111]
    assert envelope["session_pid"] == 111


def test_pid_that_is_not_alive_is_rejected(workdir, contract_dir):
    router, bridge = _router(workdir, contract_dir, ALIVE_TWO)

    envelope = router.call("nx_block", {"x": 1, "pid": 999, "skip_search": True})

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "SESSION_NOT_FOUND"
    assert bridge.calls == []


def test_non_integer_pid_is_bad_argument(workdir, contract_dir):
    router, bridge = _router(workdir, contract_dir, ALIVE_TWO)

    envelope = router.call("nx_block", {"x": 1, "pid": "abc", "skip_search": True})

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "BAD_ARGUMENT"
    assert bridge.calls == []


def test_status_pid_filters_sessions(workdir, contract_dir):
    router, _ = _router(workdir, contract_dir, ALIVE_TWO)

    envelope = router.call("nx_status", {"pid": 222})

    assert envelope["ok"] is True
    assert [s["pid"] for s in envelope["data"]["sessions"]] == [222]
    assert envelope["data"]["connected"] is True


def test_status_pid_not_found_reports_disconnected(workdir, contract_dir):
    router, _ = _router(workdir, contract_dir, ALIVE_TWO)

    envelope = router.call("nx_status", {"pid": 999})

    assert envelope["ok"] is True
    assert envelope["data"]["connected"] is False
    assert envelope["data"]["sessions"] == []


def test_no_alive_session_is_unavailable(workdir, contract_dir):
    sessions = [{"pid": 111, "alive": False, "python": "3.3.2"}]
    router, bridge = _router(workdir, contract_dir, sessions)

    envelope = router.call("nx_block", {"x": 1, "skip_search": True})

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "BRIDGE_UNAVAILABLE"
    assert bridge.calls == []
