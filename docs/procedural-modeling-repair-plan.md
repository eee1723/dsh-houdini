# 程序化建模 Agent 全链路修复计划

日期：2026-09-07。状态：v11源码候选已实施首批能力，离线验证通过；完整计划及现场发布未完成。

后续v12窄修已实施：Sweep显式输入初始化适配、静态多错汇总、node_info关键组件证据、
required_outputs必需分支、interfaces.axis_gap实际表面投影关系。H21/H22各28回归，Node18通过。
已在原吧台凳冻结几何中检出18mm分離，未保存源HIP。下次现场先短验Sweep创建与工具新契约，
再验证模型能按模块保留primitive组、调用test_controls，不重复整件任务证明同一工具bug。

目标：减少接口猜测、重复构建、无效观察和错误验收，让 agent 更快得到正确的主要形体，并交付可维护、可调且证据范围清楚的程序化资产。

输入：椅子 trace `30a6f459-36ff-4b67-9ddf-e92625335085` 的逐步审计、独立 H21 HIP 检查，以及本轮用户提出的自动现场上下文、build_module、三维观察、建模流程和节点操作知识五项要求。详细取证在本地 `tools/out/chair-trace-analysis-30a6f459.md`、`chair-offline-audit.json`、`chair-audit-metrics.json`。这些原始材料不进入生产 skill 或节点操作卡。

最初仅制定计划；用户随后明确“开始”，已授权实施。实施保留原WIP，不修改用户HIP，也尚未重启live。

### 2026-09-07 实施进度

| 包 | 状态 | 已落地与证据 | 尚余工作 |
|---|---|---|---|
| W0 | in_progress | 记录既有WIP和live H21/v10；补session创建缺preset时独立回读，修DSH0.1.2水印projectionValues兼容 | 历史cordis来源不能由现有日志唯一归因；真实新建/复用GUI验收 |
| W1 | in_progress | src/context.ts＋固定/context主线程metadata；用户确认改为每消息收件时一次，取消修改/30秒刷新；消息ID绑定与in-flight去重通过 | GUI几何选择暂not_observed；新策略live曝光待reload |
| W2 | verified | literal filter诊断、numeric tuple预检、transaction identity状态、重复tracer回显去除；18 Node及双版回归 | 新session真实效率测量；回包仅压缩已确认重复，不截断关键证据 |
| W3 | verified | 随包7类操作卡；Sweep/PolyExtrude/Revolve/Blast真实双版构造正反例通过 | 新模型是否自然使用；未验证版本不外推 |
| W4 | in_progress | 有界Polygon观察、稳定ID位移、point_mean、闭合/件数绝对range；恢复/反例双版通过 | 通用接地/镜像/有符号插入方法尚未封装，仍须合适独立量测或unverified |
| W5 | in_progress | focus_group/isolate/orthographic/framing_bounds，真实HOM相机/proxy双版测试通过 | 渲染器使用替身；GUI真实像素、诊断展示、已知缺陷盲读仍待验 |
| W6 | in_progress | SOP正文5580→3095字符，方法循环/知识路由/证据范围；trace新增preset/persona/cost/transaction | 方法判据自动风险索引与known-pattern状态进一步整理、行为反例 |
| W7 | in_progress | npm test 18文件，H21/H22各27 Python，skill audit 0issues/0warnings，包资源核对 | Repair/restart＋实际新session、GUI和未见行为验收；尚未released |

本次原始证据：tools/out/modeling-repair-baseline、v11-regressions-H21.json、v11-regressions-H22.json、
trace-evidence-30a6f459-v11.json、v11-pack.json。旧椅子重提取仍74calls/195verbs；65917ms工具耗时；
可去除重复tracer回显243819字符（旧返回561275字符中的43.4%），这是该trace文本去重机会，不是新模型提速实测。

