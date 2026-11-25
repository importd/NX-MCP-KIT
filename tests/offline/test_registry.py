import json

import pytest

from nxkit.registry import ContractError, Registry


def test_meta_tools_load(contract_dir):
    reg = Registry(contract_dir)
    meta = [t for t in reg.tools.values() if t.group == "meta"]
    assert {t.name for t in meta} == {
        "nx_status",
        "nx_find",
        "nx_help",
        "nx_call",
        "nx_job",
        "exp_search",
    }
    assert all(t.flags.get("always") for t in meta)


def test_expose_catalog_only_always(contract_dir):
    reg = Registry(contract_dir)
    always = {t.name for t in reg.tools.values() if t.flags.get("always")}
    assert always == {
        "nx_status",
        "nx_find",
        "nx_help",
        "nx_call",
        "nx_job",
        "exp_search",
    }
    assert {t["name"] for t in reg.list("catalog")} == always


def test_nx_routed_tools_expose_session_args(contract_dir):
    reg = Registry(contract_dir)
    nx_tools = [t for t in reg.tools.values() if t.route.get("kind") == "nx"]
    assert nx_tools
    for tool in nx_tools:
        props = tool.schema["properties"]
        assert props["pid"]["type"] == "integer", tool.name
        assert props["timeout_s"]["type"] == "number", tool.name


def test_local_tools_do_not_get_session_args(contract_dir):
    props = Registry(contract_dir).tools["nx_find"].schema["properties"]
    assert "pid" not in props
    assert "timeout_s" not in props


def test_duplicate_tool_name_raises(contract_dir, workdir):
    dst = workdir / "contract"
    (dst / "tools").mkdir(parents=True)
    data = json.loads((contract_dir / "tools" / "meta.json").read_text(encoding="utf-8"))
    data["tools"].append(dict(data["tools"][0]))
    (dst / "tools" / "meta.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ContractError):
        Registry(dst)
