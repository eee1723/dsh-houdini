# 可编辑路径与曲线

适用：线缆、管带、轨迹、装饰线、轮廓或表面走线需要平滑、避开部件并继续手调。
曲线造型、绕行选择、离散采样和扫掠截面朝向是不同问题；一次增加点数不能同时解决它们。
精确参数、菜单与版本事实按需读节点卡，不从旧Curve的`coords`猜Curve 2.0接口。

## 用少量可理解的控制表达走向

按当前问题明确端点及出入方向、依附面或工作平面、需要经过/绕过的区域和截面尺寸。
控制点对应接头、转弯、最高点等可解释的造型位置，使用共同坐标系和尺寸来源。
可以先在局部平面设计再变换到安装位置；空间路径才使用三维控制。
连续曲线的段间端点与切向需共同定义，不能把各段独立光滑当成拼接光滑。

| 要修改的内容 | 合适表示 | 取舍 |
|---|---|---|
| 接头方向、局部曲率、精确转弯造型 | 三次Bezier锚点和切线柄，可用`sop_recipe('curve_path')`规划原生网络 | 锚点与柄角色不同；共享端点及对齐切线控制连续性 |
| 经过少量造型锚点，形成圆弧、椭圆或直线之间的顺滑过渡 | Circle Spline的Hybrid，或插值拟合 | 保留少量锚点，观察过冲和局部曲率；它们不自动选择无障碍走向 |
| 必须经过给定位置的数据路径 | Spline Fit插值，按点分布选择参数化 | 必经锚点不等于控制顶点；全局插值可能影响较远区域 |
| 密集采集线需要减点、去抖或简化 | Spline Fit近似，给出允许形状误差 | 近似可以离开原始点，接头和禁入区需另约束 |
| 松弛、悬垂、受力后的线缆 | 合适的曲线/绳索求解，约束端点与碰撞体 | 形体来自受力关系，不能用任意正弦波替代需要的物理含义 |

Bezier的阶数、重解释和拟合是不同选择。把任意必经点折线重解释成Bezier控制顶点，不会自动得到穿过每个点的曲线。
需要固定切向时保留明确的切线柄；自动平滑不替作者选择接头离开方向。
Circle Spline官方的bounded描述不构成控制点凸包、任意障碍净距或全曲线无自交保证。

## 保留作者和用户都能修改的源

常用组合可以是：

```text
少量Add控制点/算法控制多边形
  → Curve 2.0原生编辑入口
  → Circle Spline / Spline Fit（需要时）
  → Resample（按输出精度）
  → 明确朝向的Sweep或下游消费者
```

Curve 2.0接收第一输入的曲线供原生交互态编辑，不需要写入其内嵌Geometry参数。
希望手调少量必经锚点时，将它放在拟合或密集采样前，保留Polygon控制线；希望手调样条控制顶点时，可放在拟合后。
已有Bezier控制多边形也可以由Curve 2.0重解释，随后直接采样和成形。
不要把数百个采样点当作用户唯一的造型入口；半径、截面、扭转和采样精度应能分别调整。

例如用原生Add保留少量可设参的锚点，再交给Curve编辑和Hybrid成形；`points`由当前任务提供：

```python
point_parms = {'points': len(points), 'prim0': ' '.join(map(str, range(len(points)))), 'closed0': False}
point_parms.update({'pt%d' % i: list(p) for i, p in enumerate(points)})
spec = [
    {'name': 'path_anchors', 'type': 'add', 'parms': point_parms},
    {'name': 'EDIT_PATH', 'type': 'curve', 'inputs': ['path_anchors'],
     'parms': {'outputtype': 'polygon', 'convertcurves': True, 'updatefrominput': True}},
    {'name': 'path_shape', 'type': 'circlespline', 'inputs': ['EDIT_PATH'],
     'parms': {'splinetype': 'hybrid'}},
]
build_module(parent, spec, output='path_shape')
```

这只是一个表示选择，不是通用造型配方。已有参数化路径保留有效依赖；原生编辑记录与输入点序/拓扑有关，
改变控制点数量或排序后复查原生编辑和下游。`updatefrominput`关闭会冻结输入更新，不把它当作修复上游变化的默认方法。

## 共享锚点与控制柄的原生路径

收到“接在设备上”“沿桌沿走线”时，先从实际组件/控制读取端口、接触面及局部坐标，区分设备连接端、导向点和自由端。当前 recipe **不查询或绑定几何锚点**，不把输入的数字位置自动认作真实连接。可将已有主控制的坐标分量按 `{parm:参数名}` 引用给它；需要跟随实体或运动时，保持实体与端点消费同一份有效状态，按实际原生数据流实现，而不是重复抄当前坐标。不要为了使用 recipe 重建有效的原生曲线。

