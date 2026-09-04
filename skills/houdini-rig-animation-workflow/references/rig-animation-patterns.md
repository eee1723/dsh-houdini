# Rig / Animation 稳健模式

## 目录

1. Channel animation
2. Rigid pieces 与路径依赖状态
3. Hierarchy / KineFX / skin
   - 3.1 KineFX 机械 FK 与刚体交付
   - 3.2 OBJ scene parenting 例外
4. APEX 与 simulation 边界
5. 验证矩阵
6. 探测与失败转向
7. 官方与本机基线

## 1. Channel animation

Channel 表示一个参数值随时间变化。使用：

```python
set_keyframes(node, {
    "tx": [
        {"frame": 1, "value": 0, "curve": "linear"},
        {"frame": 24, "value": 2, "curve": "bezier"},
    ]
})
```

H21/H22 基线：

- `setFrame()` 接受 frame；`setTime()` 接受秒，不能混用；
- 支持的最小曲线词汇为 `constant/linear/bezier`，对应 key expression
  `constant()/linear()/bezier()`；
- curve 描述从当前 key 离开的 segment；
- `replace=True` 替换该 channel 旧 keys；`replace=False` 保留旧 keys但不得覆盖同一 frame；
- `read_parms` 用 `time_dependent/key_count/first_frame/last_frame/curves` 做紧凑检查，完整
  channel 曲线仍以 Houdini 为真相源。

不要用大量逐帧 keys 默认替代正确曲线；确需 baked motion 时可用，但注意结果/trace 体积。
Channel 正确求值只证明控制数据，不证明被驱动 geometry/rig 的语义。

## 2. Rigid pieces 与路径依赖状态

稳健数据：

```text
stable name/piece_id
+ rest P/orient/transform
+ logical state（若后续 membership 依赖当前状态）
+ ordered operations
→ current template transforms
→ Transform Pieces / packed output
```

Copy to Points 的 packed output 不能假设自动保留模板 `name`。H21 回归显式用 Attribute Copy
把 rest point name 复制到 packed point，再由 Transform Pieces `Match by Attribute: name`。
对已经展开的 polygon geometry 使用 Pack By Name 时，应在 primitives 上建立 name；只有 point
name 会触发“source contains primitives but point name will not pack them” warning。先确认具体
source geometry 的 piece attribute class，再选择 point/primitive name，不能写一个跨两种输入的
固定假设。

路径依赖操作按顺序求值：每个 completed move 更新 logical coordinate/orientation；active move
只应用 partial transform；后续 membership 从更新后状态选择。不可把 R→U 等非交换序列压成
初始 `gx/gy/gz` 上的独立绝对角度。

验证：

- first move 活动集合/轴正确；
- non-commutative second move 使用更新后的 membership；
- P diff + orient/transform diff；
- piece local extent/刚体不变量；
- sequence mid/end；
- inverse 逐 piece 恢复。首尾相同本身无效，因为错误绝对通道也可全部归零回 rest。

历史证据来自已移除的 `houdini/tests/regress_rig_state_model.py`；当前最小等价回归尚待按
`docs/development.md` §5 重建，不能把缺失脚本当成现行验证入口。

## 3. Hierarchy / KineFX / skin

KineFX skeleton 是 SOP geometry：joint point 至少有稳定 `name`、P、3×3 `transform`，parent-child
由拓扑表达。Rig Pose 的 Pre-Multiply 常用于在 local space 叠加 FK；Post-Multiply、Override、
From Rest Pose 有不同空间/替换语义，不能混用。

Joint Capture Proximity/Biharmonic 在 rest skin 上生成 `boneCapture`。Joint Deform 三个输入是：

1. 带 capture weights 的 rest geometry；
2. capture pose skeleton；
3. animated pose skeleton。

检查 joint names 和 topology 对齐、capture 属性存在、pose transform 随帧变化、deformed P/N
变化且 warning 为空。只有 skeleton 动了不证明 skin 正确；只有 skin 图像动了也不证明权重、
层级或 rest pose 正确。

历史证据来自已移除的 `houdini/tests/regress_animation_foundations.py`（3-joint Rig Pose /
Joint Capture / Joint Deform）；当前最小等价回归尚待重建。