后续live吧台凳发现并修复源码：timestamp-only快照重复、JSON结构括号误转义、首条用户消息日志时序。
现在由公开inbox/claimed事件捕获本步用户消息；采集和发布分开，时间/耗时变化不触发同用户状态重新发布。
新用户、实际场景状态、preset或可用性变化仍更新。此修正未热替换正在运行的吧台凳会话。

## 一、事实基线与范围

### 已确认

- 椅子 session 使用 `agentPreset=cordis`、coding persona；Houdini guidance、57动词、v10可选review文案和SOP skill/reference已曝光。不能将其称为完整Houdini preset验收。
- 用户请求到最终回复约89分钟，74工具调用、12硬失败、8次自动回滚；首次mutation约22分钟，首次render约52分钟。call→result耗时求和约66秒，其余是模型生成、上下文处理和请求间隙，不能进一步无证据拆分服务端排队/网络/推理。
- 49次build_module，成功exec动词覆盖100%，成功裸修改0。主要问题已从“接口未采用”转为“构造知识、事务认知、观测和判据不足”。
- node_info将parm_filter作字面子串匹配；模型当成regex使用，导致13卡参数空。H21独立复现grid：`size|row|col`匹配0、`size`匹配1、不筛选12。
- 座面高度和顶盖长期缺失；最终修复座面闭合，但顶轨/旋转部件存在开放边界。无cook warning不能替代几何检查。
- 最终dish_depth有效：0.012→0时1528点变化，最大位移约11.986mm，面积变化而bbox不变。原报告“面积不可测”不成立。
- 插接深度、镜像对称、接地和无穿插等标签，多处超出实际量测含义；控制扰动只测响应，没有复跑装配关系。
- 本地DSH system-prompt文档有公开 `ctx.systemPrompt.context()`，用于带来源的动态runtime-context快照；真实serving runtime版本的生命周期/参数仍须实施阶段核实。
- 本轮skill结构审计：6skills、6注册、0issues、0warnings。结构正确不等于行为质量通过。

### 待确认

1. cordis来自哪个创建入口、用户选择还是preset挂载。bundle层允许加载Houdini插件，并不能据此认定launcher有bug；launcher源码已有请求houdini和响应检查。
2. 多Network Editor/Scene Viewer情况下可以无副作用取得哪些焦点和几何选择信息；不承诺不存在或会触发交互的HOM getter。
3. H21/H22上Sweep/PolyExtrude/Revolve精确参数、默认值和几何检查边界。
4. 图像误判中取景、显示方式和模型能力各自占比。
5. 更短提示、更紧凑返回与新方法对未见任务的实际收益；不提前承诺固定提速倍数。

### 实施边界

- 保持5个houdini_*工具，优先扩展已有动词。若确有无法清晰承载的跨任务观察意图，再在工具契约评审中单独决定；不以57这个数量阻止合理能力，也不预造大量动词。
- SOP建模是本轮目标；不扩为全领域重构、通用实体认证、默认独立review、默认正式渲染或所有参数组合穷举。
- 保留Raw Gate、ownership、主线程队列、严格设参、caught-failure、显式输出、恢复检查和持久render服务。
- 原HIP只在disposable进程中回读/实验，前后哈希核验；不保存原文件。测试产物写隔离临时目录；真实建模产物遵循$HIP。
- 仓库当前已有v10未提交修改；实施前记录状态与文件基线，在其上做可审查增量，不reset、覆盖或把既有修改当作本轮成果。
- 不改冻结protocol/matrix/holdout；新诊断用例放独立材料，性能实验不污染生产知识。

## 二、目标链路

```text
用户新消息
→ 自动轻量现场摘要（身份/位置/选择/显示/帧/新鲜度）
→ 选择建模方法与当前模块的节点操作卡
→ 最小代理结构与主要比例检查
→ 小模块构建 + 局部几何检查
→ 与相邻模块集成 + 关系检查
→ 代表性参数扰动 + 响应/不变量/恢复
→ 针对问题的整体及局部视觉取证
→ 最终受影响状态复验、布局保存与限定范围报告
```

