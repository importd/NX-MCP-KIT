import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _start(contract_dir: Path, expose: str | None = None) -> subprocess.Popen:
    env = dict(os.environ)
    env["NXKIT_CONTRACT_DIR"] = str(contract_dir)
    if expose is not None:
        env["NXKIT_EXPOSE"] = expose
    env["PYTHONPATH"] = str(REPO / "runtime") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.Popen(
        [sys.executable, "-m", "nxkit.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )


def _rpc(proc: subprocess.Popen, method: str, params=None, rid: int = 1) -> dict:
    msg = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        msg["params"] = params
    proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def test_initialize_reports_server_identity(contract_dir):
    proc = _start(contract_dir)
    try:
        resp = _rpc(
            proc,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
        assert resp["result"]["serverInfo"]["name"] == "nx-agent-kit"
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert resp["result"]["capabilities"]["tools"]["listChanged"] is True
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        proc.stdout.close()
        proc.stderr.close()


def test_tools_list_uses_catalog_by_default(contract_dir):
    proc = _start(contract_dir)
    try:
        resp = _rpc(proc, "tools/list")
        names = {tool["name"] for tool in resp["result"]["tools"]}
        assert names == {
            "nx_status",
            "nx_find",
            "nx_help",
            "nx_call",
            "nx_job",
            "exp_search",
        }
        for tool in resp["result"]["tools"]:
            assert tool["inputSchema"]["type"] == "object"
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        proc.stdout.close()
        proc.stderr.close()


def test_tools_list_exposes_session_args_for_nx_tools(contract_dir):
    proc = _start(contract_dir, expose="all")
    try:
        resp = _rpc(proc, "tools/list")
        tools = {tool["name"]: tool for tool in resp["result"]["tools"]}
        props = tools["nx_run_python"]["inputSchema"]["properties"]
        assert props["pid"]["type"] == "integer"
        assert props["timeout_s"]["type"] == "number"
        assert "pid" not in tools["nx_find"]["inputSchema"]["properties"]
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        proc.stdout.close()
        proc.stderr.close()


def test_unknown_tool_returns_tool_not_found(contract_dir):
    proc = _start(contract_dir)
    try:
        resp = _rpc(proc, "tools/call", {"name": "nx_nope", "arguments": {}})
        assert resp["result"]["isError"] is True
        payload = json.loads(resp["result"]["content"][0]["text"])
        assert payload["error"]["code"] == "TOOL_NOT_FOUND"
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        proc.stdout.close()
        proc.stderr.close()


def test_unknown_method_is_jsonrpc_error(contract_dir):
    proc = _start(contract_dir)
    try:
        resp = _rpc(proc, "nonexistent/method")
        assert resp["error"]["code"] == -32601
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        proc.stdout.close()
        proc.stderr.close()
