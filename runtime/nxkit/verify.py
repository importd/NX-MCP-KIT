"""Verification: compare NX-measured facts against expected values.

`build_verify` produces the `verify` block of a result envelope; `assert_holds`
evaluates one contract/assert entry (kind = geom | pos | rel). Tolerance is
absolute in the measure's unit (mm / mm3), matching the spec's "差值 ≤ tol".
"""


def build_verify(facts: dict, expect: dict | None, tol: float, what: str) -> dict:
    if not isinstance(facts, dict):
        raise TypeError("facts must be a dict")
    got = facts.get(what)
    expected = None if expect is None else expect.get(what)
    if got is None or expected is None:
        return {
            "what": what,
            "expect": expected,
            "got": got,
            "tol": tol,
            "delta": None,
            "pass": False,
            "facts": dict(facts),
            "evidence": None,
            "error": {
                "code": "VERIFY_NO_MEASURE",
                "msg": "measure %r missing (got=%r expect=%r)" % (what, got, expected),
            },
        }
    delta = abs(float(got) - float(expected))
    passed = delta <= float(tol)
    return {
        "what": what,
        "expect": expected,
        "got": got,
        "tol": tol,
        "delta": delta,
        "pass": passed,
        "facts": dict(facts),
        "evidence": "what=%s got=%s expect=%s tol=%s" % (what, got, expected, tol),
        "error": None,
    }


def assert_holds(spec: dict, facts: dict) -> dict:
    measure = spec.get("measure") or {}
    key = measure.get("type")
    expect = spec.get("expect") or {}
    tol = float(expect.get("tol", 0.0))
    value = expect.get("value")
    got = facts.get(key) if key else None
    base = {
        "kind": spec.get("kind"),
        "measure": key,
        "got": got,
        "expect": value,
        "tol": tol,
        "delta": None,
        "error": None,
    }
    if got is None:
        base["pass"] = False
        base["error"] = {
            "code": "VERIFY_NO_MEASURE",
            "msg": "measure %r missing from facts" % (key,),
        }
        return base
    delta = abs(float(got) - float(value))
    base["delta"] = delta
    base["pass"] = delta <= tol
    return base
