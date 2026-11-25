import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PWSH = shutil.which("pwsh") or shutil.which("powershell")


def _run(*args, env=None):
    assert PWSH, "no PowerShell found"
    return subprocess.run(
        [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
        + [str(arg) for arg in args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def test_probe_writes_matrix(workdir):
    nx_root = workdir / "NX 10.0"
    (nx_root / "NXBIN").mkdir(parents=True)
    (nx_root / "NXBIN" / "ugraf.exe").write_text("x", encoding="utf-8")
    (nx_root / "NXBIN" / "managed").mkdir()
    (nx_root / "NXBIN" / "managed" / "NXOpen.xml").write_text("<doc/>", encoding="utf-8")
    out = workdir / "matrix"

    result = _run(REPO / "deploy" / "probe.ps1", "-NxRoot", nx_root, "-OutDir", out)
    assert result.returncode == 0, result.stdout + result.stderr
    matrices = list(out.glob("*.json"))
    assert matrices, "probe wrote no matrix"
    data = json.loads(matrices[0].read_text(encoding="utf-8"))
    assert data["ugraf"].endswith("ugraf.exe")
    assert data["nx"]
    assert data["xml"] is True


def test_install_copies_bridge_and_writes_config(workdir):
    runtime_home = workdir / "runtime"
    result = _run(
        REPO / "deploy" / "install.ps1",
        "-RuntimeHome", runtime_home,
        "-PythonExe", "python.exe",
        "-NoNx",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (runtime_home / "bridge" / "startup" / "nx_agent_kit.py").is_file()
    assert (runtime_home / "runtime" / "nxkit" / "server.py").is_file()
    config = json.loads((runtime_home / "mcp_config.json").read_text(encoding="utf-8"))
    server = config["mcpServers"]["nx"]
    assert server["args"] == ["-m", "nxkit.server"]
    assert server["env"]["PYTHONPATH"].endswith("runtime")


def test_install_appends_custom_dirs_without_overwrite(workdir):
    custom_dirs = workdir / "custom_dirs.dat"
    custom_dirs.write_text("D:\\other_product\\\n", encoding="utf-8")
    runtime_home = workdir / "runtime"
    startup = workdir / "startup"
    result = _run(
        REPO / "deploy" / "install.ps1",
        "-RuntimeHome", runtime_home,
        "-StartupDir", startup,
        "-CustomDirsFile", custom_dirs,
        "-NoNx",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    text = custom_dirs.read_text(encoding="utf-8")
    assert text.startswith("D:\\other_product\\")
    assert text.count("D:\\other_product") == 1


def test_smoke_script_reports_no_session(workdir):
    io = workdir / "io"
    (io / "999").mkdir(parents=True)
    (io / "999" / "status.json").write_text(
        '{"pid": 999, "alive": true, "updated": 0}', encoding="utf-8"
    )
    result = _run(
        REPO / "deploy" / "smoke.ps1",
        "-RuntimeHome", REPO,
        "-IoDir", io,
        "-PythonExe", sys.executable,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "RESULT: FAIL:NO_SESSION" in result.stdout


def test_smoke_script_defaults_to_runtime_venv(workdir):
    if not (REPO / ".venv" / "Scripts" / "python.exe").is_file():
        pytest.skip("runtime .venv is not present")
    io = workdir / "io"
    (io / "999").mkdir(parents=True)
    (io / "999" / "status.json").write_text(
        '{"pid": 999, "alive": true, "updated": 0}', encoding="utf-8"
    )
    # Empty PATH: only the runtime's own .venv can satisfy the launcher.
    empty_bin = workdir / "bin"
    empty_bin.mkdir()
    env = os.environ.copy()
    env["PATH"] = str(empty_bin)
    result = _run(
        REPO / "deploy" / "smoke.ps1",
        "-RuntimeHome", REPO,
        "-IoDir", io,
        env=env,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "RESULT: FAIL:NO_SESSION" in result.stdout


def test_smoke_script_rejects_old_python(workdir):
    io = workdir / "io"
    io.mkdir()
    fake = workdir / "old-python.cmd"
    fake.write_text("@echo off\r\necho 3.9\r\n", encoding="utf-8")
    result = _run(
        REPO / "deploy" / "smoke.ps1",
        "-RuntimeHome", REPO,
        "-IoDir", io,
        "-PythonExe", fake,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "RESULT: FAIL:PYTHON_VERSION" in result.stdout


def test_smoke_script_reports_missing_python(workdir):
    io = workdir / "io"
    io.mkdir()
    result = _run(
        REPO / "deploy" / "smoke.ps1",
        "-RuntimeHome", REPO,
        "-IoDir", io,
        "-PythonExe", workdir / "no-such-python.exe",
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "RESULT: FAIL:PYTHON" in result.stdout


def test_sync_check_detects_drift(workdir):
    source = workdir / "src"
    target = workdir / "dst"
    source.mkdir()
    target.mkdir()
    (source / "x.ps1").write_text("a", encoding="utf-8")
    (target / "x.ps1").write_text("b", encoding="utf-8")

    drift = _run(REPO / "deploy" / "sync.ps1", "-Source", source, "-Target", target, "-Check")
    assert drift.returncode != 0

    (target / "x.ps1").write_text("a", encoding="utf-8")
    clean = _run(REPO / "deploy" / "sync.ps1", "-Source", source, "-Target", target, "-Check")
    assert clean.returncode == 0, clean.stdout + clean.stderr
