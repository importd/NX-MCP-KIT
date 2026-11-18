"""Read-only query commands. Python 3.3 syntax only."""


def _work_part(st):
    wp = st.session.Parts.Work
    if wp is None:
        raise RuntimeError("NX 里没有打开的工作零件")
    return wp


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


def inspect_part(st, args):
    wp = _work_part(st)
    bodies = []
    for body in wp.Bodies:
        bodies.append({"id": body.JournalIdentifier, "facts": st.facts(body)})
    return {
        "data": {"part": getattr(wp, "Leaf", None), "bodies": bodies},
        "facts": {},
    }


def measure(st, args):
    wp = _work_part(st)
    target = _find_body(wp, args.get("target"))
    return {
        "data": {"body": target.JournalIdentifier},
        "facts": st.facts(target),
    }
