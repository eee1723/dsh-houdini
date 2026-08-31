# 已知 trace 模式库

此文件只存跨任务可复用、带 session 证据的规律。`候选` 表示仍需更多 trace；`确认` 表示已有重复证据或可复现实验；`已修` 必须写明回归。

## HTA-001：长 exec 中途失败留下半成品

- 状态：已修（GUI exec undo group + 异常自动 performUndo；文件/HDA 外部副作用明确不在范围）
- 证据：`f608bfab` 的参数组增量重建；`40054277` 步骤 #6 在 Scatter 参数失败前已创建地形和部分节点。
- 症状：后续代码默认某些节点已存在，拓扑和参数来自多次补丁，恢复路径不清楚。
- 根因：桥 exec 无 undo transaction；任务脚本没有小批次 checkpoint。
- 修复：bridge 每次 GUI exec 进入唯一 undo group；异常只在栈顶 label 匹配时自动 undo，并在 envelope 回报 `rollback`。skill 仍强制小 batch checkpoint。
- 边界：纯只读 query 或幂等小赋值不需要事务。

## HTA-002：整体统计掩盖局部几何退化

- 状态：已修（`geo_piece_stats` + 模块验证阶梯）
- 证据：`40054277` 步骤 #16 的 `instance_xform` 全局 bbox/点数正常；用户 seq 19405 指出每株草宽度为 0；步骤 #61 才把 local 坐标捕获移到 PolyWire 后。
- 症状：点数、全场 bbox、cook 都通过，但每个 piece 的宽度/面积/体积退化。
- 根因：未验证单元级 local extent 和变换前后拓扑不变量。
- 修复：内存 Connectivity SOP Verb 生成 piece，报告局部 extent/面积/degenerate；H21 在真实 9000 株、306k prim 草地上识别 9000 pieces、0 退化。
- 边界：无重复单元的单体几何仍需适合自身的局部不变量，不强制 piece 分组。

## HTA-003：几何未证实时进入渲染兔子洞

- 状态：已修（SOP workflow skill + 完成门）
- 证据：`40054277` 在 14:30 宣称草已正常，14:31–14:50 连续调 display、灯光、相机、gamma；用户随后指出建模根因。
- 症状：大量 render/vision 调用围绕黑图、暗图、构图，真正 SOP 错误未被隔离。
- 根因：错误地把 aggregate cook 成功当作模块验收；视觉 prompt 带目标暗示。
- 修复：`houdini-sop-workflow` 固化源几何→单元→成形→模板点→复制→变形→合并→多帧→渲染阶梯；trace skill 同步完成门。
- 边界：明确的渲染器/灯光任务可以直接进入渲染诊断。

## HTA-004：agent-owned render 管线污染 OBJ 可见性

- 状态：已修（render_view v2 proxy isolation + display context split）
- 证据：`40054277` 步骤 #19/#21 只出绿色准星；步骤 #28 raw `setDisplayFlag(True)` 后恢复内容。`display_node('/obj')` 在步骤 #25 自身失败。
- 症状：创建 `/obj/dsh_cam`/target 后用户对象被隐藏；验证工具改变了被验证状态。
- 根因：`render_view`/`tab_create` 未保存和恢复 OBJ display 状态；`display_node` 把 SOP 单一 display child 语义套到 OBJ。
- 修复：显式 SOP 经隐藏 Object Merge proxy，ROP forceobjects 只渲染 proxy；保存/恢复 OBJ visibility、selection、frame。SOP output 与 OBJ visibility 新动词拆分，旧名兼容路由。
- 边界：SOP 子网的 display flag 仍是单节点语义，不能因 OBJ 行为删除该能力。

## HTA-005：手写 agent 相机矩阵导致恢复失败和序列化噪音

- 状态：已修（agent-owned framing + 固定多帧 framing + 通用 lossless-float 归一化）
- 证据：`40054277` 步骤 #48–#59；其中 #49–#52/#54 因 lossless JSON（负零/特殊浮点）连续失败。
- 症状：重复计算 Matrix4、extractRotates、tx/rx，输出不变，消耗十余调用。
- 根因：`render_view` 只有 full-bbox framing，缺少 agent-owned close/detail 构图控制；工具未返回足够的 camera diagnostics。
- 修复：`render_view(framing='full|detail', coverage=...)`，agent camera/target/ROP 全部 owned；H21 隔离回归两次像素完全一致。
- 边界：正式镜头制作仍允许直接编辑独立 camera + `render_frame`。

## HTA-006：旧/错误节点选择放大手写 VEX 复杂度

- 状态：已修（节点选择/变形顺序进入 `houdini-sop-workflow`）
- 证据：`40054277` 使用 classic Copy SOP，未先 `search_tab_menu('sop','copy')`，随后手写 attribute transfer 和 instance transform；正向对照 `be6367cd` 直接用 `copytopoints` + 带宽度的 Grid blade，11 次工具完成静态草地；早期自行车 trace 也已证明 Copy to Points 初始化语义重要。
- 症状：手写 orient/yaw/tilt/rest 传递，产生截面塌缩和多轮 VEX 编译修复。
- 根因：节点意图选择没有把 Houdini 原生 Copy to Points/Sweep 数据模型作为首选。
- 修复：`houdini-sop-workflow` 增加模块选择 checkpoint、Copy to Points 与 deform-before-skin 基线；guidance 要求先查 Tab Menu。
- 边界：需要自定义非刚性逐点变形时，Copy to Points 不能替代后续 deformation，但仍可承担实例变换。

## HTA-007：warning 被“无 error”覆盖

