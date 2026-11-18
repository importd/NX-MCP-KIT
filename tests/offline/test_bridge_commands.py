import sys
import types
from pathlib import Path

import pytest

import nxstub

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "bridge"


class FakeBody:
    JournalIdentifier = "BLOCK(0)"

    def GetFaces(self):
        return [object(), object(), object()]

    def GetEdges(self):
        return [object()] * 12


class FakeFeature:
    JournalIdentifier = "BLOCK(0)"
    FeatureType = "Block"

    def GetBodies(self):
        return [FakeBody()]


class FakeBuilder:
    def __init__(self):
        self.origin = None
        self.lengths = None
        self.committed = False
        self.destroyed = False

    def SetOriginAndLengths(self, origin, length, width, height):
        self.origin = (origin.X, origin.Y, origin.Z)
        self.lengths = (length, width, height)

    def CommitFeature(self):
        self.committed = True
        return FakeFeature()

    def Destroy(self):
        self.destroyed = True


class FakeWorkPart:
    def __init__(self):
        self.builder = None
        self.Bodies = [FakeBody()]
        self.Features = types.SimpleNamespace(CreateBlockFeatureBuilder=self._create)

    def _create(self, null_feature):
        self.builder = FakeBuilder()
        return self.builder


class FakeSt:
    def __init__(self):
        self.marks = []
        self.work_part = FakeWorkPart()
        self.session = types.SimpleNamespace(Parts=types.SimpleNamespace(Work=self.work_part))
        self.uf = types.SimpleNamespace()

    def undo_mark(self, name):
        self.marks.append(name)

    def facts(self, body):
        return {"bbox": [0.0, 0.0, 0.0, 10.0, 10.0, 10.0], "volume": 1000.0, "faces": 3}


def _install_nxopen_stub():
    nxstub.install()


@pytest.fixture
def commands():
    nxstub.install()
    sys.path.insert(0, str(BRIDGE))
    for name in list(sys.modules):
        if name == "commands" or name.startswith("commands."):
            del sys.modules[name]
    import commands

    yield commands
    sys.path.remove(str(BRIDGE))


def test_create_block_commits_destroys_and_measures(commands):
    st = FakeSt()
    result = commands.handle(
        st, "nx_block", {"x": 0, "y": 0, "z": 0, "length": 10, "width": 10, "height": 10}
    )
    assert result["data"]["feature"] == "BLOCK(0)"
    assert result["facts"]["volume"] == 1000.0
    assert st.work_part.builder.lengths == ("10", "10", "10")
    assert st.work_part.builder.committed is True
    assert st.work_part.builder.destroyed is True
    assert st.marks == ["nx_block"]


def test_unknown_command_is_reported_not_raised(commands):
    result = commands.handle(FakeSt(), "nx_nope", {})
    assert result["error"]["code"] == "BRIDGE_UNKNOWN_COMMAND"


def test_missing_argument_is_wrapped(commands):
    result = commands.handle(FakeSt(), "nx_block", {"x": 0})
    assert result["error"]["code"] == "BRIDGE_EXCEPTION"


def test_inspect_lists_bodies_with_facts(commands):
    result = commands.handle(FakeSt(), "nx_inspect", {})
    body = result["data"]["bodies"][0]
    assert body["id"] == "BLOCK(0)"
    assert body["facts"]["volume"] == 1000.0


def test_measure_returns_facts(commands):
    result = commands.handle(FakeSt(), "nx_measure", {"target": "last"})
    assert result["facts"]["bbox"][3] == 10.0
