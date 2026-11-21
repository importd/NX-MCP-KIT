import os
from pathlib import Path

from nxkit.headless import HeadlessRunner, find_nx_root


def _make_nx(root):
    ugii = Path(root) / "UGII"
    ugii.mkdir(parents=True)
    (ugii / "run_journal.exe").write_bytes(b"")


def test_find_nx_root_uses_env(tmp_path, monkeypatch):
    root = tmp_path / "NX 10.0"
    _make_nx(root)
    monkeypatch.setenv("NXKIT_NX_ROOT", str(root))
    assert find_nx_root() == str(root)
    assert HeadlessRunner(plan_dir=tmp_path / "plans").nx_root == root


def test_find_nx_root_scans_known_parents(tmp_path, monkeypatch):
    monkeypatch.delenv("NXKIT_NX_ROOT", raising=False)
    monkeypatch.delenv("UGII_BASE_DIR", raising=False)
    parent = tmp_path / "Program Files" / "Siemens"
    _make_nx(parent / "NX 10.0")
    newest = parent / "DesigncenterNX2512"
    _make_nx(newest)
    monkeypatch.setattr("nxkit.headless._SEARCH_PARENTS", (str(parent),))
    assert find_nx_root() == str(newest)


def test_find_nx_root_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("NXKIT_NX_ROOT", raising=False)
    monkeypatch.delenv("UGII_BASE_DIR", raising=False)
    monkeypatch.setattr("nxkit.headless._SEARCH_PARENTS", (str(tmp_path / "empty"),))
    assert find_nx_root() is None