- 状态：已修（cook_node 返回 healthy/warning_free + guidance 完成门）
- 证据：`40054277` Merge 的 N/uv attribute mismatch 从步骤 #17 持续到 #75，但 todo 在步骤 #18 将 cook 验证标 completed。
- 症状：agent 宣称健康，warning 持续存在并可能影响 shading/UV。
- 根因：完成门只检查 error 或点数，没有为 warning 建立解释/白名单。
- 修复：`cook_node(force=...)` 返回 `ok/warning_free/healthy`；guidance/skills 明确 warning 未解释不得交付。
- 边界：已知且不影响目标的 warning 可保留，但必须记录理由。

## HTA-008：动画任务缺少时序完成门

- 状态：规则已修、待新 trace 验证（客观反例阻断；静帧难裁定审美时诚实交给用户播放判断）
- 证据：`40054277` 最后工具调用 #77 的 frame 1/12 `mean_abs_diff=0`、`max_abs_diff=1`，仍有两个未完成 todo，且无最终 assistant 交付。`71d76525` 工具调用 #40 的 geometry diff 非零、#46 的 render diff 为 21.1%，但 #47 的视觉 A/B 明确判断“没有明显变化、不像行进波浪”；agent 仍在 #50 把动画验证标 completed，并在最终文本宣称“全部验证通过”。`a41c853a` #59–#64 只验证魔方第一个 R move 的 frame 25/31，却在最终文本外推为 16 步打乱/还原；frame 1/220 相同只是六个绝对通道都回零。
- 症状：旧版本完全没有时序证据；后续版本有数值差异，却把“点动了/像素不同/第一段通过/首尾相同”误当成整个用户运动契约成立，甚至覆盖视觉否定或缺失的中间状态。
- 根因：完成门只检查非零阈值或单个 A/B，没有规定证据冲突的裁决顺序、承诺序列的验证覆盖，也没有要求波峰传播、锚点/活动区、稳定 piece 身份、更新后 membership 等领域语义不变量。
- 修复：geometryAtFrame 无 playbar 副作用比较；render_check 增加 RMSE、changed/meaningful pixel % 与高精度 mean。审计/workflow 现区分：完全静止、方向相反、主体缺失等客观反例必须阻断；节点/数据/时间语义通过而静帧不足以裁定细微动态或审美时，允许标记“视觉待用户播放判断”，但不得伪称视觉确认。多 segment/路径依赖任务另需 first、非交换转折、mid/end、recovery 覆盖。
- 边界：静态建模任务不要求多帧。

## HTA-009：重复单参调用未采用 batch primitive

- 状态：已修（`set_parms` 已发布，workflow 规定三项以上优先 batch）
- 证据：`f608bfab` 有大量 `parm().set` 循环；`40054277` 有 9 个步骤一次调用 `set_parm` 3–18 次。该草地会话唯一 capability snapshot 只曝光旧 20 动词，尚无 `set_parms`，因此这是“当时缺失、现已补齐”的正向证据，不记为 agent 漏用。
- 症状：code/ledger 膨胀，单项失败使整段 exec 中断或难读。
- 根因：guidance 没有明确“同节点三项以上优先 set_parms”的采用阈值。
- 修复：guidance/workflow 规定同节点三项以上独立赋值优先 `set_parms`；保留 `set_parm` primitive。
- 边界：赋值间有条件依赖、需逐项读取结果时仍用 `set_parm`。

## HTA-010：scene/timeline 只读信息缺少意图层入口

- 状态：已修（`scene_info`）
- 证据：`40054277` 步骤 #2–#5 为读取 HIP/版本/播放范围连续三次 API 失败后才成功；`f608bfab` 的时间线/bookmark 需求曾连续 6 次 query 探索 API，并大量裸用 playbar/setFps。
- 症状：任务开场或时间线需求反复猜 `hou.playbar`、timelineStart 等 HOM 名称。
- 根因：词表只有 node/parm/geometry 等域，scene/timeline 域仍为空。
- 修复：`scene_info` 只读；`set_timeline` 管明确字段；bookmark 按 list/create/delete 拆分并支持同名安全替换/精确删除。headless round-trip 恢复原时间线、无临时 bookmark 残留。
- 边界：一次性的特殊全局状态仍可走只读 hou；scene_info 不应返回巨大场景清单。

## HTA-011：代码引用 ch() 但 spare parameter 不存在，动画静默为零

- 状态：已修（`create_spare_parms`）
- 证据：`40054277` wind snippet 引用 amp/speed/wavenum/dirx/dirz，但节点没有这些参数；`geo_frame_diff(1,12)` 为 100% unchanged。
- 症状：VEX 编译/cook 无 error，参数赋值代码因 `parm(name) is None` 被跳过，所有驱动值为 0。
- 根因：误以为写 `ch("name")` 会自动创建参数；SideFX UI 需要显式 Create Parameters。
- 修复：扫描 `ch/chf/chi/chv/chs` 创建缺失 float/int/vector/string spare 参数并应用显式 defaults；H21 临时 Wrangle frame 1/12 mean delta 0.483。
- 边界：`chramp` 等复杂引用不自动猜结构，列入 unsupported 后显式建 interface。

## HTA-012：动词 ledger 的负零破坏 lossless JSON

