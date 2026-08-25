# Rig / Animation 能力：第一性原理设计

状态（2026-08-23）：Phase A/B/C 的实现与历史 H21/H22 smoke 已完成；蜘蛛任务提供了新的刚性分件 rig trace。旧大范围回归脚本当前已移除，Phase D 除继续收集真实任务外，还需按现契约重建最小回归覆盖。

初始日期：2026-08-21
直接证据：`session-a41c853a-b833-48e8-acf7-7ff332a982f8`（魔方绑定动画）、`session-9b7bd919-47dd-4edc-aa1c-422bdbee0251`（蜘蛛刚性分件 rig）

## 1. 问题边界

本设计不回答“魔方应该用哪个节点做”，而回答更稳定的问题：agent 收到“绑定、动画、
机械运动、角色 rig、蒙皮、IK、程序化序列”等需求时，如何选择与任务语义匹配的 Houdini
数据模型，如何用最小能力集可靠执行，并如何证明整个运动契约成立。

“绑定”不是一个数据模型。它可能指：

1. 参数随时间变化；
2. 多个独立刚体 piece 的有序变换；
3. 父子层级/FK 机械结构；
4. skeleton + capture weights 的蒙皮变形；
5. animator-facing controls、约束、IK/FK、可复用 rig logic；
6. RBD、ragdoll、secondary motion 等物理求解。

如果不先分类，任何“最佳实践”都会被错误地泛化到不适用任务。

## 2. 已确认、无法绕开的基本事实

### 2.1 数学与数据事实

- 三维旋转通常不可交换；路径依赖任务必须保存**有序状态迁移**，不能把一串操作压成
  若干独立累计标量。
- piece 必须有跨帧稳定身份；没有 `name/piece_id`，就无法证明“同一块”去了哪里、朝向
  如何变化、下一步属于哪一层。
- “参数有 key”“点移动了”“首尾相同”“图像不同”是四种不同事实，都不能单独证明
  用户要求的运动语义成立。
- 最终所有控制量回到零，只证明系统回到了 rest 输入；它不证明中间曾正确执行逆运算。
- 视觉只能验证可见形态和明显运动，不能从单个外部视角证明隐藏 piece 数、权重、层级、
  约束或状态置换。

### 2.2 Houdini 官方系统的事实边界

- Houdini channel 是“参数值随时间变化”的表示，Animation Editor 用于查看和编辑这些
  channels；HOM `hou.Keyframe.setFrame()` 使用帧，`setTime()` 使用秒。
- Packed Geometry/Fragments 为 piece 提供单一 primitive transform；Copy to Points 和
  Transform Pieces 使用模板点变换属性驱动 repeated/packed pieces。
- KineFX 是 SOP 层的 procedural rigging/animation 框架；joint 的 pose 由 `P` 与
  `transform` 等几何属性表达。
- Joint Deform 面向有 `boneCapture` 的 skin，输入 capture pose 与 animated pose；它不是
  所有刚体 piece 任务的默认答案。
- APEX 是图求值框架，在 KineFX 中承载更复杂、可组合、延迟求值的 character rig logic。
  它适合 controls/FK/IK/constraint/可复用组件，不因为任务里出现“绑定”二字就自动适用。
- 本机 H21.0.440 安装中存在 KineFX/APEX/Transform Pieces 的官方帮助与示例；当前在线
  文档以 H22 为主，因此具体 type/version/tool 必须由运行时 Tab/本机帮助确认。

官方基线：

- https://www.sidefx.com/docs/houdini/anim/
- https://www.sidefx.com/docs/houdini/hom/hou/Keyframe.html
- https://www.sidefx.com/docs/houdini/nodes/sop/xformpieces.html
- https://www.sidefx.com/docs/houdini/nodes/sop/pack.html
- https://www.sidefx.com/docs/houdini/character/kinefx/index.html
- https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--rigpose.html
- https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--jointdeform.html
- https://www.sidefx.com/docs/houdini/character/kinefx/apexgraphbasics.html

### 2.3 dsh-houdini 的产品事实

- system prompt 容量有限；长 recipe 常驻会稀释所有任务的决策质量。
- skill 可版本化、按需加载，适合领域路由、官方模式和完成门。
- 动词适合跨任务稳定意图、校验、事务、状态恢复和紧凑返回，不适合收录每个 node/API。
- 裸 `hou` 必须保留为低频逃生舱，否则词表未覆盖的新领域会被硬性卡死。
- 当前 47 个目录动词已覆盖发现、建图、参数/关键帧、几何、资产、USD、渲染与视口；新增能力
  必须优先扩展现有语义，不能按单 trace 增长一组专用名字。
