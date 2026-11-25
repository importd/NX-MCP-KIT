# NX Agent Kit

> Contract-first MCP runtime for driving Siemens NX from an AI agent.
> **MCP is the hands; Skills are the brain.**

契约驱动的 Siemens NX Agent 运行时。它把「Agent → MCP → NX 会话」这条链路固定成可验证的契约：工具、命令、结果信封、判据与版本矩阵都写在 `contract/` 里；宿主运行时只负责路由、校验、快照/回滚与经验沉淀；NX 内的桥只负责在 UI 线程执行命令。

## 特性

- **零第三方依赖**：宿主只依赖 Python 3.12 标准库，MCP 传输在仓库内实现（stdio JSON-RPC 2.0，协议 `2024-11-05`）。适合内网/离线安装。
- **双版本支持**：NX 10.0（内嵌 Python 3.3.2）与 NX 2512（Python 3.12）。桥代码按 Python 3.3 语法写，向下兼容老版本。
- **契约驱动**：`contract/` 是唯一权威。工具 schema、路由命令、返回信封、版本矩阵、判据模板都由 JSON 声明，运行时在加载时校验。
- **可验证的改动**：几何操作支持预检（`nx_check`）→ 执行 → 实测（`nx_measure`）→ 断言（`nx_assert`）；改动前可建快照，失败可回滚。
- **经验库**：成功路径可沉淀为经验条目；操作流水自动聚合、在全新零件中重放验证后才进入可检索库。
- **评测**：内置黄金任务（T1 原子操作 / T2 单件建模）与 headless 跑批评分管线，见 [docs/evals.md](docs/evals.md)。

## 架构

```
┌────────────┐    MCP (stdio JSON-RPC)    ┌────────────────────┐
│  AI Agent  │ ─────────────────────────▶ │   nxkit runtime    │
│ (MCP host) │ ◀───────────────────────── │ registry / router  │
└────────────┘    result envelope         └─────────┬──────────┘
                                                    │ file bridge
                                                    │ io/<pid>/inbox|outbox
                                          ┌─────────▼──────────┐
                                          │ NX embedded Python │
                                          │ bridge (UI thread, │
                                          │ 250 ms timer)      │
                                          └────────────────────┘
```

宿主与 NX 通过本地文件桥通信：宿主写入 `io/<pid>/inbox/`，NX 内的桥在 UI 线程每 250 ms 轮询一次，执行后将结果写到 `outbox/`。因此宿主和 NX 必须运行在同一台机器、同一文件系统上。

## 目录结构

```
contract/        契约：工具、命令、schema、模板、版本矩阵
runtime/nxkit/   宿主运行时：MCP server、路由器、校验、快照、经验库、评测
bridge/          NX 内 Python 桥（Python 3.3 语法下限）
skills/          Agent 流程包（nx-modify / nx-mold-template / nx-plugin-verify）
evals/           黄金任务与跑批评分
deploy/          PowerShell 安装、探测、同步、冒烟脚本
tests/           离线测试（不需要 NX）与真机测试
docs/            验收清单、评测说明、操作流水说明
```

## 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10/11 |
| NX | Siemens NX 10.0 或 NX 2512（交互式会话） |
| 宿主 Python | 3.12+（只用标准库） |
| PowerShell | 5.1+（部署脚本） |

> NX 内嵌的 Python 版本必须与桥匹配：NX 10 = 3.3.2，NX 2512 = 3.12。

## 快速开始

### 1. 准备宿主环境

```powershell
git clone https://github.com/importd/NX-MCP-KIT.git nx-agent-kit
cd nx-agent-kit
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# 宿主无第三方依赖；运行时把 runtime\ 放进 PYTHONPATH 即可
$env:PYTHONPATH = "$PWD\runtime"
```

### 2. 部署运行时并生成 MCP 配置

```powershell
.\deploy\install.ps1 `
  -RuntimeHome D:\nxkit-runtime `
  -StartupDir "<UGII_USER_DIR>\startup" `
  -CustomDirsFile "<NX>\UGII\custom_dirs.dat"
