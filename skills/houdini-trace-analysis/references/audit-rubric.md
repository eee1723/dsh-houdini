# Houdini trace 审计量表

## 目录

1. 证据边界
2. 任务契约与完成判定
3. 轨迹阶段与推进逻辑
4. 工具机会矩阵
5. 动词组合的保留、补充、拆分与合并
6. Houdini 领域逻辑
7. 分模块验证阶梯
8. 视觉、渲染和动画验证
9. 效率、恢复和卫生
10. 证据强度与产品决策
11. 标准报告模板
12. Skill 演化协议

## 1. 证据边界

先核对session元数据的effective preset与request/header实际persona，再核对skill/card曝光。工具存在不等于Houdini persona已加载。
v11transaction区分动词执行与最终提交；rolled_back中的成功ledger不得当当前依赖。删除/替换输出可解除旧checkpoint，不能只按旧路径永久记未解决。
检查判据是否蕴含标签：unsigned距离不是插入深度、bbox极值不是镜像对称、全局最低y不是每足接地。
只测response不证明扰动后invariants；事后改阈值需独立依据；unsupported保留范围。
图像访问与正确识别分别记录；focus_group/isolate/projection/framing_bounds明确实际观察条件。

必须同时使用三层证据：

- 原始层：用户/assistant 消息、tool call、tool result、turn 结束状态。
- 结构层：工具数量、动词 ledger、失败、advisory、代码长度、重复调用、帧间 diff。
- Houdini 层：节点类型、拓扑、参数、属性、点/面/顶点、局部 bbox、cook 状态、显示旗标、帧依赖和渲染结果。

报告中的每个重要结论标注 `步骤 #N HH:MM:SS`、事件 seq 或用户原话。HTML 报告用于导航；JSON evidence 和原始 session 才是事实源。

先检查 evidence 的 `capabilitySnapshots`。只有当某能力在该步骤之前已出现在 request header/
skill catalog 或能由当时工具契约合理发现时，才允许标 `MISSED`；用当前仓库目录回看旧 trace
时，新加入的工具必须标“当时未曝光”，不能倒果为因。

当 trace 出现大面积 raw-hou 绕过时，同时判断执行守卫状态：优先读取同期 `/health.rawGate`；
若 trace 没保存 health，则用“verb-covered 裸 mutation 是否实际执行”判断 gate 当时是否 fail-open。
system/guidance 已曝光只能证明模型收到规则，不能证明 bridge 执行了规则。

若 capability snapshot 与 verb ledger/`verb_help` 返回冲突，优先怀疑 Host/Bridge generation skew。
当前 Bridge 的 `/health.verbCatalog` 名称/hash 是运行时事实；只看到 Host 目录不能证明 Houdini
进程已经 reload。旧 trace 无 health 时，用未知动词、旧签名或旧返回字段作为间接证据并降级强度。

长会话可能在 `compaction/prune` 后重放历史 `tool/result`。同一 callId 只代表一次执行；
evidence 必须去重并把后续结果列为 `replayedResults`，不得让 replay 膨胀调用、动词、
失败、耗时或阶段时间线。

不要把以下内容混为一谈：

- tool 返回错误。
- tool 成功但某个 verb 失败。
- tool/verb 都成功但节点结果语义错误。
- 结果正确但没有完成保存、清理、说明或用户验收。

失败 exec 另查 `rollbackSteps`：`applied=true` 表示 Houdini undoable scene edits 已撤销，
不表示文件/HDA 库等外部副作用消失；`supported=false` 的 headless 失败仍可能留半成品。

## 2. 任务契约与完成判定

从用户消息提取可验证契约：

