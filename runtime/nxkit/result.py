"""Uniform result envelope shared by every tool.

Contract: contract/schemas/result.schema.json. `stage` is one of precheck,
bridge, nx, verify, rollback; error codes are prefixed by their stage. A
geometry-changing success must carry `verify` with what/expect/got/tol/evidence
where evidence comes from NX measurements only.
"""

STAGES = ("precheck", "bridge", "nx", "verify", "rollback")


def make_ok(request_id: str, data=None, verify=None, elapsed_ms=None, job=None) -> dict:
    return {
        "ok": True,
        "request_id": request_id,
        "data": data,
        "verify": verify,
        "error": None,
        "job": job,
        "elapsed_ms": elapsed_ms,
    }


def make_error(
    request_id: str,
    code: str,
    stage: str,
    msg: str,
    next: str | None = None,
    hint_tool: str | None = None,
    elapsed_ms=None,
    job=None,
) -> dict:
    if stage not in STAGES:
        raise ValueError("stage must be one of %s, got %r" % (", ".join(STAGES), stage))
    return {
        "ok": False,
        "request_id": request_id,
        "data": None,
        "verify": None,
        "error": {
            "code": code,
            "stage": stage,
            "msg": msg,
            "next": next,
            "hint_tool": hint_tool,
        },
        "job": job,
        "elapsed_ms": elapsed_ms,
    }