```python
plan = sop_recipe('curve_path', {
    'name': 'lead', 'controller': 'CTRL', 'segment_length': 0.005,
    'anchors': [
        {'name':'plug', 'position':[{'parm':'plug_x'}, 0.8, 0],
         'handle':[0, 0, 0.08]},
        {'name':'rest', 'position':[0.25, 0.79, 0.2],
         'handle':[0.08, 0, 0]},
        {'name':'probe', 'position':[0.5, 0.79, 0.15],
         'handle':[0, 0, -0.04]},
    ],
})
# CTRL/plug_x 须已存在，数值按当前组件读取；示例尺寸不是通用布线默认。
built = build_module(parent, plan['nodes'], output=plan['output'],
                     required_outputs=plan['required_outputs'])
```

`handle` 是从锚点指向出向 Bézier 控制点的位移，长度是 SOP local 单位，不是单位切线。每段由前锚点、前锚点加 handle、后锚点减 handle、后锚点组成。同一接点只维护一份位置与对称控制柄，避免分段分别计算时错开。相同局部参数区间下两侧一阶导数相同（C1）；非零柄同时给出连续切向。它不承诺曲率连续或恒定弯曲半径，零柄没有有效切向。

返回 `anchors` 给出名称对应的 Add 锚点/进出柄点号，`edit_nodes` 给出控制点、原生 Curve 和采样输出。可调整 Add 原生点参数或在 Curve 2.0 继续编辑；原生局部编辑后不再自动保证原来对称柄关系。常用端点/松弛量放在主控制，局部控制柄留在路径，不把每个坐标都复制为公共滑条。当前只提供开放平滑三次路径，不求解避障、长度、最小弯曲半径或几何投影。

分段公式另行构造时，先在接缝读左右极限的位置和切向，再接成形。位置不连续的两段被折线连上会出现突兀拐折；提高 Resample/Sweep 分段不能修复这个设计错误。曲线输入使用 `polyline`，明确开放端，避免意外闭合的返回段。

## 将避障和表面贴附作为真实空间关系

- 自由走线先选择从哪一侧绕过、经过哪些空间，再拟合。线缆有半径，中心线离障碍的距离需要包含截面包络与所需净距。
  单点、整件bbox或只看一个方向的图像不能证明成品无穿插。端点附近允许的插接与其余路径避障分开处理。
- 螺旋绕线把圈距、线径和弯曲半径作为相互关联的设计量。固定半径线圈的相邻同角点中心距就是轴向圈距；圈距小于线径时，增加采样不能提供正净距余量。变半径、交错绕线和有意接触按实际三维包络判断，参数条件不替代最终实体检查。
- 多根线先分配入口、导向、交叉先后或通道，再添加受限扰动。随机相位不能代替彼此避让；靠桌面的中心线高度要包含半径，钳制水平高度不避开桌上物件。
- 松弛求解保留端点约束和碰撞体，核对Vellum的`pscale`/厚度与下游Sweep半径；模拟无报错不证明最终线径无穿插。
- 沿已知表面边网寻找通路时，可用Find Shortest Path及明确代价/禁入区域；其输出受输入边网约束，
  它不是任意三维自由空间规划器。转成平滑样条后可能切角穿过障碍，必须复验。
- 需要贴附指定表面时，Ray按明确方向或最近点投影，并限定接收面与偏移含义。多层、凹槽、孔边或背面附近，
  最近面不一定是设计目标。H22的Walk on Surface可沿表面测地线/向量场行走，H21不能依赖此节点。
- 平滑可能离开支承面，重新投影也可能引入折角；按实际曲面选择内在路径或有约束的平滑，不能靠固定的Smooth→Ray顺序宣称解决。

查看最终Sweep表面和障碍的实际关系。闭合Polygon实体且方法适用时，可声明`solid_overlap`测交集；
点到面距离只覆盖所声明样本，不能认证连续曲线、开放带面或任意自交。方法不适用时保留未验证，并给能暴露疑点的近景。

## 定位折线净空反馈

`geo_curve_clearance(node, radius, ...)` 在实际选定的开放 Polygon 曲线上全量检查有限线段对；最近点可在线段内部，不靠端点采样判断交叉。`radius` 是正数或一个 primitive 标量半径属性名，一条曲线上保持同一半径。具名 primitive 组可限制要观察的线；其他线和实体不随之通过。

先读 `status` 和 `coverage`，再读 `worst_pairs` 的 primitive/segment、`segment_u`、`position`、`path_distance` 与 `envelope_gap`。负 gap 表示两条线段的半径包络重叠；低于明确 `clearance` 才是这项间隙要求失败。根据最差位置调整对应锚点/柄、线径、螺距或路线，再查相关消费者；不要靠改随机种子反复碰运气。