| 维度 | 例子 | 完成证据 |
|---|---|---|
| 场景产物 | 程序化草地网络 | 节点存在、拓扑合理、参数可编辑 |
| 参考/真实性 | 指定车型、现实尺度、技术标准 | 用户参考或 agent 实际检索来源；无来源时明确假设 |
| 质量/LOD | 预览、镜头级、产品级、允许简化 | 用户选择或 agent 披露的默认；对应观察距离和局部完成门 |
| 形态 | 草叶有宽度、密度合理 | 单株/复制后局部几何验证 + 中性视觉检查 |
| 动态 | 风吹麦浪 | 相隔帧的几何/图像差异，且差异方向符合风场 |
| 运行健康 | 无 cook 错误 | 关键节点 errors 为空；warning 已解决或解释 |
| 用户界面 | 用户视口可见 | 仅当用户关心屏幕时，用 viewport_screenshot 诊断 |
| 交付 | 保存/路径/说明 | 明确文件、节点、控制参数和限制；最终消息存在 |

完成状态只能是：

- `完成`：全部核心契约有证据且已交付。
- `部分完成`：部分目标成立，但核心形态/动画/交付至少一项缺失。
- `未完成`：核心目标没有验证、产物错误，或会话无交付地结束。
- `不可判定`：trace 缺失必要结果；列出缺失证据，不猜。

若最后事件是 tool result、最后 todo 仍 pending/in_progress、最后 A/B 验证失败或没有 assistant 交付，不能判“完成”。
最终文本若以“完成/交付”定性，却把用户原始明确要求的质量维度列为 `unverified/未验证`，核心契约
只能判部分完成；`requested_goal_reported_unverified` 是对此矛盾的确定性审计入口，不替代人工判断
该维度是否核心。

开放式任务另检查：agent 是否识别了会改变方案的歧义，是否实际研究/询问或获得用户授权自选，
是否在大规模 mutation 前留下可复述的目标、参考状态、假设、质量门和验证计划。用户说“你决定”
允许 agent 选型，但不允许把未披露的模型记忆写成外部事实。数字彼此自洽只能证明内部一致，不能
单独证明“符合真实范围”。

`create_goal`/`todo_write` 可以证明 agent 在 mutation 前记录了结构化合同字段，但不能替代用户确认；
用户选择以 ask result/用户消息为准。重大选择的 ask 应优先提供 2–4 个有影响说明的互斥选项、推荐项
和 custom 文本补充；路径、名称、精确数值等天然唯一答案才允许纯文本。不要把“用户没填空白框”
误判成用户授权 agent 自选。

## 3. 轨迹阶段与推进逻辑

用状态跃迁而非 assistant 文案划阶段：

1. 接收/判歧义：分开用户事实、目标、解释、价值判断和未决选择。
2. 研究：只有外部真实性、当前资料或未知领域会改变方案时执行；记录来源和适用边界。
3. 澄清/合同：询问剩余重大选择，或披露用户授权 agent 自选的假设、质量门和验证计划。
4. 现场检查：版本、HIP、现有节点、帧范围、用户上下文。
5. 设计：选择 Houdini 原生模块和数据契约；明确验证点。
6. 构建：建立最小网络，避免一条超长 exec 在中途失败后留下不明半成品。
7. 模块验证：逐节点/逐分支验证输入、输出和局部不变量。
8. 集成：合并分支，处理属性和 warning。
9. 静态视觉：agent 自有 render_view；先客观 check，再中性识图。
10. 时序验证：至少 A/B 两帧，验证动态幅度与空间传播。
11. 修订：用户反馈或失败使旧假设失效时，重开合同并重跑受影响完成门。
12. 清理交付：删除 probe、恢复显示状态、布局、保存/说明、更新 todo。

标记反模式：

- 在模块验证前宣称“网络成功”。
- aggregate bbox/点数通过即判形态正确。
- 几何异常时优先调相机、灯光、gamma 或视觉 prompt。
- 连续失败后只改 API 拼写，不回到上一稳定状态。
- 为验证创建 probe 后未恢复接线或删除节点。
- 用户纠正后没有重新核对完整任务契约。
- 自己生成规格/尺寸，再凭模型记忆判其“符合真实范围”，并把内部一致写成外部验证。
- 只询问交付形式，却未询问或披露真正改变结构/质量的目标、LOD、参考和允许简化。

## 4. 工具机会矩阵

对“与本次任务相关”的每个能力使用以下唯一标签：

