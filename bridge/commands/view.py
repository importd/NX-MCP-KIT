"""View commands (screenshot via NX ImageExport). Python 3.3 syntax only."""

import os

import NXOpen
import NXOpen.Gateway


def screenshot(st, args):
    path = args.get("path")
    if not path:
        raise RuntimeError("screenshot 需要 path（PNG 输出路径）")
    wp = st.session.Parts.Work
    view = args.get("view")
    if view == "fit" and wp is not None:
        try:
            wp.ModelingViews.WorkView.Orient(
                NXOpen.View.Canned.Trimetric, NXOpen.View.ScaleAdjustment.Fit
            )
        except Exception:
            pass
    builder = NXOpen.UI.GetUI().CreateImageExportBuilder()
    try:
        builder.RegionMode = False
        builder.FileFormat = NXOpen.Gateway.ImageExportBuilder.FileFormats.Png
        builder.FileName = path
        builder.BackgroundOption = NXOpen.Gateway.ImageExportBuilder.BackgroundOptions.Original
        builder.EnhanceEdges = False
        builder.Commit()
    finally:
        builder.Destroy()
    return {"data": {"file": path, "exists": os.path.exists(path)}, "facts": {}}
