import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RUNTIME = REPO / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

# The DSH sandbox denies both pytest's 0o700 temp root and directories created
# by tempfile.mkdtemp (WinError 5 on Windows). Plain pathlib.mkdir under the
# repo works, so tests get their own directory here.
_TMP_ROOT = REPO / ".pytest-tmp"


@pytest.fixture
def workdir():
    _TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = _TMP_ROOT / ("w-" + uuid.uuid4().hex[:12])
    path.mkdir()
    yield path


@pytest.fixture
def contract_dir() -> Path:
    return REPO / "contract"
