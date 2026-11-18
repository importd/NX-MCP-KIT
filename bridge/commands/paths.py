"""Shared path rules for bridge-side files. Python 3.3 syntax only.

The bridge home is <root>/bridge (both in the repo and in a deployed runtime
home whose inner layout mirrors the repo). The host watches <root>/io/<pid>,
so the bridge must resolve its io directory from the root, not from its own
folder — otherwise a deployed bridge never sees the host's queue.
"""

import os


def default_io(bridge_home, pid):
    root = os.path.dirname(bridge_home)
    return os.path.join(root, "io", str(pid))
