# Rig / Animation 稳健模式

## 目录

1. Channel animation
2. Rigid pieces 与路径依赖状态
3. Hierarchy / KineFX / skin
4. APEX 与 simulation 边界
5. 验证矩阵
6. 官方与本机基线

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

## 6. 官方与本机基线

- Houdini Animation：https://www.sidefx.com/docs/houdini/anim/
- HOM Keyframe：https://www.sidefx.com/docs/houdini/hom/hou/Keyframe.html
- Pack：https://www.sidefx.com/docs/houdini/nodes/sop/pack.html
- Transform Pieces：https://www.sidefx.com/docs/houdini/nodes/sop/xformpieces.html
- KineFX：https://www.sidefx.com/docs/houdini/character/kinefx/index.html
- Rig Pose：https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--rigpose.html
- Joint Deform：https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--jointdeform.html
- APEX graph basics：https://www.sidefx.com/docs/houdini/character/kinefx/apexgraphbasics.html

在线文档当前以最新 Houdini 为主。实际 node type、multiparm、Tab recipe 与 HOM 行为必须用目标
H21/H22 的 runtime、本机 `$HFS/houdini/help` 和回归确认；未验证版本不能写成已支持。
