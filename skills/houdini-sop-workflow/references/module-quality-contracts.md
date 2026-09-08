# 实际输出的模块质量合同

## 适用与边界

适用：多部件SOP装配、带明确连接端的模块、需要用户调参仍保持连接的资产。
不适用：简单单参修改、纯骨架/调试helper交付、模拟求解器、文件写盘或带外部副作用的控制；
不把本流程强套到所有场景。版本：H21.0.440/H22.0.368工具回归；自然弱模型增益待新会话。

## 模块聚焦与交接

用于复杂装配或局部细节容易被整体轮廓掩盖的任务；这是顺序聚焦的工作流候选，不是自动调度器或质量增益保证。
一个模块应能独立说明用途、输出和检查方法，且对外接口较少；不按每颗小零件拆任务，也不把耦合结构强行分开。
在整体代理中先确认接口和控制依赖，再从最高风险/最重要可见部件开始；不为简单编辑或纯单部件请求另建整体代理。

复用现有prose/todo中的紧凑记录，不创建另一个可写交付账本、节点自报证书或固定格式工具：

| 记录 | 内容 |
|---|---|
| 当前焦点 | 该模块相关的原始要求/来源引用、质量距离和允许简化；其余整体义务仍保留 |
| 对外约束 | 输入、局部坐标/单位、共享控制来源、邻接模块及连接面/轴/允许间隙；不能在多个生成器复制共享常量 |
| 局部完成条件 | 必需内部结构、实际表面/拓扑、控制作用与不变量、所需特写；细节按可见作用而非面数决定 |
| 交接事实 | 已提交OUT及最近观察的runtime/identity、参数/输出指纹或调用引用、已测/未测范围、当前阻塞 |
| 集成结果 | 最终输出中的部件成员/基数、实例实际接口、共享控制扰动与恢复；不由局部pass推导 |

局部条件满足后就集成，保留正确的模块；不要为推进整体清单牺牲未完成的核心局部要求。
同一边界连续失败按主skill停止探测并换方法；邻接接口未定时记录依赖阻塞，回到整体协调，而不是继续添加装饰。
预算不足时披露哪些局部要求未完成，请求范围取舍或交付部分结果；不默认把高质量请求降为“部件齐全”。

集成先确认声明部件在实际最终输出中非空且基数合理，再复验变换后的关系。源模块可cook、
build_module.required_outputs通过，只证明源分支存在，不能证明下游Switch/选择/Merge还包含它。
代理体与正式模块保留可区分身份；替换代理后复核最终成员，不能让代理继续填补正式部件的缺失。

后续修改先回读目标：接口/共享控制变更使相关邻接检查失效；内部细节变化至少刷新本模块及实际受影响的集成证据。
用graph及已记录execution影响提示缩小范围，未观察的动态/外部依赖仍需核对。不能从路径未变推断身份或证据仍有效。
交接摘要只压缩排错过程，不删除原始未满足要求；历史pass和任务摘要均不赋予foreign修改权限。

机制验证：仓库`tools/tests/dsh-module-integration.test.py`覆盖局部通过但集成漏件、局部坐标正确但实例脱离、
共享控制联动/恢复以及独立已提交模块保留；它不运行LLM，不能证明自然任务的模块聚焦行为或美术质量提升。

## 构建前：选择接口，不发明一个“正确”布尔值

先按表示选择方法：两个仍独立的表面用下述interfaces距离合同；Boolean融合后的共享表面用
`test_controls`的`topology=[{id,groups:[部件primitive组,...],require_closed:true}]`。后者检查共享
边连通、闭合与非流形/朝向问题，当前仅Polygon，不证明自交、强度或目标形状；至少两个
非空且不重叠的部件组。`test_controls(...,topology=...)`在基准及扰动输出复查它。
未焊接但空间接触的两部件不能用共享拓扑证明；融合缝也不能用“共享点到自身距离0”自证。
更换方法时保留用户要求的连接义务；当前数据不能自行决定哪些部件必须交付。

一个模块至少明确输出、连接位置/轴向、共享控制与允许连接误差。生成几何使用同一接口作为
位置来源；另在实际最终表面保留可识别的组。point group选连接端的表面顶点，primitive group
选对方实际接触区域，不选整个场景；不能放几个无关driver点冒充最终几何。

适用时把这些组随Copy/Merge一路传到交付OUT；顶点数改变后更新明确基数，不静默接受空选择。
组名来自当前任务，不由库固定。一个模块可以有多个出口/接口，每个需独立检查。
原型通过不能代替复制/变换后的实例关系。最终输出保留可选择的部件身份和接口组；附属件
随主体一起移动只证明共同运动，不证明二者连接。先验证原型内部连接，再检查各实例的外部接口。

## 最小执行路径

```python
interfaces = [{
    'id': 'mating_interface',
    'source_group': 'port_vertices',
    'target_group': 'receiver_surface',
    'expected_points': 4,
    'max_distance': 0.001,
}]
# spec自行生成；必须包含这两个属于真实表面的命名组。
result = build_module(parent, spec, output='OUT_MODULE', interfaces=interfaces)
```

