"""Live auto-ingest: operation log -> drafts/pits -> replay verification.

Designed to be run by a scheduler (Windows Task Scheduler / cron) every few
minutes. It needs a live NX session only for the replay step; without one it
exits with code 3 and leaves the log untouched.

CLI:
  python -m nxkit.auto_ingest --io <runtime>/io --library <runtime>/library \
      --contract <runtime>/contract --parts <runtime>/io/auto_parts
"""

import argparse
import json
import sys
from pathlib import Path


def build_router(io_dir, library_root, contract_dir):
    from .bridge import BridgeClient
    from .gate import Gate
    from .library.store import Library
    from .precheck import Precheck
    from .registry import Registry
    from .router import Router
    from .snapshot import SnapshotStore

    io_dir = Path(io_dir)
    contract_dir = Path(contract_dir)
    return Router(
        Registry(contract_dir),
        BridgeClient(io_dir),
        Library(library_root).init(),
        Gate(io_dir / "workflow.json"),
        precheck=Precheck(contract_dir),
        snapshots=SnapshotStore(Path(library_root).parent / "snapshots"),
    )


def run_once(oplog_path, library_root, contract_dir=None, parts_dir=None, router=None,
             min_success=2, replay=None):
    """One ingest pass. `router`/`replay` are injectable for tests."""
    from .ingest import ingest, replay_with_router
    from .library.store import Library

    library = Library(library_root).init()
    if replay is None and router is not None and parts_dir:
        replay = lambda entry: replay_with_router(router, entry, parts_dir)
    return ingest(Path(oplog_path), library, min_success=min_success, replay=replay)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--io", required=True)
    parser.add_argument("--library", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--parts", default="")
    parser.add_argument("--min-success", type=int, default=2)
    args = parser.parse_args(argv)

    io_dir = Path(args.io)
    from .bridge import BridgeClient

    sessions = [s for s in BridgeClient(io_dir).sessions() if s.get("alive")]
    if not sessions:
        print(json.dumps({"status": "NO_LIVE_SESSION", "io": str(io_dir)}))
        return 3
    router = build_router(args.io, args.library, args.contract)
    parts = Path(args.parts) if args.parts else io_dir / "auto_parts"
    result = run_once(io_dir / "oplog.jsonl", args.library, router=router,
                      parts_dir=parts, min_success=args.min_success)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