- `hou` 只能在 Houdini 主线程执行；GUI 用户的 selection/display/frame 可能随时变化，
  agent 的验证必须保持隔离和状态恢复。

## 3. 习惯性接受、但尚未验证的假设

以下都不得作为开发前提：

- “绑定任务都应该使用 KineFX/APEX。”
- “魔方使用骨骼才算专业。”独立刚体 piece + 有序状态 evaluator 可能更直接、更透明。
- “SideFX 官方存在一个覆盖所有 rig/animation 的最佳 recipe。”官方系统按数据模型分工，
  不提供脱离任务语义的唯一答案。
- “增加关键帧动词就能解决动画正确性。”它只能消除 HOM 单位/API 错误，不能设计状态机。
- “把更多官方知识注入 system prompt，agent 就会稳定。”知识、执行能力和完成门是三层问题。
- “工具越少越好。”缺失高频原子能力会迫使 agent 重复手写危险代码；真正目标是最小完备，
  不是最小数量。
- “工具越多能力越强。”过细 API 会增加选择错误、prompt 成本、维护矩阵与版本漂移。
- “第一次 A/B 通过可代表整段 animation。”序列任务必须覆盖非交换转折和中间状态。
- “当前 trace 中 `cook_node(force=True)` 有缓存 bug。”该 trace 没有完成独立复现。
- “当前 online H22 文档的节点名可直接写死到 H21。”必须以实际 parent Tab 和安装版本确认。

## 4. 真正要实现的目标

目标不是“让 agent 会做魔方”，而是建立以下闭环：

```text
用户运动意图
→ 数据模型分类
→ 运行时发现当前版本的原生系统
→ 最小可验证网络
→ 模块/状态/时序完成门
→ 清理、保存、诚实交付
→ trace 反哺 skill 与能力层
```

具体成功标准：

1. 泛化：覆盖通道、刚体 pieces、层级、skin、character rig、simulation，而非单项目模板。
2. 稳定：写操作有参数校验、批量原子性、回读、rollback、frame/selection 状态恢复。
3. Houdini-native：优先采用当前版本真实 Tab 可用的 channel、packed pieces、KineFX/APEX
   模块；不靠过时经验猜类型。
4. 可证：每类任务有适合自身的数据契约和完成门，不能用统一 pixel diff 冒充正确性。
5. 高效：避免重复全文 VEX/HOM、逐 key 往返、无稳定 ID 的点级排错。
6. 精简：第一批不增加任何领域专用 setup 动词；新增动词必须跨任务、可校验、能显著减少
   失败面，并经过 trace/原型证据。

## 5. 现实资源与约束

- 运行基线是 H21.0.440 / Python 3.11，同时需保留 H22 / Python 3.13 兼容。
- H21 与 H22 的 APEX/KineFX recipe、node version、交互 state 可能不同。
- headless 适合数据和 cook 回归；Animate state、APEX builder 等交互行为可能需要 GUI 测试。
- 当前没有完整的版本感知 `node_help`；`describe` 只返回帮助 URL/少量元数据，在线文档可能
  与安装版本不同。本机 `$HFS/houdini/help` 是重要的同版本事实源。
- 视觉模型可能缺席或能力有限；客观数据门不能依赖 vision。
- 用户会在 agent 运行中改变 viewport、selection、display 和 frame；不得把用户界面当内部状态。
- 单次魔方 trace 对“新增哪些动词”只有 S1 强度；可以直接修复确定性工具 bug和错误完成门，
  但不能据此建立完整 KineFX/APEX API 层。

## 6. 从基本事实推导出的架构

### 6.1 领域路由层：skill，而非 system prompt 手册

新增 `houdini-rig-animation-workflow`，只做任务分类、官方模式、模块契约和完成门：

