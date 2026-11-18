import json

from nxkit.library.store import Library


def _entry(**overrides) -> dict:
    base = {
        "id": "M0001",
        "c": "招式",
        "t": "按选择器批量倒角",
        "k": ["倒角", "chamfer"],
        "general": "用 width=1.0 的 chamfer 批处理选中边",
        "impl": [{"tool": "nx_chamfer", "params": {"target": "last", "width": 1.0}}],
        "evidence": {"expect": 2.0, "got": 2.0, "tol": 0.01},
    }
    base.update(overrides)
    return base


def test_chinese_search(workdir):
    lib = Library(workdir)
    lib.init()
    assert lib.save(_entry()) == "M0001"
    hits = lib.search("倒角")
    assert [hit["id"] for hit in hits] == ["M0001"]
    assert hits[0]["t"] == "按选择器批量倒角"


def test_ascii_keyword_search(workdir):
    lib = Library(workdir)
    lib.init()
    lib.save(_entry())
    assert [hit["id"] for hit in lib.search("chamfer")] == ["M0001"]


def test_unverified_entry_goes_to_drafts(workdir):
    lib = Library(workdir)
    lib.init()
    entry = _entry(id="M0002", evidence={"expect": 2.0, "got": 2.4, "tol": 0.01})
    assert lib.save(entry).startswith("draft:")
    assert lib.search("批量倒角") == []
    assert (workdir / "_drafts" / "M0002.json").is_file()


def test_get_and_usage(workdir):
    lib = Library(workdir)
    lib.init()
    lib.save(_entry())
    stored = lib.get("M0001")
    assert stored["t"] == "按选择器批量倒角"
    assert stored["usage"]["count"] == 0
    lib.bump_usage("M0001", ok=True)
    lib.bump_usage("M0001", ok=False)
    usage = lib.get("M0001")["usage"]
    assert usage["count"] == 2
    assert usage["success"] == 1
    assert usage["fail"] == 1


def test_single_char_query_matches_bigram_entry(workdir):
    lib = Library(workdir)
    lib.init()
    lib.save(_entry(id="M0009", t="钻孔工艺", k=["钻孔"], evidence={"expect": 1.0, "got": 1.0, "tol": 0.01}))
    assert [hit["id"] for hit in lib.search("孔")] == ["M0009"]


def test_pack_export_import(workdir):
    lib = Library(workdir / "lib1")
    lib.init()
    lib.save(_entry())
    lib.save(_entry(id="M0003", t="圆角半径批量修改", k=["圆角", "fillet"]))

    pack = workdir / "moves.zip"
    assert lib.export_pack(pack) == 2

    other = Library(workdir / "lib2")
    other.init()
    assert other.import_pack(pack) == 2
    assert [hit["id"] for hit in other.search("圆角")] == ["M0003"]
