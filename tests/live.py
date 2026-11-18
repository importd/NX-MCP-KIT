"""Interactive acceptance against an already-open NX session.

Requires the bridge startup file loaded in NX and NXKIT_IO_DIR pointing at the
same io directory the bridge watches. Skips otherwise.

Run with: NXKIT_IO_DIR=<repo>\\io pytest tests/live.py -v
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("NXKIT_IO_DIR"), reason="NXKIT_IO_DIR not set"
)


def _router():
    from pathlib import Path

    from nxkit.bridge import BridgeClient
    from nxkit.gate import Gate
    from nxkit.library.store import Library
    from nxkit.registry import Registry
    from nxkit.router import Router

    repo = Path(__file__).resolve().parents[1]
    io_dir = Path(os.environ["NXKIT_IO_DIR"])
    client = BridgeClient(io_dir)
    sessions = client.sessions()
    if not sessions:
        pytest.skip("no NX session answering in %s" % io_dir)
    registry = Registry(repo / "contract")
    library = Library(repo / "library").init()
    gate = Gate(io_dir / "workflow.json")
    return Router(registry, client, library, gate)


def test_live_status_reports_session():
    router = _router()
    envelope = router.call("nx_status", {})
    assert envelope["ok"] is True
    assert envelope["data"]["sessions"]


def test_live_block_and_measure():
    router = _router()
    block = router.call(
        "nx_block",
        {"length": 20, "width": 20, "height": 20, "x": 0, "y": 0, "z": 0, "skip_search": True},
    )
    assert block["ok"] is True, block.get("error")
    measure = router.call("nx_measure", {"target": "last", "what": "volume"})
    assert measure["ok"] is True, measure.get("error")
    assert measure["data"]["body"]