- 状态：已修（统一 JSON-safe 归一化 + headless/live bridge 回归）
- 证据：`71d76525` 工具调用 #18/#19 连续返回 `tool "houdini_exec" returned invalid output: value is not lossless JSON`；两步都包含 quaternion/vector 统计，容易生成 `-0.0`。桥的 `_jsonable` 只替换非有限 float，仍原样保留 `-0.0`；动词 ledger 又独立收集未经归一化的统计结果，因此 agent 即使自行清洗 `__result__` 也无法规避。
- 症状：Houdini 代码已经执行，工具层却丢弃整个结果；第二次在 `__result__` 上做 JSON 清洗仍失败，造成重复探测和不确定场景副作用。
- 根因：dsh 工具要求 lossless JSON，`-0` 属于拒绝值；bridge 只处理 NaN/Infinity，没有在 `__result__`、verb args/result、job envelope 的共同递归边界把负零规范化为正零。
- 修复：唯一 JSON-safe coercion 对 `value == 0.0` 返回正零，hou Vector/Color/Matrix 逐分量复用；verb ledger、result、job 共用。H21 headless 回归覆盖负零/NaN/Infinity，live bridge 同时返回 `verb_help` ledger 与 `zero: 0.0`，不再被 lossless JSON 拒绝。
- 边界：字符串中的 `"-0.0"` 是普通文本，不应改写；真实有限负数必须保持。

## HTA-013：逐帧自动取景污染动画 render diff

- 状态：已修（`render_view(framing_frame=)` + GUI 固定构图回归）
- 证据：`71d76525` 工具调用 #43 frame 25 的 framing center/size/dist 为 `[0.0213,0.7147,0.0563] / 22.9003 / 50.5667`，#46 frame 55 变为 `[0.0849,0.7170,0.0217] / 22.9754 / 50.7324`；随后 `render_check` 报 21.1% changed pixels。`render_view` 实现按目标帧 bbox 每次重算 camera，因此该差值同时包含相机平移/缩放。
- 症状：pixel diff 看似明显，但语义视觉认为两帧几乎相同；agent 把被相机变化污染的指标当作动画成立证据。
- 根因：单帧自动构图适合静态验证，不满足动画 A/B 的固定观察条件；工具未显式标记“相机构图与 ref 不一致”。
- 修复：扩展现有视觉意图 `render_view(..., framing_frame=)`；A/B 传同一参考帧后 camera frame/center/size/dist/eye/direction/source signature 完全一致。H21 GUI 用 `$F*0.1` 动画 source 在 frame 1/2 回归，source fingerprint 确实变化而 framing 完全相同；暂不新增组合动词。
- 边界：静态单帧自动 framing 正确；正式镜头的相机本身有动画时，camera motion 是目标的一部分，不能强制锁定。

## HTA-014：靠失败或读仓库源码发现动词契约

- 状态：已修（`verb_help` + guidance/关键 docstring）
- 证据：`71d76525` 工具调用 #3 把 `search_tab_menu` dict 当 list、#7 把 `read_parms` list 当 dict、#12 猜错 `geo_attrib_stats` keyword、#31 假设 `describe` 含 `ok`；中途 #13–#16 用 grep/read 打开插件源码才纠正。`a41c853a` 已曝光 `verb_help`，但 #8 仍把 `read_parms` list 当 dict，导致完整 exec rollback。正常 Houdini 会话工作区是 `$HIP`，仓库源码不应成为运行期契约入口。
- 症状：一次本可只读发现的签名/结果字段，变成 exec 失败、undo、重复 batch；有时失败发生在修改之后。
- 根因：system prompt 为控制体积只列意图，没有统一的运行期动词契约自省；Python `inspect.signature` 虽可手写，但 agent 不知道 registry 边界和结果含义。
- 修复：新增 `verb_help(name)` 返回准确 signature/docstring、未知名相似建议；guidance 要求不确定时先查。`read_parms` doc 明确返回 `list[dict]`，guidance 明确 `cook_node` 才拥有 `ok/healthy`、`graph` 要围绕数据节点调用。H21 headless/live bridge 回归通过。
- 边界：节点自身的 SideFX 参数/帮助仍由 `list_parms`/`describe` 和未来 `node_help` 负责；`verb_help` 不替代它们。

## HTA-015：节点类型注册表被误当成真实 Tab 菜单

- 状态：已修基础能力、待新 Karma 用户 trace 验证（parent-aware entry + allowlist recipe）
- 证据：`71d76525` #51 已查到 `karmarendersettings`，#53 的 LOP `principled` 为空，
  但 #56 通过全局 VOP registry 找到 Principled 后在 #59 强制创建；#87 又选择 hidden/
  deprecated 的一体式 `karma` LOP。H21.0.440 shipped shelf 对照：真实入口是
  `vop_karmamtlxsubnet`（Karma Material Builder）和 `lop_karma_setup`（创建 Render
  Settings + USD Render ROP）。
- 症状：图能渲染，但用户按 Tab 找不到材质节点；setup 缺配套 ROP/表达式，随后
  `LopNode.render()` 失败并改走按钮轮询。
- 根因：`search_tab_menu` 只枚举 nodeTypes；`tab_create` 用 `ctx_type` 猜 shelf id，失败后
  裸 `createNode`，绕过 hidden/deprecated 和 Material Library tab mask。
- 修复：`search_tab_entries(parent, query)` 区分可见 node/tool；`tab_create` 拒绝隐藏旧类型
  和 Material Library 根层 shader；`tab_apply` 运行时验证真实 tool/context，再通过
  SideFX initializer/稳定 setup 契约的非交互 adapter 创建 Karma Setup/Material Builder，
  返回全部节点并恢复用户状态；新增 Solaris/Karma workflow 与 USD 自省。H21 标准
  USD Render ROP 实际出图同时修复 `render_frame` 的 outputimage/foreground 契约。
