# 冒烟自检脚本设计（deploy/smoke.ps1 + nxkit.smoke）

日期：2026-11-21  
状态：待批准

## 意图

部署或重启 NX 之后，用一个命令回答"桥到底通没通、NX 能不能真的建出几何"。
现在只有两条路：人工照 `docs/acceptance.md` 点一遍，或者跑 pytest（依赖 `.deps`、
没有会话时是 `skip`），都不适合安装脚本或 CI 消费。

## 目标

- 只测有头桥：契约 → io 根 → 活会话 → status → 建件 → 建块 → 量体积 → 保存。
- 输出 `RESULT: OK` / `RESULT: FAIL:<code>`，退出码 0 / 1 / 2。
- 失败时带 `error.msg` + `error.next`，直接告诉人下一步做什么。
- 逻辑可离线单测（注入假 Router）。

## 非目标

- 无头 / `run_journal`（`tests/headless.py`、evals 已覆盖）。
- MCP 协议握手（`tests/offline/test_server.py` 已覆盖）。
- 全工具面（evals T1/T2 已覆盖）。
- 测 `nx_run_python`（安全边界另行验证）。

## 约束

- host Python 3.12，只用标准库；PowerShell 5.1。
- 输出行保持 ASCII（Windows 控制台默认 GBK；中文只可能出现在 NX 返回的
  `error.msg` 里，由 Python 侧统一以 UTF-8 写出）。
- `io/`、`library/` 是运行期数据，冒烟产物放 `io/smoke/`。

## 方案与选择

- **A. 全写进 `smoke.ps1`，用 `python -c` 内联**：单文件，但多层引号不可维护，
  也没法单测。否决。
- **B. `smoke.ps1` 启动器 + `runtime/nxkit/smoke.py`**：逻辑可测、可复用 Router、
  能被 `install.ps1` 随 `runtime/` 拷走，和 `auto_ingest` 同构。**选中。**
- **C. 包一层 `pytest tests/live.py`**：多一个 `.deps` 依赖；无会话时 `skip` 而非
  `fail`，语义与自检相反。否决。

## 设计

### 文件

- `runtime/nxkit/smoke.py`
  - `run(router, io_dir, part_path, *, save=True, timeout_s=120.0) -> dict`：
    纯步骤逻辑，返回 `{ok, code, steps:[{name, ok, data|error}]}`；不读环境、
    不构造 Router。
  - `main(argv=None) -> int`：解析参数、构造最小 Router、调用 `run`、打印、
    返回退出码。
- `deploy/smoke.ps1`：参数 `-RuntimeHome` `-IoDir` `-PythonExe` `-Clean`
  `-TimeoutSec`；设置 `PYTHONPATH=<RuntimeHome>\runtime`，调用
  `python -m nxkit.smoke --io ... --runtime-home ...`，透传退出码。

### 步骤与失败码

| # | 步骤 | 检查 | 失败码 |
|---|---|---|---|
| 1 | contract | `Registry(contract)` 能加载 | `CONTRACT` |
| 2 | io | io 根存在（是否有活会话由第 3 步判断） | `IO_DIR` |
| 3 | session | `bridge.sessions()` 有 `alive: true` | `NO_SESSION` |
| 4 | status | `nx_status` 返回 connected | `STATUS` |
| 5 | part | `nx_part new` 到 `io/smoke/smoke-<UTC 时间戳>.prt` | `PART` |
| 6 | block | `nx_block` 50×40×30 + `skip_search` | `BLOCK` |
| 7 | measure | 体积 ≈ 60000（±1.0），bbox `[0,0,0,50,40,30]` | `MEASURE` |
| 8 | save | `nx_save` | `SAVE` |

- 1–3 是预检，失败退出码 `2`；4–8 是执行/判定，失败退出码 `1`。
- 第 5 步用唯一文件名是硬要求：见 `docs/evals.md` 已知坑 #1（重跑撞已有件会
  跑在旧件上）。
- 所有 `nx_*` 调用带 `skip_search: true` 和 `timeout_s`；冒烟不是学习路径，
  不应被经验闸门拦，也不应写经验。

### Router 组成

- `Registry(contract)`、`BridgeClient(io)`、`Library(library_root).init()`、
  `Gate(io/workflow.json)`。
- **不传** `oplog`：冒烟调用不得进入 `oplog.jsonl`，否则会被 auto_ingest
  聚成经验草稿。
- **不传** `security` / `precheck` / `headless` / `templates` / `kb`：与本检查无关；
  且 security 的路径白名单在自检里只会添乱。
- 会话选择复用 `Router._pick_session` 的规则（alive + 心跳）。

### 输出契约

成功：

```
SMOKE io=D:\...\io sessions=1 pid=1234
STEP contract: OK
STEP io: OK
STEP session: OK
STEP status: OK
STEP part: OK D:\...\io\smoke\smoke-20261121-101530.prt
STEP block: OK volume=60000.0
STEP measure: OK
STEP save: OK D:\...\smoke-20261121-101530.prt
RESULT: OK
```

失败：

```
RESULT: FAIL:NO_SESSION
NEXT: restart NX (bridge loads at startup); check NXKIT_IO_DIR matches the bridge io root
```

退出码：`0` OK；`1` 执行/判定失败；`2` 预检/参数/环境失败。

### 清理

- 默认保留冒烟件（失败时要看）。
- `-Clean` 在开跑前删除 `io/smoke/` 下旧的 `smoke-*.prt`，不删本次产物。

### 测试

- `tests/offline/test_smoke.py`
  - `run()` 注入假 router：覆盖 OK 全链路、block 失败、体积不符（`MEASURE`）、
    part 失败。
  - 假 bridge 只需 `sessions()`；假 router 按顺序返回信封。
- `deploy/smoke.ps1` 冒烟（不碰 NX）：临时 io 目录 + `-PythonExe <sys.executable>`
  → 期望 `RESULT: FAIL:NO_SESSION`、退出码 2；再用损坏的契约目录 → 期望
  `FAIL:CONTRACT`。
- 真机验证：NX10 打开且桥已加载，跑一次应得 `RESULT: OK`。

## 留给实现者

- 体积容差取 1.0（相对 60000 约 1.7e-5），沿用 `tests/headless.py` 的口径。
- `-Json` 机器可读输出暂不做；当前 STEP/RESULT 行够人看，CI 看退出码。
