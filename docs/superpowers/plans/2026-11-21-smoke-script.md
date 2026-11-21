# 冒烟自检脚本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一条命令验证 NX 桥已加载、能建出 50×40×30 的块且量回体积正确，输出 `RESULT: OK|FAIL:<code>`。

**Architecture:** `deploy/smoke.ps1` 只做启动器（设 `PYTHONPATH`、透传退出码）；`runtime/nxkit/smoke.py` 承载全部步骤逻辑，只依赖 `Router.call` / `Router.bridge.sessions`，因此可用假 Router 离线单测。与 `auto_ingest` 同构。

**Tech Stack:** Python 3.12 标准库；PowerShell 5.1；pytest（仓库自带 `.deps`）。

**Spec:** `docs/superpowers/specs/2026-11-21-smoke-script-design.md`

## Global Constraints

- host 侧 Python 3.12，零第三方依赖；本功能不进 NX，不受 bridge 的 3.3 语法限制。
- `RESULT:` / `STEP` 行固定为 ASCII；路径允许含中文（stdout 显式 UTF-8）。
- 冒烟件名唯一：`smoke-<UTC yyyyMMdd-HHmmss>-<6 hex>.prt`，放 `io/smoke/`。
- Router 不接 `oplog`，不传 `security` / `precheck` / `headless` / `templates` / `kb`。
- 所有 `nx_*` 调用带 `skip_search: true` 和 `timeout_s`。
- 退出码：`0` OK；`1` 执行/判定失败；`2` 预检失败（`CONTRACT` / `IO_DIR` / `NO_SESSION`）。
- 测试前置（pytest 不在 venv 里）：

  ```powershell
  $env:PYTHONPATH = "$PWD\.deps;$PWD\runtime"
  ```

- **提交规则**：除非用户明确要求，不自动 commit。下文的 Commit 步骤在用户批准后于功能分支上执行。

**与 spec 的一处差异（已在实现中体现）：** spec 步骤表把"含会话目录"放在 `io` 步；本计划把 `io` 步收窄为"目录存在"，"有没有活会话"由 `session` 步判 `NO_SESSION`。这样两种故障能区分为两个失败码。实现时同步改 spec 里 `io` 那一行。

## Review Focus

1. NX 返回 `ok` 但没有 `verify.facts` → 必须 `FAIL:MEASURE`，不能 `KeyError` 崩掉（Task 1）。
2. Router 抛异常或返回 `INTERNAL_ERROR` 信封 → 该步 `FAIL` 且后续步骤不再执行（Task 1）。
3. io 目录存在但为空 vs 有死会话 → 分别得 `IO_DIR` 与 `NO_SESSION`（Task 1 / Task 2）。
4. 同一秒内连跑两次 → 冒烟件名不得冲突（Task 1）。
5. `--no-save` → 不得调用 `nx_save`，该步标 `skipped`（Task 1）。

---

### Task 1: 步骤引擎 `run()` 与冒烟件命名

**Files:**
- Create: `runtime/nxkit/smoke.py`
- Test: `tests/offline/test_smoke.py`

**Interfaces:**
- Consumes: `router.call(name: str, args: dict) -> dict`（结果信封）、`router.bridge.sessions() -> list[dict]`、`router.registry.tools`。
- Produces:
  - `PREFLIGHT_CODES: frozenset[str]` = `{"CONTRACT", "IO_DIR", "NO_SESSION"}`
  - `run(router, io_dir, part_path, *, save=True, timeout_s=120.0) -> dict`
    返回 `{"ok": bool, "code": str | None, "exit_code": int, "steps": [{"name": str, "ok": bool, "detail": str, "error": dict | None}]}`。
    步骤顺序固定为 `contract, io, session, status, part, block, measure, save`。
  - `default_part_path(io_dir, now=None) -> Path`：`<io_dir>/smoke/smoke-<stamp>-<hex>.prt`。

- [ ] **Step 1: 写失败测试**

`tests/offline/test_smoke.py`：