- 边界：传统 Principled/Karma CPU 旧资产不是一律非法；用户明确选择并接受限制时可用，
  但不能作为新 XPU 工作的默认或伪称 Tab 原生路径。

## HTA-016：compaction replay 膨胀 trace 统计

- 状态：已修（callId 去重 + replay diagnostics）
- 证据：`71d76525` 原报告 116 个 tool result；seq 22231–22245 在 `compaction/prune`
  间重放 8 个旧 callId，唯一 `tool/call` 实际 108。动词原报 238，去重后 232。
- 症状：长会话看似突然多出同一批旧代码，调用/动词/失败/耗时被重复计入，阶段顺序也被
  replay 时间污染。
- 根因：extractor/report 遍历每个 `tool/result`，未区分执行结果与压缩历史重放。
- 修复：`trace-session-lib.uniqueToolResultEvents()` 以第一个 result 为执行证据，后续同
  callId 写入 `replayedResults`；evidence/HTML 共享该实现。当前 session 回归为
  108 calls / 232 verbs / 8 replays。
- 边界：无 callId 的未来 schema 仍保留给调用方判断；不能仅凭内容 hash 去重两个真实的
  相同调用。

## HTA-017：把路径依赖状态压成独立绝对控制通道

- 状态：确认（S2：用户 trace + H21 disposable 正反例回归；工具形态仍待更多任务）
- 首次/最近证据：`a41c853a` #26、#58、#59、#60–#64；历史上已移除的
  `houdini/tests/regress_rig_state_model.py` 曾在 H21.0.440 通过 6/6，当前最小等价回归待重建。
- 症状：单个面/关节/segment 能正确运动，参数也有 key；但 agent 用初始 membership 和若干
  独立累计角度表达有序、非交换操作，只验证第一段和最终 rest，就宣称完整序列成立。
- 根因：没有把 stable identity、logical state、ordered transition 当成 rig 输入/输出契约；
  完成门也没有覆盖第二个非交换步骤和 sequence midpoint。
- 建议：rig/animation 先按 channel、rigid pieces、hierarchy、skin、character graph、simulation
  分类；路径依赖任务要求稳定 `name/piece_id`、每步更新 membership/transform，并验证 first、
  非交换转折、mid/end、recovery。官方系统选择与工具预算见 `docs/rig-animation-design.md`。
- 反例/边界：单个独立通道、互不影响的并行动画、明确只要“一层转一下”的装饰动画可以用
  绝对参数；不能因此强制引入 KineFX/APEX。
- 回归：27 个 packed pieces 经显式 point `name` → Transform Pieces；正确模型在 R 后更新
  logical membership 再选 U，和初始 membership 绝对通道在第二步活动集合/最终 R→U 状态
  分叉；两者都能在 inverse 结束回 rest，证明 endpoint equality 不足。轴心 piece 的 P 不动
  但 orient 改变，完成门必须同时看 P + orient/transform。
- 下一验收：再收集一个层级机械任务和一个 KineFX/skin 任务，判断是否需要 piece-state
  自省动词；当前 `geo_frame_diff(P)` + `geo_frame_diff(orient)` 已覆盖基准，不先新增工具。

## HTA-018：在 bridge exec 内加载 HIP 破坏执行与重连生命周期

- 状态：确认/P0 本机可复现（不得简单封装 scene_open）
- 首次/最近证据：2026-08-21 ordered 魔方 GUI 验收。单 exec 的 load→render→restore 返回
  `ok=true` 空包且无产图；拆分后加载 ordered HIP 会让该次请求无 result 但场景已切换；恢复
  原 HIP 的 UTF-8 load 关闭 HTTP 连接并启动新的 Houdini 进程，bridge 8765 消失。
- 症状：调用方无法知道 load 是否执行、finally 无法可靠恢复、images/result 丢失；严重时
  共享 Houdini 重启，agent 后续无法检查当前 HIP。
- 根因：`hou.hipFile.load()` 重置当前场景/会话生命周期，与正在该 Houdini 进程内执行并等待
  HTTP 回包的 bridge transaction 互相冲突；它不是普通 undoable scene edit。
- 修复/守卫：guidance 禁止 bridge exec 内 `hipFile.load`。用户 HIP 打开/替换走 Houdini UI；
  离线分析用 disposable hython。未来若自动化，必须在 Host 侧实现 unsaved confirmation、请求
  结束前调度、bridge/process reconnect、目标 HIP 验证和失败恢复，不能新增薄 wrapper。
- 边界：`hou.hipFile.save()` 不重置场景生命周期，但仍是不可 undo 文件写；现由只保存当前已命名
  HIP 的 `scene_save` 覆盖并回报文件/dirty 证据。
- 回归：bridge 现以 AST 在执行前无条件拒绝直接 `hou.hipFile.load(...)` 与
  `hou.hipFile.clear(...)`；`allow_raw` 也不能绕过。H21 scene regression 证明错误返回且当前
  HIP 未切换；裸 `hipFile.save()` 由 Raw Gate 指向 `scene_save`，不能再用豁免旁路。
- 下一验收：设计 host-level open handshake 前不重试 live load；若未来支持 scene open，
  必须先替换本守卫并完成进程重连/unsaved/恢复集成测试。

## HTA-019：动词结果内部箭头破坏 ledger 参数/结果切分

- 状态：已修（结构扫描分隔 + evidence/report/client 同语义 + 真实 trace 回归）
- 首次证据：`83a553e7-d728-4044-b700-9a637e787d55` 的唯一 `houdini_query`；
  `verb_help('set_keyframes')` 返回 signature `(node, ...) -> dict`。