- `USED_RIGHT`：调用时机、参数和结果消费正确。
- `MISSED`：已有能力与当前意图直接匹配，但 agent 走裸 API、猜测或绕路。
- `MISUSED`：调用了工具，但语义/参数/结果解释不正确。
- `TOOL_BUG`：工具实现或契约导致错误、状态污染或不可操作报错。
- `MISSING`：目录中没有能表达该通用意图的能力，且重复手写成本高或风险大。
- `NOT_APPLICABLE`：本任务不需要；不能用来支持删除。
- `REDUNDANT_CANDIDATE`、`MERGE_CANDIDATE`、`SPLIT_CANDIDATE`：只用于跨 trace 产品建议，必须附证据强度。

采用统计必须分层，不能用一个百分比代替：

- `catalog.used/total`：目录广度，只说明任务碰过哪些能力；大量 NOT_APPLICABLE 动词不进分母推理。
- `verbAdoption.callCoveragePct`：Houdini 调用中含至少一个 verb 的比例，会被合法只读探针稀释。
- `verbDensity`：每次 Houdini 调用的 verb 数，观察 batch/组合程度。
- `successfulExecVerbCoveragePct`：全部成功exec中含动词的比例；包含加载器/纯函数测试，不是场景修改采用率。
- `rawReadOnlyCalls`：成功、无动词且没有副作用候选的query，仅描述只读接口的守卫范围。
- `blockedVerblessRawMutationCalls`：无动词调用的执行前Gate拦截，包含query和无已知动词的疑似/外部操作；优先canonical rawUsage，不依赖错误文案或方法名正则。
- `successfulVerblessRawMutationCalls`：成功返回的无动词裸修改候选，不证明实际提交或全部副作用被观测。
- `rawSuspectedEffectCalls/rawUnknownEffectCalls/rawFailedCalls`：分别保留疑似/外部副作用、未知动态调用、未证明只读的失败；不能把它们塞进只读计数。rawUsage.read_only是静态扫描结论，transaction.no_scene_change不排除文件/Python全局副作用。Host result_ref/request_ref/source_ref回读不计新HOM执行。

必查机会：

- 外部事实会改变方案时：检查当时是否曝光 research/web 能力；有则实际检索并保留来源，没有则向
  用户索取参考或降低真实性结论，不能默认 `MISSING` 或凭记忆补齐。
- 剩余用户选择会改变方案时：使用已曝光的提问能力；一次问完相互关联的重大选择，不把简单任务
  变成问卷，也不在已开始大规模 mutation 后才补问质量标准。
- 发现节点：`find_nodes`，不要默认裸遍历 `/obj`。
- 拓扑诊断：`graph`，尤其在接线或属性来源混乱时。
- 参数导航：`list_parms`；参数意图：`read_parms`。
- 同一节点三项以上赋值：优先 `set_parms`。
- 动词签名/返回形状不确定：先 `verb_help(name)`；若 agent 先制造一次失败或读取仓库源码才发现契约，标记为可避免的 discoverability 失败。
- SOP 创建：`search_tab_menu`/`tab_create`；避免猜旧节点或错误版本。
- Solaris/Material/COP 等上下文创建：优先 `search_tab_entries(actual_parent, query)`；检查
  entry 是 node type 还是多节点 tool、是否 hidden/deprecated、是否被 parent tab mask
  排除。`tab_create` 只建一个可见节点，setup/builder 用 `tab_apply`。
- 显示：SOP 用 `sop_set_output/sop_output_node`，OBJ 用 `set_object_visible/visible_objects`；旧 `set_display/display_node` 只作兼容。检查是否错误混用 singular/plural context。
- cook/状态：`cook_node` + `describe`，但不得忽略 warning。
- 属性值：`geo_attrib_stats`；若局部形态仍不可证，记录新的几何自省缺口。
- 视觉验证：`render_view`；交付 ROP 才用 `render_frame`。
- 用户屏幕问题：`viewport_screenshot` 仅作诊断。

## 5. 动词组合的保留、补充、拆分与合并

### 保留

