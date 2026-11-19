"""Tool routing: local handlers, NX bridge commands, future batch route."""

import os
import time
import uuid

from .bridge import BridgeTimeout, BridgeUnavailable
from .handlers.exp import HANDLERS as EXP_HANDLERS
from .handlers.meta import HANDLERS as META_HANDLERS
from .handlers.tools import HANDLERS as TOOLS_HANDLERS
from .registry import ContractError
from .result import make_error, make_ok
from .security import SecurityError, walk_would_do


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
        security=None,
        oplog=None,
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
        self.security = security
        self.oplog = oplog
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
            return self._finish(
                name,
                args,
                make_error(
                    request_id,
                    "TOOL_NOT_FOUND",
                    "bridge",
                    "未知工具：%s" % name,
                    next="用 nx_find 搜索工具名",
                    hint_tool="nx_find",
                ),
                started,
            )

        skip_search = bool(args.pop("skip_search", False))
        dry_run = bool(args.pop("dry_run", False))
        if tool.flags.get("gate") and not skip_search:
            blocked = self.gate.check(tool, self.part, self.library)
            if blocked is not None:
                return self._finish(
                    name,
                    args,
                    make_error(
                        request_id,
                        "SEARCH_REQUIRED",
                        "precheck",
                        blocked["msg"],
                        next=blocked["next"],
                        hint_tool="exp_search",
                    ),
                    started,
                )
        if self.security is not None:
            try:
                self.security.check_args(args)
            except SecurityError as exc:
                return self._finish(
                    name,
                    args,
                    make_error(
                        request_id,
                        "PATH_NOT_ALLOWED",
                        "precheck",
                        str(exc),
                        next="把文件放到工作区，或用 NXKIT_WORKSPACE 增加允许目录",
                    ),
                    started,
                )
            if name == "nx_run_python" and not self.security.allow_execute:
                return self._finish(
                    name,
                    args,
                    make_error(
                        request_id,
                        "EXECUTE_DISABLED",
                        "precheck",
                        "nx_run_python 已在配置中禁用（NXKIT_ALLOW_EXECUTE=0）",
                        next="需要执行代码时显式开启 NXKIT_ALLOW_EXECUTE=1",
                    ),
                    started,
                )
        if dry_run:
            return self._finish(name, args, make_ok(request_id, data=walk_would_do(tool, args)), started)

        kind = tool.route.get("kind")
        try:
            if kind in ("local", "batch"):
                handler = self.handlers.get(tool.route.get("handler"))
                if handler is None:
                    return self._finish(
                        name,
                        args,
                        make_error(
                            request_id,
                            "TOOL_NOT_IMPLEMENTED",
                            "bridge",
                            "工具 %s 的 handler %r 未实现" % (name, tool.route.get("handler")),
                        ),
                        started,
                    )
                result = handler(self, args, request_id)
            elif kind == "nx":
                result = self._call_nx(tool, args, request_id)
            else:
                result = make_error(
                    request_id,
                    "ROUTE_NOT_IMPLEMENTED",
                    "bridge",
                    "route.kind=%r 尚未实现" % kind,
                )
        except Exception as exc:  # handlers must never crash the server
            result = make_error(
                request_id,
                "INTERNAL_ERROR",
                "bridge",
                "工具 %s 内部异常：%r" % (name, exc),
                next="把 code/参数贴给开发者；先用 nx_status 确认连接",
            )
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 1)
        if args.get("path") and name in ("nx_part", "nx_save", "nx_snapshot"):
            self.current_part_path = args.get("path")
        self._log_operation(name, args, result)
        return result

    def _finish(self, name, args, result, started):
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 1)
        self._log_operation(name, args, result)
        return result

    def _log_operation(self, name, args, result):
        """Append every call to the operation log (never breaks the tool call)."""
        if self.oplog is None:
            return
        try:
            from .oplog import sanitize_args

            error = result.get("error") or {}
            self.oplog.append(
                {
                    "tool": name,
                    "args": sanitize_args(args),
                    "ok": bool(result.get("ok")),
                    "error_code": error.get("code"),
                    "error_stage": error.get("stage"),
                    "verify": result.get("verify"),
                    "part": os.path.basename(str(self.current_part_path or self.part or "")),
                    "session_id": os.environ.get("NXKIT_SESSION_ID", ""),
                    "run_id": os.environ.get("NXKIT_RUN_ID", ""),
                    "source": os.environ.get("NXKIT_SOURCE", "mcp"),
                }
            )
        except Exception:
            pass

    @staticmethod
    def _pick_session(sessions):
        alive = [session for session in sessions if session.get("alive")]
        fresh = [
            session
            for session in alive
            if session.get("heartbeat_age_s") is None or session.get("heartbeat_age_s") < 300
        ]
        pool = fresh or alive or sessions
        return pool[0].get("pid")

    def _call_nx(self, tool, args, request_id: str) -> dict:
        if tool.flags.get("precheck") and args.get("code"):
            precheck = self.precheck
            if precheck is not None:
                issues = precheck.check(
                    args["code"], args.get("target_ver") or "nx2512"
                )
                if issues:
                    first = issues[0]
                    return make_error(
                        request_id,
                        "PRECHECK_FAILED",
                        "precheck",
                        first.msg,
                        next=first.next,
                        hint_tool=first.hint_tool,
                    )
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
        pid = args.pop("pid", None) or self._pick_session(sessions)
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
                next="用 nx_job 查看任务；超时请求已从队列撤回",
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
        payload = payload or {}
        facts = payload.get("facts") or {}
        verify = None
        if facts:
            verify = {
                "facts": facts,
                "source": "bridge",
                "evidence": "measured inside NX: %s" % ", ".join("%s=%s" % (k, v) for k, v in facts.items()),
            }
        return make_ok(
            request_id,
            data=payload.get("data"),
            verify=verify,
            job=payload.get("job"),
        )
