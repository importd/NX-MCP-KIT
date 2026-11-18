"""Modeling commands. Python 3.3 syntax only (see commands/__init__.py).

block / hole / boolean are implemented from working NXOpen patterns.
extrude / revolve / fillet / chamfer / move_face carry explicit "calibrate in
live NX" errors: their builders need live validation before claiming support.
"""

import math

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities


def _work_part(st):
    wp = st.session.Parts.Work
    if wp is None:
        raise RuntimeError("NX 里没有打开的工作零件；先新建或打开一个零件")
    return wp


def _null_feature():
    return getattr(NXOpen.Features.Feature, "Null", None)


def _find_body(wp, ref):
    bodies = list(wp.Bodies)
    if not bodies:
        raise RuntimeError("工作零件里没有实体")
    if ref in (None, "", "last"):
        return bodies[-1]
    for body in bodies:
        if body.JournalIdentifier == ref:
            return body
    raise RuntimeError("找不到体：%r" % ref)


def _result(feature, st, extra=None):
    bodies = feature.GetBodies()
    body = bodies[0] if len(bodies) > 0 else None
    data = {"feature": feature.JournalIdentifier}
    if body is not None:
        data["body"] = body.JournalIdentifier
    if extra:
        data.update(extra)
    return {"data": data, "facts": st.facts(body)}


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
    return _result(feature, st)


def create_hole(st, args):
    wp = _work_part(st)
    body = _find_body(wp, args.get("target"))
    st.undo_mark("nx_hole")
    px = [float(v) for v in args["position"]]
    dvec = [float(v) for v in args.get("direction") or [0.0, 0.0, -1.0]]
    norm = math.sqrt(sum(v * v for v in dvec)) or 1.0
    dvec = [v / norm for v in dvec]
    depth = args.get("depth")
    if depth in (None, "", "through", 0):
        bbox = st.facts(body).get("bbox")
        if bbox:
            depth = math.sqrt(
                (bbox[3] - bbox[0]) ** 2
                + (bbox[4] - bbox[1]) ** 2
                + (bbox[5] - bbox[2]) ** 2
            ) + 2.0
        else:
            depth = 100.0
        through = True
    else:
        depth = float(depth)
        through = False
    lead = 1.0
    start = [px[i] - dvec[i] * lead for i in range(3)]
    builder = wp.Features.CreateCylinderBuilder(_null_feature())
    try:
        builder.Type = NXOpen.Features.CylinderBuilder.Types.AxisDiameterAndHeight
        builder.Diameter.RightHandSide = str(args["diameter"])
        builder.Height.RightHandSide = repr(depth + lead)
        point = NXOpen.Point3d(start[0], start[1], start[2])
        npoint = wp.Points.CreatePoint(point)
        direction = wp.Directions.CreateDirection(
            point,
            NXOpen.Vector3d(dvec[0], dvec[1], dvec[2]),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Axis = wp.Axes.CreateAxis(
            npoint, direction, NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        builder.BooleanOption.Type = (
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
        )
        builder.BooleanOption.SetTargetBodies([body])
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    return _result(feature, st, {"through": through})


def create_boolean(st, args):
    wp = _work_part(st)
    target = _find_body(wp, args["target"])
    tool = _find_body(wp, args["tool"])
    st.undo_mark("nx_boolean")
    operation = {
        "unite": NXOpen.Features.Feature.BooleanType.Unite,
        "subtract": NXOpen.Features.Feature.BooleanType.Subtract,
        "intersect": NXOpen.Features.Feature.BooleanType.Intersect,
    }[args["operation"]]
    builder = wp.Features.CreateBooleanBuilderUsingCollector(
        NXOpen.Features.BooleanFeature.Null
    )
    try:
        builder.Operation = operation
        builder.Target = target
        collector = wp.ScCollectors.CreateCollector()
        collector.ReplaceRules(
            [wp.ScRuleFactory.CreateRuleBodyDumb([tool], True)], False
        )
        builder.ToolBodyCollector = collector
        feature = builder.Commit()
    finally:
        builder.Destroy()
    return _result(feature, st)


def _needs_calibration(name):
    raise RuntimeError(
        "%s 的 NXOpen builder 需要实机校准（离线无法验证签名）；暂时用 nx_run_python + nx_api 查签名替代"
        % name
    )


def create_extrude(st, args):
    _needs_calibration("nx_extrude")


def create_revolve(st, args):
    _needs_calibration("nx_revolve")


def create_fillet(st, args):
    _needs_calibration("nx_fillet")


def create_chamfer(st, args):
    _needs_calibration("nx_chamfer")


def create_move_face(st, args):
    _needs_calibration("nx_move_face")
