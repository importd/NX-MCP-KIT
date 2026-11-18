import pytest

from nxkit.result import make_error, make_ok
from nxkit.verify import assert_holds, build_verify


def test_error_envelope_shape():
    envelope = make_error(
        "r1",
        "NX_BOOL_EMPTY",
        "nx",
        "布尔不相交",
        next="检查两体是否相交",
        hint_tool="nx_inspect",
    )
    assert envelope["ok"] is False
    assert envelope["request_id"] == "r1"
    assert envelope["data"] is None
    assert envelope["verify"] is None
    assert envelope["error"] == {
        "code": "NX_BOOL_EMPTY",
        "stage": "nx",
        "msg": "布尔不相交",
        "next": "检查两体是否相交",
        "hint_tool": "nx_inspect",
    }


def test_ok_envelope_shape():
    envelope = make_ok("r2", {"feature": "BLOCK(0)"}, verify={"what": "volume", "got": 1.0})
    assert envelope["ok"] is True
    assert envelope["error"] is None
    assert envelope["data"] == {"feature": "BLOCK(0)"}


def test_invalid_stage_rejected():
    with pytest.raises(ValueError):
        make_error("r3", "X", "not-a-stage", "bad stage")


def test_verify_within_tolerance():
    verify = build_verify({"volume": 1000.0}, {"volume": 1000.2}, 0.5, "volume")
    assert verify["pass"] is True
    assert verify["delta"] == pytest.approx(0.2)
    assert verify["what"] == "volume"
    assert verify["evidence"]


def test_verify_outside_tolerance():
    verify = build_verify({"volume": 1000.0}, {"volume": 1001.0}, 0.5, "volume")
    assert verify["pass"] is False


def test_verify_missing_measure():
    verify = build_verify({}, {"volume": 1.0}, 0.1, "volume")
    assert verify["pass"] is False
    assert verify["got"] is None
    assert verify["error"]["code"] == "VERIFY_NO_MEASURE"


def test_assert_geom_mismatch():
    spec = {"kind": "geom", "measure": {"type": "volume"}, "expect": {"value": 1000, "tol": 0.1}}
    result = assert_holds(spec, {"volume": 900})
    assert result["pass"] is False
    assert result["got"] == 900
    assert result["expect"] == 1000
    assert result["delta"] == pytest.approx(100.0)


def test_assert_missing_measure():
    spec = {"kind": "geom", "measure": {"type": "volume"}, "expect": {"value": 1, "tol": 0.1}}
    result = assert_holds(spec, {})
    assert result["pass"] is False
    assert result["got"] is None
    assert result["error"]["code"] == "VERIFY_NO_MEASURE"


def test_assert_within_tolerance():
    spec = {"kind": "pos", "measure": {"type": "distance"}, "expect": {"value": 50, "tol": 0.05}}
    assert assert_holds(spec, {"distance": 50.01})["pass"] is True
