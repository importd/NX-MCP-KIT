# nx-plugin-verify：写/调 NXOpen 代码并验证效果

面向二次开发：给一段 NXOpen Python（或要改的插件逻辑），先静态校验，再在 NX 里跑，最后按判据验收。

## 何时用

- 用户贴了一段 NXOpen 代码问"能不能跑/为什么报错"
- 要验证某个插件/脚本在 NX10 与 NX2512 上的行为
- 要批量跑 journal 并出一份成败报告

## 步骤

1. **定目标版本**：`nx_status` 看当前 NX 版本与内嵌 Python；NX10=3.3、NX2512=3.12。
2. **查签名**：`nx_api q=<类名>`，看 `py/sig/lic`；写代码只用查得到的签名。
3. **预检**：`nx_check code=<代码> target_ver=nx10`；有 error 先改。
4. **选执行方式**：
   - 交互调试：`nx_run_python code=...`（在已开的 NX 里跑，`result` 变量会回传）
   - 无人值守/批量：`nx_batch steps=[{tool:nx_block,args:{...}}]` 或直接 `nx_batch` 跑 plan
5. **看结果**：有错误先读 `error.code/next`；几何结果用 `nx_measure` + `nx_assert`。
6. **回归**：同一脚本在改前/改后各跑一次，比较体积/包围盒/面数。
7. **沉淀**：跑通的原子做法 `nx_exp action=save`；报错与修法存成"坑"条目。

错误码 → 修法见 [坑位表](references/pitfalls.md)。

## 硬规则

- **执行前必预检**：没有 `nx_check pass=true` 不许 `nx_run_python`。
- **不碰用户正开的件**：验证用临时件；批量用 `nx_batch` 独立进程。
- **退出码不可信**：批处理看 `NXKIT_OK/NXKIT_FAIL` marker + 实测产物。
- **NX10 语法红线**：禁 f-string、`:=`、变量注解、dataclass。
- 失败三次就停，输出已尝试清单，不瞎试。