- 症状：verb 名和计数正确，但 evidence 把 result 内 signature 的 `->` 当成调用分隔，导致
  args 吞入半段 result、result 从返回类型中间开始；详细工具证据不可信。
- 根因：extractor、HTML report 和 client 各用 greedy regex 解析
  `verb(args) -> result (Nms)`，没有识别 JSON string/array/object 边界。
- 修复：共享 `parseVerbLedgerLine()` 从固定前后缀进入，扫描字符串 escape 与 `[]/{}` 深度，
  只接受调用参数顶层的 `) -> `；extractor/report 共用，client 使用同算法。回归同时覆盖
  result 中箭头和 args 字符串中的字面 `") -> "`。
- 边界：host 为控制模型结果体积会把 detail 截断到 400 字符；截断 JSON 保持字符串是正确的，
  不能伪装成完整对象，但 args/result 分界必须保持准确。
- 回归：重新提取该 session 后 `verb_help.args == '["set_keyframes"]'`，detail 从
  `{"name":"set_keyframes"...}` 开始；3 calls / 2 verbs / 0 failure/mutation/advisory 不变。

## HTA-020：提示已曝光但 raw gate fail-open，模型采用率归零

- 状态：已修并获新 session 正向证据（默认开启 + 已覆盖调用不可豁免）
- 首次/最近证据：自行车 trace 已记录 deepseek-v4-flash 连续忽略 advisory；
  `c6481bf1-3a83-4f53-9bf8-398b9c8fa151` #1–#3、#9–#24。
- 症状：最新会话的 system snapshot 已曝光 46 个 verb，rig/SOP skills 均成功加载，但 20 个
  Houdini 调用全部纯裸；#9–#24 连续 16 个 mutation call 收到 raw hint 后仍不切换，最终
  7 个工具硬失败、多个被吞 cook failure、0 个 todo 完成且无交付。
- 根因：模型路线 `deepseek-v4-flash-vision-exp` 触发了严重 instruction-following 退化，但系统
  把安全性寄托在模型自觉：bridge `_raw_gate` 默认关闭且重启复位；旧 `allow_raw` 又能整段
  旁路已覆盖调用，使实验 gate 即使开启也可被泛化理由降级回 advisory。
- 修复：bridge 默认开启 gate，重启恢复安全默认；`allow_raw` 只豁免没有直接 verb 的低层
  mutation，不能豁免 `createNode/parm().set/cook/destroy` 等明确覆盖调用；低层代码必须与
  scene-operation batch 拆分。receiver 不唯一的 `setPosition` 降为 heuristic，避免把
  GeoPoint 写位置误报成 `layout_nodes`。host schema/guidance 与真实边界同步。
- 反例/边界：纯读取继续允许裸 HOM；低层 `hou.Geometry`/UI/显式 HIP save 可用带理由的独立
  `allow_raw` batch；插件开发者仍可在 Houdini Python Shell 临时关闭 gate，但不跨桥重启持久化。
- 回归：`tools/tests/dsh-bridge-raw-gate.test.py` 覆盖默认开启、covered call 带豁免仍零副作用、
  read-only 放行、`dict.setdefault` 聚合放行、uncovered mutation 先拦后豁免，以及 GeoPoint
  `setPosition` 不再假映射。蜘蛛 trace `9b7bd919` #25/#94 的 covered mutation 均在执行前拦截，
  随后分别改用动词/移除 query mutation；成功 exec 的动词覆盖为 48/48，成功裸修改为 0。
- 边界：调用含动词率仍会被合法只读探针稀释，不能用它单独判断 Gate 是否回归；看成功裸修改。

## HTA-021：Host 目录与运行中 Bridge 不同代

- 状态：P0 已修代码并有确定性测试；待 runtime restart + 新 session 部署验收
- 首次证据：蜘蛛 trace `9b7bd919` capability snapshot 宣称 47 verbs；#12 19:19:27 的
  `verb_help('create_spare_parms')` 返回旧签名（缺 `allow_foreign`），现场
  `verb_help('node_provenance')` 返回未知动词。
- 症状：模型看到新目录但执行的是旧 Bridge；ownership 等安全能力可在需要时才突然失败，
  `used/47` 分母也不再描述真实可用能力。
- 根因：Host/plugin 与 Houdini 进程内 Python 模块有独立 reload 生命周期，过去没有代际握手。
- 修复：构建从 `tool-design.md` 生成 Host 名称/hash；Bridge 从实际 `_VERBS` 独立计算
  `/health.verbCatalog`；Host 在 `/exec`/`/jobs` 前比较并 fail-closed，提示
  `Repair and restart runtime`。静态契约与假 HTTP server 回归覆盖 mismatch 零 `/exec` 副作用。
- 边界：同 checkout 路径、package version 或 Host catalog 都不能证明 Houdini 已 reload；
  完整重启后旧任务节点因进程内 provenance 丢失而安全降为 foreign。
- 下一验收：重启 runtime，新建 Houdini session，确认 `/health` hash 一致、
  `node_provenance` 可用、capability snapshot 与 `verb_help` 同代。

## HTA-022：视觉工具 transport 成功被误当成语义识图成功

- 状态：P0 evidence/完成门已修；待新 session 验证 agent 不再夸大
- 首次证据：蜘蛛 trace `9b7bd919` #122 返回
  `ok:false/STRUCTURED_BOOTSTRAP_DISABLED`；#123 明确说模型仅接受文本、无法看图；#128/#129
  只把图片展示给用户。旧 evidence 却把四次都记为 `ok:true`，`completionRisks=[]`，#130 仍把
  vision todo 标 completed，最终文本声称双帧视觉确认。