```

脚本会把 `bridge/`、`runtime/`、`contract/`、`skills/` 复制到 `-RuntimeHome`，并在该目录生成 `mcp_config.json`。

- `-StartupDir`：NX 启动时加载桥的目录，建议用 NX 的 `UGII_USER_DIR\startup`；没有设置该环境变量时，用 NX 安装目录下的 `UGII\startup`。
- `-CustomDirsFile`：NX 的 `custom_dirs.dat`；脚本会把桥目录追加进去，已存在则不重复写入。
- 重启 NX 后桥才会加载。

### 3. 确认桥已连通

在 NX 中打开一个新零件，然后调用 MCP 工具 `nx_status`，应返回 `connected: true` 与当前会话的 pid。

### 4. 接入 MCP 客户端

把 `install.ps1` 生成的 `mcp_config.json` 合并进你的 MCP 客户端配置，例如：

```json
{
  "mcpServers": {
    "nx": {
      "command": "python",
      "args": ["-m", "nxkit.server"],
      "env": {
        "PYTHONPATH": "D:\\nxkit-runtime\\runtime",
        "NXKIT_IO_DIR": "D:\\nxkit-runtime\\io",
        "NXKIT_LIBRARY": "D:\\nxkit-runtime\\library",
        "NXKIT_CONTRACT_DIR": "D:\\nxkit-runtime\\contract",
        "NXKIT_KB_DB": "D:\\nxkit-runtime\\kb\\nxopen.db",
        "NXKIT_EXPOSE": "all",
        "NXKIT_NX_ROOT": "D:\\Program Files\\Siemens\\NX 10.0"
      }
    }
  }
}
```

也可以不部署，直接在仓库里启动：

```powershell
$env:PYTHONPATH = "$PWD\runtime"
python -m nxkit.server
```

### 5. 一键冒烟

确认 NX 已打开、桥已加载后：

```powershell
.\deploy\smoke.ps1 -RuntimeHome D:\nxkit-runtime
```

成功输出 `RESULT: OK`；失败输出 `RESULT: FAIL:<code>`、`MSG:` 与 `NEXT:`，退出码 `1`（执行/判定失败）或 `2`（契约/io/会话预检失败）。

## 工具面

共 31 个工具，按组暴露（`NXKIT_EXPOSE` 可设为 `all`、`catalog` 或逗号分隔的组名）：

| 组 | 工具 |
|---|---|
| `meta` | `nx_status` `nx_find` `nx_help` `nx_call` `nx_job` `exp_search` |
| `part` | `nx_part` `nx_save` `nx_snapshot` |
| `model` | `nx_block` `nx_hole` `nx_fillet` `nx_chamfer` `nx_boolean` `nx_shell` `nx_delete_body` `nx_extrude` `nx_revolve` `nx_move_face` `nx_batch_edit` |
| `query` | `nx_inspect` `nx_measure` `nx_screenshot` |
| `exec` | `nx_check` `nx_run_python` `nx_plan` `nx_batch` `nx_assert` |
| `mold` | `nx_template` |
| `api` | `nx_api` |
| `exp` | `nx_exp` |

每个工具的完整 schema、关键词、返回字段与下一步建议都在 `contract/tools/*.json`。

## 配置项

| 环境变量 | 默认值 | 作用 |
|---|---|---|
| `NXKIT_IO_DIR` | `<repo>/io` | 文件桥根目录；NX 与宿主共享 |
| `NXKIT_LIBRARY` | `<repo>/library` | 经验库目录 |
| `NXKIT_CONTRACT_DIR` | `<repo>/contract` | 契约目录 |
| `NXKIT_KB_DB` | 未设置 | 可选：NXOpen API 知识库 SQLite 路径 |
| `NXKIT_EXPOSE` | `catalog` | 暴露方式：`all` / `catalog` / `model,query,...` |
| `NXKIT_NX_ROOT` | 空 | NX 安装根目录，无头 `run_journal` 模式使用 |
| `NXKIT_WORKSPACE` | 未设置（仅仓库根可写） | 额外的合法工作区根（`os.pathsep` 分隔）；设置后启用路径白名单 |
| `NXKIT_ALLOW_EXECUTE` | `1` | 设为 `0` 禁用 `nx_run_python` |
| `NXKIT_WORKFLOW` | `<io>/workflow.json` | 经验闸门状态文件 |
| `NXKIT_OPLOG` | `<io>/oplog.jsonl` | 操作流水路径（自动沉淀用） |

桥侧还识别 `NXKIT_HOME`（桥根）与 `NXKIT_IO_BASE`（io 根），通常由 `install.ps1` 处理，不需要手动设置。

## 测试

离线测试不需要 NX：

```powershell
pip install pytest
python -m pytest tests/offline -q
```

如果使用仓库内 vendored 的 `.deps`（未提交到 Git）：

```powershell
$env:PYTHONPATH = "$PWD\.deps;$PWD\runtime"
python -m pytest tests/offline -q
```

真机无头测试需要 NX 安装：

```powershell
$env:NXKIT_NX_ROOT = "D:\Program Files\Siemens\NX 10.0"
pytest tests\headless.py -v
```

评测跑批：

```powershell
$env:PYTHONPATH = "$PWD;$PWD\runtime"
python -m evals.v2.run_all --mode headless --tier all --attempts 1 `
  --nx-root "<NX_ROOT>" --baseline nx10
```

## 文档

- [验收清单](docs/acceptance.md)：NX 10.0 真机逐项实测结果
- [评测说明](docs/evals.md)：基线指标、任务分层与复跑方法
- [操作流水与自动沉淀](docs/oplog.md)：`oplog.jsonl` → 经验草稿 → 重放验证的链路
- [nx-modify](skills/nx-modify/SKILL.md)：改现有零件的标准流程
- [nx-mold-template](skills/nx-mold-template/SKILL.md)：模具结构模板化建模
- [nx-plugin-verify](skills/nx-plugin-verify/SKILL.md)：NXOpen 代码静态校验与真机验证

## 已知限制

- NX 对建模是单线程的：所有命令在 NX UI 线程串行执行，一次只能有一个命令在跑。
- 文件桥依赖宿主与 NX 共享同一文件系统，不支持跨机器调用。
- NX 10 的截图走 Win32 `PrintWindow`，窗口最小化时会返回明确错误。
- `nx_run_python` 能执行任意代码；生产部署建议设置 `NXKIT_ALLOW_EXECUTE=0`，并配合 `NXKIT_WORKSPACE` 限制可访问路径。

## 许可证

[MIT](LICENSE)