骨架门检查主要尺寸、世界位置、轴向和主关系；模块门检查部件自己的几何与属性；关系门检查实际部件之间的关系。模块与关系循环推进，不把关系检查拖到整资产细化之后。简单一步编辑只走现场摘要、修改和相关回读，不强迫完整流程。

## 三、工作包与依赖

| 包 | 内容 | 依赖 | 合入条件 |
|---|---|---|---|
| W0 | 基线与有效配置定位 | 无 | 明确实际创建入口和版本，保留源码/live/模型能力三层证据 |
| W1 | 自动现场摘要 | W0 | 有界、无cook、无UI修改、无跨session泄漏、可取消和降级 |
| W2 | 接口发现、事务结果、返回体积 | W0 | 原失败链定向复现通过，信息范围与安全性不退化 |
| W3 | 节点操作知识与可靠构造方法 | W2 | H21/H22正例和相邻反例通过，唯一知识来源 |
| W4 | 几何观测与控制判据 | W2；与W3共同核验 | 能检出已知几何缺陷且不把不支持的方法标pass |
| W5 | 针对性视觉观察 | W4定义目标/范围；W1提供UI边界 | 指定部件可辨认，构图/隔离/恢复可靠，有已知缺陷检出证据 |
| W6 | SOP/preset/guidance与trace审计收敛 | W1–W5 | 文档匹配真实能力，简单任务不膨胀，原判据错误不再被默许 |
| W7 | 集成、发布与行为验收 | 前述包 | 两版技术回归及实际新session证据；缺失门明确留candidate |

这些是分批提交的边界，不要求创建多个agent或并行执行。每包通过必要检查后继续下一包，不为重复证明同一件事反复跑整模型任务。

## 四、W0：基线与有效配置

**修改位置候选**：`houdini/python3.11libs/dsh_launcher.py`、版本诊断/manager模块、`presets/houdini/agent.cordis.yml`、相关client会话提示；具体文件按入口定位结果缩小。

1. 记录当前git状态、现有源码/构建版本、Host/Bridge契约版本、真实serving DSH版本与有效preset。不打印凭据。
2. 追踪Open Workspace自动建/复用会话、Web手动新建会话、插件通过bundle挂载三条路径，定位为何本次是cordis。
3. Houdini入口创建/复用时验证effective preset；响应字段缺失时使用公开会话查询确认，不把“请求里传了houdini”当成功。
4. 诊断展示实际preset与persona来源、契约版本、skill/card版本标识。不能通过“看到houdini_*工具”推断已启用Houdini persona。
5. 保留开发模式中cordis使用Houdini工具的合法场景；不在插件全局偷偷替换任意agent persona。普通建模入口默认路由到houdini，入口错配时给出准确状态。

**验收**：自动创建、正确复用、手动选择、响应缺字段、错误preset、开发模式合法使用各一条可观察路径；新session原始header/metadata与UI显示一致。是否要修launcher或Web入口由结果决定，不预定根因。

## 五、W1：自动现场摘要

**建议实现**：新增Host上下文提供模块，例如`src/context.ts`，在`src/index.ts`注册公开`systemPrompt.context()`；Bridge增加固定结构的只读上下文请求，复用主线程队列与`scene_info`。HOM采集逻辑可拆为小型`dsh_context.py`，避免大helper继续堆叠。

### 触发与生命周期

- 在启用Houdini上下文的会话中，用户每条实质性新消息默认取摘要；明显纯问候可跳过，意图不确定时取轻量摘要，不增加一次分类模型请求。
- 每条用户消息在Host inbox/inserted收件时采集一次，绑定消息ID；任务中追加消息同样处理。claim/assemble复用同一结果或in-flight请求，不按工具执行、场景改变或定时刷新。首次恢复缺收件事件时仅补一次采集并明确实际时间。
- 不把不断变化的场景信息放进固定system段，避免无谓破坏稳定前缀。保留来源、时间和替代旧快照的语义。
- 新用户消息重新观察选择/frame；旧消息快照保持为历史上下文。mutation/HIP切换后需要当前状态时显式query，工具继续校验身份/存在性/权限，不额外注入现场prompt。采集失败不在同消息内自动重试。
- “选中的这个”绑定用户消息时的快照；执行前目标已删除/换场景/明确选项产生歧义时停在相关动作并说明，不重新猜一个节点执行。

