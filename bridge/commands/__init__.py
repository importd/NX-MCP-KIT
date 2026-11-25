"""Command dispatch for the in-NX bridge.

Python 3.3 syntax only: NX10 embeds CPython 3.3.2, so no f-strings, no walrus,
no annotations, no dataclasses anywhere under bridge/. The key set here must
match contract/commands.json exactly (checked by tests/offline).
"""

from . import batch, exec as exec_cmd
from . import model, part, query, view

COMMANDS = {
    "nx_part": part.create_part,
    "nx_save": part.save_part,
    "nx_block": model.create_block,
    "nx_extrude": model.create_extrude,
    "nx_revolve": model.create_revolve,
    "nx_hole": model.create_hole,
    "nx_fillet": model.create_fillet,
    "nx_chamfer": model.create_chamfer,
    "nx_boolean": model.create_boolean,
    "nx_move_face": model.create_move_face,
    "nx_shell": model.create_shell,
    "nx_delete_body": model.create_delete_body,
    "nx_run_python": exec_cmd.run_python,
    "nx_screenshot": view.screenshot,
    "nx_inspect": query.inspect_part,
    "nx_measure": query.measure,
    "nx_batch_edit": batch.batch_edit,
}


def handle(st, cmd, args):
    fn = COMMANDS.get(cmd)
    if fn is None:
        return {"error": {"code": "BRIDGE_UNKNOWN_COMMAND", "msg": "unknown command: %s" % cmd}}
    try:
        return fn(st, args)
    except Exception as exc:
        return {"error": {"code": "BRIDGE_EXCEPTION", "msg": repr(exc)}}
