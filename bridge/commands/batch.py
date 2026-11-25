"""Batch edit command: attributes / names / layer / visibility / transform.

Python 3.3 syntax only (NX10 embeds CPython 3.3.2).

Why this exists: doing these four things one object at a time is 5x-189x slower
than doing them in batch. Measured on NX 10.0.0.24, 500 solids in one part:

    attributes x2, update=TRUE   -> 5.67 s   (extrapolated)
    attributes x2, update=FALSE  -> 0.030 s
    set name (500)               -> 0.286 s
    blank one by one             -> 0.052 s (0.001 s with display suppressed)
    uf5947 batch transform (500) -> 3.349 s
    uf5947 looped per object     -> 15.3 s   (extrapolated)

Transform uses uf5947 (= UF_TRNS_transform_objects) through ctypes, because the
NXOpen Python wrapper does not expose it. NOT UF_MODL_transform_entities: that
one drives the interactive Transform operation and stacks dialogs until NX
freezes (observed twice).

The 12 element matrix is [R|T] row major: translation lives in m[3], m[7], m[11].
"""

import ctypes
import os
import time

import NXOpen
import NXOpen.UF


def _ufs():
    return NXOpen.UF.UFSession.GetUFSession()


def _body_list(wp):
    """Alive solids only; deleted bodies linger as zero-face objects."""
    return [b for b in wp.Bodies if len(b.GetFaces()) > 0]


def _pick(wp, targets):
    bodies = _body_list(wp)
    if not targets or targets == "all":
        return bodies
    wanted = set(str(t) for t in targets)
    return [b for b in bodies if b.JournalIdentifier in wanted or b.Name in wanted]


def _libufun():
    session = NXOpen.Session.GetSession()
    base = None
    for var in ("UGII_BASE_DIR", "UGII_ROOT_DIR"):
        try:
            base = session.GetEnvironmentVariableValue(var)
        except Exception:
            base = None
        if base:
            break
    candidates = []
    if base:
        candidates.append(os.path.join(base, "UGII", "libufun.dll"))
        candidates.append(os.path.join(base, "UGII", "libufun.so"))
    candidates.append(r"D:\Program Files\Siemens\NX 10.0\UGII\libufun.dll")
    for path in candidates:
        if os.path.exists(path):
            return ctypes.CDLL(path)
    raise RuntimeError("找不到 libufun，无法调用 uf5947")


_ROT = {
    "X": lambda c, s: [1.0, 0.0, 0.0, 0.0, 0.0, c, -s, 0.0, 0.0, s, c, 0.0],
    "Y": lambda c, s: [c, 0.0, s, 0.0, 0.0, 1.0, 0.0, 0.0, -s, 0.0, c, 0.0],
    "Z": lambda c, s: [c, -s, 0.0, 0.0, s, c, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
}


def _matrix(rotate_axis, rotate_angle, translate):
    import math

    mat = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    axis = (rotate_axis or "").upper()
    if axis in _ROT and rotate_angle:
        rad = math.radians(float(rotate_angle))
        mat = _ROT[axis](math.cos(rad), math.sin(rad))
    if translate:
        for i in range(3):
            mat[i * 4 + 3] = float(translate[i])
    return mat


def _transform(bodies, mat, move=1):
    """One uf5947 call for the whole batch."""
    lib = _libufun()
    fn = lib.uf5947
    fn.restype = None
    fn.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_int),
    ]
    tags = [b.Tag for b in bodies]
    n = len(tags)
    mat_c = (ctypes.c_double * 12)(*mat)
    arr = (ctypes.c_uint * n)(*tags)
    n_c = ctypes.c_int(n)
    move_c = ctypes.c_int(int(move))
    layer_c = ctypes.c_int(0)
    trace_c = ctypes.c_int(2)
    copies = (ctypes.c_uint * max(1, n))()
    tcg = ctypes.c_uint(0)
    status = ctypes.c_int(0)
    fn(mat_c, arr, ctypes.byref(n_c), ctypes.byref(move_c), ctypes.byref(layer_c),
       ctypes.byref(trace_c), copies, ctypes.byref(tcg), ctypes.byref(status))
    return status.value