### 默认字段

运行实例/契约/effective preset、HIP和dirty可靠性、Houdini版本、frame/播放状态、可确定的网络上下文、selected/current节点路径与类型、相关display/render输出、已知状态、可安全取得的几何选择类型/数量、采集时间、fresh/stale/partial/unavailable、截断数量。

几何选择不能可靠无求值读取时标unknown并允许任务中显式查询。多pane列候选，无法确认焦点就focus_unknown。选择是定位信息，不扩大foreign修改授权。

### 资源与失败策略

- 默认不遍历全图、不调用geometry/cook、不解包几何、不抓屏、不渲染。基础metadata与重型观察分离。
- 初始预算：模型摘要约2K字符、至多16个选中节点明细，更多给总数与截断说明；这是待实测调整的工程预算，不截掉唯一目标身份或错误状态。
- 主线程执行目标为轻量毫秒级；Host初始等待上限2秒，排队超时返回带原因的缺失/旧摘要。超时不终止用户任务、不留下后来反复采集的无主队列工作项。记录采集耗时。
- Snapshot不可用不影响概念问答；需要现场目标的mutation通过正常工具路径重新确认，不能凭缺失状态推断空场景。
- 用户数据如节点名/注释作为不可信数据序列化，不拼成系统指令；不混入其他session节点授权或私有消息。

**验收**：空场景、无选择、多选择、边/面选择、双pane、headless、播放、重cook/队列忙、Bridge断开、取消、HIP切换、目标删除、两会话并发。每例验证无场景/旗标/选择/frame改变、无geometry求值；同一状态不产生无穷快照，改变后不会继续声称fresh。

## 六、W2：接口发现、事务与结果反馈

### W2.1 node_info与参数表达式

- 明确`parm_filter`现有字面子串语义，保留兼容；增加总参数数/匹配数/筛选方式，零匹配给一条无过滤重查建议。含`|`等常见误用时指出可能误当regex，不悄悄改变现有含义。
- 需要多词时提供显式词列表或匹配模式，schema在实施时定稿；不得一个字段同时靠猜测解释字面/regex。
- type不可见时明确可用发现路径；card已返回visible=false后build仍安全拒绝。
- 数值tuple预检与标量表达式行为对齐：第一版优先精确拒绝含表达式的tuple并指向组件名/显式表达式写法，避免运行到HOM深层才报错。若增加组件表达式支持，纳入严格参数快照恢复，不隐式改变菜单/字符串语义。
- `list_parms`/build返回提供稳定最小字段例子，减少模型猜dict/list和字段名。

### W2.2 事务状态

- 保留build_module的小模块检查与新增节点清理、外层exec整体undo语义；不因追求效率允许吞异常或隐式部分提交。
- 回包在最前列最终事务结果：committed/rolled_back/rollback_failed/no_scene_change，以及本请求journal中受影响节点的可确认存在状态。名称仅作展示，判断基于identity/现有provenance。
- ledger内动词执行成功与最终事务持久状态分别表达。回滚后先前成功的build不能作为当前依赖证据。
- 存活节点摘要只查本请求相关identity，不全图扫描，不按parent/path清理foreign。状态无法确认写unknown。
- skill指导一个exec对应一个独立推进步骤；不改成每个节点一次调用，也不禁止已知小操作合理batch。

### W2.3 返回体积

- 保持完整原始审计数据和UI可取详情；默认模型文本只给关键结果、失败原因、最终状态、证据范围、media及下一步定位信息。
- 抑制stdout、__result__、ledger中重复的完整spec/VEX/大目录；成功构建优先给路径、数量、output和检查，失败保留具体错误字段/节点。
- 详细原始内容通过已有公开详情/读取渠道按需访问，不把截断对象伪装成完整JSON；先验证当前DSH能否区分存储和模型文本，再选适配层，不修改未知宿主内部字段。
- 本次audit解析器依赖现有文本前缀，新结果格式必须同时升级规范化层、HTML和client，并继续读旧trace。

