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
| 接头方向、局部曲率、精确转弯造型 | 三次Bezier锚点和切线柄 | 锚点与柄角色不同；共享端点及对齐切线控制连续性 |
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

## 将避障和表面贴附作为真实空间关系

- 自由走线先选择从哪一侧绕过、经过哪些空间，再拟合。线缆有半径，中心线离障碍的距离需要包含截面包络与所需净距。
  单点、整件bbox或只看一个方向的图像不能证明成品无穿插。端点附近允许的插接与其余路径避障分开处理。
- 螺旋绕线把圈距、线径和弯曲半径作为相互关联的设计量。固定半径线圈的相邻同角点中心距就是轴向圈距；圈距小于线径时，增加采样不能提供正净距余量。变半径、交错绕线和有意接触按实际三维包络判断，参数条件不替代最终实体检查。
- 沿已知表面边网寻找通路时，可用Find Shortest Path及明确代价/禁入区域；其输出受输入边网约束，
  它不是任意三维自由空间规划器。转成平滑样条后可能切角穿过障碍，必须复验。
- 需要贴附指定表面时，Ray按明确方向或最近点投影，并限定接收面与偏移含义。多层、凹槽、孔边或背面附近，
  最近面不一定是设计目标。H22的Walk on Surface可沿表面测地线/向量场行走，H21不能依赖此节点。
- 平滑可能离开支承面，重新投影也可能引入折角；按实际曲面选择内在路径或有约束的平滑，不能靠固定的Smooth→Ray顺序宣称解决。

查看最终Sweep表面和障碍的实际关系。闭合Polygon实体且方法适用时，可声明`solid_overlap`测交集；
点到面距离只覆盖所声明样本，不能认证连续曲线、开放带面或任意自交。方法不适用时保留未验证，并给能暴露疑点的近景。

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