- 根因：旧提取器只看 tool transport/`isError`，且把 bootstrap、inspection、presentation
  合并成一个成功布尔值。
- 修复：evidence schema v2 记录 `role/transportOk/semanticOk/reason`；结构化 `ok:false` 和
  中英文拒绝看图判 semantic failure；只有 inspection success 能满足视觉完成门。完成视觉 todo
  而无证据另报风险。重提取该 trace 产生三个 completion risks。
- 反例/边界：`render_view`/`render_check` 成功仍是有效文件/像素证据，但不能证明蜘蛛形态、
  穿模或自然步态；`vision_present` 对用户交付有价值，但不是 agent 自证。
- 下一验收：换用实际可读图的 provider 跑同图 A/B，确认成功 inspection 为 true；再用文本模型
  重跑一次，确认 todo 保持未完成或最终明确写“视觉语义未验证”。

## HTA-023：自生成质量标准被写成外部真实性证据

- 状态：P1 强完成协议已获两模型建模 + 一个程序化特效的跨域正向行为证据；合同/扰动/新鲜证据门已部署验收，视觉语义完成门仍有新候选缺口。
- 首次证据：`d6df94d7-d778-4d35-8529-a6f3e9f4e804`。#3 只确认“山地车”和
  SOP + render_view 交付；没有外部参考、目标 LOD、允许简化或程序化控制合同。#7 起把尺寸直接
  写入多个 VEX；首轮 #21/#23 看完整车远景后宣布验证通过。用户纠正后 #26 才手写四类局部检查，
  最终又把轴距/轮径/头管角等称为“真实山地车范围”，trace 中没有来源，部分数字也没有同级工具证据。
- 最近证据：`e0bc309b-ab8b-4a40-b636-14217cd2b91f` 已加载 P0 preset 并主动写出目标、无参考假设、
  14 个控制、关系与视图计划，证明行为层生效；但 `web_search`/`read` 明明可用却均未用于参考，
  没有 LOD/允许简化，未读取 quality-contract reference，首张 render 前已创建 116 个节点，未做
  控制扰动。最终又把修改前的 5740/4561 写入报告，实际末次 render fingerprint 为 6027/4848。
- 两模型复核：`937bfa1e-f183-46e2-a717-d930bd701c34`（qwen3.8-max）与
  `73bc9795-d45c-4774-ae32-c2a6291dd2b8`（k3）均读取质量合同、建立集中控制/骨架、执行关系门，
  并真实完成 `wheel_radius` 扰动、受影响验证、恢复和新鲜统计。Qwen 另做 web 调研和结构化
  goal/todo，K3 主动检出后胎/车架 `-17.76mm` 穿插并修到 `+3.33mm`，证明 P1 已从“会说合同”
  前进到“会按结果返工”。仍有共同缺口：mutation 前没有明确 LOD/允许简化；Qwen 四张 render
  近黑或视角错误却只按文件成功，K3 只看被裁切的 viewport 局部。
- 症状：产物可辨认、cook 和 render 都成功，但部件关系错误需要用户指出；agent 能补局部问题，
  却不知道还有哪些未进入自己检查清单，完成声明的证据等级高于事实。
- 根因：P0 的 `research → clarify → contract` 只在主 preset 中可见，而骨架/扰动/新鲜证据门藏在
  “按需阅读”的 reference；agent 会复述合同，却没有把它作为持续更新的证据账本。
- 修复：主 SOP skill 对符合条件的任务强制读取质量合同，并内联研究、骨架、关系账本、视觉批评、
  扰动恢复和末次 mutation 后刷新证据六个 checkpoint；preset 要求逐项 `pass/fail/unverified`。
  evidence/report 新增 `qualityLoopEvidence` 与确定性风险：合同缺字段、未加载质量合同、可用研究未用、
  无来源真实性、过晚首次视觉、无控制扰动、关系合同无证据和最终几何统计陈旧。
- 审计纠正：两模型 trace 暴露 `CTRL(S)` 子节点扰动、goal/todo 合同、反向词序骨架描述、明确
  `unverified` 视觉 todo 和逗号/中文面数格式均被旧提取器漏读；这些是 evidence 假阳性/未知，
  不是 agent 未执行。提取器与反例 fixture 已按可观察事实扩展。
- 交互/视觉窄修：重大选择使用 2–4 个互斥选项、推荐项、影响说明和自定义文本补充；唯一
  路径/名称/精确值才用纯文本。SOP 视觉门要求声明资产轴向，并用 render check 拒绝近黑、空白、
  错误视角或裁切图片；语义视觉失败不等于像素展示门可跳过。
- 跨域部署复核：`bbaedb46-60f0-40c9-b59a-52795c727895` 的沙尘任务在首次 mutation 前加载
  SOP skill/质量合同、用三组有效选项确认形态/技术/交付，写出镜头级轮廓合同，集中 12 个控制，
  完成 `ring_speed` 扰动/恢复及末次修改后的 cook、帧差和三帧图像证据。说明研究→澄清→合同→
  扰动→新鲜证据已跨建模/特效生效；仍未在 mutation 前披露无地面碰撞、SOP 点云近似等允许简化，
  且最终将用户原始“电影感”标为 `unverified` 后仍以“完成”交付。