**验收**：复现#11过滤失败、#17诊断异常回滚、#22多模块后项失败、#27引用撤回输出、#65内部检查失败。紧凑格式必须保留所有关键失败/恢复/media信息；对固定fixture统计文本缩减作为收益，不用少报错误换长度。新旧trace统计一致、replay仍去重。

## 七、W3：节点操作知识与构造方法

### 单一维护源

建立小型、随包的节点操作契约资源（建议`houdini/node-operation-contracts.json`），由helper读取并通过node_info的usage_notes/knowledge_refs暴露；将已有Boolean说明纳入同源。每条含类型族、版本/上下文、输入语义、坐标约定、危险默认、适用/不适用、构建后观测、官方来源和本机验证状态。

固定机器可读facts由此维护；SOP reference维护多节点组合方法和决策，不复制整份节点卡。具体官方参数值仅在双版本复现后定稿。

### 首批范围

| 类型/方法 | 必须传达 | 反例 |
|---|---|---|
| Sweep | input0路径、input1截面；默认原点附近XY平面/+Y up，法向Z；路径frame、是否封端；普通圆管可用内置截面 | 非XY但显式预旋转、自定义ribbon不应被强改圆管 |
| PolyExtrude | front为挤出后、back为原始面、side为桥接；相对世界上下取决于方向；开放面厚化应明确保留哪些面 | 闭合体局部挤出保留原面可能生成内部面，不统一强开outputback |
| Revolve | 周向closed与端口封盖不同；轮廓半径/轴向、profile端点与拓扑 | 有意开放花瓶/管口不得自动封闭 |
| Copy to Points | 原型局部轴、P/orient/scale及优先级、实例身份/属性传播 | packed/native primitive不能只依赖P比较 |
| Blast/组选择 | point/primitive/edge class必须匹配输入语义 | 一条polyline包含多点但只有一个primitive，不能把点号当面号 |
| 表达式边界 | HScript参数表达式、VEX代码和Python分别适用的ch函数/返回形状 | 不把所有字符串都当表达式，不误改菜单token |

### 何时送达

- 当前模块准备阶段用node_info获取该类型简短操作卡；一条卡只回答会改变构造决策的知识。
- build_module静态预检对可确定的错误前置拒绝；对缺乏意图的风险给可解释提示，不假设所有Sweep必须为管、所有曲面必须闭合。
- 构造需要的数据观测在明确cook之后执行，不能为读卡暗中构建scratch或求值重型上游。
- 不每次重发全部卡；首次出现或节点版本变化时提供，错误时只引用对应条目与实际证据。

**验收**：每条双版本最小正例＋反例；修复必须改变构造或诊断结果，不仅检查提示词中出现某句话。Sweep默认XY与显式旋转对照、PolyExtrude两种意图、Revolve封口与开放意图、Blast点/面类型均有确定性结果。官方在线H22说明不能单独替代H21复现。

## 八、W4：几何观察与可靠判据

优先扩展geo_piece_stats、geo_check_interfaces和test_controls的底层能力；API细节在W2的返回约定上定稿。观测结果统一含output/frame/坐标空间/方法/选择范围/覆盖率/容差单位/限制，unknown和unsupported不得作pass。

### 首批实现