即使低频，只要语义独立、风险边界不同或是关键逃生能力，就应保留。零使用只说明本 trace 不适用或采用率低。

### 补充

同时满足以下条件时列 `MISSING`：

1. 意图可跨任务复用，不是某个草地/镜头的专用操作。
2. 当前需要多段易错裸 hou/VEX 或多次探测。
3. 封装能加入校验、状态恢复或更诚实的返回。
4. 已有动词不能自然扩展覆盖。

### 合并

只有两项能力的用户意图、生命周期、副作用和返回契约基本相同，且 trace 显示 agent 经常选错，才考虑合并。`set_parm` 与 `set_parms` 是 primitive + batch，不因名字近就合并。

### 拆分

当同名动词跨 context 有不同基数、所有权或副作用时拆分或改为 context-aware。例如 SOP 网络只有一个 display child，而 OBJ 可有多个可见对象；单一“display node”契约若假设错误，就必须拆分或显式返回不同形状。

### 删除

至少满足：三个以上多样 trace 中无独立价值；有等价且更安全的替代；迁移路径明确；没有诊断/逃生用途。单 trace 不允许建议删除。

## 6. Houdini 领域逻辑

### HDA / OTL 代码维护

- 先重建用户要的是定位原因、修改回调、消除外部包，还是可移机交付；本机依赖链不证明远端具体缺包原因。实际定义库与完整类型名、用户授权和受影响实例范围分别核对。
- 相关自省优先hda_info/hda_get_section，局部修正可用hda_patch_section；批量磁盘定义盘点不硬套仅接受node的接口。文件列表与被检查定义逐项对齐，不能只因使用loadedFiles就判漏扫，也不能靠总数一致证明完整。
- 依赖包含Python import、内部自定义HDA类型、其他资源；扫描无包名不证明闭包完整。section写入/hash、内部helper、实际hdaModule/回调、cook后的最终几何、隔离目标环境可用分别列证据。声明单文件自包含须覆盖实际自定义节点依赖。
- 新实例菜单显示、底层token和实际业务输入分别取证；空默认、失效选择、切class不混同。输出仅errors()、分支数量不代替cook/warnings/分支关系。同步或替换纯函数通过不代替实际副作用与恢复。
- 手动exec源码绕过真实回调时只认可所测函数层；弹窗未测等范围应保留。测试需隔离，不鼓励为补证直接操作用户网络。无图像的功能维护不算视觉失败，不强迫艺术/动画完成门。
- 多section写入与普通文件写回不自动原子，HDA库不属场景undo保证。备份不等于恢复已经执行；清理临时节点不证明用户视口/dirty未变。具体维护候选按名加载houdini-tool-development，再读取其references/hda-maintenance.md，量表不自动认证其采用效果。

### Solaris / USD / Karma

- “节点类型注册表里存在”不等于“用户在当前 parent 的 Tab 菜单可见”。Material Library
  根层、各类 Builder 与 setup recipe 必须按实际 context 审计。
- 新 Karma 材质检查 render context（kma/mtlx/preview），不能用最终像素颜色替代；传统
  Principled 在 CPU 能出图不证明 XPU 完整兼容。
- 最终 Karma 交付检查 geometry/material binding/light/camera/RenderSettings/
  RenderProduct/RenderVar/USD Render ROP。普通 LopNode 按钮成功不等于 ROP 产物成功。
- SOP time dependency、单次 stage time sample 和最终 Karma 序列是三层证据；动画任务仍需
  同一 USD camera 的两帧或小序列。

### 节点类型和模块

- 选择节点前确认 Tab Menu 类型和最新版；优先 Houdini 语义正确的 SOP，而非熟悉但过时的 SOP。
- Copy to Points 应承担模板点 orient/pscale/N/up 的实例变换；使用经典 Copy 后手写变换需要强证据。
- 形变和成形的顺序必须保留数据：通常先变形中心线/曲面，再 Sweep/PolyWire 生成厚度，比生成截面后用错误 rest 坐标重建更安全。
- 草叶等扁平对象优先 Sweep/skin/ribbon 语义；PolyWire 是管状截面，不应无理由替代叶片模块。

