"""Tool routing: local handlers, NX bridge commands, future batch route."""

import time
import uuid

from .bridge import BridgeTimeout, BridgeUnavailable
from .handlers.exp import HANDLERS as EXP_HANDLERS
from .handlers.meta import HANDLERS as META_HANDLERS
from .handlers.tools import HANDLERS as TOOLS_HANDLERS
from .registry import ContractError
from .result import make_error, make_ok


class Router:
    def __init__(
        self,
        registry,
        bridge,
        library,
        gate,
        expose: str = "catalog",
        jobs=None,
        precheck=None,
        snapshots=None,
        headless=None,
        kb=None,
        templates=None,
    ):
        self.registry = registry
        self.bridge = bridge
        self.library = library
        self.gate = gate
        self.expose = expose
        self.jobs = jobs
        self.precheck = precheck
        self.snapshots = snapshots
        self.headless = headless
        self.kb = kb
        self.templates = templates
        self.current_part_path = None
        self.part = "current"
        self.handlers = dict(META_HANDLERS)
        self.handlers.update(EXP_HANDLERS)
        self.handlers.update(TOOLS_HANDLERS)

    def call(self, name: str, args: dict | None = None) -> dict:
        args = dict(args or {})
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        try:
            tool = self.registry.get(name)
        except ContractError:
            return make_error(
                request_id,
                "TOOL_NOT_FOUND",
                "bridge",
                "未知工具：%s" % name,
                next="用 nx_find 搜索工具名",
                hint_tool="nx_find",
            )

        skip_search = bool(args.pop("skip_search", False))
        if tool.flags.get("gate") and not skip_search:
            blocked = self.gate.check(tool, self.part, self.library)
            if blocked is not None:
                return make_error(
                    request_id,
                    "SEARCH_REQUIRED",
                    "precheck",
                    blocked["msg"],
                    next=blocked["next"],
                    hint_tool="exp_search",
                )

        kind = tool.route.get("kind")
        if kind in ("local", "batch"):
            handler = self.handlers.get(tool.route.get("handler"))
            if handler is None:
                return make_error(
                    request_id,
                    "TOOL_NOT_IMPLEMENTED",
                    "bridge",
                    "工具 %s 的 handler %r 未实现" % (name, tool.route.get("handler")),
                )
            result = handler(self, args, request_id)
        elif kind == "nx":
            result = self._call_nx(tool, args, request_id)
        else:
            result = make_error(
                request_id,
                "ROUTE_NOT_IMPLEMENTED",
                "bridge",
                "route.kind=%r 尚未实现（T9 无头执行器）" % kind,
            )
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 1)
        return result

    def _call_nx(self, tool, args, request_id: str) -> dict:
        try:
            sessions = self.bridge.sessions()
        except BridgeUnavailable as exc:
            return make_error(request_id, "BRIDGE_UNAVAILABLE", "bridge", str(exc))
        if not sessions:
            return make_error(
                request_id,
                "BRIDGE_UNAVAILABLE",
                "bridge",
                "没有在线的 NX 会话",
                next="先打开 NX 并确认桥已加载（nx_status）",
                hint_tool="nx_status",
            )
        pid = args.pop("pid", None) or sessions[0].get("pid")
        timeout_s = float(args.pop("timeout_s", 120.0))
        try:
            payload = self.bridge.submit(pid, tool.route["cmd"], args, timeout_s=timeout_s)
        except BridgeUnavailable as exc:
            return make_error(request_id, "BRIDGE_UNAVAILABLE", "bridge", str(exc))
        except BridgeTimeout as exc:
            return make_error(
                request_id,
                "BRIDGE_TIMEOUT",
                "bridge",
                str(exc),
                next="用 nx_job 查看任务；超时任务不会自动重放",
                hint_tool="nx_job",
            )
        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            return make_error(
                request_id,
                error.get("code", "NX_ERROR"),
                "nx",
                error.get("msg", "NX 执行失败"),
                next=error.get("next"),
                hint_tool=error.get("hint_tool"),
            )
        return make_ok(
            request_id,
            data=(payload or {}).get("data"),
            verify=(payload or {}).get("verify"),
            job=(payload or {}).get("job"),
        )
