"""Data-driven mold templates: parameter schema + steps + asserts.

A template is a JSON contract (id/name/params/steps/asserts); apply validates
params and substitutes {{name}} placeholders, returning a step list the agent
runs through nx_plan or nx_template itself.
"""

import copy
import json
import re
from pathlib import Path

_PLACEHOLDER = re.compile(r"^\{\{(\w+)\}\}$")
_ANY_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


class TemplateError(Exception):
    pass


class TemplateParamError(TemplateError):
    pass


class TemplateStore:
    def __init__(self, contract_dir):
        self.dir = Path(contract_dir) / "templates"
        self._templates = []
        if self.dir.is_dir():
            for path in sorted(self.dir.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(data, dict) and data.get("name"):
                    self._templates.append(data)

    def list(self):
        return [copy.deepcopy(template) for template in self._templates]

    def _find(self, name):
        for template in self._templates:
            if template.get("name") == name or template.get("id") == name:
                return template
        return None

    def apply(self, name, params):
        template = self._find(name)
        if template is None:
            raise TemplateError("unknown template: %s" % name)
        params = dict(params or {})
        resolved = {}
        for spec in template.get("params", []):
            key = spec["n"]
            if key in params:
                value = params.pop(key)
                if spec.get("type") == "number":
                    if not isinstance(value, (int, float)) or isinstance(value, bool):
                        raise TemplateParamError("参数 %s 必须是数字" % key)
                    low, high = spec.get("min"), spec.get("max")
                    if low is not None and value < low:
                        raise TemplateParamError("参数 %s=%r 小于下限 %r" % (key, value, low))
                    if high is not None and value > high:
                        raise TemplateParamError("参数 %s=%r 大于上限 %r" % (key, value, high))
                resolved[key] = value
            elif "default" in spec:
                resolved[key] = spec["default"]
            else:
                raise TemplateParamError("缺少参数 %s" % key)
        if params:
            raise TemplateParamError(
                "模板 %s 不认识的参数：%s" % (name, ",".join(sorted(params)))
            )
        return {
            "template": template.get("id"),
            "name": template["name"],
            "steps": self._substitute(template.get("steps", []), resolved),
            "asserts": self._substitute(template.get("asserts", []), resolved),
        }

    def _substitute(self, value, resolved):
        if isinstance(value, str):
            exact = _PLACEHOLDER.match(value)
            if exact:
                return resolved.get(exact.group(1), value)
            return _ANY_PLACEHOLDER.sub(
                lambda match: str(resolved.get(match.group(1), match.group(0))), value
            )
        if isinstance(value, list):
            return [self._substitute(item, resolved) for item in value]
        if isinstance(value, dict):
            return {key: self._substitute(item, resolved) for key, item in value.items()}
        return value