1. **部件身份与拓扑**：支持现有part选择及稳定piece id；区分名称分组与真实连通分量。Polygon输出提供边界边/环、非流形、零面积统计，明确覆盖上限；超预算不抽样后声称闭合。原生/packed保留类型语义或unsupported，不为检测强制解包用户输出。
2. **局部截面与形状观测**：明确输入平面、局部basis与横向extent；对直杆/指定截面测两个横向维度，避免以世界bbox证明非退化。曲线路径没有可靠frame时不自动猜。可先支持有界平面/直杆检查，复杂截面返回需要的额外输入。
3. **局部表面变化**：test_controls增加适用的表面位移/目标区域高度或剖面量测；同拓扑点位移需先验证稳定点对应，拓扑变化不得继续按点号做差。面积继续复用现有指标；native primitive沿用完整几何/适当intrinsic，不退化成P-only。
4. **关系方法选择**：保留接口最近距离的原意；距离结果不命名为插入深度。接地按每个要求的足部覆盖；对称用实际对应或有界全量镜像几何距离；无穿插必须声明部件对和实际方法，不能由一项轴向bbox推出全部。
5. **插入/包含的有限支持**：首版优先已知平面/板层、明确轴与稳定端面等可独立验证的情况，给有符号投影范围＋横向包含检查；任意实体插入需可靠闭合/朝向和点内外/表面方法，开放几何或不可判定保留unverified。近期不实现万能CSG认证，也不通过放大距离容差替代该缺口。

### 控制测试语义

- 每个代表性case声明响应、需保持的不变量、适用参数域和恢复要求；测量来自最终输出。
- 尽量复用interfaces/topology/domain机制；本轮新增几何观测的可声明不变量进入同一测试执行/恢复窗口，不允许随意Python回调。
- 根据依赖选择少量case，不要求23项穷举；报告实际覆盖的控制和未测范围。数量参数验证确切件数/身份，形变参数选择局部形状指标。
- 预期值在运行前确定。修正测试错误要保留旧结果、独立理由，并用未参与调阈值的样本或解析关系复核。没有独立依据只报告观察到的响应。
- 恢复参数/keys/frame及完整bgeo语义检查；恢复失败停后续case，保留失败状态，不用重新保存掩盖。

**防假绿用例**：一条腿接地其余悬空、两侧bbox对称但内部缺件、近但分離/正确接触/穿过/过深插入、bbox不变但碟形改变、点数增加却件数错误、默认关系通过但扰动脱开、packed仅transform变化、拓扑改变后点号错配、恢复失败。各case只有对应方法支持时允许pass。

## 九、W5：针对性视觉观察

### render_view增强

- 在显式交付SOP基础上支持受限part/group目标与目标bbox取景，返回目标覆盖/尺度、相机方向、投影、隔离方式和像素状态；不存在/空目标失败，不能回退整物冒充特写。
- 复用持久agent render服务，通过proxy/临时内部展示实现隔离，不改用户几何/选择/display。用户明确要观察屏幕时才用viewport_screenshot。
- 提供少量诊断展示模式：中性实体、部件区分、可选边线；展示颜色覆盖只作用proxy，并明确原Cd/材质是否被覆盖。
- 支持明确正交观察和固定相机的参数A/B；固定相机依据基准/测试包络，而不是每次自动重新居中。动画仍遵守framing_frame；相同framing_frame不自动保证跨参数构图固定。
- 先完成group特写、正交和固定构图；剖切/透明可作为同包后续扩展，只有上述视图仍无法解答已确认问题才增加，不默认每资产拍全套。

### 观察流程

每张图绑定一个问题、一个部件范围和可见目标：整体轮廓、轨端是否开口、连接是否悬空等。先检查file/pixel，再请求模型定位异常和不确定项；具体故障必要时用几何方法复核。图片访问成功、模型正确识别、最终质量通过三层分别记录。

**验收材料**：少量带已知缺陷的视图对，包括轨端开口、座面错位、Sweep退化、缺一重复件；再加入有意开放曲面/合法简化反例。保留同一几何下旧整图与新目标图的对照、盲读结果和误报，不把提示中告诉缺陷位置当检出能力。确定性像素测试与真实模型读图分别报告；若视觉模型仍漏检，由几何检测承担对应完成门。

## 十、W6：工作流、提示词和审计收敛

### SOP工作流

