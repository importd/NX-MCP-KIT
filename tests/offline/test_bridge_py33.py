"""Every bridge file must stay parsable by NX10's embedded Python 3.3."""

import ast
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[2] / "bridge"


def _parse_py33(src: str):
    try:
        return ast.parse(src, feature_version=(3, 3))
    except ValueError:
        return ast.parse(src, feature_version=(3, 4))


def test_bridge_files_are_py33_syntax():
    files = sorted(BRIDGE.rglob("*.py"))
    assert files, "no bridge files found"
    for path in files:
        src = path.read_text(encoding="utf-8")
        try:
            tree = _parse_py33(src)
        except SyntaxError as exc:
            raise AssertionError("%s is not Python 3.3 parsable: %s" % (path, exc))
        for node in ast.walk(tree):
            assert not isinstance(node, ast.JoinedStr), "%s uses f-string" % path
            assert not isinstance(node, ast.NamedExpr), "%s uses walrus :=" % path
            assert not isinstance(node, ast.AnnAssign), "%s uses variable annotation" % path
            if isinstance(node, ast.FunctionDef):
                assert node.returns is None, "%s has return annotation" % path
                for arg in list(node.args.args) + list(node.args.kwonlyargs):
                    assert arg.annotation is None, "%s has arg annotation" % path
