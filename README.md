# NX Agent Kit

契约驱动的 Siemens NX Agent 运行时：MCP 是手，Skill 是脑。

- `contract/` — 唯一权威：工具、命令、结果信封、经验条目、判据、版本矩阵
- `runtime/nxkit/` — Python 3.12 MCP host（stdio JSON-RPC）
- `bridge/` — NX 内 Python 桥（3.3 语法下限，兼容 NX10 内嵌 Python 3.3.2）
- `skills/` — Agent 流程包（nx-modify / nx-mold-template / nx-plugin-verify）
- `evals/` — 金标准任务与跑批

设计规格见 `docs/superpowers/specs/2026-11-18-nx-agent-kit-design.md`。