重写既有SKILL.md的执行脊柱，不追加第二套长协议：现场快照→任务关键选择→相关方法→粗模→单模块与相邻关系循环→代表性扰动→有目的视觉→交付。普通任务用几句假设即可，质量敏感任务才展开reference。

- 首个模块优先验证世界位置、主要尺寸、应有的表面/截面；这些未过不加装饰。
- 原型通过再复制；重复件有稳定identity，分支输出先明确part/属性class，减少后补清理。
- 表面方法按表示选择，不一律Boolean、封口或套完整榫接合同。
- 骨架/模块/关系门绑定观测对象与方法；基础cook门与语义门不同。检查只重做受影响范围。
- 一次构建失败先读事务最终状态和实际依赖；同边界两次失败换最小诊断，不连续全文重建。
- 参数控制先表达用户需要及派生关系，后添加次要控制；独立min/max不声称组合域全部有效。

### 提示词与维护位置

- preset负责身份、观察驱动的建模习惯、选择与诚实交付；guidance只保留工具生命周期/安全边界和路由。
- 节点卡负责单节点操作事实；SOP reference负责组合方法；trace patterns负责问题历史。
- 保留现有6skills，更新SOP与trace，不新建每节点skill，不触动governance自身政策。
- 删除相互重复的长合同要求；保留简单编辑快路径、无参考假设、原生节点与VEX合理边界、非视觉交付边界。
- 不默认委派；具体疑点可选review。艺术判断仍需参考与可见证据，无法由数值门认证。

### trace审计

- 新增effective preset/persona/skill/card曝光记录、自动context来源及新鲜度。
- 事务持久状态与动词执行计数分离；删除/替换后已不存在的旧输出不无限记unresolved。
- 添加工具延迟、模型请求间隙、返回字符、首次正确模块/首次有效视图等指标，保留使用率分层与replay去重。
- 增加方法不蕴含标签、测试后改阈值、只测response未测invariant、detail名与实际取景不符等可复核索引；静态规则只提供索引，不声称自动裁判艺术质量。
- known-pattern的“已修”拆成工具实现/曝光/采用/行为再现状态，新增复发证据，避免把加规则写成问题消失。

**验收**：结构audit、资源注册/打包、简单编辑反例、原失败局部实例、一个未见同族多模块任务、一个相邻领域任务。严格区分技术verified与自然行为released。

## 十一、测试、收益评估与发布

### 分层验证

1. 每包做最窄、能暴露因果链的确定性测试；新增功能有正例、故障、边界和恢复用例，不为文案改字写镜像测试。
2. `npm test`完成生成/tsc和全部Node回归；HOM变更至少跑AGENTS指定raw-gate、node-ownership、caught-failure、tab-create-failure、object-parenting、scene/network/render contract，加该包相关suites。
3. 发布前H21/H22都跑受影响Python回归及必跑安全集；UI上下文/渲染恢复要有GUI实测，headless不能代替。
4. `audit-houdini-skills.mjs --strict`、资源/引用检查、`npm pack --dry-run`验证包内文件。
5. 定向旧失败复现优先用最小几何，不让用户再花89分钟重建原椅子。
6. 真实模型第一轮限定为一个未见同族资产、简单编辑和相邻任务反例；所有用例在执行前固定检查意图，agent只收到原始需求。相邻/简单任务可短执行，不强制完整建模。
7. 结果表必须包含检出的真实缺陷、漏检、误报、用户纠正、参数关系、恢复、首次正确模块时间、失败/回滚、观测成本和总耗时。固定模型/provider/版本/任务条件，比较才有意义。
8. 椅子旧trace带cordis与现状配置混杂，只能作故障基线，不能与新Houdini preset任务直接声称严格A/B提速。若需要量化归因，用隔离配置重跑小而可比的流程片段，不默认启动整批benchmark。

### 合格条件

