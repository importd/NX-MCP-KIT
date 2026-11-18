"""Modeling commands. Python 3.3 syntax only (see commands/__init__.py).

Calibrated against a live NX 10.0.0.24 session on 2026-11-18:
block / hole / boolean (headless), fillet / chamfer / move_face (interactive).
extrude / revolve still need a Section API calibration; they raise a clear
error instead of pretending to work.
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
    data = {}
    if feature is not None:
        data["feature"] = feature.JournalIdentifier
        bodies = feature.GetBodies()
        body = bodies[0] if len(bodies) > 0 else None
    else:
        body = None
        data["feature"] = None
    if body is None:
        body = list(st.session.Parts.Work.Bodies)[-1] if list(st.session.Parts.Work.Bodies) else None
    if body is not None:
        data["body"] = body.JournalIdentifier
    if extra:
        data.update(extra)
    return {"data": data, "facts": st.facts(body)}


def _point_distance(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _edge_midpoint(edge):
    pts = []
    for vertex in edge.GetVertices():
        pts.append((vertex.X, vertex.Y, vertex.Z))
    if not pts:
        return None
    n = float(len(pts))
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)


def _edge_collector(st, body, points):
    """Collect body edges: all of them, or the ones nearest the given points."""
    edges = list(body.GetEdges())
    if points:
        picked = []
        for point in points:
            best = None
            best_distance = None
            for edge in edges:
                mid = _edge_midpoint(edge)
                if mid is None:
                    continue
                distance = _point_distance(tuple(float(v) for v in point), mid)
                if best_distance is None or distance < best_distance:
                    best = edge
                    best_distance = distance
            if best is not None and best not in picked:
                picked.append(best)
        edges = picked
    if not edges:
        raise RuntimeError("没有可用的边")
    collector = st.session.Parts.Work.ScCollectors.CreateCollector()
    collector.ReplaceRules(
        [st.session.Parts.Work.ScRuleFactory.CreateRuleEdgeDumb(edges)], False
    )
    return collector


def _faces_near(st, body, points):
    faces = list(body.GetFaces())
    picked = []
    for point in points:
        best = None
        best_distance = None
        for face in faces:
            for edge in face.GetEdges():
                mid = _edge_midpoint(edge)
                if mid is None:
                    continue
                distance = _point_distance(tuple(float(v) for v in point), mid)
                if best_distance is None or distance < best_distance:
                    best = face
                    best_distance = distance
        if best is not None and best not in picked:
            picked.append(best)
    if not picked:
        raise RuntimeError("没有找到匹配的面")
    collector = st.session.Parts.Work.ScCollectors.CreateCollector()
    collector.ReplaceRules(
        [st.session.Parts.Work.ScRuleFactory.CreateRuleFaceDumb(picked)], False
    )
    return collector


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


def create_fillet(st, args):
    wp = _work_part(st)
    body = _find_body(wp, args.get("target"))
    st.undo_mark("nx_fillet")
    collector = _edge_collector(st, body, args.get("edges"))
    builder = wp.Features.CreateEdgeBlendBuilder(NXOpen.Features.EdgeBlend.Null)
    try:
        builder.AddChainset(collector, str(args["radius"]))
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    return _result(feature, st)


def create_chamfer(st, args):
    wp = _work_part(st)
    body = _find_body(wp, args.get("target"))
    st.undo_mark("nx_chamfer")
    collector = _edge_collector(st, body, args.get("edges"))
    builder = wp.Features.CreateChamferBuilder(NXOpen.Features.Chamfer.Null)
    try:
        builder.Option = NXOpen.Features.ChamferBuilder.ChamferOption.SymmetricOffsets
        builder.SmartCollector = collector
        builder.FirstOffset = str(args["width"])
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    return _result(feature, st)


def create_move_face(st, args):
    wp = _work_part(st)
    body = _find_body(wp, args.get("target"))
    st.undo_mark("nx_move_face")
    delta = [float(v) for v in args["delta"]]
    length = math.sqrt(delta[0] ** 2 + delta[1] ** 2 + delta[2] ** 2)
    if length <= 1e-9:
        raise RuntimeError("delta 不能为零向量")
    unit = [v / length for v in delta]
    if not args.get("faces"):
        raise RuntimeError("move_face 需要 faces：给面附近的点坐标列表")
    collector = _faces_near(st, body, args["faces"])
    builder = wp.Features.CreateMoveFaceBuilder(NXOpen.Features.MoveFace.Null)
    try:
        builder.Type = NXOpen.Features.MoveFaceBuilder.Types.TranslateDirectionAndDistance
        builder.MoveFaceCollector.ReplaceRules(
            [wp.ScRuleFactory.CreateRuleFaceDumb(
                collector.GetObjects()
            )],
            False,
        )
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        builder.Direction = wp.Directions.CreateDirection(
            origin,
            NXOpen.Vector3d(unit[0], unit[1], unit[2]),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Distance.RightHandSide = repr(length)
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    return _result(feature, st)


def _needs_calibration(name):
    raise RuntimeError(
        "%s 的 NXOpen Section API 需要实机校准；暂时用 nx_run_python + nx_api 查签名替代"
        % name
    )


def create_extrude(st, args):
    _needs_calibration("nx_extrude")


def create_revolve(st, args):
    _needs_calibration("nx_revolve")
