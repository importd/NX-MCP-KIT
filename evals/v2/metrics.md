# 指标字典（人读版）

机器可读版本：`metrics.json`（实现只允许引用这里的 ID）。

| ID | 名称 | 层 | 公式 | 方向 | v1 阈值 |
|---|---|---|---|---|---|
| M-TASK-01 | 任务成功率 TSR | L2 | 通过 run / 总 run | 越高越好 | ≥0.70 |
| M-TASK-02 | pass@k | L2 | k 次内至少 1 次通过的任务比例 | 越高越好 | ≥0.85 |
| M-GEO-01 | 最大相对几何误差 | L1 | max |got-expect|/|expect| | 越低越好 | ≤0.5% |
| M-EFF-01 | 成功任务平均工具调用数 | L2 | mean(calls \| pass) | 越低越好 | ≤10（p95≤16） |
| M-EFF-02 | 成功任务平均耗时 | L2 | mean(seconds \| pass) | 越低越好 | ≤300s |
| M-EFF-03 | 单任务 token | L2 | mean(tokens \| pass) | 越低越好 | ≤15000 |
| M-CMP-01 | 经验闸门合规率 | L2 | 几何调用前有 exp_search 的 run 比例 | 越高越好 | ≥0.90 |
| M-CMP-02 | 预检合规率 | L2 | run_python 前有 nx_check 的比例 | 越高越好 | ≥0.90 |
| M-VER-01 | 判据覆盖率 | L1 | 实际执行断言 / 声明断言 | 越高越好 | =1.0 |
| M-VER-02 | 虚假完成率 | L2 | 声称完成但评分失败 / 声称完成 | 越低越好 | =0 |
| M-EXP-01 | 经验复用率 | L3 | 使用 exp_replay/get 的 run 比例 | 越高越好 | — |
| M-EXP-02 | 冷热库提效差 | L3 | 平均调用数(冷) − 平均调用数(热) | 越高越好 | — |
| M-VER-03 | 双版本几何等价率 | L1 | NX10 通过的断言在 2512 也通过的比例 | 越高越好 | =1.0 |
| M-QUA-01 | 运行完整性 | L1 | trace 完整的 run 比例 | 越高越好 | =1.0 |

## 口径约定

- **几何判据**由独立进程（`run_journal`）量测，不经过被测 MCP。
- **token** 使用客户端计费口径；server 侧 prompt 大小另记 `prompt_tokens`，不混用。
- **耗时**从首个任务步骤开始到保存完成，不含人工干预/排队。
- **对比前提**：`model + skill_version + library_state + nx_version + tool_surface` 五个维度必须对齐。
- 指标变更必须升 `metrics_version`，并在报告里记录。
