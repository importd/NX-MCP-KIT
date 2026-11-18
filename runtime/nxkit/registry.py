"""Contract loader: the single source of truth for tool definitions.

Replaces the `jsonschema` dependency with a deliberately small subset
validator (see Ruling in .superpowers ledger): required keys, types,
enums and a couple of structural checks that matter for MCP clients.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ContractError(Exception):
    """Raised when a contract file is malformed or self-contradictory."""


_REQUIRED_KEYS = ("name", "s", "desc", "route", "schema")
_TOOL_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_")
_ROUTE_KINDS = {"nx", "local", "batch"}
_GROUPS = {"meta", "part", "model", "mold", "query", "exec", "api", "exp"}


@dataclass(frozen=True)
class ToolDef:
    name: str
    group: str
    s: str
    k: tuple
    desc: str
    route: dict
    flags: dict
    schema: dict
    next: str
    matrix: dict

    def to_mcp(self) -> dict:
        return {
            "name": self.name,
            "description": self.desc,
            "inputSchema": self.schema,
        }


def _fail(path: Path, msg: str) -> None:
    raise ContractError("%s: %s" % (path, msg))


def _validate_tool(raw: Any, group_hint: str | None, path: Path) -> None:
    if not isinstance(raw, dict):
        _fail(path, "tool entry must be an object")
    missing = [key for key in _REQUIRED_KEYS if key not in raw]
    if missing:
        _fail(path, "tool missing required keys: %s" % ", ".join(missing))

    name = raw["name"]
    if not isinstance(name, str) or not name:
        _fail(path, "tool name must be a non-empty string")
    if not set(name) <= _TOOL_NAME_CHARS or not name[0].isalpha():
        _fail(path, "tool name must be snake_case ASCII: %r" % name)

    group = raw.get("group", group_hint)
    if not group:
        _fail(path, "tool %s has no group (file-level group missing too)" % name)
    if group not in _GROUPS:
        _fail(path, "unknown group: %r" % group)
    if group_hint and raw.get("group") and raw["group"] != group_hint:
        _fail(path, "tool %s group %r disagrees with file group %r" % (name, raw["group"], group_hint))

    for key in ("s", "desc"):
        if not isinstance(raw[key], str):
            _fail(path, "%s must be a string for tool %s" % (key, name))

    route = raw["route"]
    if not isinstance(route, dict) or "kind" not in route:
        _fail(path, "tool %s route must be an object with kind" % name)
    if route["kind"] not in _ROUTE_KINDS:
        _fail(path, "tool %s unknown route kind %r" % (name, route["kind"]))
    if route["kind"] == "nx" and not route.get("cmd"):
        _fail(path, "tool %s nx route needs cmd" % name)
    if route["kind"] == "local" and not route.get("handler"):
        _fail(path, "tool %s local route needs handler" % name)

    schema = raw["schema"]
    if not isinstance(schema, dict) or schema.get("type") != "object":
        _fail(path, "tool %s schema must be an object schema" % name)
    props = schema.get("properties")
    if props is not None and not isinstance(props, dict):
        _fail(path, "tool %s schema.properties must be an object" % name)
    required = schema.get("required", [])
    if not isinstance(required, list):
        _fail(path, "tool %s schema.required must be a list" % name)
    for req in required:
        if props is None or req not in props:
            _fail(path, "tool %s required %r not in properties" % (name, req))

    keywords = raw.get("k", [])
    if not isinstance(keywords, list) or any(not isinstance(kw, str) for kw in keywords):
        _fail(path, "tool %s k must be a list of strings" % name)

    flags = raw.get("flags", {})
    if not isinstance(flags, dict):
        _fail(path, "tool %s flags must be an object" % name)

    matrix = raw.get("matrix", {})
    if not isinstance(matrix, dict):
        _fail(path, "tool %s matrix must be an object" % name)
    for ver, state in matrix.items():
        if state not in ("verified", "expected", "unavailable"):
            _fail(path, "tool %s matrix[%s] must be verified|expected|unavailable" % (name, ver))


class Registry:
    """Loads contract/tools/*.json and answers discovery queries."""

    def __init__(self, contract_dir: Path):
        self.contract_dir = Path(contract_dir)
        self.tools: dict[str, ToolDef] = {}
        tools_dir = self.contract_dir / "tools"
        if not tools_dir.is_dir():
            raise ContractError("missing contract tools dir: %s" % tools_dir)
        for path in sorted(tools_dir.glob("*.json")):
            self._load_file(path)

    def _load_file(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ContractError("%s: cannot read JSON: %s" % (path, exc)) from exc
        if not isinstance(data, dict) or "tools" not in data:
            _fail(path, "file must be an object with tools")
        group_hint = data.get("group")
        tools = data["tools"]
        if not isinstance(tools, list) or not tools:
            _fail(path, "tools must be a non-empty list")
        for raw in tools:
            _validate_tool(raw, group_hint, path)
            if raw["name"] in self.tools:
                _fail(path, "duplicate tool name: %s" % raw["name"])
            self.tools[raw["name"]] = ToolDef(
                name=raw["name"],
                group=raw.get("group", group_hint),
                s=raw["s"],
                k=tuple(raw.get("k", [])),
                desc=raw["desc"],
                route=dict(raw["route"]),
                flags=dict(raw.get("flags", {})),
                schema=dict(raw["schema"]),
                next=raw.get("next", ""),
                matrix=dict(raw.get("matrix", {})),
            )

    def get(self, name: str) -> ToolDef:
        try:
            return self.tools[name]
        except KeyError:
            raise ContractError("unknown tool: %s" % name) from None

    def list(self, expose: str = "all") -> list:
        if expose == "all":
            selected = list(self.tools.values())
        elif expose == "catalog":
            selected = [tool for tool in self.tools.values() if tool.flags.get("always")]
        else:
            groups = {part.strip() for part in expose.split(",") if part.strip()}
            selected = [
                tool
                for tool in self.tools.values()
                if tool.group in groups or tool.flags.get("always")
            ]
        return [tool.to_mcp() for tool in selected]