```python
from types import SimpleNamespace

from nxkit.smoke import default_part_path, run

GEOM = {"volume": 60000.0, "bbox": [0, 0, 0, 50, 40, 30]}


class FakeBridge:
    def __init__(self, sessions):
        self._sessions = sessions

    def sessions(self):
        return list(self._sessions)


class FakeRouter:
    def __init__(self, handler, sessions=None):
        self.bridge = FakeBridge(
            sessions
            if sessions is not None
            else [{"pid": 1234, "alive": True, "heartbeat_age_s": 1.0}]
        )
        self.registry = SimpleNamespace(tools={"nx_block": object()})
        self.calls = []
        self._handler = handler

    def call(self, name, args):
        self.calls.append((name, dict(args)))
        return self._handler(name, args)


def _env(ok=True, data=None, facts=None, error=None):
    env = {"ok": ok, "data": data or {}}
    if facts is not None:
        env["verify"] = {"facts": facts}
    if error is not None:
        env["error"] = error
    return env


def _good(name, args):
    if name == "nx_status":
        return _env(data={"connected": True})
    if name == "nx_block":
        return _env(data={"feature": "BLOCK(0)"}, facts=dict(GEOM))
    if name == "nx_measure":
        return _env(data={"body": "BLOCK(0)"}, facts=dict(GEOM))
    return _env(data={})


def _part(workdir):
    return workdir / "smoke" / "p.prt"


def test_run_ok_path(workdir):
    router = FakeRouter(_good)
    result = run(router, workdir, _part(workdir))
    assert result["ok"] is True
    assert result["code"] is None
    assert result["exit_code"] == 0
    assert [s["name"] for s in result["steps"]] == [
        "contract", "io", "session", "status", "part", "block", "measure", "save",
    ]
    assert router.calls[-1][0] == "nx_save"


def test_run_no_session_is_preflight(workdir):
    router = FakeRouter(_good, sessions=[])
    result = run(router, workdir, _part(workdir))
    assert result["code"] == "NO_SESSION"
    assert result["exit_code"] == 2
    assert router.calls == []


def test_run_missing_io_dir(workdir):
    missing = workdir / "nope"
    result = run(FakeRouter(_good), missing, missing / "smoke" / "p.prt")
    assert result["code"] == "IO_DIR"
    assert result["exit_code"] == 2


def test_measure_without_facts_fails(workdir):
    def handler(name, args):
        if name == "nx_measure":
            return _env(data={"body": "BLOCK(0)"})
        return _good(name, args)

    result = run(FakeRouter(handler), workdir, _part(workdir))
    assert result["code"] == "MEASURE"
    assert result["exit_code"] == 1


def test_measure_rejects_wrong_volume(workdir):
    def handler(name, args):
        if name == "nx_measure":
            return _env(data={"body": "BLOCK(0)"}, facts=dict(GEOM, volume=60010.0))
        return _good(name, args)

    result = run(FakeRouter(handler), workdir, _part(workdir))
    assert result["code"] == "MEASURE"


def test_part_failure_stops_after_part(workdir):
    def handler(name, args):
        if name == "nx_part":
            return _env(ok=False, error={"code": "NX_ERROR", "msg": "boom"})
        return _good(name, args)

    router = FakeRouter(handler)
    result = run(router, workdir, _part(workdir))
    assert result["code"] == "PART"
    assert [name for name, _ in router.calls] == ["nx_status", "nx_part"]


def test_router_exception_becomes_step_failure(workdir):
    def handler(name, args):
        raise RuntimeError("boom")

    result = run(FakeRouter(handler), workdir, _part(workdir))
    assert result["ok"] is False
    assert result["code"] == "STATUS"


def test_no_save_skips_nx_save(workdir):
    router = FakeRouter(_good)
    result = run(router, workdir, _part(workdir), save=False)
    assert result["ok"] is True
    assert all(name != "nx_save" for name, _ in router.calls)
    assert [s for s in result["steps"] if s["name"] == "save"][0]["detail"] == "skipped"


def test_default_part_path_is_unique_and_under_smoke(workdir):
    first = default_part_path(workdir)
    second = default_part_path(workdir)
    assert first != second
    assert first.parent == workdir / "smoke"
    assert first.name.startswith("smoke-") and first.suffix == ".prt"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\offline\test_smoke.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'nxkit.smoke'`。

- [ ] **Step 3: 实现 `runtime/nxkit/smoke.py`**

签名与行为（body 由实现者写）：

```python
PREFLIGHT_CODES = frozenset({"CONTRACT", "IO_DIR", "NO_SESSION"})

def run(router, io_dir, part_path, *, save=True, timeout_s=120.0) -> dict: ...
def default_part_path(io_dir, now=None) -> Path: ...
```

