import sys

from nxkit.headless import HeadlessRunner


def _write_fake_run_journal(workdir):
    script = workdir / "fake_run_journal.py"
    script.write_text(
        "import json\n"
        "import os\n"
        "import sys\n"
        "path = os.environ.get('NXKIT_PLAN') or sys.argv[1]\n"
        "plan = json.load(open(path, 'r'))\n"
        "print('NXKIT_BEGIN')\n"
        "if plan.get('fail'):\n"
        "    print('NXKIT_FAIL:NX_BOOL_EMPTY')\n"
        "    sys.exit(0)\n"
        "if plan.get('sleep'):\n"
        "    import time; time.sleep(10)\n"
        "print('NXKIT_OK')\n",
        encoding="utf-8",
    )
    return script


def _runner(workdir, script):
    return HeadlessRunner(
        workdir / "nx",
        runner_cmd=[sys.executable, str(script)],
        plan_dir=workdir / "headless",
    )


def test_ok_marker_wins_even_with_exit_zero(workdir):
    script = _write_fake_run_journal(workdir)
    result = _runner(workdir, script).run({"steps": []}, timeout_s=30)
    assert result["ok"] is True
    assert result["markers"] == ["NXKIT_BEGIN", "NXKIT_OK"]
    assert result["artifacts"] == []


def test_fail_marker_beats_exit_code(workdir):
    script = _write_fake_run_journal(workdir)
    result = _runner(workdir, script).run({"fail": True}, timeout_s=30)
    assert result["ok"] is False
    assert "NXKIT_FAIL:NX_BOOL_EMPTY" in result["markers"]


def test_timeout_reports_timeout(workdir):
    script = _write_fake_run_journal(workdir)
    result = _runner(workdir, script).run({"sleep": True}, timeout_s=0.5)
    assert result["ok"] is False
    assert result.get("error") == "HEADLESS_TIMEOUT"
