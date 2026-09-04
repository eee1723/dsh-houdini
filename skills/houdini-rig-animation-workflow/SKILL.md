---
name: houdini-rig-animation-workflow
description: 在 Houdini 中设计、构建、调试和交付参数动画、刚体 piece 序列、机械层级、KineFX skeleton/skin 与 animator-facing rig。用于任务涉及 keyframes、绑定、FK/IK、capture/deform、非交换多步骤或可复用控制器；不用于普通静态 SOP 建模，也不把所有“绑定”默认路由到 KineFX/APEX。
---

# Houdini Rig / Animation Workflow

先选择正确的状态模型，再写 key、建节点或看画面。目标是留下当前 Houdini 版本中可维护、
可验证的 channel/piece/skeleton/rig，而不是让“有东西动了”替代运动契约。

## 分类门

构建前把用户意图归入一个主模型；混合任务可分阶段联用：

- 普通参数、对象、灯光、镜头：channels/keyframes；
- 独立刚体 pieces、装配、魔方：stable identity + packed/template transforms；
- 新建几何父子机械/FK：KineFX joints；`/obj` 只表示创建位置，不授权 OBJ hierarchy。首个 mutation
  前必须读 reference §3.1；
- OBJ parenting 只用于 camera/light/null 等场景装配、既有 legacy、用户明确要求或下游 OBJ 交付；
  使用 `set_object_parent(child,parent,reason=...)`，不用 `connect`，细节见 reference §3.2；
- skeleton + skin：KineFX capture pose + animated pose + Joint Deform；
- animator-facing controls、constraints、FK/IK：KineFX + APEX；
- 物理运动：SIM/RBD/ragdoll，不能用 keyframe 完成门代替 solver/cache 契约。

没有完成分类、rest/current state 和身份契约前，不建复杂 rig。

简单的单 channel/单节点编辑直接完成并回读；跨层级、capture/deform、非交换状态、solver 或正式
动画交付才写下面的紧凑合同。合同可放 prose 或 todo，不为满足格式输出长篇计划。

## 三层交付合同

构建前用一行写清 `driver state → binding/evaluation → driven deliverable → 验收`：

- driver 是 channel、joint、control、template transform 或 solver state；它正确只证明驱动端成立；
- binding/evaluation 是 capture、约束、匹配属性、graph 或 solver 关系；它存在只证明关联成立；
- driven deliverable 是用户最终要播放、渲染、缓存或继续编辑的 geometry/state。除非用户明确只要
  rig/control 网络，否则必须在最终输出边界独立验证它，不能用 driver 的 P/transform、混合输出总
  bbox、绑定元数据或像素有差异替代。

若下游实际几何/状态探针失败，保留失败并回到数据模型；不得改测上游 proxy/anchor 后把同一契约
改判为通过。最终输出应能暂时隐藏 driver/helper visualization 后单独检查；用户明确要求显示 controls
或 skeleton 时才把它们作为交付内容。

## 高效执行

- 命中 KineFX §3.1 或 OBJ 例外 §3.2 时先读对应小节；已有 H21/H22 fast path 就直接使用，只探测
  当前任务真正未知的类型、参数或输入。不要把 HDA internals 当默认文档。
- 未知契约依次用 `verb_help`、Tab/parm/describe、自包含单变量 probe、本机 help；只有公开合同与
  runtime 冲突时才进入 HDA 内部。
- 同一模块边界连续两次失败后回到最后一个健康 checkpoint，说明失败在 driver、binding 还是
  deliverable，查 fast path 后换策略；不要继续堆猜测式补丁。
- 每批只跨一个可验证边界。核心求值或最终形态修改后，只刷新受影响的下游证据；最终报告使用
  最后一轮数据，不重复包装旧结果。

## 执行顺序

1. `scene_info` 确认 HIP、Houdini 版本、fps、frame range；检查已有控制器、动画和输出。
2. 写出 `identity/rest state → control/ordered operation → current state → binding/evaluation → driven output → 验收`。
3. 用当前 parent 的 Tab 查询确认节点；普通单节点 `tab_create`，setup tool 才 `tab_apply`。
4. 普通 controller 参数用 `create_spare_parms(spec=[...])`；数值 channel 用
   `set_keyframes`，不要手写 `hou.Keyframe.setTime()` 或猜 interpolation API。