实现要点：
- 每个步骤失败即返回，不再执行后续步骤；`exit_code` 由失败码是否在 `PREFLIGHT_CODES` 决定（在 → 2，否则 → 1）。
- `contract` 步：`router.registry` 存在且 `router.registry.tools` 非空，否则 `CONTRACT`。
- `io` 步：`Path(io_dir).is_dir()`，否则 `IO_DIR`。
- `session` 步：`router.bridge.sessions()` 中取第一个 `alive`（优先 `heartbeat_age_s < 300`，规则同 `Router._pick_session`）；无则 `NO_SESSION`。异常按 `NO_SESSION` 处理。
- `status` 步：`router.call("nx_status", {})`，要求 `ok` 且 `data.connected` 为真。
- `part` 步：先 `part_path.parent.mkdir(parents=True, exist_ok=True)`，再 `router.call("nx_part", {"action": "new", "path": str(part_path), "timeout_s": timeout_s})`。
- `block` 步：`{"length": 50, "width": 40, "height": 30, "skip_search": True, "timeout_s": timeout_s}`。
- `measure` 步：`{"target": "last", "skip_search": True, "timeout_s": timeout_s}`；从信封 `verify.facts` 取 `volume`/`bbox`，缺任一或 `abs(volume - 60000.0) > 1.0` 或 bbox 不等于 `[0, 0, 0, 50, 40, 30]` → `MEASURE`。
- `save` 步：`save=False` 时记录 `detail="skipped"`；否则 `{"path": str(part_path), "timeout_s": timeout_s}`。
- 单步 `router.call` 抛异常时，把该步标失败，`detail="EXCEPTION"`，`error={"code": "EXCEPTION", "msg": repr(exc)}`，用该步自己的失败码。
- 信封 `ok` 为假时，把 `envelope["error"]` 存进步骤记录，失败码用该步的码。
- `default_part_path`：`now` 默认 `datetime.now(timezone.utc)`，格式 `%Y%m%d-%H%M%S`，后缀 `uuid.uuid4().hex[:6]`。

- [ ] **Step 4: 跑测试确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests\offline\test_smoke.py -q`
Expected: 9 passed。

- [ ] **Step 5: 同步 spec 的 io 行并提交**

把 `docs/superpowers/specs/2026-11-21-smoke-script-design.md` 步骤表第 2 行改为"io 根存在"。
Run: `git add runtime/nxkit/smoke.py tests/offline/test_smoke.py docs/superpowers/specs/2026-11-21-smoke-script-design.md && git commit -m "feat(smoke): step engine for live bridge self-check"`（需用户批准提交后执行）。

---

### Task 2: CLI `main()` 与退出码

**Files:**
- Modify: `runtime/nxkit/smoke.py`
- Test: `tests/offline/test_smoke.py`

**Interfaces:**
- Consumes: Task 1 的 `run`、`default_part_path`、`PREFLIGHT_CODES`。
- Produces: `main(argv=None) -> int`；CLI 参数 `--io`（必填）、`--contract`、`--library`、`--part`、`--no-save`、`--timeout-s`、`--clean`。

- [ ] **Step 1: 写失败测试**

在 `tests/offline/test_smoke.py` 顶部补 `import json`、`from pathlib import Path`、`import nxkit.smoke as smoke`、`REPO = Path(__file__).resolve().parents[2]`，然后追加：

```python
def _argv(workdir, io, *extra):
    return [
        "--io", str(io),
        "--contract", str(REPO / "contract"),
        "--library", str(workdir / "library"),
        *extra,
    ]


def _dead_session(io, pid=999):
    (io / str(pid)).mkdir(parents=True)
    (io / str(pid) / "status.json").write_text(
        json.dumps({"pid": pid, "alive": True, "updated": 0}), encoding="utf-8"
    )


def test_main_reports_contract_error(workdir, capsys):
    bad = workdir / "bad_contract"
    bad.mkdir()
    rc = smoke.main([
        "--io", str(workdir / "io"),
        "--contract", str(bad),
        "--library", str(workdir / "library"),
    ])
    assert rc == 2
    assert "RESULT: FAIL:CONTRACT" in capsys.readouterr().out


