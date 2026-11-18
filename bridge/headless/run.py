"""run_journal entry point for headless plans.

Runs inside a separate NX process: loads plan.json, executes each step through
the same command table as the interactive bridge, writes a result file and
prints markers. Python 3.3 syntax only.
"""

import json
import os
import sys

import NXOpen
import NXOpen.UF

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.append(_HERE)

from commands import handle  # noqa: E402


def _marker(text):
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


class HeadlessState(object):
    def __init__(self):
        self.session = NXOpen.Session.GetSession()
        self.uf = NXOpen.UF.UFSession.GetUFSession()

    def undo_mark(self, name):
        try:
            self.session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, name)
        except Exception:
            pass

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
                    result["bbox"] = [
                        round(float(v), 6)
                        for v in getattr(self.uf, holder).AskBoundingBox(body.Tag)
                    ]
                    break
                except Exception:
                    pass
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
        except Exception:
            pass
        return result


def main():
    plan_path = os.environ.get("NXKIT_PLAN")
    if not plan_path:
        plan_path = sys.argv[1]
    fh = open(plan_path, "r", encoding="utf-8")
    try:
        plan = json.loads(fh.read())
    finally:
        fh.close()
    state = HeadlessState()
    _marker("NXKIT_BEGIN")
    ok = True
    results = []
    for step in plan.get("steps", []):
        payload = handle(state, step.get("cmd"), step.get("args") or {})
        results.append(payload)
        if payload.get("error"):
            ok = False
            _marker("NXKIT_FAIL:" + str(payload["error"].get("code", "NX_ERROR")))
            break
    out_path = plan_path + ".result.json"
    fh = open(out_path, "w", encoding="utf-8")
    try:
        fh.write(json.dumps({"ok": ok, "steps": results}))
    finally:
        fh.close()
    if ok:
        _marker("NXKIT_OK")


main()