### 开放式程序化资产

- 先读取 evidence 的 `qualityLoopEvidence`：合同字段、research/web 可用性与实际调用、质量合同
  是否加载、首张 render 前 `tab_create` 数、关系 probe、控制扰动恢复和末次修改后的统计新鲜度。
  `completionRisks` 中的 HTA-023 系列风险是审计入口，不替代对原始步骤和画面的人工判断。
- 区分“代码生成的固定结果”和“用户可调且关系保持成立的程序化资产”。关键尺寸若分散复制在
  多个 VEX/Python 字符串中，默认值能 cook 不证明参数化完成。
- 共享尺寸、anchor/局部坐标、模块输入输出和部件关系应有单一真相源或明确派生链；审计至少选
  一个关键控制做扰动，检查受影响模块是否仍满足关系门。
- `geo_piece_stats` 的非退化只证明面积/extent，不证明部件连接、包含、间隙或禁止相交；整体
  bbox/点数、无 warning、能出图同样不能替代装配关系检查。
- “细节丰富/高质量”必须落实到目标 LOD、允许简化、局部观察距离和证据视角。节点数、primitive
  数或装饰件数量只能描述复杂度，不能单独判质量。

### Rig / Animation 系统路由

- 不把“绑定”直接等同 KineFX/APEX。先分类：parameter channel、rigid pieces、hierarchy/FK、
  skeleton + skin、animator-facing character rig、simulation。
- `/obj` 等路径只说明放置 context，不自动授权相同名称的数据模型。新建几何父子机械/FK 默认
  KineFX；OBJ parenting 只在用户明确要求、既有 legacy、场景对象装配或下游 OBJ 交付时成立。
- rigid piece 任务检查稳定 `name/piece_id`、rest transform、当前 transform 与 membership；
  packed pieces/Copy to Points/Transform Pieces 通常比对所有展开点手写矩阵更符合数据模型。
- 旋转轴上的 piece 可能 `P` 完全不变而 `orient/transform` 已改变；活动集合和刚体动画不能只
  用 P diff，至少同时检查 orientation/transform。Copy/Pack 后还要确认稳定 name 真正存在于
  Transform Pieces 用来匹配的属性 class，不能假设模板 `name` 自动传播。
- KineFX 检查 joint `name/P/transform`、parent/local/world space；skin 另检查 `boneCapture`、
  capture pose、animated pose 与 Joint Deform。没有 skin/层级需求时，不因“专业”而强制 KineFX。
- 把 driver skeleton、control/capture binding 与 driven deliverable 分开。Attach Joint Geometry 的
  `jointgeo`/anchor、包含 skeleton 的总 bbox 或 joint P 变化都不能证明最终 skin/link 在动；实际
  geometry 探针失败后不得换测上游 metadata 并把同一契约改判为通过。
- APEX 面向 controls、constraints、FK/IK 与可复用 rig graph；必须证明任务需要延迟图求值和
  animator-facing 逻辑，不能用它替代简单 piece state evaluator。
- 路径依赖/非交换序列必须表示 ordered state transition。使用初始 membership + 独立绝对
  通道时，除非各通道确实互不影响，否则是结构性反例。
- 审计 OBJ parenting 时核对 `parent output → child input`，但 agent 应通过
  `set_object_parent(child,parent,reason=...)` 表达意图；generic `connect` 成功不得作为新建几何
  rig 使用 OBJ hierarchy 的依据。若最终契约是 geometry，仍需显式 final geometry 取证。

### 数据流和属性

对每个关键边界写出 `输入属性 → 操作 → 输出属性`。检查：

- 属性 class（point/prim/vertex/detail）是否正确。
- Copy/Merge 后属性是否传递、缺失、默认初始化或冲突。
- rest/local 坐标是在最终拓扑之前还是之后捕获。
- per-instance 属性是否在复制后仍存在。
- warning 中的 N/uv/Cd 等是否影响显示、材质或下游运算。

### Cook 和缓存

