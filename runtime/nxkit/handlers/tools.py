"""Local handlers for part/exec/api/exp/mold tools."""

from ..plan import run_plan
from ..result import make_error, make_ok
from ..verify import assert_holds


def _error_with_data(request_id, code, stage, msg, data, next=None, hint_tool=None):
    envelope = make_error(request_id, code, stage, msg, next=next, hint_tool=hint_tool)
    envelope["data"] = data
    return envelope


def handle_snapshot(router, args, request_id):
    store = getattr(router, "snapshots", None)
    if store is None:
        return make_error(request_id, "SNAPSHOT_UNAVAILABLE", "bridge", "快照存储未配置")
    action = args.get("action")
    if action == "list":
        return make_ok(request_id, data={"snapshots": store.list()})
    if action == "save":
        path = args.get("path") or router.current_part_path
        if not path:
            return make_error(
                request_id,
                "BAD_ARGUMENT",
                "precheck",
                "save 需要 path（当前 .prt 路径）",
                next="传 path=<当前件绝对路径>",
            )
        snapshot_id = store.save(path, note=args.get("note") or "")
        return make_ok(request_id, data={"id": snapshot_id, "snapshots": store.list()})
    if action == "restore":
        try:
            restored = store.restore(args.get("id"), args.get("to"))
        except Exception as exc:
            return make_error(
                request_id,
                "SNAPSHOT_RESTORE_FAILED",
                "bridge",
                str(exc),
                next="先关闭 NX 里正开着的件，或传 to=<新路径>",
            )
        return make_ok(request_id, data={"restored": str(restored)})
    return make_error(request_id, "BAD_ARGUMENT", "precheck", "action 只能是 save|list|restore")


def handle_check(router, args, request_id):
    precheck = getattr(router, "precheck", None)
    if precheck is None:
        return make_error(request_id, "PRECHECK_UNAVAILABLE", "bridge", "预检器未配置")
    issues = precheck.check(args.get("code") or "", args.get("target_ver") or "nx2512")
    items = [
        {"code": issue.code, "msg": issue.msg, "node": issue.node, "next": issue.next}
        for issue in issues
    ]
    return make_ok(request_id, data={"pass": not items, "issues": items})


def handle_plan(router, args, request_id):
    store = getattr(router, "snapshots", None)
    if store is None:
        return make_error(request_id, "SNAPSHOT_UNAVAILABLE", "bridge", "快照存储未配置")
    result = run_plan(router, args.get("steps") or [], store, args["part"])
    if result["ok"]:
        return make_ok(request_id, data=result)
    return _error_with_data(
        request_id,
        "PLAN_FAILED",
        "rollback",
        "计划第 %s 步失败" % (result["error"].get("code") if result.get("error") else "?"),
        result,
        next="已回到计划起点快照；读 steps 定位失败步骤",
        hint_tool="nx_inspect",
    )


def handle_assert(router, args, request_id):
    result = assert_holds(args.get("spec") or {}, args.get("facts") or {})
    if result["pass"]:
        return make_ok(request_id, data=result)
    return _error_with_data(
        request_id,
        "ASSERT_FAILED",
        "verify",
        "实测与期望不符：got=%r expect=%r" % (result.get("got"), result.get("expect")),
        result,
        next="重新量测或改模型；不许把不达标当完成",
        hint_tool="nx_measure",
    )


def handle_batch(router, args, request_id):
    runner = getattr(router, "headless", None)
    if runner is None:
        return make_error(request_id, "BATCH_UNAVAILABLE", "bridge", "无头执行器未配置")
    result = runner.run(
        {"steps": args.get("steps") or []},
        timeout_s=float(args.get("timeout_s") or 600.0),
    )
    if result["ok"]:
        return make_ok(request_id, data=result)
    return _error_with_data(
        request_id,
        "BATCH_FAILED",
        "bridge",
        "无头执行失败：%s" % (result.get("error") or "unknown"),
        result,
        next="看 log 与 markers；超时任务已被杀进程树",
    )


def handle_template(router, args, request_id):
    store = getattr(router, "templates", None)
    if store is None:
        return make_error(request_id, "TEMPLATE_UNAVAILABLE", "bridge", "模板库未配置（T13）")
    action = args.get("action")
    if action == "list":
        return make_ok(request_id, data={"templates": store.list()})
    if action == "apply":
        try:
            result = store.apply(args.get("name"), args.get("params") or {})
        except Exception as exc:
            return make_error(request_id, "TEMPLATE_PARAM_ERROR", "precheck", str(exc))
        return make_ok(request_id, data=result)
    return make_error(request_id, "BAD_ARGUMENT", "precheck", "action 只能是 list|apply")


def handle_api(router, args, request_id):
    kb = getattr(router, "kb", None)
    if kb is None:
        return make_error(
            request_id,
            "KB_NOT_READY",
            "bridge",
            "API 知识库尚未构建（T14）",
            next="先跑 nx_api 构建索引，或 nx_run_python 用 dir() 确认",
        )
    hits = kb.search(
        args.get("q") or "", src=args.get("src") or "all", k=int(args.get("k") or 8)
    )
    return make_ok(request_id, data={"items": hits})


def handle_exp(router, args, request_id):
    library = router.library
    action = args.get("action")
    if action == "get":
        entry = library.get(args.get("id"))
        if entry is None:
            return make_error(request_id, "ENTRY_NOT_FOUND", "bridge", "经验条目不存在：%s" % args.get("id"))
        library.bump_usage(entry["id"], None)
        return make_ok(request_id, data=entry)
    if action == "save":
        try:
            result = library.save(args.get("entry") or {})
        except Exception as exc:
            return make_error(request_id, "ENTRY_INVALID", "precheck", str(exc))
        return make_ok(request_id, data={"saved": result})
    if action == "replay":
        entry = library.get(args.get("id"))
        if entry is None:
            return make_error(request_id, "ENTRY_NOT_FOUND", "bridge", "经验条目不存在：%s" % args.get("id"))
        library.bump_usage(entry["id"], None)
        return make_ok(request_id, data={"id": entry["id"], "impl": entry.get("impl"), "evidence": entry.get("evidence")})
    if action == "export":
        try:
            count = library.export_pack(args.get("path"))
        except Exception as exc:
            return make_error(request_id, "PACK_EXPORT_FAILED", "bridge", str(exc))
        return make_ok(request_id, data={"exported": count, "path": args.get("path")})
    if action == "import":
        try:
            count = library.import_pack(args.get("path"))
        except Exception as exc:
            return make_error(request_id, "PACK_IMPORT_FAILED", "bridge", str(exc))
        return make_ok(request_id, data={"imported": count})
    return make_error(
        request_id, "BAD_ARGUMENT", "precheck", "action 只能是 get|save|replay|export|import"
    )


HANDLERS = {
    "snapshot": handle_snapshot,
    "check": handle_check,
    "plan": handle_plan,
    "assert": handle_assert,
    "batch": handle_batch,
    "template": handle_template,
    "api": handle_api,
    "exp": handle_exp,
}
