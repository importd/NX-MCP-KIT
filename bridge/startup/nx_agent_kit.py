# nx: threaded
# -*- coding: utf-8 -*-
"""In-NX bridge entry point, loaded from a startup directory.

Runs a 250 ms timer on the NX UI thread: drain io/<pid>/inbox, execute one
command under the UG access lock, write io/<pid>/outbox/<request_id>.json.

Python 3.3 syntax only: NX10 embeds CPython 3.3.2.

NX loads this file from a startup folder and calls startup(*args) (and/or
imports the module). The `# nx: threaded` header makes NX load it on its
startup thread; every entry point catches BaseException and only writes a log
so a failure here can never leave an error dialog in front of the user.
"""

import json
import os
import sys
import time
import traceback

import NXOpen
import NXOpen.UF

# NX imports startup modules with a CWD-relative __file__, so deriving the
# bridge home from __file__ alone is unreliable. Order: env NXKIT_HOME ->
# nxkit_home.txt next to this file -> parent of the startup folder.
def _resolve_home():
    home = os.environ.get("NXKIT_HOME")
    if home:
        return home
    try:
        folder = os.path.dirname(os.path.abspath(__file__))
        pointer = os.path.join(folder, "nxkit_home.txt")
        if os.path.isfile(pointer):
            handle = open(pointer, "r")
            try:
                text = handle.read().strip()
            finally:
                handle.close()
            if text:
                return text
        return os.path.dirname(folder)
    except Exception:
        return os.path.dirname(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"))


_HOME = _resolve_home()
if _HOME not in sys.path:
    sys.path.append(_HOME)

try:
    from commands import handle  # noqa: E402
    from commands.paths import default_io  # noqa: E402
except Exception:
    _BASE = os.environ.get("NXKIT_IO_BASE") or os.path.dirname(_HOME)
    try:
        if not os.path.isdir(_BASE):
            os.makedirs(_BASE)
        _ERR = open(os.path.join(_BASE, "bootstrap_error.log"), "a")
        try:
            _ERR.write(traceback.format_exc() + "\n")
        finally:
            _ERR.close()
    except Exception:
        pass
    raise

_LOG_NAME = "nxkit_bridge.log"
_ERROR_LOG = os.path.join(
    os.environ.get("NXKIT_IO_BASE") or os.path.dirname(_HOME), "nx_startup_error.log"
)


def _boot_error(text):
    try:
        folder = os.path.dirname(_ERROR_LOG)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        handle = open(_ERROR_LOG, "a")
        try:
            handle.write(text + "\n")
        finally:
            handle.close()
    except Exception:
        pass


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Bridge(object):
    def __init__(self, session):
        self.session = session
        self.uf = NXOpen.UF.UFSession.GetUFSession()
        self.io = os.environ.get("NXKIT_IO")
        if not self.io:
            io_base = os.environ.get("NXKIT_IO_BASE")
            if io_base:
                self.io = os.path.join(io_base, str(os.getpid()))
            else:
                self.io = default_io(_HOME, os.getpid())
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
        # Atomic replace: readers may poll status.json every tick and must never
        # observe a missing file between remove and rename.
        os.replace(tmp, path)

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


_TIMER = {}


def _claim_process():
    # NX can load startup python from more than one registered directory; keep
    # exactly one bridge per NX process.
    import ctypes
    from ctypes import wintypes as w

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
    kernel32.CreateMutexW.restype = w.HANDLE
    handle = kernel32.CreateMutexW(None, False, u"Local\\NXAgentKit_%d" % os.getpid())
    _TIMER["mutex"] = handle
    return ctypes.get_last_error() != 183


def _start_timer(bridge):
    # NXOpen has no portable timer for Python; Win32 SetTimer on the NX UI
    # thread is the mechanism proven on NX10 (same technique as NXAgentLink).
    import ctypes
    from ctypes import wintypes as w

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    timer_proc_type = ctypes.WINFUNCTYPE(None, w.HWND, w.UINT, ctypes.c_size_t, w.DWORD)
    user32.SetTimer.argtypes = [w.HWND, ctypes.c_size_t, w.UINT, timer_proc_type]
    user32.SetTimer.restype = ctypes.c_size_t
    user32.KillTimer.argtypes = [w.HWND, ctypes.c_size_t]
    user32.KillTimer.restype = w.BOOL

    def callback(hwnd, msg, idevent, dwtime):
        try:
            bridge.tick()
        except Exception:
            bridge._log("tick error: " + traceback.format_exc())

    proc = timer_proc_type(callback)
    timer_id = user32.SetTimer(None, 0, 250, proc)
    if not timer_id:
        raise RuntimeError("SetTimer failed, WinError %d" % ctypes.get_last_error())
    _TIMER.update({"user32": user32, "id": timer_id, "proc": proc})
    return timer_id


def _run_bridge():
    if not _claim_process():
        return
    session = NXOpen.Session.GetSession()
    bridge = Bridge(session)
    bridge._log("bridge started, io=" + bridge.io)
    _start_timer(bridge)


def _boot(source):
    try:
        _run_bridge()
    except BaseException:
        _boot_error(source + "\n" + traceback.format_exc())


def startup(*args):
    """NX startup loader entry point (it passes two positional arguments)."""
    _boot("startup()")
    return 0


def main(*args):
    _boot("main()")


_boot("module")