- 每次改接线/代码后 cook 目标分支；需要时强制更新。
- 渲染字节长期完全相同而场景已变，优先怀疑未 cook、显示对象错误或 ROP 缓存。
- 性能问题使用节点 cook 时间和 SideFX Performance Monitor；工具调用次数不是 Houdini cook 性能。

### 显示和所有权

- 区分 SOP display/render flag、OBJ visibility、用户 viewport 和 agent-owned camera/ROP。
- agent 验证管线不得改变用户视口或永久抢走对象可见性。
- 创建 camera/light/null 后核对并恢复原有 OBJ 显示状态。

## 7. 分模块验证阶梯

复杂程序化网络必须由小到大验证：

1. 源数据：地形或输入几何。
2. 最小生成单元：单株草叶、单块碎片、单个实例。
3. 成形后：宽度、面积、法线、UV、局部 bbox。
4. 模板点：数量、orient/pscale/id/phase 等。
5. 复制/实例后：随机抽样单个 piece 的局部 bbox 和属性。
6. 变形后：根部固定、尖端位移、面积/厚度未退化。
7. Merge/输出：属性一致、warning 解释、显示旗标正确。
8. 静态渲染。
9. 多帧差异。

“全场景 bbox 高度正常”无法证明每个草叶有宽度；“点数很多”无法证明拓扑没有重合。若现有工具无法低成本检查 piece/local extent，应列为通用几何自省缺口。

## 8. 视觉、渲染和动画验证

### 静态视觉

1. `cook_node`/模块不变量先通过。
2. `render_view` 返回非空、合理 content bbox 和亮度。
3. 第一轮视觉 prompt 只问“描述可见几何、颜色、位置、异常”，不说“这是成功的草地”。
4. 第二轮才按用户目标核验草叶、密度、风向等。
5. 视觉结论与数值冲突时回到几何，不用 prompt 说服视觉模型。
6. 视觉工具 transport 成功不等于看图成功。bootstrap 是 setup、present 是交付；只有 semantic
   inspection 可作视觉结论。结构化 `ok:false`、模型声明不支持图像/图片被省略等文本拒绝必须判失败。
7. 整物远景只适合轮廓/构图；小零件、接缝、间隙和穿插需要目标在画面中可辨认的局部视角。
   没有对应特写时，不得把“整物可辨认”升级成“局部关系视觉通过”。
8. 声称与外部参考一致时，参考和验证图必须具备可比较的视角/尺度或明确只做定性判断；单独看
   agent 自己生成的图不能证明外部一致。
9. 语义视觉失败或不可用时，仍读取 `render_view.check`/`render_check` 的亮度、非黑占比和
   content bbox。近黑、近空、目标缺失、触边或资产轴向错误的图片只能判像素展示失败；
   `stale=false`、文件字节非零和无 render error 只证明 transport/file 层。

### 动画

- 至少选两帧，帧距足以覆盖相位变化。
- 比较几何样本或 render diff；仅文件大小不同不够。
- `mean_abs_diff≈0`、max diff 仅 1 灰阶时，按静态或缓存问题处理。
- 几何 diff 明显非零只证明“数据随时间变化”，不证明运动符合用户语义。继续验证锚点、活动区、方向和空间传播。若固定相机 A/B 暴露明确的结构性反例（完全静止、方向相反、主体缺失），完成门失败；若节点/数据/时间语义均通过而静帧只是不足以裁定细微动态或审美力度，可停止追图并标记“视觉待用户播放判断”，但不能写成“视觉已确认通过”。
- render A/B 必须使用完全相同的相机与构图。逐帧按动态 bbox 自动重取景时，先比较返回的 camera `center/eye/dist/direction`；任一变化都会把相机漂移混入 pixel diff，该 diff 只能证明两张图不同，不能证明几何运动。
- 固定相机还必须覆盖验收帧的空间包络。检查每帧 `render_check.content_bbox` 与图像边界；触边或安全边距不足时记录为 framing clip risk，不能把“相机一致”写成“构图完整”。
- 验证根部近似固定、尖端运动更大、波峰沿风向传播；不能只看“画面动了”。
- 多 segment 或路径依赖任务不得只抽 first A/B。验证覆盖至少包括：第一段、一个会改变后续
  membership/空间的非交换转折、sequence mid/end、recovery；报告实际覆盖帧。
