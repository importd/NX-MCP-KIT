# NX Agent Kit

Connects DeepSeek Harness to a running Siemens NX session through the
`nxkit` MCP server (stdio, Python standard library only).

## What it provides

- Modeling tools: block, hole, fillet, chamfer, boolean, shell, delete body,
  extrude, revolve, move face, part open/save.
- Query tools: inspect part, map geometry, screenshot.
- Safety and verification: precheck, `nx_assert`, undo/rollback marks,
  snapshots, dry-run, workspace path guard.
- Experience library: search/get/replay verified steps; auto-ingest from an
  append-only operation log (drafts are replayed in a fresh part before they
  become searchable).

## Requirements

- An open NX session with the bridge loaded from a startup directory
  (`nx_agent_kit.py`). The bridge polls `io/<pid>/inbox` every 250 ms.
- `NXKIT_IO_DIR` pointing at the bridge io root.

## Limitations

- NX is single-threaded for modeling: one command at a time; the bridge runs
  on the NX UI thread.
- The bridge must match the NX Python version (3.3 on NX 10, 3.12 on newer).
- Tools report `BRIDGE_UNAVAILABLE` when no live session is found.
