# 网络交接布局

目标是让用户一眼分清控制、放置、可替换源、处理/装配和输出，同时保留足够空白供人工审查与继续编辑。它是交付展示层，不替代几何、关系、控制或视觉验收。

## 何时执行

新建或实质扩展的非平凡SOP网络，在功能与输出已经验证、保存之前执行。单节点或很短的直链、一次性诊断/探针、只做维护、foreign网络、用户明确不要整理，或包含不受支持的嵌套/混合NetworkMovableItem时跳过；不要为满足形式而制造空Box。

## 分组

先区分逻辑模块与技术阶段。普通单作者装配默认可在同层以逻辑模块组织：每个可独立替换、细化或重复的组件让源、局部处理和稳定`OUT_<MODULE>`相邻，父装配只消费这些输出；不因为模块化自动创建Subnet。根层预计继续编辑的非平凡资产使用稳定`OUT_ASSET` Null。Network Box只是同parent的扁平展示，不能冒充层级、公共端口或成员/权限证据；小模块可合并成一个清楚的Box，不机械创建空角色框。

- `controls`：用户控制、共享参数和驱动入口。
- `placement`：点流、方向、尺度、随机化与装配位置。
- `source`：可独立替换的源几何/原型。
- `assembly`：处理、复制、合并和最终装配。
- `output`：稳定`OUT_ASSET`/`OUT_<MODULE>` Null、显式公共输出或交付检查点。非平凡根资产已有稳定最终输出时应单独列入本角色，不把它埋在assembly框内。

按实际网络选用，不要求五类全部存在。一个节点只能进入一个本次管理的扁平Box；标签写给用户看，名字保持稳定。角色色由`network_boxes`统一设置，不手调成无语义的彩虹色。

## 两阶段执行

先预览分组，再应用；然后预览comfortable handoff，再应用。两次apply都必须使用刚取得的`plan_sha256`，不要复用陈旧计划。

```python
box_plan = network_boxes(parent, groups, dry_run=True)
network_boxes(parent, groups, expected_plan=box_plan['plan_sha256'])

names = [group['name'] for group in groups]
layout_plan = layout_nodes(parent, mode='handoff', boxes=names, dry_run=True)
layout_nodes(parent, mode='handoff', boxes=names,
             expected_plan=layout_plan['plan_sha256'])
```

handoff只移动当前session自有Box及其完整自有成员。未选节点、foreign/service/未选Box、Sticky Note和Network Dot是固定障碍；不要用`allow_foreign`试图越权。若返回`blocked`，缩小显式Box范围或由用户处理固定障碍，不删除/移动外来内容。

## 验收

要求`layout_status='passed'`、节点/Box/障碍重叠计数为0、`containment_failures=[]`、`clearance_failures=[]`；比较`required_clearances`与apply后从实际回读重算的`achieved_clearances`，不能把profile常量当实测净距。再做一次fresh dry-run/apply应为`scene_writes=0`。确认接线、display/render flags、frame、selection、cook状态与foreign/service/注释障碍未变。该结果不证明线条完全不交叉，也不使旧几何或视觉证据自动变新；节点内容变化后按正常交付门刷新受影响证据。