上述数值仅展示schema；容差、点数要由单位/连接要求与实际构造决定，不是所有任务的固定标准。
`dry_run=True`只预检声明，不能证明几何接口。正常build会在最终输出检查接口；fail或unverified
使该新增模块失败并清理本批节点。修改已有节点后，用 `geo_check_interfaces(out, interfaces)`
再次读取实际结果；它是诊断返回，不会替你修模或强制完成。

检查含义：全部source表面顶点到指定target表面的最近距离须不超过容差。
支持target为closed Polygon、Mesh、Sphere、Tube；source必须是polygon/mesh表面顶点。
Packed/volume/NURBS等暂未验证的表示返回unverified。超点数/内存/查询预算拒绝，不抽样假绿。
这个检查**不证明**整个表面无穿插、包含深度、焊接、机械强度，也不能把方向平行当成连接。
需要插入或实体相交时应选择对应独立方法，不通过放大max_distance来使错误结果变绿。
顶点对顶点的最小距离是完整表面最小距离的上界，不是安全间隙下界；面中部相交时顶点仍可远离。
源顶点到真实目标表面也只覆盖这些样本，不证明连续全表面无穿插。要求贴合时检查指定接口的
全部声明样本；要求无碰撞却无适用检测时保留unverified。独立装配允许经设计确认的间隙，
不因没有共享点就强制Fuse/Boolean，也不把封闭且朝外的各部件当作装配关系已通过。

## 控制契约：改变什么，什么必须不变

### 实际表面组的轴向间隙（v12）

上下叠放/沿轴布置的部件，可用最终输出primitive组计算投影间隙，避免重复构造公式自证。
例如声明source为上方部件、target为下方部件：

```python
relations = [{'id': 'stack_projection', 'method': 'axis_gap',
              'source_group': 'upper_surface', 'target_group': 'lower_surface',
              'axis': 1, 'gap_range': [-0.001, 0.001], 'min_overlap': 0.01}]
measured = geo_check_interfaces(out, relations)
# 同一关系可以进入参数扰动窗口，在基准与每个case上复查：
tested = test_controls(controller, out, tests, interfaces=relations)
```

数值仅示schema，范围按设计单位明确。量测是source.min[axis]−target.max[axis]；正数为分離，
负数为轴向投影重叠。另外两轴区间重叠须≥min_overlap。曲面bbox相接不证明表面实际接触，
需要真实接触时再加适用的点到面接口；不用于任意弯曲榫接、实体穿透深度或强度认证。
source/target必须为实际交付中的非空且互不重叠primitive组；不得临时加入driver点伪造表面。
观察→参数扰动→同关系复查→完整恢复应在test_controls内完成，不能以恢复了几个bbox替代bgeo恢复证据。

在暴露参数时声明一个可测预期：具体输出部件、metric、测试值与有符号delta允许区间。
优先测相关primitive group，避免整体bbox掩盖局部变化。至少确认每个交付控制有预期作用；
相互依赖的控制再选择少量组合测试，不把一次通过说成全范围成立。

```python
tests = [{
    'id': 'length_response',
    'values': {'length': 1.2},
    'expectations': [{
        'group': 'driven_part', 'metric': 'bounds_size', 'axis': 0,
        'delta': [0.199, 0.201],
    }],
}]
report = test_controls(controller, out, tests, interfaces=interfaces)
```

示例基准length为1、单位米且输出长度一比一响应；实际参数/目标变化由任务决定。
metric精确为bounds_size、bounds_center、bounds_min、bounds_max（axis0/1/2）、point_count、primitive_count、area；不接受center/min/max缩写。
v11另支持point_mean（axis）、boundary_edges、piece_count（Polygon共享边连通）、max_point_displacement/mean_point_displacement。
位移必须提供id_attrib：稳定唯一integer/string point ID，面连接在ID空间保持一致；对应关系变化返回unverified。
已知变换的控制可附max_transform_error，提供同样id_attrib、实际primitive group和transform（16数row-major仿射矩阵，Houdini行向量约定，SOP-local空间）。它测量全组真实点相对`P_baseline * transform`的最大残差，baseline残差定义为0；delta/range使用设计容差，另加一项非零位移响应。将主体和附属件声明为同一变换，未选中组声明identity，可检出“主体动了但附属件不跟随”。它不是拟合当前结果来反推正确变换，也不证明全部姿态/碰撞；混合几何的点均值不能当设计轴心。修改生成器后需重新建立基准。
expectation可带range=[min,max]检查基准及扰动绝对范围，例如封闭面的boundary_edges要求range=[0,0]、delta=[0,0]；
单纯delta=0不能证明基准已闭合。仍需至少一条响应delta排除0；有意分组切口不能无条件要求闭合。
每case至少一个delta区间必须排除0以声明实际响应；不变量可作为额外expectation。
这是数值标量测试，只传组件名，不直接传元组、菜单、按钮、multiparm或callback控制。
测试值被范围钳制而未按要求生效时判失败，不把未真正执行的case计为通过。