### 3.1 机械 FK 与刚体交付实测基线（2026-09-04，H21.0.440 / H22.0.368 双版本通过）

回归：`tools/tests/dsh-kinefx-fk.test.py`。先把 driver、binding 与 driven output 分开：

**Applies when**：父子 joint 层级驱动最终可见的 rigid/packed geometry；需要从 rest pose 得到
可编辑 FK channels，并交付真实变形后的 geometry。

**Do not use when**：互不依赖的普通 channels；需要更新 membership 的非交换 piece 状态机；
纯 joint/control-shape 交付；带连续权重的有机 skin；solver 物理运动；需要 animator-facing IK、
constraint 或可复用 graph 时另走对应模式。

1. skeleton：Python SOP 生成 joint 点（稳定 `name` + P）+ polyline 拓扑 + **16-float
   `rest_transform`** 点属性（`attachjointgeo` 必需，缺它报 "No valid roots found"）。
2. `rigdoctor` 的 `inittransforms` 默认关，必须显式设 1 才会初始化 `transform`/`localtransform`。
3. `kinefx::rigpose` 的 `transformations` multiparm 每实例控制一组 joint：
   `insertMultiParmInstance` 没有动词，单独一次裸调用（gate 不拦，它不在动词覆盖面）；
   **group 必须写 `@name=<joint>`**（裸 joint 名命中空组、只有 warning、不报错）；实例的
   `r{i}x/y/z` 是普通 channel，直接 `set_keyframes` 打帧。
4. `kinefx::attachjointgeo` 只把 control geometry 或 capture-influence geometry 作为 `jointgeo`
   元数据附到 skeleton；Role 的 Control/Capture Geo 都不是最终刚体 skin deformation。它适合
   选择 controls、辅助 capture solve 或传递 shape template，不用来证明可渲染 link 已随 pose 运动。
5. 可见刚体交付：`kinefx::capturepackedgeo` 输入 `(rest geometry, capture-pose skeleton)`，打开
   Capture by Attribute，以 primitive `name` 匹配 skeleton point `name`，产生 100% rigid
   `boneCapture`；随后 `kinefx::jointdeform` 输入 `(captured rest geometry, capture pose,
   animated pose)`，输出真正随 joint 运动的 geometry。
6. FK 验证分两层：joint `transform` 验 driver；最终 deform 输出按 piece 检查实际 world center、
   orientation/extent 与 recovery。混有 skeleton 的总 bbox、joint P、`jointgeo` offset 或 packed
   anchor transform 都不能替代 driven geometry 证据；临时隐藏/排除 skeleton 后 link 仍须存在并运动。

#### H21/H22 fast path

下列只固定跨版本验证过、在自然 trace 中重复出错的 API 边界；joint 数、名称、位置、轴、动画和
shape 仍由任务决定。

Python SOP 建 skeleton 时：

```python
geo = hou.pwd().geometry()
geo.addAttrib(hou.attribType.Point, "name", "")
geo.addAttrib(hou.attribType.Point, "rest_transform", tuple([0.0] * 16))

# 对每个任务定义的 joint：
p = geo.createPoint()
p.setPosition(rest_position)
p.setAttribValue("name", joint_name)
p.setAttribValue("rest_transform", rest_matrix.asTuple())

# parent-child 顺序由任务定义；open Polygon 表达 hierarchy。
poly = geo.createPolygon(is_closed=False)
poly.addVertex(parent_point)
poly.addVertex(child_point)
```

不要用标量 `16` 作为属性默认值（会得到错误类型），不要用 `Matrix4.explode()`（返回分组结果而非
稳定 16-float flat tuple），也不要猜不存在的 `hou.primType.PolyLine`。

Rigid capture 的最小参数合同：

```python
cap = tab_create(parent, "kinefx::capturepackedgeo",
                 inputs=[rest_geometry, capture_pose])
set_parms(cap, {
    "packinput": 1,
    "useconnectivity": 0,
    "nameattribute": "name",
    "capturebyname": 1,
    "skinattr": "name",
    "skelattr": "name",
})
deform = tab_create(parent, "kinefx::jointdeform",
                    inputs=[cap, capture_pose, animated_pose])
```

