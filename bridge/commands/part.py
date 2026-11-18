"""Part-level commands. Python 3.3 syntax only."""

import NXOpen


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
    if path:
        wp.SaveAs(path)
        return {"data": {"saved": path}, "facts": {}}
    wp.Save()
    return {"data": {"saved": "current"}, "facts": {}}
