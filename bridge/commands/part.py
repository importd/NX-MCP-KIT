"""Part-level commands. Python 3.3 syntax only."""

import os

import NXOpen


def _same_path(first, second):
    if not first or not second:
        return False
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def create_part(st, args):
    session = st.session
    action = args.get("action")
    path = args.get("path")
    if action == "open":
        if not path:
            raise RuntimeError("open 需要 path")
        session.Parts.OpenDisplay(path)
        return {"data": {"part": path}, "facts": {}}
    units = NXOpen.Part.Units.Inches if args.get("units") == "inch" else NXOpen.Part.Units.Millimeters
    if not path:
        raise RuntimeError("new 需要 path（.prt 保存路径）")
    session.Parts.NewDisplay(path, units)
    return {"data": {"part": path}, "facts": {}}


def save_part(st, args):
    wp = st.session.Parts.Work
    if wp is None:
        raise RuntimeError("没有工作零件")
    path = args.get("path")
    current = getattr(wp, "FullPath", "") or ""
    if path and not _same_path(path, current):
        wp.SaveAs(path)
        return {"data": {"saved": path}, "facts": {}}
    # Same path (or no path): NX10 SaveAs refuses an existing file, so use Save.
    # Save(saveComponentParts, close) needs the enum members; "False" is a
    # Python keyword, hence getattr.
    save_components = getattr(NXOpen.BasePartSaveComponents, "FalseValue")
    close_after = getattr(NXOpen.BasePartCloseAfterSave, "FalseValue")
    wp.Save(save_components, close_after)
    return {"data": {"saved": current or "current"}, "facts": {}}