前提是 rest geometry 的 primitive `name` 与 skeleton point `name` 一一表达预期绑定。若输入已经是
正确 packed pieces，可按实际输入关闭内部 packing；不得机械照搬 `packinput=1`。Capture Packed
Geometry 的交付输出是 captured geometry；不要猜不存在的 skeleton output，capture pose 直接使用
已验证的 rest/capture skeleton。

按下面四个 checkpoint 前进，某层失败就停在该层：

1. capture pose：joint `name/P/transform`、hierarchy、无 warning；
2. rest geometry：primitive `name` class 正确，每个目标 piece 非空；
3. captured geometry：piece 数合理，point `boneCapture` 存在，capture path 能匹配 joint name；
4. driven output：隐藏 skeleton/helper 后仍非空；运动帧的实际 piece center/orientation/extent 符合
   joint transform，刚体距离不变量保持，recovery 回到 rest。

**版本敏感 claim**

- Claim：KineFX rigid deliverable 使用 Capture Packed Geometry → Joint Deform；Attach Joint Geometry
  只承担 control/capture 辅助形状。
- Why it changes a decision：防止 skeleton/metadata 正确但最终 link 保持 rest 的虚假完成。
- Source/provenance：SideFX 官方 Attach Joint Geometry、Capture Packed Geometry、Joint Deform 文档；
  一次自然层级刚体任务及其同版本 viewport 复现只作为匿名反例，不提供实例 recipe。
- Houdini version/context：SOP，H21.0.440 / H22.0.368。
- Evidence level：E2（官方合同 + 两个目标版本的 disposable runtime 复现）。
- Applies when：用户最终需要 packed/rigid geometry 随 KineFX animated pose 运动。
- Counterexample/boundary：只制作 joint controls、capture influence 或 shape template 时，
  Attach Joint Geometry 正是目标；用户只要 skeleton 数据时不强制建立 skin。
- Validation：非立方 link 在测试帧的 center 与 x/y extent 都随 joint 旋转，恢复帧回到 rest；
  final output 不含 skeleton polygon，capture 输出存在 `boneCapture`。
- Last reviewed：2026-09-04。

**命名空间坑**：kinefx 类型注册名带 `kinefx::` 前缀，`createNode(exact_type_name=True)`
不接受裸别名；`resolve_latest_type` 已支持 namespace 解析（2026-09-04 修复）。但 H22 的裸名
`rigpose` 会命中 `apex::rigpose`（接口不同，无 `transformations` multiparm）——跨版本 recipe
一律钉 `kinefx::rigpose`。`apex::rigpose` 是 H22 更新的节点，但交互重心在 viewer state，
agent 程序化路径未验证，不进 recipe。

### 3.2 OBJ scene parenting 例外

**Applies when**：camera/light/null 等顶层场景对象跟随、既有 OBJ hierarchy 维护、用户明确要求独立
OBJ nodes，或下游必须接收 OBJ hierarchy。**Do not use when**：新建几何父子机械/FK；`/obj` 路径
本身不算授权。

使用 `set_object_parent(child, parent, keep_world=True, reason=...)`；不使用通用 `connect`。`reason`
选 `scene_assembly/camera_light_null/existing_legacy/explicit_user/downstream_obj_delivery`。操作后要求
`child.inputs()[0] == parent`；`keep_world=True` 时另检查 world transform preserved。若最终合同是几何，
仍需 Object Merge/导出形成显式 final geometry 并在该输出上验证，Object transforms 不替代交付证据。

## 4. APEX 与 simulation 边界

APEX 是 graph evaluation，不是所有 rig 的默认层。采用前证明需要：animator-facing controls、
constraints、FK/IK、可复用 component 或 delayed evaluation。先用当前版本真实 Tab/官方组件，
不要手写大段 APEX graph 只为替代简单矩阵或 channel。

H21.0.440 / H22.0.368 的最小非交互基线已经确认：两版均提供 `apex::graph` 与
`apex::invokegraph`。SideFX 随安装的 `APEXGraphExamples.hda` 用 detail dictionary 输入
`a=2, b=3.5`，Invoke Graph 无 warning/error 地输出 detail dictionary
`output_parms.result=5.5`；把输入改为 `10,-4` 后重新求值得到 `6.0`。缺少 graph 输入时
`cook(force=True)` 抛 `hou.OperationFailed`，`node.errors()` 明确包含
`Not enough sources specified.`；`errorhandlingmode` 的稳定菜单为 `ignore/warn/abort`。