def batch_edit(st, args):
    wp = st.session.Parts.Work
    if wp is None:
        raise RuntimeError("NX 里没有打开的工作零件")
    ufs = _ufs()
    bodies = _pick(wp, args.get("targets"))
    if not bodies:
        raise RuntimeError("没有匹配的实体")

    timing = {}
    done = {"targets": len(bodies), "attributes": 0, "renamed": 0,
            "layered": 0, "visibility": 0, "transformed": 0}

    # Suppress the two global costs up front: display refresh and model update.
    display_off = bool(args.get("suppress_display", True))
    if display_off:
        try:
            ufs.Disp.SetDisplay(0)
        except Exception:
            display_off = False

    try:
        # ---- attributes: update=False, one UF_MODL_update at the end ----
        attrs = args.get("attributes") or []
        if attrs:
            t0 = time.time()
            for body in bodies:
                for item in attrs:
                    title = item.get("title")
                    if not title:
                        continue
                    kind = (item.get("type") or "string").lower()
                    value = item.get("value")
                    if kind in ("int", "integer"):
                        ufs.Attr.SetIntegerUserAttribute(body.Tag, title, -3, int(value), False)
                    elif kind in ("real", "double", "float"):
                        ufs.Attr.SetRealUserAttribute(body.Tag, title, -3, float(value), False)
                    elif kind in ("bool", "boolean"):
                        ufs.Attr.SetBoolUserAttribute(body.Tag, title, -3, bool(value), False)
                    else:
                        ufs.Attr.SetStringUserAttribute(body.Tag, title, -3, str(value), False)
                    done["attributes"] += 1
            timing["attrs_ms"] = int((time.time() - t0) * 1000)

        # ---- names ----
        pattern = args.get("name_pattern")
        if pattern:
            t0 = time.time()
            for i, body in enumerate(bodies):
                try:
                    name = pattern.format(i=i, n=len(bodies), id=body.JournalIdentifier)
                except Exception:
                    name = "%s%d" % (pattern, i)
                ufs.Obj.SetName(body.Tag, name)
                done["renamed"] += 1
            timing["names_ms"] = int((time.time() - t0) * 1000)

        # ---- layer ----
        # 若 visibility_mode=layer，图层在这里一次性设好，不再重复跑一遍
        layer = args.get("layer")
        vis_mode = (args.get("visibility_mode") or "object").lower()
        skip_layer = (args.get("hidden") is not None and vis_mode == "layer")
        if layer is not None and not skip_layer:
            t0 = time.time()
            for body in bodies:
                ufs.Obj.SetLayer(body.Tag, int(layer))
                done["layered"] += 1
            timing["layer_ms"] = int((time.time() - t0) * 1000)

        # ---- visibility ----
        # visibility_mode:
        #   "object" (默认) -> 逐个 UF_OBJ_set_blank_status，语义是"这个体隐藏"
        #   "layer"        -> 逐个设图层 + 一次 UF_LAYER_set_status，语义是"整层隐藏"
        # 实测 500 体：object 约 50ms（显示开）/ 1ms（显示抑制）；layer 约 48ms + 1 次
        hidden = args.get("hidden")
        if hidden is not None:
            mode = (args.get("visibility_mode") or "object").lower()
            t0 = time.time()
            if mode == "layer":
                target_layer = args.get("layer")
                if target_layer is None:
                    target_layer = 20
                    done["layer_fallback"] = target_layer
                status = 4 if hidden else 2      # UF_LAYER_INACTIVE_LAYER / ACTIVE_LAYER
                for body in bodies:
                    ufs.Obj.SetLayer(body.Tag, int(target_layer))
                    done["layered"] += 1
                ufs.Layer.SetStatus(int(target_layer), status)
                done["visibility_mode"] = "layer"
                done["layer_status_set"] = int(target_layer)
            else:
                flag = 1 if hidden else 0
                for body in bodies:
                    ufs.Obj.SetBlankStatus(body.Tag, flag)
                    done["visibility"] += 1
                done["visibility_mode"] = "object"
            timing["visibility_ms"] = int((time.time() - t0) * 1000)

        # ---- transform: one call for the whole batch ----
        tf = args.get("transform")
        if tf:
            mat = _matrix(tf.get("rotate_axis"), tf.get("rotate_angle"),
                          tf.get("translate"))
            t0 = time.time()
            status = _transform(bodies, mat, tf.get("move", 1))
            timing["transform_ms"] = int((time.time() - t0) * 1000)
            if status == 0:
                done["transformed"] = len(bodies)
            else:
                timing["transform_status"] = status
    finally:
        # One model update and one redraw for everything above.
        try:
            ufs.Modl.Update()
        except Exception:
            try:
                ufs.ModlGeneral.Update()
            except Exception:
                pass
        if display_off:
            try:
                ufs.Disp.SetDisplay(1)
                ufs.Disp.RegenerateDisplay()
            except Exception:
                pass

    return {"data": dict(done, elapsed_ms=timing, part=wp.Leaf), "facts": {}}
