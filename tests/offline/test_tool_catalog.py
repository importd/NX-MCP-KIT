import json
import sys
from pathlib import Path

import pytest

import nxstub
from nxkit.registry import Registry

REPO = Path(__file__).resolve().parents[2]

GROUP_COUNTS = {
    "meta": 6,
    "part": 3,
    "model": 8,
    "mold": 1,
    "query": 3,
    "exec": 5,
    "api": 1,
    "exp": 1,
}


def test_tool_count_and_groups(contract_dir):
    registry = Registry(contract_dir)
    assert len(registry.tools) == 28
    counts = {}
    for tool in registry.tools.values():
        counts[tool.group] = counts.get(tool.group, 0) + 1
    assert counts == GROUP_COUNTS


def test_nx_routes_are_declared_in_commands(contract_dir):
    registry = Registry(contract_dir)
    commands = json.loads((contract_dir / "commands.json").read_text(encoding="utf-8"))
    declared = {entry["name"] for entry in commands["commands"]}
    for tool in registry.tools.values():
        if tool.route["kind"] == "nx":
            assert tool.route["cmd"] in declared, tool.name


def test_bridge_command_table_matches_contract(contract_dir):
    nxstub.install()
    sys.path.insert(0, str(REPO / "bridge"))
    for name in list(sys.modules):
        if name == "commands" or name.startswith("commands."):
            del sys.modules[name]
    try:
        import commands

        commands_json = json.loads((contract_dir / "commands.json").read_text(encoding="utf-8"))
        declared = {entry["name"] for entry in commands_json["commands"]}
        assert set(commands.COMMANDS) == declared
    finally:
        sys.path.remove(str(REPO / "bridge"))


def test_every_tool_is_matrix_tagged(contract_dir):
    registry = Registry(contract_dir)
    for tool in registry.tools.values():
        assert tool.matrix, tool.name
        for state in tool.matrix.values():
            assert state in ("verified", "expected", "unavailable")