def test_main_reports_no_session(workdir, capsys):
    io = workdir / "io"
    _dead_session(io)
    rc = smoke.main(_argv(workdir, io))
    assert rc == 2
    assert "RESULT: FAIL:NO_SESSION" in capsys.readouterr().out


def test_main_prints_ok_and_returns_zero(workdir, monkeypatch, capsys):
    monkeypatch.setattr(
        smoke, "run",
        lambda *a, **k: {
            "ok": True, "code": None, "exit_code": 0,
            "steps": [{"name": "contract", "ok": True, "detail": "", "error": None}],
        },
    )
    rc = smoke.main(_argv(workdir, workdir))
    out = capsys.readouterr().out
    assert rc == 0
    assert "STEP contract: OK" in out
    assert out.strip().splitlines()[-1] == "RESULT: OK"


def test_main_clean_removes_old_smoke_parts(workdir, monkeypatch, capsys):
    io = workdir / "io"
    old = io / "smoke" / "smoke-old.prt"
    old.parent.mkdir(parents=True)
    old.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        smoke, "run",
        lambda *a, **k: {"ok": True, "code": None, "exit_code": 0, "steps": []},
    )
    rc = smoke.main(_argv(workdir, io, "--clean"))
    assert rc == 0
    assert not old.exists()


def test_main_prints_next_on_failure(workdir, monkeypatch, capsys):
    monkeypatch.setattr(
        smoke, "run",
        lambda *a, **k: {
            "ok": False, "code": "BLOCK", "exit_code": 1,
            "steps": [{
                "name": "block", "ok": False, "detail": "NX_ERROR",
                "error": {"code": "NX_ERROR", "msg": "boom", "next": "check target"},
            }],
        },
    )
    rc = smoke.main(_argv(workdir, workdir))
    out = capsys.readouterr().out
    assert rc == 1
    assert "RESULT: FAIL:BLOCK" in out
    assert "NEXT: check target" in out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\offline\test_smoke.py -q -k main`
Expected: FAIL，`AttributeError: module 'nxkit.smoke' has no attribute 'main'`。

- [ ] **Step 3: 实现 `main()`**

要点：
- `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`（防御 GBK 控制台）。
- `--clean`：删除 `<io>/smoke/smoke-*.prt`，在 `run` 之前。
- 构造 `Registry(contract)`；`ContractError` → 打印 `STEP contract: FAIL`、`RESULT: FAIL:CONTRACT`，返回 2。
- 构造 `BridgeClient(io)`、`Library(library).init()`、`Gate(io / "workflow.json")`、`Router(registry, bridge, library, gate, expose="all")`。
- 未传 `--part` 时用 `default_part_path(io)`。
- 打印首行 `SMOKE io=<io> contract=<contract> part=<part>`。
- 每个步骤打印 `STEP <name>: OK[ <detail>]` 或 `STEP <name>: FAIL <detail>`；失败时若有 `error.next` 再打印 `NEXT: <next>`。
- 末尾 `RESULT: OK` / `RESULT: FAIL:<code>`，返回 `result["exit_code"]`。
- 未捕获异常 → `RESULT: FAIL:INTERNAL`、返回 1。

- [ ] **Step 4: 跑全部冒烟测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests\offline\test_smoke.py -q`
Expected: 14 passed。

- [ ] **Step 5: 跑全量离线套件**

Run: `.\.venv\Scripts\python.exe -m pytest tests\offline -q`
Expected: 全绿（原 119+ 通过，无新增失败）。

- [ ] **Step 6: 提交**（需用户批准）

```bash
git add runtime/nxkit/smoke.py tests/offline/test_smoke.py
git commit -m "feat(smoke): CLI with result codes and clean flag"
```

---

### Task 3: PowerShell 启动器与文档入口

**Files:**
- Create: `deploy/smoke.ps1`
- Modify: `tests/offline/test_deploy.py`（新增一个测试，补 `import sys`）
- Modify: `docs/acceptance.md`（加"一键自检"一行）
- Modify: `contract/tools/meta.json`（`nx_status.next` 里的失效引用 `one_click` → `deploy/smoke.ps1`）

**Interfaces:**
- Consumes: Task 2 的 `python -m nxkit.smoke --io ... --contract ... --library ... [--clean] [--timeout-s N]`。
- Produces: `deploy/smoke.ps1 -RuntimeHome <dir> [-IoDir <dir>] [-PythonExe <exe>] [-Clean] [-TimeoutSec <n>]`，退出码与 Python 一致。