- trace 中只要状态求值器、核心 transform 图或 membership 规则被修过，修复前的上述序列证据全部失效；审计必须要求修复后重新覆盖 first、非交换 transition、mid/end、recovery，而不是沿用旧证据拼接完成门。
- 最终帧等于 rest 时，区分“正确 inverse 后恢复”与“所有绝对控制量归零后天然重算 rest”。
  后者不能证明中间序列正确。
- hidden piece 数、capture weights、joint hierarchy、constraint 和 state permutation 不能由
  单视角视觉确认，必须使用数据/属性/transform 证据。

### Render 工具边界

- `render_view(EXPLICIT_SOP)`：agent 自有快速验证，显式 SOP 经隐藏 proxy + forceobjects；检查 fingerprints、stale、状态恢复、确定性 headlight/Cd 和用户 display 漂移隔离。
- 动画 A/B 给每次 `render_view` 传同一 `framing_frame`；不同 framing metadata 下的 pixel diff 不作纯几何运动证据。
- 两张 render 已生成但缺 `render_check(ref=...)` 时，只能证明各自有效，不能声称固定相机 A/B 已完成客观图像比较。
- `render_frame`：已有 ROP 的正式或自定义构图渲染，不应承担反复修复 `render_view` 的职责。
- `viewport_screenshot`：用户屏幕诊断，不是 agent 自证成功的主路径。

## 9. 效率、恢复和卫生

统计并解释：

- 首次正确模块产物时间、首次视觉证据时间、用户纠正时间、最终交付时间。
- 构建、几何调试、渲染调试各占多少调用/分钟。
- 同类硬失败是否连续发生；是否在第三次前改变策略。
- **同一 resolved node** 三项以上 `set_parm` 是否可批量；跨多个节点的总次数不能算 batch
  opportunity，已经使用 `set_parms` 的字段不重复计入。
- 是否反复全文重发 VEX/Python；能否局部 patch。
- 是否创建并清理 test box/light/probe/camera。
- 是否恢复 display/ROP/frame，是否保存或说明未保存。

## 10. 证据强度与产品决策

- `S1 单例`：一个 trace；只能提出假设或 P0 可复现工具 bug。
- `S2 重复`：两个独立 trace 或当前 trace + 可复现实验；可进入 P1 设计。
- `S3 稳定`：至少三个多样任务、反例分析完成；才可删工具或大幅重构契约。

工具自身抛错、污染状态或虚假成功，现场可复现后可直接 P0，不必等待三个 trace。采用率、拆并和删除必须积累证据。

## 11. 标准报告模板

### 结论

- 完成状态、最严重因果链、用户是否被迫纠正。

### 任务契约差距

| 契约 | 证据 | 状态 | 缺口 |

### 阶段时间线

| 时间/步骤 | 阶段 | 行为 | 结果/转折 |

### 工具矩阵

| 能力/动词 | 标签 | 证据 | 正确替代/产品动作 | 强度 |

### Houdini 模块审计

| 模块 | 输入/输出契约 | 验证 | 问题 |

### 最小正确轨迹

列出 8–15 个状态跃迁，不写逐参数流水账。

### 优先级

P0/P1/P2，每项写：问题、证据、建议、验收、是否需要更多 trace。

## 12. Skill 演化协议

每次复盘后回答：

1. 当前量表是否漏掉了一个可复用维度？
2. `known-patterns.md` 是否已有同类模式？追加证据还是创建新条目？
3. 新发现是 task-specific、Houdini domain、tool contract 还是 agent policy？放到对应层。
4. 是否出现反例，要求降级或关闭旧建议？
5. evidence 脚本是否漏计失败、工具结果或新 schema？若是先修脚本并回归旧 trace。

模式库条目必须包含：ID、状态、首次/最近证据、症状、根因、建议、反例/边界、下一验收。不得把一次草地任务的专有节点名写成通用硬规则。