| 意图类别 | 默认 Houdini 表示 | 关键完成证据 |
|---|---|---|
| 普通参数/镜头/灯光动画 | channels + keyframes | key 回读、曲线范围、目标帧求值 |
| 独立刚体 pieces / 装配 / 魔方 | stable `name/piece_id` + packed pieces + template transforms / Transform Pieces | 每 piece transform、活动集合、非交换步骤、刚体不变量 |
| 父子层级/FK 机械结构 | object hierarchy 或 KineFX joint transforms，按规模/交付选 | parent/local/world transform、limits、层级传播 |
| skeleton + skin deformation | KineFX capture + animated skeleton + Joint Deform | `boneCapture`、rest/animated pose、变形/法线/体积 |
| animator-facing character rig | KineFX + APEX components/graph | controls、FK/IK/constraints、graph evaluation、animate state |
| 物理运动 | RBD/DOP/KineFX secondary/ragdoll | solver 状态、碰撞、缓存、确定性/随机种子 |

常驻 guidance 只保留一句 dispatch 和两个不变量：

- 绑定/动画任务先加载该 skill 并分类，未分类不得建复杂网络。
- 路径依赖序列必须验证稳定身份、状态迁移与至少一个非交换转折。

### 6.2 最小执行层：先修/扩展，后新增

第一批能力预算：**最多新增一个目录动词**。

1. 新增候选 `set_keyframes(node, channels, replace=True)`：多 channel 批量写入，输入统一用
   frame；支持有限、明确的曲线模式；提交后回读 frame/value；恢复用户 frame；失败事务回滚。
   不把它并入 `set_parm`，因为普通赋值与动画替换的副作用/权限不同。
2. 扩展 `read_parms`：默认只增加紧凑 `animated/key_count/first_frame/last_frame` 摘要；完整
   key dump 先不做新动词，原型证明必要后再决定。
3. 扩展 `create_spare_parms`：保留代码扫描模式，同时允许显式、JSON-safe 的 controller
   `spec`（folder/label/type/default/min/max）；同一“创建 spare 参数”意图，不新增平行名字。
4. 修复 `search_tab_menu` 的 label/token 归一化，使 `copy to points` 可发现
   `copytopoints::2.0`；parent/tool recipe 继续由现有 `search_tab_entries/tab_apply` 承担。
5. 修复 repo-write advisory 对 relay 图片只读 `render_check` 的假阳性。
6. 修复 evidence batch 机会：只统计**同一 resolved node**三项以上 `set_parm`，不能跨节点求和。
7. 暂不新增 `rubik_*`、`piece_*`、`kinefx_*`、`apex_*` 动词。piece 状态诊断先用稳定
   attributes、现有 `geo_frame_diff/geo_attrib_stats` 与裸读原型；出现重复、通用、易错证据后，
   再决定扩展 `geo_frame_diff` 还是新增独立 piece-state 自省。

### 6.3 版本感知知识层

知识进入系统的顺序必须是：

```text
SideFX 官方文档
→ 本机对应版本 Tab/帮助/源码确认
→ 最小可复现实验
→ skill reference（带适用边界）
→ system prompt 只加 dispatch
→ 只有执行反复失败才新增/扩展动词
```

不把网页段落原样注入 prompt。官方信息必须记录：用途、输入/输出数据、版本、反例、验证方法。
现有 `node_help` Stage 2 路线继续保留，但不作为本轮先新增多个 rig 动词的理由。

### 6.4 完成门层

所有动画先满足公共门：

- time dependency 或 channel keys 可回读；
- 至少两个目标帧客观数据不同，或明确解释静态段；
- 用户 frame/selection/display 得到恢复；
- 最终 warning/error 已清理或解释；
- 视觉只做可见结果判断。

路径依赖/多步骤任务另加序列门：

1. 第一步的活动集合和轴/空间正确；
2. 至少一个非交换的第二步使用**更新后的状态**选择对象；
3. sequence midpoint/end 状态有证据；
4. inverse/recovery 不能只用“全部控制量归零”证明；
5. 若承诺 N 个 segment，验证帧必须覆盖 first、non-commutative transition、mid/end、recovery。

## 7. 原方案中只在修补表面的部分

- 继续修正 `setTime`、大小写、相对路径、vertex `@P`、matrix 符号，只能让当前六通道模型
  更稳定地执行，不能让它变成有序魔方状态机。
- 新增一个“魔方动画”专用 verb/VEX 模板，会把 task-specific 方案固化进产品词表。
- 把 KineFX/APEX 节点列表塞进 system prompt，只会增加选择噪音，仍不会教 agent 何时不该用。
- 只新增 keyframe 写入工具，可消除 HOM 失败，却不能修复状态表示和验证覆盖。
- 继续增加 frame 25/31 render 或调视觉 prompt，只会更确定第一步成功，不能证明第 2–16 步。
- 单纯禁止裸 `hou` 会把控制面板、关键帧、未来 APEX 等真实缺口变成任务阻塞。
- 因一次 trace 把所有 animation/KineFX/APEX API 动词化，会迅速造成目录臃肿和版本维护债务。

