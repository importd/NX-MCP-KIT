import pytest

from nxkit.registry import Registry
from nxkit.templates import TemplateError, TemplateParamError, TemplateStore


def test_list_returns_mold_templates(contract_dir):
    templates = TemplateStore(contract_dir).list()
    assert {template["id"] for template in templates} == {"T001", "T002"}
    assert {template["name"] for template in templates} == {"模架", "圆形镶件"}


def test_apply_substitutes_typed_params(contract_dir):
    plan = TemplateStore(contract_dir).apply("圆形镶件", {"d": 60, "h": 40})
    assert plan["template"] == "T002"
    first = plan["steps"][0]
    assert first["tool"] == "nx_block"
    assert first["args"]["length"] == 60
    assert first["args"]["width"] == 60
    assert first["args"]["height"] == 40


def test_apply_uses_defaults(contract_dir):
    plan = TemplateStore(contract_dir).apply("圆形镶件", {})
    first = plan["steps"][0]
    assert first["args"]["length"] == 60


def test_apply_rejects_out_of_range(contract_dir):
    with pytest.raises(TemplateParamError):
        TemplateStore(contract_dir).apply("圆形镶件", {"d": 5, "h": 40})


def test_apply_rejects_unknown_param(contract_dir):
    with pytest.raises(TemplateParamError):
        TemplateStore(contract_dir).apply("圆形镶件", {"diameter": 60})


def test_unknown_template_raises(contract_dir):
    with pytest.raises(TemplateError):
        TemplateStore(contract_dir).apply("不存在的模板", {})


def test_template_steps_only_reference_known_tools(contract_dir):
    registry = Registry(contract_dir)
    store = TemplateStore(contract_dir)
    for template in store.list():
        for step in template["steps"]:
            assert step["tool"] in registry.tools, (template["id"], step["tool"])