- [ ] **Step 1: 写失败测试**

在 `tests/offline/test_deploy.py` 顶部补 `import sys`，追加：

```python
def test_smoke_script_reports_no_session(workdir):
    io = workdir / "io"
    (io / "999").mkdir(parents=True)
    (io / "999" / "status.json").write_text(
        '{"pid": 999, "alive": true, "updated": 0}', encoding="utf-8"
    )
    result = _run(
        REPO / "deploy" / "smoke.ps1",
        "-RuntimeHome", REPO,
        "-IoDir", io,
        "-PythonExe", sys.executable,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "RESULT: FAIL:NO_SESSION" in result.stdout
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\offline\test_deploy.py -q -k smoke`
Expected: FAIL（`smoke.ps1` 不存在，PowerShell 非零退出且无 RESULT 行）。

- [ ] **Step 3: 实现 `deploy/smoke.ps1`**

```powershell
param(
    [string]$RuntimeHome = (Split-Path -Parent $PSScriptRoot),
    [string]$IoDir,
    [string]$PythonExe = "python.exe",
    [switch]$Clean,
    [int]$TimeoutSec = 120
)
$ErrorActionPreference = "Stop"
if (-not $IoDir) { $IoDir = Join-Path $RuntimeHome "io" }
$env:PYTHONPATH = Join-Path $RuntimeHome "runtime"
$env:PYTHONIOENCODING = "utf-8"
$pyArgs = @(
    "-m", "nxkit.smoke",
    "--io", $IoDir,
    "--contract", (Join-Path $RuntimeHome "contract"),
    "--library", (Join-Path $RuntimeHome "library"),
    "--timeout-s", "$TimeoutSec"
)
if ($Clean) { $pyArgs += "--clean" }
& $PythonExe @pyArgs
$code = $LASTEXITCODE
if ($null -eq $code) { $code = 2 }
exit $code
```

- [ ] **Step 4: 跑两个脚本测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests\offline\test_deploy.py -q`
Expected: 5 passed。

- [ ] **Step 5: 更新文档与契约提示**

- `docs/acceptance.md` 的"复跑命令"块后加：

  ```markdown
  ## 一键自检（有头）

  ```powershell
  .\deploy\smoke.ps1 -RuntimeHome "D:\NX_Agent\nx-agent-kit"
  ```
  成功最后一行 `RESULT: OK`；失败看 `RESULT: FAIL:<code>` 与 `NEXT:`。退出码 0/1/2。
  ```

- `contract/tools/meta.json` 的 `nx_status.next` 改为：
  `"未连接先跑 deploy/install.ps1 或 deploy/smoke.ps1；多开先用 sessions 里的 pid"`。

- [ ] **Step 6: 全量离线套件**

Run: `.\.venv\Scripts\python.exe -m pytest tests\offline -q`
Expected: 全绿。

- [ ] **Step 7: 真机验证（人工，可选）**

NX10 打开、桥已加载：
`.\.venv\Scripts\python.exe -m nxkit.smoke --io D:\NX_Agent\nx-agent-kit\io --contract D:\NX_Agent\nx-agent-kit\contract --library D:\NX_Agent\nx-agent-kit\library`
Expected: 8 行 `STEP ...: OK`，末行 `RESULT: OK`，退出码 0。

- [ ] **Step 8: 提交**（需用户批准）

```bash
git add deploy/smoke.ps1 tests/offline/test_deploy.py docs/acceptance.md contract/tools/meta.json
git commit -m "feat(deploy): one-command live bridge smoke check"
```

---

## 自检记录

- **Spec 覆盖**：8 个步骤 → Task 1；输出契约与退出码 → Task 2；ps1 与文档 → Task 3；清理策略 → Task 2（`--clean`）+ Task 3（参数）；测试计划 → Task 1/2/3 各自步骤。
- **Review Focus**：5 条均在 Task 1 有对应测试（缺 facts、异常、IO_DIR/NO_SESSION、唯一命名、no-save）。
- **类型一致性**：`run` 返回键 `ok/code/exit_code/steps` 在 Task 1 定义、Task 2 消费；步骤键 `name/ok/detail/error` 在两处一致。
- **比例**：实现约 140 行 + ps1 约 25 行，计划中的代码块以测试为主。
