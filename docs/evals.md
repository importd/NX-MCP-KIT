# 评测 v2：基线与用法

## 当前基线（NX10.0.0.24，headless）

基线文件：`evals/v2/baselines/nx10.json`（commit 记录在 `tool_surface` 字段）

| 指标 | 值 | 说明 |
|---|---|---|
| M-TASK-01 任务成功率 | **1.000**（16/16） | T1 原子 8 + T2 单件 8 |
| M-TASK-02 pass@k | 1.000 | 单次运行 |
| M-GEO-01 最大相对几何误差 | **0.000** | 全部断言在容差内 |
| M-EFF-01 成功任务平均工具调用 | 4.25 | |
| M-EFF-02 成功任务平均耗时 | 9.99 s | run_journal 冷启动约 10 s |
| M-VER-01 判据覆盖率 | 1.000 | 所有 hidden asserts 都执行且量到 |
| M-QUA-01 运行完整性 | 1.000 | trace 完整 |
| M-CMP-01 闸门合规率 | 0.000 | **oracle 驱动绕过闸门**，该指标对 agent 驱动才有意义 |
| M-EXP-01/02、M-VER-03 | — | 需要冷/热库与双版本对照实验 |

**这个基线证明的是"工具面 + 评分管线正确"，不是"模型能力"**：驱动是 oracle（按 solution_steps 执行），
没有 LLM 参与。模型能力要等 agent driver 接入后才有 TSR/合规/自愈等指标。

## 复跑

```powershell
$env:PYTHONPATH="<repo>;<repo>\runtime"
python -m evals.v2.run_all --mode headless --tier all --attempts 1 `
  --nx-root "D:\Program Files\Siemens\NX 10.0" --baseline nx10
```

- `--mode headless`：任务全部走 `run_journal` 独立进程（无需 GUI 会话）。
- 评分器在**另一个 run_journal 进程**里打开保存的零件重新量测（独立于被测链路）。
- 任务文件不含期望值；期望值在 `tasks/hidden/*.asserts.json`，仅评分器读取。
- 运行产物 `runs/`、`scores/` 不入库；基线入 `baselines/`。

## 已知坑（本轮修掉的）

1. 同任务重跑必须用唯一零件名，否则 `nx_part new` 撞已有文件、后续步骤跑在旧件上。
2. NX10 的 `Part.Save()` 需要枚举参数；同路径保存要用 `Save(FalseValue, FalseValue)`，`SaveAs` 只用于新路径。
3. 面选择不能用"最近边中点"：顶面与侧面的边中点可能同距，会随机选面（抽壳体积 13632 vs 14552）。
   改为按面顶点质心距离选面。
4. 布尔的目标/工具体不要写死 `BLOCK(n)`（布尔特征也占号）；用 `tool="last"` 按几何取。
5. NX GUI startup 加载对启动环境敏感：从非交互 shell 启动 NX 可能报初始化错误；
   桥按 ngxz-ya 的写法（`# nx: threaded` + `startup(*args)` 内 catch BaseException + home 指针文件）部署，
   用户正常双击启动 NX 时可加载。
