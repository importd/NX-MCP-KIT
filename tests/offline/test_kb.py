from pathlib import Path

from nxkit.kb.build import KbBuilder
from nxkit.kb.search import Kb

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "nx10"


def _build(workdir):
    db_path = workdir / "nxopen.db"
    stats = KbBuilder(FIXTURE).build(db_path)
    return Kb(db_path), stats


def test_build_indexes_xml_and_pyi(workdir):
    kb, stats = _build(workdir)
    assert stats["members"] >= 3
    assert stats["indexed_py"] >= 2


def test_search_by_short_name(workdir):
    kb, _ = _build(workdir)
    hits = kb.search("ExtrudeBuilder")
    assert hits
    assert hits[0]["name"].endswith("ExtrudeBuilder")
    assert hits[0]["py"] == "NXOpen.Features.ExtrudeBuilder"


def test_search_is_case_insensitive(workdir):
    kb, _ = _build(workdir)
    assert kb.search("extrudebuilder")


def test_license_extracted(workdir):
    kb, _ = _build(workdir)
    hits = kb.search("cam_base")
    assert hits
    assert hits[0]["lic"] == "CAM BASE"


def test_src_filter_pyi_only(workdir):
    kb, _ = _build(workdir)
    hits = kb.search("ExtrudeBuilder", src="pyi")
    assert hits
    assert all(hit["source"] == "pyi" for hit in hits)
    xml_hits = kb.search("ExtrudeBuilder", src="xml")
    assert xml_hits
    assert all(hit["source"] == "xml" for hit in xml_hits)


def test_empty_query_returns_empty(workdir):
    kb, _ = _build(workdir)
    assert kb.search("   ") == []
