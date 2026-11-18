"""Command dispatch for the in-NX bridge.

Python 3.3 syntax only: NX10 embeds CPython 3.3.2, so no f-strings, no walrus,
no annotations, no dataclasses anywhere under bridge/.
"""

from . import model, query

COMMANDS = {
    "nx_block": model.create_block,
    "nx_inspect": query.inspect_part,
    "nx_measure": query.measure,
}


def handle(st, cmd, args):
    fn = COMMANDS.get(cmd)
    if fn is None:
        return {"error": {"code": "BRIDGE_UNKNOWN_COMMAND", "msg": "unknown command: %s" % cmd}}
    try:
        return fn(st, args)
    except Exception as exc:
        return {"error": {"code": "BRIDGE_EXCEPTION", "msg": repr(exc)}}
