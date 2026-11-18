"""Multi-step plans with a transaction boundary at the starting snapshot.

A plan takes a snapshot before the first step; if any step fails, the part is
restored to that snapshot and the error is returned. Tool calls still go
through the Router, so gate/precheck/verify semantics are unchanged.
"""


def run_plan(router, steps, snapshot_store, part_path) -> dict:
    snapshot_id = snapshot_store.save(part_path, note="plan:before")
    results = []
    for index, step in enumerate(steps or []):
        tool = step.get("tool")
        args = dict(step.get("args") or {})
        envelope = router.call(tool, args)
        ok = bool(envelope.get("ok"))
        results.append(
            {
                "index": index,
                "tool": tool,
                "ok": ok,
                "error": envelope.get("error"),
            }
        )
        if not ok:
            restored = snapshot_store.restore(snapshot_id)
            return {
                "ok": False,
                "steps": results,
                "snapshot": snapshot_id,
                "rollback": {
                    "snapshot": snapshot_id,
                    "restored": True,
                    "to": str(restored),
                },
                "error": envelope.get("error"),
            }
    return {
        "ok": True,
        "steps": results,
        "snapshot": snapshot_id,
        "rollback": None,
        "error": None,
    }