同一条线的局部点对属于连续扫掠的邻域，不能按独立管段互相碰撞来判断。工具按真实两点的沿线弧距裁剪每对线段的参数域，只排除 `self_exclusion` 内的点对；长段即使端点靠近，远弧部分仍会被测，直接相邻的长回折也不会整段漏掉。省略时使用该线 `π*(radius+clearance/2)`：以有效半径的半圆弧长定义局部连续管邻域，返回每条线实际采用的数值。它是明确的设计尺度，不是测得的最小弯曲半径，也不保证局部曲率合法。用 `2*radius` 作为窗口会让普通弯曲在边界弧距处的弦长小于线径，误把局部连续包络判断为非局部碰撞。显式零表示不排除局部邻域，连接处的包络重叠也会出现。

**排除区域没有被认证**，过大的排除会掩盖局部紧弯；不得靠放大排除使失败变通过。`coverage` 区分完全局部的线段对与只裁掉一部分局部域的线段对。开放 Polygon 的首尾坐标精确相同才识别为几何环，同时裁去环缝两个方向的局部域；近似重合不猜测闭合意图。环太短而全部落入局部窗口时返回 unverified。数值比较只容纳结果量级的双精度浮点舍入，`worst_pairs.roundoff_tolerance` 不是可放宽的建模间隙。

`max_pairs` 约束排除前全部候选对；预算不足时零距离测量并返回 unverified，不抽样。当前不支持闭 Polygon 面、Bézier/NURBS 原曲线、packed 或退化线段；不要给它整个 Sweep 网格。对 Resample 输出的通过只覆盖那组折线段及半径包络，不证明未采样的平滑曲线、局部曲率、Sweep 截面/封口、障碍物或接头关系。最终实体有明确完整闭合 Polygon 组时，仍可用已有 `geo_check_interfaces(method='solid_overlap')` 检查具体相交；接触和控制变化沿既有模块合同检查。

## 平滑、精度和截面分别判断

Resample默认按直边解释Polygon；只增加采样不会重新设计转弯。显式选择插值/细分解释会改变形状，
须同时核对锚点、端点、过冲和净距。采样长度按曲率与最终观察尺度决定，数值更小不是更好的走向。
Spline Fit近似的容差控制偏离，不能用增加采样补偿错误拟合。

Sweep的截面朝向由路径frame（沿线的局部方向基）决定。非圆截面、闭环或空间路径要明确up、端部方向及扭转意图；
原生Orientation along Curve可输出`orient`或`N/up`，Sweep是否消费这些属性要在实际成品上检查。
同一扭转不要在上游frame和Sweep重复施加；端点切向/截面翻转与中心线折角分别定位。

调整路径、截面或主尺寸后，复查受影响的接头、狭窄区和用户代表性控制状态。检查cook、闭合或非空仍不代表路径顺滑、
无穿插或艺术质量已确认；证据范围沿[模块关系与控制检查](module-quality-contracts.md)表达。

依据：[Curve 2.0](https://www.sidefx.com/docs/houdini/nodes/sop/curve.html)、
[Circle Spline](https://www.sidefx.com/docs/houdini/nodes/sop/circlespline.html)、
[Spline Fit](https://www.sidefx.com/docs/houdini/nodes/sop/fit.html)、
[Resample](https://www.sidefx.com/docs/houdini/nodes/sop/resample.html)、
[Orientation along Curve](https://www.sidefx.com/docs/houdini/nodes/sop/orientalongcurve.html)、
[Ray](https://www.sidefx.com/docs/houdini/nodes/sop/ray.html)、
[Find Shortest Path](https://www.sidefx.com/docs/houdini/nodes/sop/findshortestpath.html)、
[Walk on Surface](https://www.sidefx.com/docs/houdini/nodes/sop/walkonsurface.html)。
原生输入、局部修改、重采样反例及Sweep消费朝向的验证在`tools/tests/dsh-node-knowledge.test.py`；
该范围不认证任意避障求解、GUI交互态或自然任务的造型质量。

原生路径规划与折线净空的源码为`dsh_curve_paths.py`，公开入口沿`sop_recipe`与`geo_curve_clearance`；
`tools/tests/dsh-curve-paths.test.py`在隔离H21/H22核对原生构造、控制驱动到实际Sweep、原生控制点修改、
内部交叉/近平行反例、规则卷线、环缝、预算和不支持输入。这些检查不证明自然作者采用或最终实体质量。
三次Bezier四控制点表示见[PBRT Curves](https://pbr-book.org/4ed/Shapes/Curves)；有限线段最近距离参考
[Geometric Tools](https://github.com/davideberly/GeometricTools/blob/master/GTE/Mathematics/DistSegmentSegment.h)，
当前实现求闭区间二次距离的内部驻点及边界最小值，不调用外部库。
需要物理松弛时使用原生[Vellum Constraints](https://www.sidefx.com/docs/houdini/nodes/sop/vellumconstraints.html)/
[Vellum Solver](https://www.sidefx.com/docs/houdini/nodes/sop/vellumsolver.html)并验证实际输出；几何插值不求解受力和材料扭转。
