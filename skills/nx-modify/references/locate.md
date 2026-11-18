# 定位：认体、认面、认孔位

## 体的识别

- `nx_inspect` 返回每个体的 `id / faces / edges / bbox / volume`。
- "上面那个体" = 包围盒 z 最大；"左边那个" = x 最小。用数值比较，不要靠顺序。
- `JournalIdentifier` 在同一会话内稳定，但**特征重排后会重新编号**；跨会话长期引用不要用它。
- 要长期标识：给体打用户属性（`nx_run_python` 里 `body.SetAttribute("nxkit.id","B1")`），存盘不丢。

## 点落在哪个体上

`nx_inspect point=[x,y,z]`：先看包围盒粗筛，再结合 `volume` 判断。

## 孔的定位

1. `nx_inspect` 看体的包围盒，建立坐标框架。
2. 图纸孔位通常是相对基准边/中心的偏移：先算绝对坐标，再 `nx_hole target=... position=[x,y,z]`。
3. 已存在的孔：用 `nx_run_python` 遍历 `body.GetFaces()` 找圆柱面，或按直径在 `nx_measure` 里交叉验证。

## 判断"选对了没有"

- 改动前后都量一次：体积/包围盒/面数。变化的量应与意图一致。
- 不确定时先 `nx_screenshot` 看一眼，再继续。
