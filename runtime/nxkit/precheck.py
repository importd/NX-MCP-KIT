"""Static precheck before sending code into NX.

Two jobs: (1) reject syntax that the target NX's embedded Python cannot parse
(NX10 ships Python 3.3.2 -> no f-strings, walrus, annotations); (2) catch
Builder lifecycle mistakes (Commit/Destroy) that NX reports late and vaguely.
"""

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

SYNTAX_BY_NX = {
    "nx10": "3.3",
    "nx12": "3.6",
    "nx2412": "3.10",
    "nx2512": "3.12",
}

_BUILDER_CREATE = re.compile(r"Create\w*Builder\s*\(")
_COMMIT = re.compile(r"\.Commit\s*\(")
_DESTROY = re.compile(r"\.Destroy\s*\(")


@dataclass
class Issue:
    code: str
    msg: str
    node: str | None = None
    next: str | None = None
    hint_tool: str | None = None


class Precheck:
    def __init__(self, contract_dir: Path):
        self.contract_dir = Path(contract_dir)
        self.rules = {}
        rules_path = self.contract_dir / "rules" / "py33.json"
        if rules_path.is_file():
            try:
                self.rules = json.loads(rules_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.rules = {}

    def check(self, code: str, target_ver: str = "nx2512") -> list[Issue]:
        issues: list[Issue] = []
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return [
                Issue(
                    "PY_SYNTAX",
                    "Python 语法错误：%s" % exc.msg,
                    node="line %s" % exc.lineno,
                    next="修语法后重试；NX10 只支持 Python 3.3 语法",
                    hint_tool="nx_check",
                )
            ]

        if SYNTAX_BY_NX.get(target_ver, "3.12") == "3.3":
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr):
                    issues.append(
                        Issue(
                            "PY33_FSTRING",
                            "NX10 的 Python 3.3 不支持 f-string",
                            node="line %s" % getattr(node, "lineno", "?"),
                            next='改成 "…".format(...) 或字符串拼接',
                            hint_tool="nx_check",
                        )
                    )
                elif isinstance(node, ast.NamedExpr):
                    issues.append(
                        Issue(
                            "PY33_WALRUS",
                            "NX10 的 Python 3.3 不支持海象运算符 :=",
                            node="line %s" % getattr(node, "lineno", "?"),
                            next="改成先赋值再判断",
                            hint_tool="nx_check",
                        )
                    )
                elif isinstance(node, ast.AnnAssign):
                    issues.append(
                        Issue(
                            "PY33_ANNOTATION",
                            "NX10 的 Python 3.3 不支持变量注解",
                            node="line %s" % getattr(node, "lineno", "?"),
                            next="去掉类型注解，用普通赋值",
                            hint_tool="nx_check",
                        )
                    )

        if _BUILDER_CREATE.search(code):
            if not _COMMIT.search(code):
                issues.append(
                    Issue(
                        "BUILDER_NO_COMMIT",
                        "创建了 Builder 但没有 Commit()，特征不会生成",
                        next="在设置完参数后调用 builder.Commit()",
                        hint_tool="nx_api",
                    )
                )
            elif not _DESTROY.search(code):
                issues.append(
                    Issue(
                        "BUILDER_NO_DESTROY",
                        "Builder 没有 Destroy()，会泄漏 NX 资源",
                        next="Commit() 之后调用 builder.Destroy()",
                        hint_tool="nx_api",
                    )
                )
        return issues
