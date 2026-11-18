# nx-mold-template：模具结构模板化建模

面向"模架 / 镶件 / 滑块 / 流道"这类结构化件：模板给出参数 schema + 步骤 + 判据，Agent 只负责选模板、填参数、执行、验证。

## 何时用

- 用户说"做一个 400×300 的模架""出一块直径 60 的圆镶件"
- 要批量出一组同结构件（改参数不改变结构）
- 需要保证结构一致、尺寸可追溯

## 步骤

1. **看模板**：`nx_template action=list`，读每个模板的 `params`（名字/范围/默认值）。
2. **查经验**：`exp_search` 搜同类件的历史做法。
3. **填参**：`nx_template action=apply name=圆形镶件 params={d:60,h:40}` 得到 `steps + asserts`。
4. **执行**：`nx_plan steps=<上一步 steps> part=<当前件路径>`（自动快照+失败回滚）。
5. **验证**：按 `asserts` 用 `nx_measure` + `nx_assert` 判定；模板自带判据的照抄。
6. **存盘**：`nx_save`；把参数与实测 evidence 一起 `nx_exp action=save` 沉淀成方案。

模板常见参数见 [步骤提示](templates/step-prompts.md)。

## 硬规则

- **先 list 后 apply**：参数名/范围以模板为准，不许猜。
- **参数越界直接报错**：不要自己"调整"到合法值再继续，先问用户。
- **结构改动不许走模板**：模板只做参数化实例化；改结构走 `nx-modify`。
- 每个模板至少一条几何判据；没有判据的模板不许标记 verified。
- 模板生成的步骤必须用注册表里存在的工具（`nx_find` 可查）。
