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
- 证据：`40054277` 最后工具调用 #77 的 frame 1/12 `mean_abs_diff=0`、`max_abs_diff=1`，仍有两个未完成 todo，且无最终 assistant 交付。`71d76525` 工具调用 #40 的 geometry diff 非零、#46 的 render diff 为 21.1%，但 #47 的视觉 A/B 明确判断“没有明显变化、不像行进波浪”；agent 仍在 #50 把动画验证标 completed，并在最终文本宣称“全部验证通过”。
- 症状：旧版本完全没有时序证据；新版本有数值差异，却把“点动了/像素不同”误当成“用户要求的运动语义成立”，甚至覆盖视觉工具的直接否定。
- 根因：完成门只检查非零阈值，没有规定证据冲突的裁决顺序，也没有要求波峰传播、锚点/活动区分层等语义不变量。
- 修复：geometryAtFrame 无 playbar 副作用比较；render_check 增加 RMSE、changed/meaningful pixel % 与高精度 mean。审计/workflow 现区分：完全静止、方向相反、主体缺失等客观反例必须阻断；节点/数据/时间语义通过而静帧不足以裁定细微动态或审美时，允许标记“视觉待用户播放判断”，但不得伪称视觉确认。
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
- 证据：`71d76525` 工具调用 #3 把 `search_tab_menu` dict 当 list、#7 把 `read_parms` list 当 dict、#12 猜错 `geo_attrib_stats` keyword、#31 假设 `describe` 含 `ok`；中途 #13–#16 用 grep/read 打开插件源码才纠正。正常 Houdini 会话工作区是 `$HIP`，仓库源码不应成为运行期契约入口。
- 症状：一次本可只读发现的签名/结果字段，变成 exec 失败、undo、重复 batch；有时失败发生在修改之后。
- 根因：system prompt 为控制体积只列意图，没有统一的运行期动词契约自省；Python `inspect.signature` 虽可手写，但 agent 不知道 registry 边界和结果含义。
- 修复：新增 `verb_help(name)` 返回准确 signature/docstring、未知名相似建议；guidance 要求不确定时先查。`read_parms` doc 明确返回 `list[dict]`，guidance 明确 `cook_node` 才拥有 `ok/healthy`、`graph` 要围绕数据节点调用。H21 headless/live bridge 回归通过。
- 边界：节点自身的 SideFX 参数/帮助仍由 `list_parms`/`describe` 和未来 `node_help` 负责；`verb_help` 不替代它们。
