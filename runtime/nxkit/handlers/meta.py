"""Local tool handlers (status / find / help / call)."""

from ..registry import ContractError
from ..result import make_error, make_ok


def handle_status(router, args, request_id):
    try:
        all_sessions = router.bridge.sessions()
    except Exception:
        all_sessions = []
    alive = [session for session in all_sessions if session.get("alive")]
    return make_ok(
        request_id,
        data={
            "connected": bool(alive),
            "sessions": alive,
            "ignored_dead": len(all_sessions) - len(alive),
            "part": router.part,
            "expose": router.expose,
        },
    )


def handle_find(router, args, request_id):
    query = (args.get("q") or "").strip().lower()
    module = args.get("module")
    items = []
    for tool in router.registry.tools.values():
        if module and tool.group != module:
            continue
        if query:
            haystack = " ".join([tool.name, tool.s, " ".join(tool.k)]).lower()
            if query not in haystack:
                continue
        items.append(
            {
                "t": tool.name,
                "g": tool.group,
                "s": tool.s,
                "need": tool.schema.get("required", []),
            }
        )
    return make_ok(request_id, data={"items": items})


def handle_help(router, args, request_id):
    name = args.get("t")
    try:
        tool = router.registry.get(name)
    except ContractError:
        return make_error(
            request_id,
            "TOOL_NOT_FOUND",
            "bridge",
            "未知工具：%s" % name,
            next="用 nx_find 搜索工具名",
            hint_tool="nx_find",
        )
    return make_ok(
        request_id,
        data={
            "name": tool.name,
            "group": tool.group,
            "s": tool.s,
            "description": tool.desc,
            "inputSchema": tool.schema,
            "next": tool.next,
            "matrix": tool.matrix,
        },
    )


def handle_call(router, args, request_id):
    name = args.get("t")
    target_args = args.get("args") or {}
    if not isinstance(target_args, dict):
        return make_error(
            request_id,
            "BAD_ARGUMENT",
            "precheck",
            "args 必须是对象",
            next='用 args={"x":0,"y":0} 形式传参',
        )
    if args.get("skip_search"):
        target_args = dict(target_args, skip_search=True)
    result = router.call(name, target_args)
    result["request_id"] = request_id
    return result


HANDLERS = {
    "status": handle_status,
    "find": handle_find,
    "help": handle_help,
    "call": handle_call,
}


def handle_job(router, args, request_id):
    jobs = getattr(router, "jobs", None)
    if jobs is None:
        return make_error(request_id, "JOBS_UNAVAILABLE", "bridge", "job 调度未启用")
    action = args.get("action") or "status"
    if action == "list":
        return make_ok(request_id, data={"jobs": jobs.list()})
    job_id = args.get("id")
    if not job_id:
        return make_error(request_id, "BAD_ARGUMENT", "precheck", "需要 id", next="先 action=list")
    if action == "status":
        try:
            return make_ok(request_id, data=jobs.status(job_id))
        except KeyError:
            return make_error(request_id, "JOB_NOT_FOUND", "bridge", "未知 job：%s" % job_id)
    if action == "cancel":
        return make_ok(request_id, data={"cancelled": jobs.cancel(job_id)})
    return make_error(
        request_id, "BAD_ARGUMENT", "precheck", "action 只能是 status|cancel|list"
    )


HANDLERS["job"] = handle_job