## 8. 分阶段开发计划

### Phase A — 证据与规则（不新增动词）

1. 更新 trace 审计：序列覆盖、稳定身份、非交换转折、rest-return 与 inverse-return 区分。
2. 修 evidence 同节点 batch 分组；为 render/geometry 验证列出覆盖帧。
3. 建立本文件与官方参考清单；新建 rig/animation skill 骨架和路由表。
4. 为魔方 trace 建立最小反例：当前绝对六通道 vs 正确 R→U 状态 evaluator。

验收：审计必须把当前 HIP 判为“第一步通过、完整序列未通过”，且不依赖视觉。

**2026-08-21 Batch A 结果**：

- ✅ evidence batch 按同一 resolved node + 唯一 parm 分组；魔方 #7/#8/#9 跨节点误报清零。
- ✅ evidence/HTML 增加 geometry/render/framing/comparison/vision 覆盖帧；魔方实际为 geometry
  `[1,25,31,121,220]`，render/vision `[25,31]`。
- ✅ `search_tab_menu('sop', 'copy to points')` 按 label/token 归一化命中
  `copytopoints`；relay `render_check` 不再触发 repo-write advisory，真实写入仍报警。
- ✅ governance GOV-001 dry-run 边界通过（执行者自评；独立新 session activation 仍待测）。
- ✅ H21.0.440 disposable R→U 正反例 6/6：正确模型更新 logical membership 后选 U，
  与初始 membership 绝对通道在第二步分叉；两者最终都回 rest，证明 endpoint equality
  不足。Copy to Points packed output 需显式复制 point `name` 后再由 Transform Pieces 匹配；
  轴心 piece 的 P 不动但 orient 改变，活动/完成门必须检查 P + orient/transform。
- 决策：HTA-017 升为 S2 确认；当前已有 `geo_frame_diff(P/orient)` 足够支撑基准，暂不新增
  piece-state verb。`set_keyframes` 和正式 rig/animation skill 仍留在 Phase B，未抢跑。

### Phase B — 最小通用执行能力

1. 原型并拍板 `set_keyframes` 的 JSON 契约；H21/H22 用 frame 单位回读。
2. `read_parms` 增加紧凑动画摘要。
3. `create_spare_parms` 增加显式 controller spec；现有代码扫描调用保持兼容。
4. 修搜索 label 与 repo media advisory。
5. 更新 `docs/tool-design.md`、catalog/build、headless/live regression；只有此时动词进入真相源。

验收：参数动画任务不再裸用 `hou.Keyframe`，不再出现秒/帧混淆；多 channel 写入一次事务完成。

**2026-08-21 Batch B 结果**：

- ✅ 新增唯一通用动词 `set_keyframes`：frame 单位、constant/linear/bezier、全量预检、
  replace/append、失败恢复旧 keys、有限回读/采样和 frame 恢复。
- ✅ `read_parms` 增加 `animated/time_dependent/key_count/first_frame/last_frame/curves` 摘要；
  不默认倾倒全部 channel keys。
- ✅ `create_spare_parms(spec=...)` 支持普通 controller 的 folder/toggle/int/float/string，
  同名拒绝；扫描 VEX channel reference 的旧模式保持兼容。
- ✅ H21 channel + KineFX foundation 7/7；正式注册 `houdini-rig-animation-workflow`，细节
  渐进到 reference，不增加 KineFX/APEX 专用动词。
- ✅ 原 `魔方.hip` 未改；新建 `魔方_ordered_rig.hip`：27 named packed pieces、ordered
  16 moves、R 后 U membership 更新、frame 121 scramble 非零、frame 217 逐 piece P/orient
  回 rest（约 1e-32 浮点误差）、`OUT_ORDERED` 保存并在新 hython 进程重开验证。
- 发现并固化：展开 polygon geometry 的 Pack By Name 需要 primitive name；Copy to Points
  packed instance 场景则可显式把 rest point name 复制到 packed point。attribute class 取决于
  source representation，不能写成单一规则。
- ✅ H22.0.368 / Python 3.13：channel/KineFX 7/7、rigid R→U 6/6、scene/geometry 11/11。
- 该批当时未完成 APEX evaluation/session/GUI；三项已在后续批次完成，当前只待更多真实任务。

