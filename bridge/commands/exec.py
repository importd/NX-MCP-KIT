"""Execution commands. Python 3.3 syntax only."""


def run_python(st, args):
    code = args["code"]
    namespace = getattr(st, "ns", None)
    if namespace is None:
        namespace = {}
        st.ns = namespace
    exec(code, namespace)
    result = namespace.get("result")
    return {
        "data": {"executed": True, "result": repr(result) if result is not None else None},
        "facts": {},
    }