5. 每个模块后 `cook_node` + `describe/read_parms`；piece 检查 P 和 orient/transform，skin
   检查 name/transform/boneCapture/rest pose/animated pose；最终再对 driven output 本身取证，
   不把 driver 或 binding 层统计重复包装成输出证据。
6. 路径依赖序列先验证第一步，再验证一个会改变后续 membership/空间的非交换第二步；
   然后覆盖 sequence mid/end 与 recovery。所有控制量归零不能证明 inverse 正确。
   一旦修改状态求值器、核心 transform 图或 membership 规则，先前所有序列证据立即失效；必须从
   first、非交换 transition、mid/end 到 recovery 全部重跑，不能只验证修复点后的终帧。
7. 客观状态通过后才用 `render_view(EXPLICIT_SOP)`；先隐藏非交付 skeleton/control/helper，确认
   主体仍完整且运动成立。动画 A/B 使用同一 `framing_frame`，且该参考取景必须覆盖整个验收帧
   包络并留边，不能只保证参考帧本身不裁切。视觉明确报告主体静止、缺失或方向相反时阻断完成；
   pixel diff 不能覆盖该反例。
8. 清理 probe、恢复 frame/selection/visibility、布局、设置交付输出并说明尚未验证的审美项。

## 关键边界

- `set_keyframes` 只写 channel 数据，不设计状态机，不替代 KineFX/APEX 或 solver。
- Copy to Points/Pack 后必须确认 stable `name/piece_id` 真正存在于 Transform Pieces 的匹配
  class；模板点有 name 不等于 packed 输出自动保留。Pack 按 polygon pieces 分包时通常需要
  primitive name，point name 会产生“不打包 primitives”的 warning，不能忽略。
- 旋转轴上的 piece 可能 P 不变但 orient/transform 变化；P diff 不能单独定义活动集合。
- KineFX 的 joint `name/P/transform` 与拓扑是 rig 数据；Joint Deform 另要求 boneCapture、
  capture pose 和 animated pose。没有 skin/层级需求时不强制 KineFX。
- Attach Joint Geometry 产生 control/capture 辅助形状与 `jointgeo` 绑定元数据，不是最终 skin/link
  deformation。需要可见刚体随 KineFX pose 运动时，按 reference 选择 rigid capture + deform；
  只需要 joint controls/capture influence 时才把 attached joint geometry 当目标。
- APEX 只在需要可复用 controls、constraints、FK/IK 或延迟 graph evaluation 时采用；简单
  scalar channel 或 ordered piece evaluator 不因“更专业”而升级 APEX。
- 静态视觉不能证明隐藏 piece 数、capture weights、joint hierarchy、constraint 或状态置换。

详细 channel、packed-piece、KineFX/APEX 模式和 H21/H22 验证基线按需读取
[references/rig-animation-patterns.md](references/rig-animation-patterns.md)。复杂源 SOP 同时加载
`houdini-sop-workflow`；最终 Karma 交付再加载 `houdini-solaris-karma-workflow`。

## 完成门

- 控制器和 keyframes 回读正确，frame 单位/curve/replace 语义明确，用户 frame 已恢复。
- stable identity、rest/current transform 和属性 class 可自省；所有 warning/error 已解释。
- rigid pieces 保持刚体，活动集合用 P + orient/transform 验证。
- driver、binding 与 driven deliverable 分层取证；最终输出不依赖非交付 helper 才能显得正确，
  且逐 piece/skin 的实际世界状态满足目标，而不只是 skeleton、anchor 或总 bbox 在变化。
- skin 有有效 boneCapture、capture/animated pose，变形与 normals 随目标帧变化。
- APEX 有明确 graph inputs/bindings、可读取 outputs 和 cook error；引擎 smoke 不能冒充
  animator-facing controls、constraints、FK/IK 或 Animate State 已完成。
- 多步骤任务覆盖 first、非交换 transition、mid/end、recovery；正确 inverse 由逐状态证据证明。
- 固定构图 render/vision 只承担可见结果；隐含 rig 数据由数值/拓扑证据证明。
