"""Async job table persisted under io/jobs/.

One NX session runs one command at a time (NX is single-threaded): the first
submitted job is `running`, later ones are `queued` and promoted on finish.
Jobs carry a request_id so a retried request cannot execute twice, and an
expired job's late result is refused (`stale`) instead of silently accepted.
"""

import json
import os
import time
import uuid
from pathlib import Path

ACTIVE_STATES = ("queued", "running")


class Jobs:
    def __init__(self, io_dir):
        self.root = Path(io_dir) / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def _lock(self):
        path = self.root / ".lock"
        for _ in range(400):
            try:
                return os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                time.sleep(0.005)
        raise RuntimeError("job table lock timeout")

    def _unlock(self, fd):
        os.close(fd)
        try:
            (self.root / ".lock").unlink()
        except OSError:
            pass

    def _path(self, job_id):
        return self.root / (job_id + ".json")

    def _read(self, job_id):
        path = self._path(job_id)
        if not path.is_file():
            raise KeyError(job_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, job):
        path = self._path(job["id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _all(self):
        jobs = []
        for path in sorted(self.root.glob("*.json")):
            try:
                jobs.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(jobs, key=lambda job: job.get("created", 0))

    def _promote_next(self):
        for job in self._all():
            if job["state"] == "queued":
                job["state"] = "running"
                job["updated"] = time.time()
                self._write(job)
                return job["id"]
        return None

    def submit(self, kind, payload, request_id=None):
        fd = self._lock()
        try:
            if request_id:
                for job in self._all():
                    if job.get("request_id") == request_id:
                        return job["id"]
            running = any(job["state"] == "running" for job in self._all())
            job = {
                "id": uuid.uuid4().hex[:12],
                "kind": kind,
                "payload": payload,
                "state": "queued" if running else "running",
                "request_id": request_id,
                "created": time.time(),
                "updated": time.time(),
                "result": None,
            }
            self._write(job)
            return job["id"]
        finally:
            self._unlock(fd)

    def status(self, job_id):
        job = self._read(job_id)
        return {
            "id": job["id"],
            "kind": job.get("kind"),
            "state": job["state"],
            "created": job.get("created"),
            "updated": job.get("updated"),
            "result": job.get("result"),
        }

    def list(self):
        return [
            {
                "id": job["id"],
                "kind": job.get("kind"),
                "state": job["state"],
                "created": job.get("created"),
            }
            for job in self._all()
        ]

    def cancel(self, job_id):
        fd = self._lock()
        try:
            job = self._read(job_id)
            if job["state"] == "queued":
                job["state"] = "cancelled"
                job["updated"] = time.time()
                self._write(job)
                return True
            if job["state"] == "running":
                (self.root.parent / "STOP").write_text("1", encoding="utf-8")
                job["state"] = "cancelled"
                job["updated"] = time.time()
                self._write(job)
                return True
            return False
        finally:
            self._unlock(fd)

    def finish(self, job_id, ok, result=None):
        fd = self._lock()
        try:
            job = self._read(job_id)
            if job["state"] in ("cancelled", "stale"):
                return False
            job["state"] = "done" if ok else "failed"
            job["result"] = result
            job["updated"] = time.time()
            self._write(job)
            self._promote_next()
            return True
        finally:
            self._unlock(fd)

    def expire(self, job_id):
        fd = self._lock()
        try:
            job = self._read(job_id)
            if job["state"] != "running":
                return False
            job["state"] = "stale"
            job["updated"] = time.time()
            self._write(job)
            self._promote_next()
            return True
        finally:
            self._unlock(fd)