每个case先改值/cook，再测指标与接口，最后恢复原值、表达式、关键帧、frame，并核对实际
output完整bgeo解码数据恢复：排除导出头date和派生group_summary，已知组目录按组名规范排列；
保留所有组成员、ordered group内部顺序、用户属性及几何。原生Tube/Sphere半径不靠P-only判定。控制测试当前仅支持
Polygon/Mesh/Sphere/Tube及点几何；Packed/NURBS/volume等在写参数前返回unverified。
Packed序列化含随recook变化的数据，暂不把原始bgeo hash当它的恢复oracle。
恢复失败必须停止继续改场景并检查，不自动抹掉错误；无法测量的类型保持unverified。
文件I/O、Python/solver状态、未声明外部回调不属参数恢复范围，不要对此类控制运行测试。

## 读结果与返工

- 先读control_summary的status/reason/case_counts和restored；results=[]可能是基准失败或unsupported，not_run不是pass。摘要保留controller/output、失败case/判据和基准值，不能只打印results后丢掉失败原因。
- `status=fail`：看具体接口点/最近primitive/距离，或控制测量的baseline/measured/delta。range同时约束基准与扰动；只希望约束变化时用delta。验证恒定件时连同应响应的主体一起选取，保留非零响应以排除死控制。
- `status=unverified`：证据方法不支持，不得改写成pass；换经过验证的数据表示或独立方法。
- `restored=False`：状态恢复异常，先处理，不重试下一case。
- `ok=True`：仅已声明接口/控制case通过；还需最终网络warning及视觉质量验收。
- 数值最近距离是无符号邻近，不等于插入深度；整组bbox极值对称不是镜像几何。需要局部轴、明确部件对和覆盖范围，方法不能证明的关系保持unverified。
- 保存草稿/部分交付不被这些门禁止，完成报告必须保留未完成项。

修订生成器后刷新受影响检查，不沿用旧geometry_sha256/contract_sha256。接口检测和构造可
共享设计坐标，但验证必须从真实交付表面取值，不能只检设计anchor的一致性。
期望写错可以依据独立解析或已知几何纠正，但修正后必须复跑受影响case；语言解释不能替代新结果。

## 来源与验证

SideFX [Prim.nearestToPosition](https://www.sidefx.com/docs/houdini/hom/hou/Prim.html#nearestToPosition)
和 [Geometry.freeze/data](https://www.sidefx.com/docs/houdini/hom/hou/Geometry.html)；本项目
`dsh-quality-contracts.test.py`覆盖连接正例、方向正确但脱开、默认通过/扰动失败、空组、基数、
自重叠、游离driver点、unsupported target、预算、死控制、原生Tube、表达式/cook恢复、ownership。
`dsh-interface-evidence.test.py`另覆盖真实实例脱开、允许间隙、接触及相交时顶点距离仍为正的反例。
工具合同以目标版本回归为据；SOP工作流自然采用仍需新会话验证，不宣称制造认证。


## v13：不改变交付网格的截面观察

Applies when：独立Polygon部件在明确轴平面处应邻近另一表面，现有顶点太稀或点组选取随参数跳变。
Do not use when：任意实体碰撞、融合部件、自交或需要证明整面接触；共面面/歧义截面保持unverified。

```python
interfaces = [{'id':'section_fit', 'method':'section_proximity',
  'source_group':'supports', 'target_group':'cross_member',
  'axis':1, 'plane_at':'target_center', 'expected_components':4,
  'max_distance':0.002}]
report = geo_check_interfaces(out, interfaces)
```

示例数字只是schema；组件数量和容差来自任务。每个源组件都需非空闭合截面，取实际交线段中点到目标面的距离。
不需要给交付网格加Resample，也不把expected_points简单删除。component_coverage明确各组件样本量，
预算/不支持保持显式状态。参数扰动复用同一interfaces，target_center每次来自目标实际几何。

派生参数域可用数据化线性右值，例如移动量必须低于可用尺寸减去壁厚和余量：

```python
domain = [{'id':'clearance', 'left':'travel', 'op':'lt',
  'right':{'terms':{'available_length':1, 'wall_thickness':-1}, 'constant':-0.01}}]
```

不执行表达式字符串、不自动钳制；它只验证声明case。至少选一个接近耦合边界的组合，
对真实输出关系复验，不能用两个公开参数大小关系代替全部派生锚点。

闭合壳的观察分三层：boundary_edges、orientation_conflicts、shell_orientation。
后者positive只在简单非嵌套壳条件下解释为外向；自交/嵌套未测，开放表面不推断内外。
双面预览能掩盖反向面；按HOM primitive normal与已知外表面方向核对，不能任取叉积约定。

实现回归见`dsh-modeling-semantics.test.py`；过程证据留在会话/CI或非发布临时产物，
新模型自然采用及质量提升仍待新会话验收。
