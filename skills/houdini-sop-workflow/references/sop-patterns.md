# SOP 稳健模式

## 目录

1. 模块契约模板
2. Copy to Points
3. 形变与成形顺序
4. 属性传播
5. 局部几何验证
6. 时间动画
7. 视觉与用户 viewport
8. 失败恢复和性能

## 1. 模块契约模板

每个分支先写：

```text
输入：拓扑、坐标空间、必须属性
操作：使用的原生 SOP/VEX
输出：新增/删除/变更的几何和属性
不变量：根部固定、宽度非零、piece 数、面积、bbox、warning
验证：cook_node / describe / geo_* 动词
```

模块尚未通过时不要进入材质、相机或灯光调试。

## 2. Copy to Points

适用：把一个或多个源几何复制/实例到模板点。

模板点常用属性：

- `P`：根位置。
- `orient`：四元数旋转。
- `N` + `up`：没有 orient 时的对齐基。
- `pscale` / `scale`：统一/非统一缩放。
- `id` / `phase` / `variant`：后续随机和动画标识。

流程：

1. 先验证模板点属性数值。
2. `search_tab_menu('sop', 'copy to points')`。
3. `tab_create(..., 'copytopoints', inputs=[source, points])`。
4. 验证 Copy 后属性和 piece local extent。

不要因为 classic Copy 看起来熟悉就使用它。若必须使用 classic Copy，要明确其模板属性传递参数，并验证 Copy 后相邻点/单 piece，而非只看全场 bbox。

## 3. 形变与成形顺序

稳健顺序通常是：

```text
中心线/低维拓扑
→ curveu/rest/root 等驱动
→ 时间变形
→ Sweep/ribbon/skin 生成宽度
→ Copy/Merge
```

或对每实例刚性摇摆：

```text
成形后的单元
→ 模板点时间依赖 orient
→ Copy to Points
```

危险模式：

```text
中心线保存 local P
→ PolyWire/Sweep 生成截面
→ 用旧 local P 重建所有截面点
```

它会把截面点压回中心线。任何 rest/local 坐标都必须说明捕获时的拓扑阶段。

## 4. 属性传播

检查属性 class：point、primitive、vertex、detail。Copy/Merge 后：

- 驱动属性是否复制到所有目标点。
- `Cd/N/uv` 是否因输入不一致产生默认值。
- 同名不同 class/size/type 是否冲突。
- 临时属性是否在交付前删除。

Merge warning 是数据契约失败证据。用 Attribute Delete/Rename/Promote 或显式初始化解决，不要忽略。

## 5. 局部几何验证

全场 bbox 会被散布 root 位置放大，不能发现每个实例零宽。

使用：

```python
geo_piece_stats(copy_or_deform_node)
```

检查：

- piece count 是否符合实例数。
- sampled piece 的 extent/area。
- `degenerate_surface_pieces`。
- 变形前后 piece 面积和最小 extent 是否保留。

需要追查时先隔离一株/一个 piece，再看全场。

## 6. 时间动画

不要只写 `@Time` 就宣称动画成立。

```python
geo_frame_diff(out, 1, 12, attrib='P')
```

验证：

- 根部或锚点近似不动。
- 尖端/活动点有显著位移。
- 波峰沿预期方向传播。
- frame A/B 的 topology 是否一致。
- 用户当前 frame 在调用后未改变。

全局 `mean_delta/max_delta` 非零证明时间依赖，不自动证明审美语义。若固定相机 A/B 暴露完全静止、方向相反、主体缺失等明确反例，应回到风场设计；若节点、属性、锚点/活动区和时间依赖均通过，而两张静帧只是不足以裁定细微动态或视觉力度，可诚实交付“画面待用户播放判断”，不能宣称视觉已经确认，也不必无限渲染说服视觉模型。

做 render A/B 时必须锁定同一相机和构图。当前若分别调用会按每帧动态 bbox 重取景的渲染工具，应先核对返回的 `center/eye/dist/direction`；这些值不同，则 pixel diff 混入了相机变化，不能单独证明动画。固定参考帧要按整段验收帧的 bbox 包络来选，并留足 coverage；任一帧的 `render_check.content_bbox` 触到图像边缘或安全边距不足，都说明“相机固定但取景不完整”，应扩大 coverage 或更换包络更大的 `framing_frame` 后重渲染。

若 geometry diff 非零但 render diff 为零，调查 proxy/ROP 缓存；若两者都为零，调查表达式、spare 参数和 time dependency。

## 7. 视觉与用户 viewport

- `render_view(EXPLICIT_SOP)`：agent 产物验证，走隐藏 proxy；用户 display/visibility 不选择源。
- `viewport_screenshot`：用户屏幕诊断；用户显示空节点时空图是正确诊断结果。
- 两者对照：render 有内容而 viewport 空，说明用户 display/viewport 漂移；两者都空，回到 SOP 数据。

视觉 prompt 先中性描述，不要预设“这是成功的草地”。

## 8. 失败恢复和性能

- 利用 exec undo rollback；失败结果检查 `rollback.applied`。
- 文件写入和 HDA 库修改不在 Houdini undo 范围内，必须另做事务/备份。
- 把大网络拆成 checkpoint batch；每批可重复、可验证。
- 性能以 cook time、点面数和 SideFX Performance Monitor 为证据，不用工具调用次数代替 cook 性能。
- 结束时 `layout_nodes`；缺省只整理当前 agent session 创建的节点并返回
  `foreign_nodes_skipped`，不要为了整洁移动用户临时创建的节点。