- 反例/边界：抽象/风格化任务、用户给出完整 recipe、简单可逆编辑不需要强制研究或问卷；用户
  明确授权 agent 自选时可以继续，但必须披露选型和未验证的真实性边界；用户已提供参考时不强制
  额外 web 搜索。regex 风险只证明可观察步骤缺失，不冒充艺术质量评分。
- 下一验收：再用一个体积/模拟任务检查简化是否在 mutation 前披露，并为承诺形态提供独立于整体
  hero 图的数值或分层诊断；不再重复验证已通过的 choice-first/扰动基础路径。

## HTA-024：ask schema 近似字段静默退化成空白输入框

- 状态：P0 fail-closed 修复已部署；合法 choices 真实 UI/trace 验收通过，畸形字段的现场拦截重试路径仍只有确定性回归。
- 首次/最近证据：`645cd673-b9f7-4e99-a547-d8bf7270c7e0`，tool/call seq 262。K3 已生成三组
  合理选择内容，但问题对象使用带尾随空格的 `"header "`、`"options "`；UI 因执行器只读取精确
  `header/options` 而为三题都显示自由文本框。system snapshot 已含 choice-first 规则，说明仅靠提示
  不能保证 JSON key 精确。
- 根因：上游 `@deepseek-ai/dsh-tool-ask-user@0.1.1-rc.2` 的 question/option schema 设置
  `additionalProperties: true`；参数校验接受近似/未知字段，执行器又静默忽略它们。DSH
  `tools/pre-execute` 明确禁止改写已记录参数，因此不能在中间件偷偷 trim key。
- 修复：dsh-houdini agent scope 注册 pre-execute guard。`ask_user_question` 的 question 只接受
  `id/question/header/options/multi_select`，option 只接受 `label/description`；未知或尾空格字段在 UI
  前拒绝并返回精确重试说明。选择型问句没有 2–4 个 options 同样拒绝；路径、名称、精确数值和
  自由补充等天然文本问题继续放行。日志参数、展示和实际执行保持一致。
- 反例/边界：guard 不改写参数、不替换上游工具、不把所有问题强制成选择题；合法 custom 回答由
  原 ask 工具/UI 保留。它只在挂载 dsh-houdini 的 agent scope 生效，不影响其他 DSH agent。
- 回归：新增 `ask-user-choice-guard.test.mjs` 覆盖合法选择、尾空格 key、无 options 的选择型问句、
  选项数边界、option key 近似、精确路径和自由补充；`npm test` 现为 7 个 Node 测试文件全绿。
- 部署验收：`bbaedb46-60f0-40c9-b59a-52795c727895` tool call #5 / seq 216 使用精确
  `header/options`，三题各有 2–3 个互斥选项和影响说明；result 完整记录三项选择，用户界面不再退化
  成空白输入框。该次模型首次即生成合法 schema，因此没有触发 guard 的拒绝分支。
- 下一验收：未来自然出现一次近似字段时，确认畸形调用只形成工具错误、不会打开问卷，且模型用
  精确 schema 重试；无需为制造错误专门污染用户任务。

## HTA-025：整体体积预览被目标先验误读为承诺形态

- 状态：候选 E1（单 trace + 人工同图复核）；先修审计漏检，不发布沙尘专用强规则或新动词。
- 首次/最近证据：`bbaedb46-60f0-40c9-b59a-52795c727895`。#32/#33 的 f24/f60/f120
  `render_view` 文件、像素 bbox 和亮度均有效；#34–#36 确实把三张图送入支持图像的 K3。随后
  assistant seq 4879 把 f60 称为“clear ring/donut with raised outer rim and central column”。人工复核
  同一原图时，f60/f120 主要呈现为黑底上的灰色扁平椭圆尘团，环孔、沙浪墙和中心柱均不足以可靠
  分辨；两轮返工后的 f60 仍是实心团块式读法。
- 症状：transport、像素门和 semantic access 都成功，模型也写了缺陷清单并迭代，但目标词先验使
  它把模糊整体图升级为形态通过；`geo_frame_diff(P)` 只证明点在动，source detail 的
  `ring_radius_now` 只证明公式半径，不证明最终 VDB 密度仍保留可见环形结构。
- 根因候选：环形墙、中心柱与内部贴地尘被合成到同一中性灰 OpenGL 体积，iso hero 图发生遮挡和
  投影塌缩；完成门没有要求承诺的体积分层形态用独立诊断视角、隔离分支或场采样复核。同一模型既
  知道目标又裁判图像，弱证据容易被目标描述补全。
- 当前修复：evidence 的开放式质量触发扩展到电影感/镜头级/可靠验证/可调效果；最终以“完成”交付
  却把用户原始质量维度列为 `unverified` 时新增确定性风险；生产 persona 明确核心项 fail/unverified
  只能判 partial/incomplete。重新提取本 trace 应报告
  `quality_contract_incomplete(simplifications)` 与 `requested_goal_reported_unverified(cinematic)`。
- 候选建议：体积/合成效果的承诺形态至少再给一种独立证据（例如隔离层、正交/切片诊断或密度
  采样），并把结构运动预览与材质/灯光/颜色意义上的“电影感”分开签约；具体工具形态等待第二个
  独立模拟任务，不因本例直接新增 `volume_*` 动词。
- 反例/边界：抽象云团、只要求数据网络、用户明确接受不可判形态的中性预览时，不强制 hero 级
  外观；正式 Karma 画面本身也不能替代隐藏层/密度关系等数值证据。
- 下一验收：用另一类体积效果（非环形冲击）要求两个可区分的形态层，检查独立诊断能否阻止整体
  图像的目标先验误判，再决定扩展现有 geometry/volume 自省还是新增通用动词。

