"""Modeling commands. Python 3.3 syntax only (see commands/__init__.py)."""

import NXOpen
import NXOpen.Features


def _work_part(st):
    wp = st.session.Parts.Work
    if wp is None:
        raise RuntimeError("NX 里没有打开的工作零件；先新建或打开一个零件")
    return wp


def _null_feature():
    return getattr(NXOpen.Features.Feature, "Null", None)


def create_block(st, args):
    wp = _work_part(st)
    st.undo_mark("nx_block")
    builder = wp.Features.CreateBlockFeatureBuilder(_null_feature())
    try:
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        point = NXOpen.Point3d(
            float(args.get("x", 0.0)),
            float(args.get("y", 0.0)),
            float(args.get("z", 0.0)),
        )
        builder.SetOriginAndLengths(
            point,
            str(args["length"]),
            str(args["width"]),
            str(args["height"]),
        )
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    bodies = feature.GetBodies()
    body = bodies[0] if len(bodies) > 0 else None
    body_id = body.JournalIdentifier if body is not None else None
    return {
        "data": {"feature": feature.JournalIdentifier, "body": body_id},
        "facts": st.facts(body),
    }
