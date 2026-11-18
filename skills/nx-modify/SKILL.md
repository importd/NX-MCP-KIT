# nx-modify：改现有零件

面向"打开一个已有 .prt，读图定位、改尺寸/改结构、量了验证"的流程。

## 何时用

- 用户给了一张图纸/一句话尺寸要求，要在**已有零件**上改
- 要改孔位、孔径、壁厚、倒角、面偏置，或删/改特征
- 任何"先看看这个件长什么样再动手"的任务

## 步骤

1. **先看**：`nx_inspect` 拿体清单（id/面数/包围盒/体积）。要认"哪个体"用几何（center/size/volume），不要写死 `JournalIdentifier`。
2. **查经验**：`exp_search` 短词检索（0 命中也算查过，闸门才放行）。
3. **查 API**：`nx_api` 查真实签名；写代码前先看 `lic`（没许可的接口写了也白撞）。
4. **写前快照**：`nx_snapshot action=save path=<当前件>`，拿到快照 id。
5. **预检**：`nx_check code=...`，有 error 不许执行；按 `next` 改到达标。
6. **执行**：优先 `nx_hole`/`nx_block` 这类原子工具；没有对应工具时 `nx_run_python`。
7. **量了再说话**：`nx_measure` 拿实测 facts → `nx_assert spec=... facts=...`；不达标回到第 5 步或 `nx_snapshot action=restore id=<id>`。
8. **沉淀**：达标后 `nx_exp action=save`，evidence 直接抄 verify 的实测值。

细节：[定位](references/locate.md) · [修改](references/modify.md) · [验证](references/verify.md)

## 硬规则

- **不猜 API**：`nx_api` 查不到就停下来报错，不许凭记忆写签名。
- **写前必快照**：`.prt` 没有 git 可退。
- **量了才算完成**：没有 `nx_assert pass=true` 不许说"已改好"。
- **单位 mm**：进函数先看零件单位；NX10 的 Python 是 3.3，禁 f-string/海象/注解。
- **只动工作区**：文件只写本仓库或用户指定目录，不碰别的盘上的件。
- 改完 `nx_save`；大改走 `nx_plan`（失败自动回滚到计划起点）。
