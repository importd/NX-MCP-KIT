# NX Agent Kit v1 验收清单

> 实测环境：NX 10.0.0.24（内嵌 Python 3.3.2，`UGII\run_journal.exe`），
> 宿主 Python 3.12.14（DSH 运行时）。测试日期：2026-11-18。

## 已验证（NX10 无头真机）

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

## 待验证（需要桥加载到 NX 会话）

| 项 | 前置 |
|---|---|
| 交互式 `nx_status` / `nx_block` / `nx_measure` | 把 `<RuntimeHome>\bridge` 加进 NX 的 `custom_dirs.dat`，重启 NX10，再跑 `NXKIT_IO_DIR=<repo>\io pytest tests\live.py -v` |
| `nx_screenshot` | 同上（需要图形窗口） |
| NX2512 双版本 | 打开 2512 并重复上述步骤 |
| `nx_fillet` / `nx_chamfer` / `nx_extrude` / `nx_revolve` / `nx_move_face` | 桥内仍是"待校准"错误；用 `nx_api` 查签名后逐个实机验证 |

## 已知限制

- 交互式桥需重启 NX 生效（NX 启动时扫描 startup 目录）。
- 占位命令（上表 5 个）在 `contract` 里标 `expected`，实机校准后改 `verified`。
- 无头模式不能截图；无头截图需求走 `Drafting` 导 PDF 或 STL 离线渲染。
- 本机 NX 版本混装（NX10 与 2512），跑测试时用 `NXKIT_NX_ROOT` 明确指定。
