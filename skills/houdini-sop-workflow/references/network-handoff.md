# 网络交接布局

目标是让用户一眼分清控制、放置、可替换源、处理/装配和输出，同时保留足够空白供人工审查与继续编辑。它是交付展示层，不替代几何、关系、控制或视觉验收。

## 何时执行

新建或实质扩展的非平凡SOP网络，在功能与输出已经验证、保存之前执行。单节点或很短的直链、一次性诊断/探针、只做维护、foreign网络、用户明确不要整理，或包含不受支持的嵌套/混合NetworkMovableItem时跳过；不要为满足形式而制造空Box。

## 分组

先区分逻辑模块与技术阶段。普通单作者装配默认可在同层以逻辑模块组织：每个可独立替换、细化或重复的组件让源、局部处理和稳定`OUT_<MODULE>`相邻，父装配只消费这些输出；不因为模块化自动创建Subnet。根层预计继续编辑的非平凡资产使用稳定`OUT_ASSET` Null。Network Box只是同parent的扁平展示，不能冒充层级、公共端口或成员/权限证据；小模块可合并成一个清楚的Box，不机械创建空角色框。

- `controls`：用户控制、共享参数和驱动入口。
- `component`：仅用于包含叶子角色框的一层组件展示容器，不直接装节点。
- `placement`：点流、方向、尺度、随机化与装配位置。
- `source`：可独立替换的源几何/原型。
- `assembly`：处理、复制、合并和最终装配。
- `output`：稳定`OUT_ASSET`/`OUT_<MODULE>` Null、显式公共输出或交付检查点。非平凡根资产已有稳定最终输出时应单独列入本角色，不把它埋在assembly框内。

按实际网络选用，不要求五类全部存在。一个节点只能进入一个本次管理的扁平Box；标签写给用户看，名字保持稳定。纯技术角色布局使用`network_boxes`默认角色色，不手调成无语义的彩虹色。

当用户既要按组件接手，又要保留“可替换源、模板点/放置、Copy/处理、模块输出”等技术阶段时，使用两层**组件容器→角色单元格**。先按实际节点建立`MODULE · SOURCE`、`MODULE · TEMPLATE/COPY`、`MODULE · OUT`叶子框并完成`mode='handoff'`；短链可合并相邻角色，不制造空框。再单独调用`network_boxes`，让`role='component'`的大框通过`boxes=[...]`包含这些已布局叶子框，最后对所有组件大框执行两阶段`layout_nodes(mode='component', boxes=[...])`，它以叶子框为整体移动单元，不打散小框内部。同一节点仍只属于一个叶子框；组件框不直接装节点、不与叶子框同批创建、不再套第三层。这是Network Box展示层级，不是Subnet、公共端口或所有权层级。

需要快速观察不同组件时，可给同一组件的大框和叶子框使用同一低饱和色相，以轻微明度差区分阶段；相邻组件避免近似色，控制、总装和最终输出仍保留稳定的中性色/角色色。颜色必须与组件标签、几何`part`/piece身份保持可解释对应，不按创建顺序随机分配，也不能用“颜色不同”替代实际成员、接线和输出验证。已有用户自定义配色默认保留；只有用户要求重配或新建交接布局时才覆盖。

## 两阶段执行

先预览分组，再应用；然后预览comfortable handoff，再应用。两次apply都必须使用刚取得的`plan_sha256`，不要复用陈旧计划。
建好成员Network Box后，不能再对整网调用`layout_nodes(mode='children'/'flow')`：
它会把框内节点重新打散而不验证框间排布，工具现会写前拒绝这种调用。
要整理框之间的关系，继续用下方的`handoff`预览/应用；只调整单个框内
少量节点时，传明确的`nodes`列表。

```python
box_plan = network_boxes(parent, groups, dry_run=True)
network_boxes(parent, groups, expected_plan=box_plan['plan_sha256'])

names = [group['name'] for group in groups]
layout_plan = layout_nodes(parent, mode='handoff', boxes=names, dry_run=True)
layout_nodes(parent, mode='handoff', boxes=names,
             expected_plan=layout_plan['plan_sha256'])
```

handoff默认只移动当前session自有Box及其完整自有成员。未选节点、foreign/service/未选Box、Sticky Note和Network Dot是固定障碍；不能仅为整理美观使用`allow_foreign`越权。用户明确授权修复某个已命名既有网络时，可对精确列出的旧Box及成员传一次性非空`allow_foreign`理由，并在dry-run与apply保持同一授权；持久render service永不豁免。若返回`blocked`，缩小显式Box范围或由用户处理固定障碍，不删除/移动未授权内容。

`handoff`只接叶子框，`component`只接组件大框；不能把父子框混在同一次布局。更新或移除嵌套叶子框时必须同批声明其组件容器最终`boxes`列表或移除容器，避免留下隐式重归属。

## 验收

要求`layout_status='passed'`、节点/Box/障碍重叠计数为0、`containment_failures=[]`、`clearance_failures=[]`；比较`required_clearances`与apply后从实际回读重算的`achieved_clearances`，不能把profile常量当实测净距。再做一次fresh dry-run/apply应为`scene_writes=0`。确认接线、display/render flags、frame、selection、cook状态与foreign/service/注释障碍未变。该结果不证明线条完全不交叉，也不使旧几何或视觉证据自动变新；节点内容变化后按正常交付门刷新受影响证据。
