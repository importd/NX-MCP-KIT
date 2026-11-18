# 修改：常用原子操作

| 意图 | 工具 | 关键参数 |
|---|---|---|
| 新建毛坯/加料 | `nx_block` | `length/width/height`，原点 x/y/z |
| 打孔/通孔 | `nx_hole` | `target/position/diameter`，`depth` 省略=通孔 |
| 重新定位体 | `nx_run_python` + Transform | 先用 `nx_api q=Transform` 查签名 |
| 布尔 | `nx_boolean` | `target/tool/operation` |
| 面偏置 | `nx_move_face`（待实机校准） | 暂用 `nx_run_python` 替代 |

## 用 nx_run_python 时的骨架

```python
wp = NXOpen.Session.GetSession().Parts.Work
body = [b for b in wp.Bodies if b.JournalIdentifier == "BLOCK(0)"][0]
builder = wp.Features.Create...Builder(NXOpen.Features.Feature.Null)
try:
    # 设参数
    feature = builder.CommitFeature()
finally:
    builder.Destroy()
result = feature.JournalIdentifier
```

- `result` 变量会回传给 Agent 作为返回。
- Builder 必须 `Commit`/`Destroy`，否则 `nx_check` 会报 BUILDER_NO_COMMIT。
- NX10 里禁 f-string：用 `"%.3f" % x` 或 `str.format`。

## 多步改动

3 步以上用 `nx_plan`：先拍快照，逐步执行，失败自动回滚。计划里每步是 `{"tool":..., "args":...}`。
