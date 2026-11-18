"""Host-side security policy.

NX commands cannot be sandboxed once they are inside the NX process, so the
host enforces what it can before routing:

* workspace guard: file paths passed to tools (path/to/part) must resolve under
  one of the configured roots;
* execute switch: `nx_run_python` is only routed when execute is allowed;
* dry run: geometry tools can be asked to report what they would do.

Defaults stay permissive for local use; set NXKIT_WORKSPACE and
NXKIT_ALLOW_EXECUTE=0 for a locked-down deployment.
"""

import os
from pathlib import Path

PATH_KEYS = ("path", "to", "part", "out", "file", "source")


class SecurityError(Exception):
    pass


class SecurityPolicy:
    def __init__(self, workspace_roots, allow_execute=True, enforce_paths=True):
        self.workspace_roots = [Path(root).resolve() for root in workspace_roots]
        self.allow_execute = bool(allow_execute)
        self.enforce_paths = bool(enforce_paths)

    @classmethod
    def from_env(cls, repo_root):
        roots = [Path(repo_root).resolve()]
        extra = os.environ.get("NXKIT_WORKSPACE", "")
        for piece in extra.split(os.pathsep):
            piece = piece.strip()
            if piece:
                roots.append(Path(piece).resolve())
        allow = os.environ.get("NXKIT_ALLOW_EXECUTE", "1").strip().lower()
        # Path restriction is opt-in: a local desktop user routinely opens parts
        # outside the repo, so only lock paths when NXKIT_WORKSPACE is set.
        return cls(
            roots,
            allow not in ("0", "false", "no", "off"),
            enforce_paths=bool(extra.strip()),
        )

    def check_path(self, raw_path):
        if not self.enforce_paths:
            return Path(str(raw_path))
        candidate = Path(str(raw_path))
        if not candidate.is_absolute():
            candidate = self.workspace_roots[0] / candidate
        resolved = candidate.resolve()
        for root in self.workspace_roots:
            if resolved == root or root in resolved.parents:
                return resolved
        raise SecurityError(
            "路径不在允许的工作区内：%s（允许：%s）"
            % (resolved, ", ".join(str(root) for root in self.workspace_roots))
        )

    def check_args(self, args):
        for key, value in args.items():
            if key not in PATH_KEYS:
                continue
            if isinstance(value, str) and value:
                self.check_path(value)


def walk_would_do(tool, args):
    return {"dry_run": True, "tool": tool.name, "cmd": tool.route.get("cmd"), "args": args}