- 已知确定性接口/状态错误能被预防或准确恢复；无新增安全回归。
- 关键几何缺陷能被适用方法检出，反例不被强制改坏；不支持时诚实保留范围。
- 用户要求的控制有代表性响应及关系证据，不能只凭bbox/计数交付所有参数域。
- 图像为实际问题提供可辨认信息，图片缺失/裁切/识别不确定不升级为通过。
- 简单任务没有长合同、成批probe或无需求渲染；新增context/card/检查的成本有记录。
- 技术测试通过但新session/GUI/行为未验的包保持candidate或verified，不能写released。

### 发布与回滚

- 建议先完成W0–W2作为第一批稳定性增量，W3–W6作为第二批建模能力增量；中间只做必要smoke，最终W7统一现场验收，避免每小改就重启live。
- `docs/tool-design.md`仍为动词目录唯一来源；参数/返回/语义变化同步该文档并由现有生成器刷新generated contract/client目录，禁止手改lib/生成区。
- 记录已验证的agent surface和compatibility surface；W1涉及Host/Bridge接口，双方契约一起更新；不能只换Python或只改prompt。是否提升执行契约版本由schema/语义变更决定，不能以名字hash未变当兼容。
- 部署重启安排在用户任务结束的可控时点，通过Repair and restart runtime执行；保留当前HIP与用户未保存状态，不能自动load/clear。
- 新session验证真实请求含有效preset、自动快照、对应卡/skill版本，实际query/exec/render/Trace串联通过。
- 每包记录可回退增量；回退源码、生成物、相应部署组合后重启，保留用户HIP/session/渲染服务。上下文/展示增强可独立停用，安全检查和ownership不可为兼容临时关闭。
- 更新development/相关诊断文档只记录真实完成项、命令、版本与未覆盖边界；baseline变更不重置冻结矩阵或解封holdout。

## 十二、交付清单与续跑方式

实施交付包含：自动现场摘要与有效配置诊断；改进的节点发现/表达式提示/事务结果/紧凑返回；首批操作卡与双版本方法fixture；适用几何观测与控制不变量；目标取景与视觉故障材料；精简后的SOP/preset/guidance；兼容新旧trace的审计；测试与发布记录。

每个工作包在本计划或关联实施记录中维护四项：当前完成文件、已执行验证、剩余失败/未知、下一条可直接执行的动作。状态只用planned/in_progress/verified/released/blocked，并解释证据。若发现新问题，先判所属包与用户目标相关性，不自动扩大到无关域。

**第一条实施动作**：记录当前WIP基线与实际runtime配置，复现三条会话创建路径，查清有效preset；随后沿公开systemPrompt.context接口实现无cook的最小现场摘要，并以空场景/多选择/Bridge忙三例打通Host→Bridge主线程→模型快照链路。

### 来源

- 本地源码：scene_info/node_info/describe/render_view、build_module/verify_network、test_controls/interfaces、Host工具formatter、launcher、skill注册。
- 本地DSH system-prompt README：公开动态context服务、作用域、快照及前缀缓存边界；serving版本实施时再核对。
- SideFX [Sweep 2.0](https://www.sidefx.com/docs/houdini/nodes/sop/sweep.html)：截面平面/输入/frame约定。
- SideFX [PolyExtrude](https://www.sidefx.com/docs/houdini/nodes/sop/polyextrude.html)：front/back/side语义。
- SideFX [Copy/instance attributes](https://www.sidefx.com/docs/houdini/copy/instanceattrs.html)：实例属性与变换语义。
- 仓库houdini-skill-governance：唯一维护位置、版本/反例验证、候选与发布区分；只将抽象规律进入生产知识。


## 2026-09-07 双模型复盘追加包（v13源码候选）

已接入：菜单规范set_value、Merge接线快照、输出短名一致、逐壳方向观察、真实表面截面取样、
有界线性参数域、图片能力路由提示与SOP小幅替换。反例与验证见development v13条目。
仍未完成：一般自交/嵌套壳与真实实体接触/穿透求解、自动约束UI/钳制、广义镜像几何判定、
新模型任务的自然采用/品质/效率验收。普通建模不新增审批/默认委派，不扩展冻结benchmark。
