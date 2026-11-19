# 操作流水与自动经验沉淀

## 为什么不能靠模型自觉

`exp_save` / `nx_exp` 都是显式工具调用，模型不调用就没有沉淀。把"沉淀"绑在提示词上，
相当于把数据质量绑在模型注意力上——不可靠，也无法审计。

## 现在的链路（生产侧，强制）

```
每次 tools/call
   │ Router._log_operation()
   ▼
io/oplog.jsonl          # 追加写；args 里的绝对路径脱敏成 <path:文件名>
   │ python -m nxkit.ingest（定时/手动）
   ▼
签名聚合（tool + 脱敏 args 的哈希）
   │ 成功 ≥ min_success 且失败率 ≤ 20%
   ▼
library/_drafts/AUTO-xxxx.json     # v=0，不可检索
   │ verify_drafts（在全新零件里重放，独立量测）
   ▼
library/moves/AUTO-xxxx.json       # v=1，可 exp_search 命中
```

## 关键设计

1. **成功 ≠ 返回 ok**：入草稿看重复成功与低失败率；升级为 verified 必须**重放 + 实测 facts 匹配**（容差默认 1%）。
2. **默认保守**：`min_success=2`、失败率 >20% 不沉淀；自动条目带 `source: auto`，人工可审计。
3. **失败也有价值**：同一签名反复失败会记录 `error_codes`，后续可生成"坑"草稿。
4. **不被模型注意力的影响**：Router 保证每次调用都写日志（写入失败也不会影响工具调用本身）。
5. **可回放/可审计**：`oplog.jsonl` 是人类可读的 JSONL；`event_id` 唯一；`run_id/session_id/source` 可区分来源。

## 命令

```bash
# 从流水生成草稿（默认读 io/oplog.jsonl，写 library/）
python -m nxkit.ingest --oplog io/oplog.jsonl --library library

# 复测并把通过的草稿升级为 verified（需要 live NX + 重放函数；CLI 为手动入口）
```

`ingest()` 的 `replay` 参数由调用方注入：生产上是用新零件重放 `impl` 步骤并量测；
测试里是纯函数。这样流水/聚合逻辑可以完全离线验证。

## 与 evals 的关系

- `io/oplog.jsonl`：**生产侧**事实来源，永远在写，用于沉淀。
- `evals/v2/runs/*.json`：**评测侧**运行记录，用于指标计算，两者互不替代。
