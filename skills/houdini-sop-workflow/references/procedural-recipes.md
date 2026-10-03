# 可编辑构造与参数状态模板

适用：来源明确的局部形体需要共同运动、重复布局、中心线成管或平面轮廓厚化。
不适用：直接生成整件产品、任意CAD装配求解、连续碰撞认证、外部资产自动坐标猜测。
配方只输出可审查的普通SOP spec；创建仍由build_module经过所有权、严格设参和失败清理。

## 按需选用

来源尺寸需要单位换算时可用modeling_dimensions，并保留source说明；已统一的场景值无需重复换算。
返回controller_spec可直接用于create_spare_parms，scene_values用于适配现有单位；工具不修改场景单位。
换算表只记录输入解释，最终物理尺寸仍从实际输出检查。

```python
dims = modeling_dimensions({'length':{'value':120,'unit':'mm'},
                            'travel':{'value':30,'min':10,'max':70,'unit':'mm'}})
create_spare_parms(ctrl, spec=dims['controller_spec'])
# length=0.12m、travel=0.03m；构造从CTRL读值，不再把原始120/30写入SOP。
```

quantities是按参数名索引的dict；原始数值与单位需一起解释。

不确定模板种类时读`sop_recipe('catalog')`；已知kind可直接`sop_recipe(kind)`取得完整示例，空dict不是schema查询。输入是同一parent已有直属源节点；controller是同层CTRL名。
复制模板先核点数与位置：零尺寸Box仍有多个重合点，不能当单点；复制后核真实件数，外观位置数和图元数都不能替代。融合后的装饰特征不适用独立连通件数验收。
模板需要明确源与控制入口，可以复用已有节点。例如把已知源和附件共同放到一个转轴上：

```python
plan = sop_recipe('hinge', {
    'name':'joint', 'inputs':['body_source','attached_detail'],
    'controller':'CTRL','parameter':'angle',
    'origin':[{'parm':'pivot_x'},{'parm':'pivot_y'},{'parm':'pivot_z'}],
    'axis':[0,1,0],
})
build_module(parent,plan['nodes'],plan['output'],required_outputs=plan['required_outputs'])
```

角度为度；轴归一化，源模型绕局部原点旋转，再放到共享origin。
活动主体与附属件消费同一个FRAME点的P/orient，不重复编写矩阵。
FRAME是驱动证据，不是接点证明；非零角查最终实际表面接口，并确认原点不漂移、方向正确。
多个调用需要唯一name；已有源保持不变。同名、缺参数、缺源或cook失败由build_module拒绝。

| kind | 参数与输入 | 原生构造/验收 |
|---|---|---|
| hinge | parameter角度、origin、axis；局部源及附件 | Merge→单FRAME→Copy to Points；查旋转中心与实际连接 |
| slider | parameter位移、origin、axis | 同一FRAME位移；查行程端点、附件、导向间隙 |
| guided_slider | inputs移动件/附件，guide直属Polygon输出，parameter、travel_min/max、clearance、origin、axis | 实际源/导轨点投影推导相对行程，源最小投影对齐导轨起点+clearance；全范围不容纳时cook失败。投影不是槽面接合证明，仍查真实接口 |
| surface_attach | inputs细节源，receiver/receiver_group，origin、tangent、max_distance | 投影到真实指定面组，以法线和切线构造FRAME；源脚面Y=0，+Y向外。缺组/超距/退化方向拒绝，脚面整体另验 |
| gusset | length/height/thickness | 三角轮廓→原生厚化→命名脚面点组{name}_foot；源局部Y=0，需另装配到真实表面 |
| fastener | shaft_radius/shaft_length/head_radius/head_height，segments可选 | 原生封口Tube的头杆共享接合面；无螺纹/受力认证，接收件开孔和插入深度另验 |
| repeat | parameter整数1..256、origin、axis、spacing | 一份源→带id模板→Copy；查期望数量、间距、源替换和碰撞 |
| sweep_tube | 单一开放中心线、radius | Sweep内建圆管/端盖；查切向、封口、绕序和局部轮廓 |
| profile_shell | 单一闭合平面Polygon薄片、thickness | PolyExtrude前/后/侧面；不对已有实体照搬，查壁厚和内面 |

origin各分量及spacing/radius/thickness接受数值或`{parm:'同CTRL标量名'}`。
依赖参数的合法范围由设计给出；配方不求解、不钳制、不保证极端值能成形。
父级共享尺寸变更后，输出、细节、外部固定承接件的关系分别复查。

结构模板可先`sop_recipe('guided_slider')`或`sop_recipe('surface_attach')`读具体示例schema。
guided_slider中的guide和移动源必须为有界Polygon，统一SOP坐标系；它将参数解释为从travel_min起算的相对位移，
不把参数数值当世界位置，也不静默钳制超过范围的请求。源的实际投影包含随动附件，变长后会重新检查可用行程。
surface_attach只建立一个锚点，整个肋板脚面仍需点到面检查；狭窄面、孔边、曲面不能靠单点投影宣称全面贴合。

## 代表性参数状态

`control_test_plan(CTRL, {'width':[最小,默认,最大], 'angle':[关闭,中间,打开]})`
只读当前参数，基于显式levels规划最多16个case，覆盖单值与两两组合；候选网格最多4096。
domain可排除独立无动画标量的非法组合；动画/表达式耦合用明确case实际测试。
coverage=partial_pairwise时保留missing，不用减小levels把未测窗口隐藏。

输出tests的expectations为空，**不能直接当验收运行**。逐case补：谁应变化、谁保持不变、实际输出组、
有符号delta/绝对范围，以及该状态的interfaces，再调用test_controls。已有控制默认值若正确静止，
基准由test_controls读取；规划器不为覆盖计数再次写入同值。两两组合覆盖不等于全组合，
离散角度不等于连续运动无碰撞；狭小间隙、锁止、计数变化按风险增加专属case。

## 高细节与Packed检查

geo_check_interfaces/test_controls只在内存中展开嵌入PackedGeometry，递归预检8层、4096实例，
展开总预算为100000面、250000点、400000顶点、32MiB。保留实际变换与组/属性；
原输出的拓扑/属性/内嵌内容/实例变换仍做恢复指纹，不以展开bbox代替。
PackedDisk、Alembic、PackedFragment、volume/NURBS等不属于支持范围；预算拒绝不自动简化网格。

solid_overlap每个完整实体组最多20000面，面包围盒扫描排除不可能接触的候选，Boolean仍消费完整实体，
因此全包裹但表面不相交也能发现体积重叠。候选对和扫描上限保护主线程；不承诺抢占单次原生Boolean。
OUT_ASSET表面检查按可用part/name做完整互斥分区并报告未覆盖部分；各件健康不证明件间无穿插。

来源：本库配方/检查模块、H21.0.440与H22.0.368隔离正反例；[SopVerb](https://www.sidefx.com/docs/houdini/hom/hou/SopVerb.html)、
[Unpack](https://www.sidefx.com/docs/houdini/nodes/sop/unpack)、[Copy to Points](https://www.sidefx.com/docs/houdini/nodes/sop/copytopoints.html)。
验证入口：tools/tests/dsh-procedural-plans.test.py、dsh-meter-structure.test.py、dsh-packed-evidence.test.py；自然模型采用与质量增益独立评估。
