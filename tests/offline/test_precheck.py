from nxkit.precheck import Precheck


def test_fstring_rejected_for_nx10(contract_dir):
    issues = Precheck(contract_dir).check('print(f"{1}")', target_ver="nx10")
    assert [issue.code for issue in issues] == ["PY33_FSTRING"]


def test_fstring_allowed_on_2512(contract_dir):
    assert Precheck(contract_dir).check('print(f"{1}")', target_ver="nx2512") == []


def test_walrus_rejected_for_nx10(contract_dir):
    issues = Precheck(contract_dir).check("if (n := 1):\n    pass", target_ver="nx10")
    assert [issue.code for issue in issues] == ["PY33_WALRUS"]


def test_annotation_rejected_for_nx10(contract_dir):
    issues = Precheck(contract_dir).check("x: int = 1", target_ver="nx10")
    assert [issue.code for issue in issues] == ["PY33_ANNOTATION"]


def test_missing_commit_detected(contract_dir):
    code = "b = wp.Features.CreateBlockBuilder(None)\nb.SetLength(1)"
    issues = Precheck(contract_dir).check(code)
    assert [issue.code for issue in issues] == ["BUILDER_NO_COMMIT"]


def test_missing_destroy_detected(contract_dir):
    code = "b = wp.Features.CreateBlockBuilder(None)\nb.Commit()"
    issues = Precheck(contract_dir).check(code)
    assert [issue.code for issue in issues] == ["BUILDER_NO_DESTROY"]


def test_valid_code_passes(contract_dir):
    code = (
        "b = wp.Features.CreateBlockBuilder(None)\n"
        "b.Commit()\n"
        "b.Destroy()\n"
    )
    assert Precheck(contract_dir).check(code) == []


def test_syntax_error_reported(contract_dir):
    issues = Precheck(contract_dir).check("def f(:")
    assert [issue.code for issue in issues] == ["PY_SYNTAX"]
    assert issues[0].next
