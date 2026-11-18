from nxkit.gate import Gate
from nxkit.jobs import Jobs
from nxkit.library.store import Library
from nxkit.registry import Registry
from nxkit.router import Router


class FakeBridge:
    def sessions(self):
        return [{"pid": 8016, "nx": "2512", "alive": True}]

    def submit(self, pid, cmd, args, timeout_s=120.0):
        return {"data": {"feature": "BLOCK(0)"}, "facts": {}}


def _jobs(workdir):
    return Jobs(workdir / "io")


def test_first_running_second_queued(workdir):
    jobs = _jobs(workdir)
    first = jobs.submit("nx", {"cmd": "nx_block"})
    second = jobs.submit("nx", {"cmd": "nx_block"})
    assert jobs.status(first)["state"] == "running"
    assert jobs.status(second)["state"] == "queued"
    jobs.finish(first, ok=True)
    assert jobs.status(second)["state"] == "running"


def test_cancel_queued_job(workdir):
    jobs = _jobs(workdir)
    jobs.submit("nx", {})
    second = jobs.submit("nx", {})
    assert jobs.cancel(second) is True
    assert jobs.status(second)["state"] == "cancelled"


def test_cancel_running_writes_stop_file(workdir):
    jobs = _jobs(workdir)
    running = jobs.submit("nx", {})
    assert jobs.cancel(running) is True
    assert (workdir / "io" / "STOP").is_file()


def test_duplicate_request_id_reuses_job(workdir):
    jobs = _jobs(workdir)
    first = jobs.submit("nx", {}, request_id="r1")
    second = jobs.submit("nx", {}, request_id="r1")
    assert first == second
    assert len(jobs.list()) == 1


def test_late_result_after_expire_is_dropped(workdir):
    jobs = _jobs(workdir)
    job = jobs.submit("nx", {})
    assert jobs.expire(job) is True
    assert jobs.status(job)["state"] == "stale"
    assert jobs.finish(job, ok=True) is False
    assert jobs.status(job)["state"] == "stale"


def test_nx_job_tool_lists_jobs(workdir, contract_dir):
    registry = Registry(contract_dir)
    library = Library(workdir / "library").init()
    gate = Gate(workdir / "workflow.json")
    jobs = Jobs(workdir / "io")
    router = Router(registry, FakeBridge(), library, gate, jobs=jobs)
    job = jobs.submit("nx", {})
    envelope = router.call("nx_job", {"action": "list"})
    assert envelope["ok"] is True
    assert [item["id"] for item in envelope["data"]["jobs"]] == [job]
