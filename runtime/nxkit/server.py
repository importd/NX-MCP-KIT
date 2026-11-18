"""Minimal MCP stdio server over JSON-RPC 2.0 (protocol 2024-11-05).

Implemented in-tree because the intranet machine cannot install the official
`mcp` SDK (PyPI unreachable). Only the methods an MCP client actually uses for
tools are implemented: initialize, ping, tools/list, tools/call, plus
notifications/tools/list_changed emission when exposure changes.
"""

import json
import os
import sys
from pathlib import Path

from . import __version__
from .bridge import BridgeClient
from .gate import Gate
from .headless import HeadlessRunner
from .jobs import Jobs
from .kb.search import Kb
from .library.store import Library
from .precheck import Precheck
from .registry import ContractError, Registry
from .router import Router
from .security import SecurityPolicy
from .snapshot import SnapshotStore
from .templates import TemplateStore

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "nx-agent-kit", "version": __version__}
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def default_contract_dir() -> Path:
    override = os.environ.get("NXKIT_CONTRACT_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "contract"


def _tool_result(payload: dict) -> dict:
    text = json.dumps(payload, ensure_ascii=False)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": not payload.get("ok", False),
        "structuredContent": payload,
    }


class Server:
    def __init__(self, registry: Registry, expose: str = "catalog", router: Router | None = None):
        self.registry = registry
        self.expose = expose
        self.router = router

    def handle(self, method: str, params: dict) -> dict:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "NX Agent Kit: 契约驱动的 NX 操作层。改几何前先 exp_search；"
                    "不确定工具用 nx_find；失败先读 error.next。"
                ),
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.registry.list(self.expose)}
        if method == "tools/call":
            return self._call_tool(params)
        raise _RpcError(METHOD_NOT_FOUND, "method not found: %s" % method)

    def _call_tool(self, params: dict) -> dict:
        if not isinstance(params, dict) or "name" not in params:
            raise _RpcError(INVALID_PARAMS, "tools/call needs params.name")
        name = params["name"]
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise _RpcError(INVALID_PARAMS, "tools/call arguments must be an object")
        if self.router is None:
            return _tool_result(
                {
                    "ok": False,
                    "error": {
                        "code": "TOOL_NOT_IMPLEMENTED",
                        "stage": "bridge",
                        "msg": "server has no Router configured",
                    },
                }
            )
        return _tool_result(self.router.call(name, arguments))


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _write(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    # Windows default console encoding is GBK; MCP clients require UTF-8.
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    try:
        registry = Registry(default_contract_dir())
    except ContractError as exc:
        sys.stderr.write("nxkit.server: contract error: %s\n" % exc)
        return 2
    expose = os.environ.get("NXKIT_EXPOSE", "catalog")
    repo = Path(__file__).resolve().parents[2]
    io_dir = Path(os.environ.get("NXKIT_IO_DIR", str(repo / "io")))
    library_root = Path(os.environ.get("NXKIT_LIBRARY", str(repo / "library")))
    workflow = Path(os.environ.get("NXKIT_WORKFLOW", str(io_dir / "workflow.json")))
    bridge = BridgeClient(io_dir)
    library = Library(library_root).init()
    gate = Gate(workflow)
    jobs = Jobs(io_dir)
    nx_root_env = os.environ.get("NXKIT_NX_ROOT")
    kb_db_env = os.environ.get("NXKIT_KB_DB")
    kb = Kb(Path(kb_db_env)) if kb_db_env and Path(kb_db_env).is_file() else None
    router = Router(
        registry,
        bridge,
        library,
        gate,
        expose,
        jobs=jobs,
        precheck=Precheck(default_contract_dir()),
        snapshots=SnapshotStore(repo / "snapshots"),
        headless=HeadlessRunner(Path(nx_root_env) if nx_root_env else None),
        templates=TemplateStore(default_contract_dir()),
        kb=kb,
        security=SecurityPolicy.from_env(repo),
    )
    server = Server(registry, expose, router)

    while True:
        line = sys.stdin.readline()
        if not line:
            return 0
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        if "id" not in message:
            continue  # notifications from the client need no reply
        rid = message["id"]
        try:
            result = server.handle(message.get("method", ""), message.get("params") or {})
            _write({"jsonrpc": "2.0", "id": rid, "result": result})
        except _RpcError as exc:
            _write({"jsonrpc": "2.0", "id": rid, "error": {"code": exc.code, "message": exc.message}})
        except Exception as exc:  # pragma: no cover - defensive envelope
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {"code": -32603, "message": "internal error: %s" % exc},
                }
            )


if __name__ == "__main__":
    raise SystemExit(main())
