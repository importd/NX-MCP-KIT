# 坑位表：错误码 → 原因 → 修法

| 错误码 | 典型原因 | 修法 |
|---|---|---|
| `PRECHECK` / `PY33_FSTRING` | NX10 内嵌 Python 3.3 不支持 f-string | 改 `"…".format(...)` 或 `%` 格式化 |
| `PY33_ANNOTATION` | 变量/参数注解 | 去掉注解，用普通赋值 |
| `PY33_WALRUS` | `:=` | 拆成先赋值再判断 |
| `BUILDER_NO_COMMIT` | Builder 没 Commit | 设完参数后 `CommitFeature()` |
| `BUILDER_NO_DESTROY` | 没 Destroy | `finally: builder.Destroy()` |
| `NX_BUILDER_FIRST_ARG` | `Create<X>Builder` 入参类型不对 | 用 `NXOpen.Features.Feature.Null` 或 `XBuilder.Null` 试；查 `nx_api members=<类>` |
| `NX_BOOL_EMPTY` | 布尔两体不相交 | 先 `nx_inspect` 看包围盒是否重叠 |
| `BRIDGE_TIMEOUT` | 长任务超过 timeout | 用 `nx_job` 跟进；超时任务不会自动重放 |
| `BRIDGE_UNAVAILABLE` | NX 未开 / 桥未加载 | 开 NX 并确认 `nx_status connected=true` |
| `HEADLESS_TIMEOUT` | run_journal 卡住 | 已杀进程树；缩小批量重跑 |
| `VERIFY_NO_MEASURE` | facts 里没有该量测 | 先 `nx_measure` 拿 facts 再 assert |

## NX10 专有注意

- 没有 `UGOPEN\pythonStubs`：`nx_api` 走 XML 索引，`py=` 是推导名，进 NX 用 `dir()` 确认。
- `NXOpen.dll` 在 `UGII\managed`，不在 `NXBIN`。
- 无 pip：只能用标准库；要第三方库得外挂 3.3 兼容的纯 Python 包。
- C# 插件必须用 `UGII\SignDotNet.exe` 签名，否则 NX 静默不加载。
