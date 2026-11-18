from nxkit.plan import run_plan
from nxkit.snapshot import SnapshotStore


def _part(workdir):
    path = workdir / "E-0021.prt"
    path.write_text("v1", encoding="utf-8")
    return path


def test_snapshot_save_list_restore(workdir):
    part = _part(workdir)
    store = SnapshotStore(workdir / "snapshots")
    snapshot_id = store.save(part, note="改前")
    assert part.read_text(encoding="utf-8") == "v1"
    entries = store.list()
    assert entries[0]["id"] == snapshot_id
    assert entries[0]["source"] == str(part)

    part.write_text("v2", encoding="utf-8")
    restored = store.restore(snapshot_id)
    assert restored.read_text(encoding="utf-8") == "v1"


def test_restore_to_new_path_keeps_original(workdir):
    part = _part(workdir)
    store = SnapshotStore(workdir / "snapshots")
    snapshot_id = store.save(part)
    part.write_text("v2", encoding="utf-8")
    copy = workdir / "copy.prt"
    store.restore(snapshot_id, to=copy)
    assert copy.read_text(encoding="utf-8") == "v1"
    assert part.read_text(encoding="utf-8") == "v2"


def test_plan_rolls_back_on_failure(workdir):
    part = _part(workdir)
    store = SnapshotStore(workdir / "snapshots")
    seen = []

    class FakeRouter:
        def call(self, name, args):
            seen.append(name)
            if name == "nx_hole":
                return {"ok": False, "error": {"code": "NX_BOOL_EMPTY", "stage": "nx", "msg": "布尔不相交"}}
            part.write_text("v2", encoding="utf-8")
            return {"ok": True, "data": {}}

    result = run_plan(
        FakeRouter(),
        [
            {"tool": "nx_block", "args": {}},
            {"tool": "nx_hole", "args": {}},
        ],
        store,
        part,
    )
    assert seen == ["nx_block", "nx_hole"]
    assert result["ok"] is False
    assert result["rollback"]["restored"] is True
    assert part.read_text(encoding="utf-8") == "v1"


def test_plan_success_keeps_snapshot(workdir):
    part = _part(workdir)
    store = SnapshotStore(workdir / "snapshots")

    class FakeRouter:
        def call(self, name, args):
            return {"ok": True, "data": {}}

    result = run_plan(FakeRouter(), [{"tool": "nx_block", "args": {}}], store, part)
    assert result["ok"] is True
    assert result["rollback"] is None
    assert result["snapshot"] == store.list()[0]["id"]
