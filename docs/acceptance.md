# NX Agent Kit v1 验收清单

> 实测环境：NX 10.0.0.24（内嵌 Python 3.3.2，`UGII\run_journal.exe`），
> 宿主 Python 3.12.14。测试日期：2026-11-18。

## 已验证（NX10 交互式真机，2026-11-18 22:19）

启动方式：桥的 `startup\nx_agent_kit.py` 部署到 NX10 的 `UGII_USER_DIR\startup`（同时把
`<RuntimeHome>\bridge` 追加进 `custom_dirs.dat`），NX10 启动时自动加载；
Win32 `SetTimer(250ms)` 在 UI 线程 tick，单实例互斥锁防重复加载。

| 项 | 结果 |
|---|---|
| `nx_status` | ✅ 自动识别活会话（另一个已死的 NX 会话按心跳标 `alive:false`，不再被选中） |
| `nx_part action=new` | ✅ 新建零件 `interactive.prt` |
| `nx_block 50×40×30` | ✅ 体积 60000，bbox `[0,0,0,50,40,30]`，面 6 / 边 12，表面积 9400 |
| `nx_measure` | ✅ 实测 facts 回传（`verify.facts`） |
| `nx_hole φ8 通孔` | ✅ 体积 58492.0355（理论 58492.04），面 7 / 边 14 |
| `nx_inspect` | ✅ `BLOCK(0)` 清单 + facts，part=`interactive` |
| `nx_fillet radius=2`（全边） | ✅ `BLEND(1)`，面 26/边 48，体积 59598.68（算例：50×40×30 圆角） |
| `nx_chamfer width=1.5`（全边） | ✅ `CHAMFER(1)`，面 26/边 48，体积 59478.0 |
| `nx_boolean unite`（两体） | ✅ `UNITE(2)`，体积 40000（50×40×20 ∪ 20³，扣重叠 8000） |
| `nx_move_face delta=[0,0,2]`（顶面） | ✅ z 从 30 → 32，体积 64000；NX10 的 MoveFace 是 direct-edit，`feature=null` |
| `nx_save`（另存为） | ✅ `saved_live.prt` 已落盘 |
| `nx_extrude`（4 点矩形→拉伸 5） | ✅ `EXTRUDE(0)`，体积 1000（20×10×5） |
| `nx_revolve`（矩形绕 Y 轴 360°） | ✅ `REVOLVED(0)`，体积 9424.778 = π(20²−10²)×10 |
| `nx_screenshot` | ✅ NX10 降级成功：NX 进程内 Win32 PrintWindow（PW_RENDERFULLCONTENT）抓主窗口，含 OpenGL 模型视口；zlib 自写 PNG（1634×1174）。窗口最小化时返回明确错误 |

> 桥支持热重载（NX 不必重启）：`nx_run_python` 里执行
> `import sys, imp; [imp.reload(sys.modules[m]) for m in ('commands.model','commands.query','commands.part','commands.view','commands.exec')]; import commands; imp.reload(commands)`
> （NX10 的 Python 3.3 用 `imp.reload`，不是 `importlib.reload`）。

## 另已验证（NX10 无头，run_journal）

| 项 | 结果 |
|---|---|
| `deploy/probe.ps1` 扫描 NX10 | ✅ `contract/matrix/NX_10.0.json`：版本 10.0.0.24，`py=3.3`，`xml=true` |
| `run_journal` 无头执行 | ✅ NXKIT_BEGIN / NXKIT_OK，热启动约 11–13 s |
| `nx_part action=new` | ✅ 生成内存零件 `live_nx10_2` |
| `nx_block 50×40×30` | ✅ 体积 60000，bbox `[0,0,0,50,40,30]`，面 6 / 边 12 |
| `nx_hole d=8 通孔` | ✅ 体积 58492.04（理论 58492.04），面 7 / 边 14 |
| `nx_inspect` | ✅ 体清单 `BLOCK(0)` + facts |
| `nx_measure` | ✅ 返回体积/包围盒/面数 |
| API 知识库 | ✅ 从本机 `UGII\managed\NXOpen.xml` 建索引：75,562 成员，3.6 s，61 MB；`ExtrudeBuilder` / `CreateBlockFeatureBuilder` 检索命中且排序正确 |

复跑命令：

```powershell
$env:NXKIT_NX_ROOT = "D:\Program Files\Siemens\NX 10.0"
pytest tests\headless.py -v
```

## 一键自检（有头）

```powershell
.\deploy\smoke.ps1 -RuntimeHome "<repo>"
```

成功最后一行 `RESULT: OK`；失败看 `RESULT: FAIL:<code>`、`MSG:` 与 `NEXT:`。退出码 0/1/2
（2 = 契约/io/会话预检失败）。启动器默认优先用 `<RuntimeHome>\.venv\Scripts\python.exe`，
找不到再退回 PATH 的 `python.exe`；找不到为 `RESULT: FAIL:PYTHON`，版本 < 3.12 为
`RESULT: FAIL:PYTHON_VERSION`，都是退出码 2。加 `-Clean` 先删旧的 `io\smoke\smoke-*.prt`。

## 待验证（需要桥加载到 NX 会话）

| 项 | 前置 |
|---|---|
| 交互式 `nx_status` / `nx_block` / `nx_measure` | 把 `<RuntimeHome>\bridge` 加进 NX 的 `custom_dirs.dat`，重启 NX10，再跑 `NXKIT_IO_DIR=<repo>\io pytest tests\live.py -v` |
| `nx_screenshot` | 同上（需要图形窗口） |
| NX2512 双版本 | 打开 2512 并重复上述步骤 |
| `nx_fillet` / `nx_chamfer` / `nx_extrude` / `nx_revolve` / `nx_move_face` | 桥内仍是"待校准"错误；用 `nx_api` 查签名后逐个实机验证 |

## 已验证（NX 2512 交互式真机，2026-11-18 23:1x）

桥由同一份 3.3 兼容代码在 NX2512（内嵌 Python 3.12.11）上自动加载，无需改代码：

| 项 | 结果 |
|---|---|
| `nx_status` | ✅ 自动识别 2512 会话（py=3.12.11），NX10 死会话标 `alive:false` |
| `nx_part / nx_block 50×40×30` | ✅ 体积 60000 |
| `nx_hole φ8 通孔` | ✅ 体积 58492.0355，面 7 / 边 14 |
| `nx_measure` | ✅ 实测 facts |
| `nx_screenshot` | ✅ 原生 `ImageExportBuilder` 导出 926×945 PNG（仅视口，无 UI） |
| `nx_fillet R2` | ✅ `BLEND(2)`，体积 58042.7466 |

## 新增工具（2026-11-18 23:2x，NX10 实测）

| 项 | 结果 |
|---|---|
| `nx_shell`（壁厚 2，顶面开口） | ✅ `SHELL(1)`，体积 13632 = 60000 − 46×36×28（需显式 `Tolerance=0.01`） |
| `nx_delete_body` | ✅ `Delete Body(2)`，删除后活体 1 个（NX 残留零面死体已在 inspect 中过滤） |

## 已知限制

- 交互式桥需重启 NX 生效（NX 启动时扫描 startup 目录）。
- 占位命令（上表 5 个）在 `contract` 里标 `expected`，实机校准后改 `verified`。
- 无头模式不能截图；无头截图需求走 `Drafting` 导 PDF 或 STL 离线渲染。
- 本机 NX 版本混装（NX10 与 2512），跑测试时用 `NXKIT_NX_ROOT` 明确指定。