### Phase C — 三类官方工作流基准

1. Channel 基准：一个普通参数的 hold/linear/ease 动画与 Animation Editor/HOM 回读一致。
2. Rigid piece 基准：27 个 named packed pieces 执行 R→U 两个非交换步骤；第二步活动集合
   必须来自 R 后状态；再执行正确 inverse，逐 piece transform 回到 rest。
3. KineFX 基准：最小 3-joint skeleton → Rig Pose → Joint Deform，验证 `name/P/transform`、
   `boneCapture`、animated pose、deformed normals；证明 skill 路由和现有 Tab/parm/geo 动词足够。
4. APEX 只做发现与小型 graph evaluation smoke test，不先封装 builder；等 animator-facing rig
   真实任务后再扩展。

验收：三类任务使用不同数据契约，不能互相用“图动了”替代。

当前状态：channel、rigid piece、KineFX/Joint Deform 与 APEX 非交互 evaluation 的 H21/H22
基准均完成，仍不封装脆弱 builder recipe；正确新 session 与 GUI 视觉也已通过，Phase D
只剩更多真实 channel/mechanical/KineFX/APEX 用户任务与 trace 准入判断。

**首个真实 Houdini agent trace**：`session-8fe0e669...` 在正确 Houdini preset 下成功加载
rig skill，只读调用 `verb_help('set_keyframes') + scene_info()`，0 mutation/failed/advisory，
最终准确说明 channel 不替代 ordered state/KineFX。Skill activation 和 verb discoverability
通过。第二次 Restart 后 `session-872f6d34...` request header 达到 46/46 verbs、system reminder
达到 5/5 Houdini skills；agent 同样只读，并成功发现三个 bookmark verbs。部署态曝光完成；
实际写 key 与 GUI 魔方 A/B 仍需后续用户任务验证。

### Phase D — 新 trace 与词表准入

1. 用新 session（确保最新 capability snapshot）分别跑 channel、mechanical/piece、KineFX 任务。
2. 统计 raw exemptions、失败步骤、首次正确状态时间、验证覆盖和用户返工。
3. 只有同一意图在至少两个独立任务反复需要易错裸代码，才进入 P1 动词设计。
4. 删除/合并仍要求三个以上多样 trace、等价安全替代和反例分析。

可能但尚未批准的后续能力：`node_help`、piece transform/state summary、KineFX/APEX setup
adapter。它们都必须先通过 Phase C/D 证据门。

## 9. 这条路径成立的前提

- SideFX 官方系统的角色边界在 H21/H22 中保持概念稳定，具体类型允许版本解析。
- agent 能按短 dispatch 可靠加载 skill；若采用率不足，应先修 skill activation/会话版本提示，
  不是把整份 skill 复制进 system prompt。
- stable `name/piece_id` 与 transform 是刚体序列任务可接受的公共契约。
- `set_keyframes` 可以被设计成窄、可事务、可回读的通用原语，而不是迷你 Animation Editor。
- raw `hou` 继续存在并被 trace 记录，使未知领域可前进且能产生下一轮词表证据。
- 测试必须覆盖 H21 主基线、H22 兼容、headless 数据语义与必要 GUI 行为。

## 10. 验证它的第一步

先不增加工具，直接在 H21 disposable HIP 做一个最小 **R→U 非交换刚体实验**：

1. 27 个带稳定 `piece_id/logical_coord` 的 packed pieces；
2. 用模板点 `P/orient` + Transform Pieces 表达 pose；
3. evaluator 按顺序应用 R，再更新 logical coordinates，再选择当前 U 层；
4. 同时保留当前“六个初始面绝对通道”作为反例；
5. 在 rest、R 完成、U 中间、U 完成、inverse 完成五个状态比较每 piece transform；
6. 验证第二步活动集合与初始 `gy=1` 集合不同，且 inverse 后逐 piece transform 精确恢复；
7. 测试网络、截图和缓存都放 `$HIP`，不保存进用户正式场景。

该实验现已清楚区分两个模型并进入自动回归；它是 rig/animation skill、关键帧工具和
未来 trace 的首个防作弊基线。ordered 魔方副本、channel/KineFX 基准和固定构图 GUI A/B
也已完成；APEX 最小非交互 evaluation 随后也在 H21/H22 通过。下一步是更多真实用户任务，
不能把 packed-piece 或 graph-engine smoke 外推为所有绑定系统均已覆盖。
