import os
import sys
import types
from pathlib import Path

import nxstub

REPO = Path(__file__).resolve().parents[2]


def _load_paths():
    nxstub.install()
    sys.path.insert(0, str(REPO / "bridge"))
    for name in list(sys.modules):
        if name == "commands" or name.startswith("commands."):
            del sys.modules[name]
    from commands import paths

    return paths


def test_bridge_io_lives_next_to_root_not_bridge_folder():
    paths = _load_paths()
    try:
        resolved = paths.default_io(os.path.join("C:", "kit", "bridge"), 8016)
        assert resolved == os.path.join("C:", "kit", "io", "8016")
        assert "bridge" not in resolved.split(os.sep)
    finally:
        sys.path.remove(str(REPO / "bridge"))


def test_startup_uses_shared_path_rule():
    source = (REPO / "bridge" / "startup" / "nx_agent_kit.py").read_text(encoding="utf-8")
    assert "default_io" in source
    assert "NXKIT_IO" in source
    assert 'encoding="utf-8"' in source
