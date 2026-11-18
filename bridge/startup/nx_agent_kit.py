"""In-NX bridge entry point, loaded from a startup directory.

Runs a 250 ms timer on the NX UI thread: drain io/<pid>/inbox, execute one
command under the UG access lock, write io/<pid>/outbox/<request_id>.json.

Python 3.3 syntax only: NX10 embeds CPython 3.3.2.
"""

import json
import os
import sys
import time
import traceback

import NXOpen
import NXOpen.UF

_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HOME not in sys.path:
    sys.path.append(_HOME)

from commands import handle  # noqa: E402
from commands.paths import default_io  # noqa: E402

_LOG_NAME = "nxkit_bridge.log"


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Bridge(object):
    def __init__(self, session):
        self.session = session
        self.uf = NXOpen.UF.UFSession.GetUFSession()
        self.io = os.environ.get("NXKIT_IO") or default_io(_HOME, os.getpid())
        self.inbox = os.path.join(self.io, "inbox")
        self.outbox = os.path.join(self.io, "outbox")
        self.stop_file = os.path.join(os.path.dirname(self.io), "STOP")
        for path in (self.inbox, self.outbox):
            if not os.path.isdir(path):
                os.makedirs(path)
        self._write_status()

    def _log(self, text):
        try:
            with open(os.path.join(self.io, _LOG_NAME), "a") as fh:
                fh.write("[" + _now() + "] " + text + "\n")
        except Exception:
            pass

    def _write_json(self, path, data):
        tmp = path + ".tmp"
        fh = open(tmp, "w", encoding="utf-8")
        try:
            fh.write(json.dumps(data))
        finally:
            fh.close()
        try:
            os.remove(path)
        except OSError:
            pass
        os.rename(tmp, path)

    def _write_status(self):
        payload = {
            "pid": os.getpid(),
            "alive": True,
            "updated": time.time(),
            "python": sys.version.split()[0],
            "jobs_queued": len(os.listdir(self.inbox)) if os.path.isdir(self.inbox) else 0,
        }
        self._write_json(os.path.join(self.io, "status.json"), payload)

    def _inbox_jobs(self):
        try:
            names = os.listdir(self.inbox)
        except Exception:
            return []
        names = [name for name in names if name.endswith(".json")]
        names.sort()
        return names

    def _run_job(self, path):
        fh = open(path, "r", encoding="utf-8")
        try:
            job = json.loads(fh.read())
        finally:
            fh.close()
        request_id = job.get("request_id", "unknown")
        cmd = job.get("cmd", "")
        args = job.get("args") or {}
        started = time.time()
        try:
            self.uf.Ui.LockUgAccess(NXOpen.UF.UFConstants.UF_UI_FROM_CUSTOM)
            try:
                payload = handle(self, cmd, args)
            finally:
                self.uf.Ui.UnlockUgAccess(NXOpen.UF.UFConstants.UF_UI_FROM_CUSTOM)
        except Exception:
            payload = {"error": {"code": "BRIDGE_EXCEPTION", "msg": traceback.format_exc()}}
        payload["request_id"] = request_id
        payload["elapsed_s"] = round(time.time() - started, 3)
        self._write_json(os.path.join(self.outbox, request_id + ".json"), payload)
        try:
            os.remove(path)
        except Exception:
            pass

    def undo_mark(self, name):
        try:
            self.session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, name)
        except Exception:
            self._log("SetUndoMark failed: " + name)

    def facts(self, body):
        result = {}
        if body is None:
            return result
        try:
            result["faces"] = len(body.GetFaces())
            result["edges"] = len(body.GetEdges())
        except Exception:
            pass
        try:
            for holder in ("Modl", "ModlGeneral"):
                try:
                    uf_holder = getattr(self.uf, holder)
                    result["bbox"] = [round(float(v), 6) for v in uf_holder.AskBoundingBox(body.Tag)]
                except Exception:
                    pass
                if "bbox" in result:
                    break
        except Exception:
            pass
        try:
            wp = self.session.Parts.Work
            uc = wp.UnitCollection
            units = [
                uc.GetBase("Area"),
                uc.GetBase("Volume"),
                uc.GetBase("Mass"),
                uc.GetBase("Length"),
            ]
            mp = wp.MeasureManager.NewMassProperties(units, 0.99, [body])
            result["volume"] = round(float(mp.Volume), 4)
            result["area"] = round(float(mp.Area), 4)
        except Exception:
            pass
        return result

    def tick(self):
        if os.path.exists(self.stop_file):
            return
        for name in self._inbox_jobs():
            if os.path.exists(self.stop_file):
                return
            self._run_job(os.path.join(self.inbox, name))
        self._write_status()


def main():
    session = NXOpen.Session.GetSession()
    bridge = Bridge(session)
    bridge._log("bridge started, io=" + bridge.io)
    try:
        session.SetTimer(250, bridge.tick)
    except Exception:
        bridge._log("SetTimer unavailable; run tick() manually")


main()