## HTA-026：query/exec 只靠提示分工，query 实际包含副作用

- 状态：P0 Bridge 边界已修；待 Repair/restart 后真实 session 验收。
- 证据：2026-08-28～31 discovery session 中，多个 `houdini_query` 调用了 `set_timeline`、
  `cook_node`、`set_parm(s)`、`tab_create/delete_node`、`render_view` 或裸 `pressButton/parm().set`；
  旧 evidence 只检查裸方法，进一步漏掉了动词 ledger 中的副作用。
- 根因：Host 只用 description 要求“read-only”，Bridge 的 `/exec` 对 query/exec 使用同一权限；审计器
  又把“没有裸 mutation”误当成“没有 mutation”。
- 修复：query 不再暴露 `allow_raw`，Host 发送 `read_only=true`；Bridge 不向 query namespace 注入修改
  动词，并在执行前拒绝修改动词、cook、render、viewport capture 和裸修改。evidence 同时检查裸方法
  与 side-effect verb ledger。
- 反例/边界：`scene_info`、`describe`、`read_parms`、几何/USD 统计和真正只读 HOM getter 可继续在
  query；需要改变 frame/cook/render 的验证不是“读”，必须转 exec/job 并接受其回滚/审计语义。

## HTA-027：Houdini undo 成功但 Bridge ownership provenance 未回滚

- 状态：P0 修复并通过 H21 regression。
- 证据：在同一 mutation exec 中删除当前 session 所有节点后故意抛错，Houdini `performUndo()` 能把
  节点恢复；旧 `_OWNED_NODE_SESSIONS` 已在 `delete_node` 时移除条目，恢复节点随后被误判为 foreign。
- 根因：事务只覆盖 Houdini undo stack，没有把 Bridge 进程内的所有权注册表视为同一事务状态。
- 修复：mutation 前快照 registry；只有 `performUndo()` 成功时同步恢复快照。回归检查节点存在且
  `node_provenance` 仍为 `owned_current_session`。
- 反例/边界：Houdini 进程重启后 registry 有意丢失，旧节点应安全降为 foreign；不能跨进程伪造
  ownership。若 undo 本身失败，也不能恢复 registry 冒充场景已回滚。

## HTA-028：像素工具被当作语义识图，掩盖 inspection 失败

- 状态：P0 evidence 修复；旧 trace 已重提取。
- 证据：第二模型机械 session 的 `read_image` 与 `vision_glance` 均失败，只有
  `vision_pixel_diff` 成功；旧报告仍把它列为 `semanticOk=true`，从而没有报告 render 缺少成功识图。
- 根因：旧分类把所有 `vision_*` 统一当作 semantic inspection，没有区分 transport、像素事实、
  presentation 与内容理解。
- 修复：只有 `read_image`、glance/ground/detect/OCR 等 inspection 能提供 semantic success；
  pixel diff、crop、dominant colors 等归 `pixel`，只证明客观像素/派生事实。该 session 现在稳定产生
  `render_without_successful_vision`。
- 反例/边界：像素证据仍可证明新鲜度、差异、亮度、bbox 或颜色，不应删除；它只是不能回答对象
  是什么、关系是否合理、画面是否满足语义目标。

## HTA-029：provider/额度终止被压扁成普通未完成

- 状态：P0 evidence 修复；真实 quota 与 network error 已复核。
- 证据：一条模拟 session 的最终 `turn/end` 明确含 `insufficient_quota`，旧 terminal 只有
  `lastEventType=turn/end`；另一条 session 在无任何 assistant/tool 工作前因 `network_error` 终止，
  旧报告仍误报质量合同缺失。
- 根因：提取器没有解析 `turn/end.reason`，完成风险也没有“工作是否实际开始”的前置条件。
- 修复：terminal 记录 completed/quota/external error 的 category/code/message；quota 单列
  `quota_exhausted`。零 assistant、零 tool 的外部启动失败不运行质量闭环判定。
- 反例/边界：quota 不等于 agent 能力失败，也不等于产物无价值；若已有工具执行，仍保留未完成 todo、
  无最终交付、质量门缺失等可观察风险，不能用 provider 原因洗掉执行事实。

## HTA-030：保存状态与渲染成功缺少可审计的新鲜度

- 状态：P0 工具合同已修；H21 headless regression 通过，待 GUI runtime 验收。
- 证据：真实任务用裸 `hou.hipFile.save()` 逃生，旧 `scene_info.hip_saved` 不能区分已命名和已落盘；
  MCP 参考运行也出现 save 返回成功但 live scene 仍 dirty。旧 `render_frame` 只验证目标存在/非空，
  预先存在的旧文件可能被误当成新渲染，临时 picture 覆盖还会泄漏到 ROP。
- 根因：合同用单布尔压缩了 path、dirty reliability 与磁盘事实；render 没有 pre/post fingerprint，
  也没有把临时参数纳入恢复状态。
- 修复：`scene_info` 拆为 `has_named_path/has_unsaved_changes/dirty_reliable/clean_on_disk`；
  `scene_save` 只保存已命名场景并返回 dirty/bytes/mtime。`render_frame` 比较前后 bytes、mtime 与有界
  内容摘要，只有新建或变化才 fresh，并 finally 恢复 picture/frame/foreground。
- 反例/边界：H21 `hython` 保存后 dirty flag 仍不可靠，必须返回 null/false 边界，不能硬说 clean；
  文件指纹证明本次产物变化，不等于渲染内容语义正确。