版本差异在帮助入口而非这条求值契约：H21 fixture 位于
`$HFS/houdini/help/examples/nodes/sop/apex--editgraph/`，H22 位于 `apex--graph/`。
历史回归 `houdini/tests/regress_apex_evaluation.py`（现已移除）曾按当前 `$HFS` 选择 SideFX
fixture，仅证明
APEX graph engine、字典 binding、输出与失败读取可用；它不证明 Animate State、control
shape、constraint、FK/IK、component graph 或完整 character rig 已验收。真实 rig 仍需按任务
建立 controls/pose/deform 的数据门，不能把该 smoke 外推成“APEX 已全部支持”。

RBD、ragdoll、secondary motion 等具有 solver state、substeps、collision、cache、随机性与长 job
生命周期，应交 SIM workflow；本 skill 只负责其输入 rig/动画和输出姿态边界。

## 5. 验证矩阵

| 模型 | 必查数据 | 时间门 | 视觉边界 |
|---|---|---|---|
| Channel | keys/frames/curves/eval | key + segment midpoint | 不能证明下游语义 |
| Rigid pieces | name/rest/current P+orient/transform | first/non-commutative/mid/recovery | 不证明隐藏 piece state |
| Hierarchy | name/topology/local/world transform | parent/child propagation | 不证明 constraint 数据 |
| Skin | boneCapture/capture pose/animated pose/P/N | rest vs posed 多帧 | 不证明权重质量细节 |
| APEX | graph inputs/outputs/controls/evaluation | control-driven states | 只验证 animator-facing 可见部分 |

所有模型都要恢复用户 frame/selection/display；正式 output 最后才设置。

## 6. 探测与失败转向

- 优先读本 reference 的对应模式，再查动词、Tab entry、parm 与 `describe`；不要先枚举整个类型表。
- 精确类型存在但参数/数据不符时，用一个最小 joint 或 piece probe，先证明输入/输出合同，再扩成
  完整资产。probe 不与正式网络交叉接线，验证后删除。
- 两次同边界失败后按层换策略：skeleton 失败回到属性/拓扑；capture 失败先查 name class 与 packing；
  deform 失败查 boneCapture、capture/animated pose 对齐；画面失败先查 driven output，不先调相机。
- 锁定 HDA internals 只用于“公开参数和本机 help 无法解释实际结果”的诊断。内部节点名不是公共
  合同，不得写入正式 recipe 或依赖其跨版本稳定。
- 最后一次改变 skeleton、capture mapping、deform inputs 或 piece topology 后，旧 FK、rigidity、
  frame diff 和 render 全部失效；只重跑这些下游门。只改 display-only color 时仍须刷新最终 render、
  warning 和保存证据，数值 FK 可用新鲜 topology/signature 确认未变后复用或重跑。

## 7. 官方与本机基线

- Houdini Animation：https://www.sidefx.com/docs/houdini/anim/
- HOM Keyframe：https://www.sidefx.com/docs/houdini/hom/hou/Keyframe.html
- Pack：https://www.sidefx.com/docs/houdini/nodes/sop/pack.html
- Transform Pieces：https://www.sidefx.com/docs/houdini/nodes/sop/xformpieces.html
- KineFX：https://www.sidefx.com/docs/houdini/character/kinefx/index.html
- Rig Pose：https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--rigpose.html
- Joint Deform：https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--jointdeform.html
- Capture Packed Geometry：https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--capturepackedgeo.html
- Attach Joint Geometry：https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--attachjointgeo.html
- APEX graph basics：https://www.sidefx.com/docs/houdini/character/kinefx/apexgraphbasics.html

在线文档当前以最新 Houdini 为主。实际 node type、multiparm、Tab recipe 与 HOM 行为必须用目标
H21/H22 的 runtime、本机 `$HFS/houdini/help` 和回归确认；未验证版本不能写成已支持。
