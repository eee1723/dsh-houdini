# 执行契约 v2：修复、review 与验收边界

> 本文为逐代历史记录。当前v9已退役delivery生产状态流程，保留底层检查器并接入独立
> 资产评审；现行合同见[独立评审](independent-asset-review.md)与[工具设计](tool-design.md)。

> 本文前半保留v2/v3历史；当前源码为v4/57动词，见末节。已有版本曝光不等于新候选已发布。

2026-09-05；用户授权按三任务复盘推进修复，同时 review 代码风险。状态：源码候选，非 live release。

## 本轮设计决策

优先降低弱模型需要自行处理的技术判断和错误成功判定，不增加对象专用配方。新增四个意图：
`scene_save_as`、`node_info`、`build_module`、`verify_network`，共 54 动词。Host 工具仍为五个。
新增 SOP 组合层独立在 `dsh_sop_contracts.py`，通过原有 primitive helpers 执行，Host 不调用 HOM。
没有重写 DSH、MCP adapter、通用规划器或任务持久状态机。

SOP skill 为 UPDATE：替换执行步骤中的探测/构建/检查指引，并在现有 sop-patterns reference
追加受限 fast path。未改 rig/Solaris 路由、governance 核心规则或用户的模型/provider 配置。

## 发现与修复

| 风险 | 修正 | 确定性证据 |
|---|---|---|
| 批量参数部分失败仍被视作成功 | set_parms 默认 strict；名称/重叠/锁定预检，失败恢复值/表达式/keys；单项失败同样恢复。显式 strict=False 返回 ok/failed 并显示 checks 警示 | 新 execution-contract 回归；原 trace 有24次部分失败 |
| 菜单 token、label、表达式混淆 | node_info 在实际 parent context 提供类型、端口、组件、静态 menu/default；list_parms 提供动态菜单。Menu 字符串只接受 token，显式表达式对象可保留菜单动画 | H21/H22 actual Wrangle/Box 菜单与表达式回归 |
| HIP setName 被误映射为节点 rename | 单一 Raw Gate 分类与精确 HIP 提示；新增受路径/当前HIP/reason/overwrite约束的 Save As；不放开 raw load/clear | 原失败 #8/#10/#11；新 save-as/拒绝覆盖回归 |
| basename=untitled 即认定未保存 | scene_info 结合磁盘文件存在，clean_on_disk 需实际文件；可正常保存名为 untitled.hip 的合法工程 | saved-untitled 回归 |
| OUT 无警告冒充整网健康 | verify_network 汇总所有直属 SOP 或明确选定模块，列出 scope、error/warning、非空输出、frame/time/fingerprint；semantic 固定 unverified | 上游 Merge warning 被下游 null 隐藏的反例 |
| Python 长 batch 缺少可靠模块边界 | build_module 静态预检 1..64 个新增 SOP，复用 Tab/strict参数，cook失败清理本批新节点；不覆盖既有节点/显示状态 | dry_run零创建、缺参/重复名/坏VEX、headless失败清理 |
| connect 失败改接其他口 | 精确端口语义，失败不使用 setNextInput；布局异常不再进入重接线分支 | invalid input零接线副作用 |
| tab_create 输入可旁路 OBJ parenting，失败留节点 | Object inputs 拒绝，端口预检；初始化/命名/连接失败清理新节点及provenance | parenting旁路与旧 shelf failure 回归 |
| 无pump时HTTP线程运行HOM | run_code/start/pump拥有线程检查，worker _execute 无pump拒绝；stop唤醒/作废排队工作；不能挂起到下一次启动再执行 | worker与HTTP线程反例 |
| 被拦截请求继承上次图片 | 在锁内先清空produced-images，完成时锁内抓取本次快照 | blocked request不含旧images |
| ledger达上限后静默无追踪执行 | 超限拒绝并记录可被caught-failure守卫识别的失败，不再调用未追踪动词 | 捕获超限异常也不能返回成功 |
| running job被cancel后丢掉真实结果 | 只取消queued；running保持running/返回说明，保存真正done/failed结果；派发异常转failed | cancellation与pump error回归 |
| job无限排队/持锁网络写阻塞 | active jobs上限32，校验和登记同锁；响应使用锁外快照 | 饱和429、status/cancel回归 |
| 本机执行端口接受浏览器简单跨站POST、异常length | 只接受无Origin的application/json，拒绝非对象/非法length/transfer encoding/错误read_only；拒绝时关闭未读请求 | 本机HTTP 403/400/413反例 |
| 名称指纹不识别语义变化，30秒缓存接受旧runtime | 文档独立execution contract version=2，生成器与Bridge一致测试；每次health检查，无共享AbortSignal缓存，请求expected_contract二次守卫 | Node假服务器同名旧语义立即拒绝 + HTTP409 |
| transport超时提示诱发盲重试 | POST错误明确“可能已排队/执行/生效，先回读” | Host错误路径review；不声称能中断HOM |
| 抽样指纹却全量生成P列表，图片转百万Python RGB元组 | P最多257个点按索引读；Qt像素惰性读取；PNG按字节行保留，像素/文件/解压尺寸上限，拒绝不支持Adam7 | image diagnostics与既有render合同 |
| 图像有文件就pass | render_check.presentation 明示非黑bbox过小/触边/无内容；仅needs_review，不冒充分割或语义评分 | 黑图/触边/同图diff回归 |
| compact evidence丢代码、结构化用户选择未入合同 | 分析保留完整code/result，序列化才隐藏；只吸收已选option；mixed edit+probe保留；显式骨架render作为可观察checkpoint | full/compact真trace一致、未选option反例 |

## 验证

- H21.0.440 与 H22.0.368：各17个 Python 回归文件通过，包括三个新文件
  `dsh-execution-contract.test.py`、`dsh-bridge-transport.test.py`、`dsh-image-diagnostics.test.py`，
  以及 raw-gate/ownership/caught-failure/tab-failure/object-parenting/scene-network-render/layout/
  KineFX/color、launcher/manager/profile/runtime/web-auth。
- Node suite：构建和全部16个确定性测试文件；增加语义版本漂移、checks展示、结构化choice/
  mixed probe/non-enumerable分析数据等回归。
- 五skill治理严格审计无issues/warnings；SOP quick_validate（一次性 uv/PyYAML、UTF-8环境）、
  npm pack --dry-run及Python compileall均通过。打包包含新的dsh_sop_contracts模块。
- 增补真实HTTP→队列→Houdini主线程→JSON只读链路，以及stop作废旧队列的双版本回归；模块
  恢复实际display/render旗标，不用可能回退到display的renderNode()冒充原render flag。
- 原K3 trace重新提取：137 tool / 663 verb不变；partialParameterFailures=24；full/compact
  qualityLoopEvidence完全一致。LOD/骨架/关系“未做”误报修正；reference/simplifications缺项保留。
  探针检测不证明探针正确，也不重新为旧任务打艺术质量分。

## 不应夸大的保证

1. 原HIP、用户测试模型和运行中Bridge未修改/重启。新入口需 Repair and restart runtime 后新session
   验证；baseline.runtimeVerification仍false，历史verifiedAt/旧runtime字段不代表v2。
2. Save As文件I/O、参数回调、任意SOP代码外部副作用都不属undo/参数快照保证。失败可能留下
   部分新文件；缺省禁止覆盖，不能把自动清空文件当“恢复”。
3. build_module只新建SOP、不修改既有网络；dry_run是静态预检，不验证VEX、动态菜单或cook。
   正常构建可返回warning，需要调用者处理；不支持一口气创建无限网络或跨域setup。
4. verify_network默认直属范围，不递归穿透每个HDA；超过预算拒绝而非抽样假绿。
   指纹是有界P样本+统计，不证明全部拓扑/材质相等。Python成功、cook健康、关系和视觉仍分层。
5. HTTP只做本机可信客户端的请求边界，不是完整鉴权或恶意Python沙箱。主线程执行不能强制中断，
   无法对单次HOM cook承诺硬超时；不应把运行中job改成cancelled。
6. 新SOP fast path的工具行为已验证，弱模型未见任务质量增益仍candidate；未宣称优于MCP。

## 下一阶段及退出边界

先用新session确认语义v2/54动词、Save As、SOP module、warning回读和图像实际检查。确认无误后，
同K3/同宿主/同预算对比旧工作流与新模块路径，先已知失败、再未见同族与领域内反例。
下一步再设计少数绑定实际part/坐标系的关系检查、场景变更驱动的证据失效；不以本轮小模块工具
冒充完成了整个自主质量闭环。MCP adapter和跨模型等条件实验仍是后续阶段。

本轮不解封holdout、不改写v5冻结协议/六场pending矩阵，不为每个确定性修复运行收费大矩阵。
回退按本轮文件diff逐项恢复到之前已验证版本，并重新生成目录/构建；不得覆盖用户原有改动、
删除持久render service或把运行中场景作为试验品。

## 2026-09-06：test7反馈后的 v3 候选

### 已证问题与本轮落实

K3 `a28410c5…` 的v2加载已由54目录、新工具行为和只读health确认；不是部署失败。实际
89工具/19失败，build_module零采用；六次verify检查CONTROLS或空output0，明示未通过后仍
进入交付。相对picture写到进程cwd而非HIP；无后缀render的check解码失败被顶层成功盖住。
独立备份回读进一步检出有序点列中的异常短间距和无效控制。

本轮变更：

1. **显式checkpoint**：verify_network必须给output，无display fallback；empty/error默认抛
   CheckpointError，Bridge保留失败的结构化证据。require_valid=False只用于诊断。返回
   failure_reasons/next_action以及范围hash，不能靠不同输出或范围的成功自动抹掉旧失败。
   warnings仍需解释，不一律硬异常；这里未实现全局禁止最终回答的agent状态机。
2. **渲染路径**：共享path resolver先展开目标帧变量，裸文件名锚HIP/render或cache ROP的HIP/geo，
   相对子路径锚HIP；无扩展名、相对逃逸和插件仓库路径拒绝。显式绝对路径保留调用者意图。
   ROP临时路径/前台参数的表达式、keys及frame恢复，避免跟随引用修改其他参数。
3. **渲染结果**：file/pixel/semantic独立状态；PNG等像素解码错误进入errors和ok=false，
   EXR等不支持像素检查的格式保持unverified，不能混同失败的展示PNG。restore错误不能冒充成功。
4. **证据摘要**：Bridge生成operation-evidence，在长stdout前展示完整路径、frame、范围、失败
   原因和关键像素指标；不依赖模型额外print正确字段。normalized parser按ledgerIndex+verb合并
   摘要，维持Python执行与检查结果分层，并保留传统ledger格式兼容。
5. **构建易用性**：connect/tab_create对different_parent提前报两端网络与Object Merge/subnet
   替代路径，不让模型试端口。build_module支持None输入空槽（Wrangle input 1属性源）和静态
   menu预检；SOP skill主入口提供最小spec形状。未添加任意跨网络连线或无界建图能力。
6. **全量序列检查**：新增geo_point_spacing（第55动词），扫描所有有序相邻点，包括可选闭环；
   默认point number或唯一数值order attribute，统计全量min/max/failure_count，返回最多16个
   最差对。超预算拒绝而非采样。它只证明局部坐标的弦长，不能冒充弧长、真实链板啮合/碰撞。
7. **审计修正**：数字明确为假设/非核实规格不再误报外部真实性；新结构化输出检查失败单列为
   unresolved_output_checkpoints，只有同output/scope的后续成功才能消除该观察。诊断性probe
   是否属于交付，仍需人工结合合同，不将自动risk当艺术评分。

### 验证结果

- H21.0.440/H22.0.368各18个Python回归通过，包含新增dsh-output-checkpoint：省略/空输出
  拒绝及诊断反例、合法Object Merge路径、稀疏输入、静态menu失败零创建、局部异常/闭环序列
  检查、查询模式、摘要保留、路径/后缀/目录逃逸、真实Geometry ROP输出与参数恢复。
- 原交付备份在隔离H21中只读复验：111个相邻对，预期12.7mm/容差0.5mm，检出一个失败对
  26→27（2.8355mm）；与上轮独立检查一致。显式OUT几何通过且warning保留。文件SHA256前后不变。
- Node回归覆盖operation-evidence即使ledger截断仍恢复路径/frame/失败状态、摘要前置、同范围
  checkpoint失败恢复和假设边界。构建生成55目录与语义v3；全量npm test的16个文件通过。
- 五skill严格治理审计0 issues/0 warnings；SOP quick_validate通过；Python compileall、diff检查通过。
- npm pack --dry-run确认新SOP合同模块与skill/reference包含在包中。candidate agent surface
  `ca804a05…`、compatibility surface `d0056d05…`，runtimeVerification保持false；没有重封v5协议。

### 发布与未覆盖边界

工具合同是双版本本地验证，SOP工作流仍candidate，未自动重启用户runtime或修改自行车HIP。
live v3的GUI render/semantic smoke、新K3会话自然采用及未见任务质量增益尚未证明。
用户模型中的具体链条、hub_width和接地问题未直接修；本轮修的是通用检测/执行路径。
自动控制扰动审计、受限spare参数删除、绑定最终交付的持久证据失效状态机仍是后续工作，
不以本轮新增一个测量动词宣称全部质量闭环完成。holdout、v5 frozen matrix与provider配置未动。

## 2026-09-06：模块接口与控制契约 v4 候选

### 授权、证据与分层

用户要求继续推进质量主线。输入为test8实际结构反例、两个无效控制、原生Tube的P-only审计
假阳性，以及前几轮构建/验收经验；不直接修改用户模型，也不复制对象配方进生产面。
SOP skill为UPDATE，治理/rig/Solaris保持不变。新逻辑放入`dsh_quality_contracts.py`，
由原有helpers/Bridge调用，Node Host不触碰HOM。

v4新增两个动词，合计57：

- `geo_check_interfaces`：在同一实际输出里，命名point group必须属于最终Polygon/Mesh表面，
  对方为独立primitive group；每个声明点到指定表面距离都须满足容差和基数。空组、基数不符、
  重叠自证不通过；游离driver点和不支持的primitive保持unverified。最大查询对数/几何点面/
  序列化内存均有预算，不做抽样假绿。仅证明接口接近，不证明所有表面相交/包含/机械强度。
- `test_controls`：exec内按声明case改变数值组件，验证具体输出primitive group的预期尺寸/
  位置/计数/面积delta，可同时检查接口；默认接口不通过时不做参数写入。每case至少一项非零
  响应，值被钳制未应用则fail；每次恢复参数/表达式/keys/frame，核对实际输出bgeo恢复。
  只支持Polygon/Mesh/Sphere/Tube及点几何；Packed序列化有recook变化，控制测试写前unverified。
  不允许menu/button/callback/multiparm/tuple整体写入，foreign需单次明确授权，service不豁免。
- `build_module(..., interfaces=...)`在构建完成后的实际输出运行接口合同；fail/unverified
  会使本批新增模块失败并清理新节点，既有图/flags保持原边界，dry_run仍只校验声明。

### 反例推动的收敛

1. 默认BoundingBox不是空累加器，原点会污染远处部件的局部尺寸/中心；指标改从首个实际
   primitive开始，空group不退回全图。
2. P不变不代表原生Tube半径不变；使用实际primitive bounds/area度量和bgeo恢复证据。
3. Packed内容看似恢复而序列化不同，原始hash尚不构成可靠oracle，因此保持unsupported，
   不以放宽hash比较或只看bbox伪造“已恢复”。
4. 控制测试全部只检查不变量会把死控制判成功，因此每case要求至少一个排除0的响应区间。
   这不是对所有参数组合的证明；独立参数是否有效仍需独立case。
5. 失败诊断不禁止保存草稿/部分交付；未引入全局阻断final answer的agent状态机。

### 验证与真实文件复核

新`dsh-quality-contracts.test.py`覆盖：连接正例、同方向但脱开、默认通过而扰动失败、缺组/
基数/自重叠/游离driver点/unsupported surface、预算、局部指标、空group、死控制、原生Tube、
Packed写前unverified、表达式恢复、perturbed cook失败、注入恢复错误、ownership/service/query边界
和build失败清理。H21.0.440/H22.0.368完整矩阵各19/19通过；Packed写前unverified、空group、
至少一项非零响应、恢复异常等补充反例又分别在双版本追加通过。Node全量16文件、五skill严格审计、
SOP quick_validate（临时uv/PyYAML、UTF-8环境）、compileall、diff检查均通过；npm pack --dry-run
确认新quality模块和module-quality-contracts reference包含在包中。

test8在独立H21中只读加载，两个控制测试正确判fork_travel/crank_len不响应，bb_shell_d改变
原生Tube直径则通过，全部恢复且源文件SHA256不变。另对真实OUT冻结副本仅添加诊断group，
P/primitive数量不改；按原外管端部表面12点对实际前轴Tube检查，12点全部超过1mm，最近约
22.1mm，确认工具能检出已有错误。这是针对选定接口的反例验证，不是整件碰撞距离或模型修复。
私有工程的节点名/尺寸没有进入通用skill或回归fixture。

本轮candidate agent surface为`b8f09154…`，compatibility surface为`b2fa33d1…`，目录hash
`e632778a1cc6…`；baseline.runtimeVerification仍false。几何bgeo hash只在同一进程/同次
测试中作恢复对照，不声称跨会话的稳定资产标识。

### 后续门与未覆盖项

当前是本地双版本工具verified、SOP工作流candidate。尚未自动重启live、未跑新K3未见任务，
不能声称质量接近强模型。用户现有自行车未修；也未实现自动识别所有接口、通用约束求解器、
完整碰撞/包含验证、自动生成全部控制case、视觉艺术评分或全局证据失效状态机。
下一轮只需验证：模型能否主动声明正确接口/响应、检出错误后修生成器并复验，再用未见同族
与不应触发的反例检查泛化；不解封holdout、不立即扩张大评测矩阵。v5协议与provider配置不变。

## 2026-09-06 test9 后调整：执行v5安全窄修，交付原型不发布

test9 `d5ce091d…`已加载v4，19次build_module、11次verify_network、零最终warning；
但geo_check_interfaces/test_controls均0次，新模块reference未读。最终胎齿断线、两个dead
controls及局部拓扑/连接错误仍未阻止“产品级完成”。不能把v4工具回归写成自然质量增益。

确定性风险：`connect(src,dst,0,5)`把5绑定到allow_foreign，而index仍为0。现connect与
disconnect_input权限理由keyword-only，所有_require_owned入口在任何快路径前校验显式
理由为非空字符串；数字/布尔/容器/空白不得转换为权限。名称仍57，执行合同升5并由生成器
同步Host，用语义握手阻止新旧混用；live没有自动重启。

Node16、H21/H22各21项Python回归通过；新权限测试验证错误位置参数零改线、foreign拒绝、
合法显式keyword和持久服务不可豁免。当前agent surface `90832b70…`，compatibility
`6b6c45ce…`；baseline仍为未release候选，不修改冻结正式protocol/matrix/holdout。

同时建立非生产离线原型`tools/prototypes/delivery_audit.py`：从实际OUT核对必交组，枚举
全部数值spare控制，复用现有接口/控制检查，观测状态变化时保守失效全部旧控制证据。
通用Box例完成失败→局部修正→复验；test9在H21/H22隔离内存补一条原有接线后，最终胎齿
0→1584面，控制旧证据失效，重测两项仍fail；其余17项未声明用例保持unverified，源HIP
SHA不变。该fixture是开发诊断材料，不打包、不注入skill，不算完整自行车验收。

原型尚未接生产Host、持久会话或自动契约生成/自主纠正，数值pass始终保留语义未验证；
详细范围、限制、复现和停止条件见[可信交付原型](trusted-delivery-prototype.md)。不要求用户
再跑整辆自行车来验证一个模型尚不可用的离线状态层。

## 2026-09-06 v6：受限Host/Bridge接入候选

v5的health与keyword-only签名已由用户和独立只读health确认加载。本轮不是重复v5曝光验收，
而是增加原型的受限生产入口：仍5工具/57动词，houdini_exec的delivery参数与code/allow_raw
互斥，Host冻结session合同/缓存证据，Bridge的typed `/delivery`在主线程观察与测试。
观察核心迁入dsh_delivery.py，旧离线adapter复用它，重启launcher同步reload新增模块。

Host跟踪修改请求和job代际，观察到变化则丢弃旧证据；runtime/HIP load/clear/path重新绑定。
query不接受typed mutation入口，另一个session不能继承证据或经register获得外来控制权限。
当前仅原生无副作用SOP/Polygon、128直属节点/15000点/10000面，VEX/Python/file/solver/
subnet/外部依赖拒绝；没有自动修模或全局final-answer拦截。数值pass保持语义unverified。

Node17、H21/H22各22项回归包括真实Node工具→HTTP→main-thread→Host合并通过；小原生
装配例验证dead control、局部修正、丢件和证据失效，不代表K3自然任务验收。
当前agent surface `88a3c709…`、compatibility `e98e2e67…`，目录仍`e632778a…`；baseline
runtimeVerification仍false，冻结formal protocol/matrix/holdout未动。未重启用户live v6、
未修改test9；下一步只跑原生小任务采用smoke，操作/边界见[运行时入口](trusted-delivery-runtime.md)。

## 2026-09-06 test10反馈后v7：支持策略前置与参数域

用户授权继续修复。最新c7bf5c01第8步明确尝试delivery.inspect，被boolean::2.0拒绝；不能
归因为“模型未采用”，也不能把底层test_controls的3case成功当成Host闭环已验收。
v7仍5工具/57动词：准入Boolean，node_info/build_module预检共享运行时类型策略并说明
类型准入不等于实际参数/依赖/输出已验证；Boolean卡片区分输入选择组与输出部件标识。

可选domain比较复用一套quality层实现：当前基准与实际扰动值检查，独立无key候选可以零写入
拒绝；表达式/动画耦合不靠覆盖一个字典猜其余变量，而是赋值后检查并恢复。仅lt/le/gt/ge/
eq/ne标量比较，无表达式eval、求解或自动钳制；不推导整个域的形状正确性。

新增dsh-delivery-domain回归，并在真实Node→HTTP→主线程测试中覆盖Boolean、跨客户端
改参使证据失效、域失败与必交部件消失。原始test10的7节点HIP在隔离H21/H22复用：
inspect成功，3控制case通过；厚7/高6失败、vertical组空；恢复后unverified，复验后数值
pass；无效候选test值零写入拒绝。原HIP sha始终9a487f34…，没有保存或重建源资产。
开发fixture放不打包的tools/prototypes，未携带进preset/领域skill。

Node17文件、双版本各23项回归通过；skill治理前后5项均0 issue。根据governance执行一次
UPDATE窄修：仅把module-quality-contracts reference的bounds_size/center/min/max改成
精确枚举，与helper docstring、错误信息、inspect元数据一致。来源是c7bf5c01 #9/#10与
实际参数校验代码、双版本执行；属于确定性API说明纠正，不新增路由/长流程/支架配方。
原主skill触发、复杂度门、停止和反例未改变；自然弱模型行为门仍pending，不标released。
回滚该reference说明不影响执行器，但不应重新引入已知缩写歧义。

候选agent surface `36813ec9…`，compatibility `d9694d8f…`，执行语义v7；正式冻结
protocol/matrix/holdout未改，runtimeVerification仍false。未自动重启live v7，未声明
K3已自然完成登记/失效/复验或质量接近强模型。无需用户再造自行车；当前修复先以既有资产
和定向回归关闭，操作边界见[运行时说明](trusted-delivery-runtime.md)。

## 2026-09-06 v8：表示匹配、证据复用与恢复指纹

e8c90d2b已真实完成v7按提示登记/失效/复验，但55calls中有接口方法误选和全量失效开销。
本轮仍5工具/57动词：可选topology在实际输出上检查已声明部件组的共享Polygon边连通/
闭合/非流形/绕向，基准与控制扰动均查；独立表面仍用interfaces。inspect提供当前数据的
方法候选，Host记录contract_changes及复用/失效case IDs，不能删除连接义务后冒充完整验收。

数值证据复用仅对Bridge识别出的受限AST查询/展示整理且执行/检查成功的路径启用，仍需
重新核对runtime/HIP、身份、图/参数/几何。未知Python、失败检查/恢复、setter、job仍失效，
独立activity代际防止并发观察交错。不是Raw Gate豁免，不接受agent自报无副作用。
e8原始轨迹有render参数失败，该失败在v8也仍失效；不虚构全部重复测试都会被省掉。

回归期间发现原bgeo字节恢复判据会跨秒误报：捕获两份数据，逐字段差异仅顶层info.date。
读取本机SideFX hjson和Geometry.data API说明后，改为对完整bgeo解码负载哈希，只排除
此导出时间戳。其余字段、原生primitive形状、用户date属性、拓扑/group均保留。未知格式/
预算超限拒绝，Packed等unsupported边界不变，真实恢复错误注入仍阻断；没有降为P-only。

验证：Node17、H21.0.440/H22.0.368各25项；补充退化边用例后双版本定向再过。真实Node→
HTTP→主线程→Host测试覆盖保存/布局/查询复用、未知代码/实际改参/外部客户端失效、合同
义务变更和跨session边界。旧test2.hip以临时副本回放，四控制通过后连续三类成功整理操作
每次复用四项，零额外控制调用；真正改参仍撤销并重测，连接义务在收据中。源sha63f833de…
不变。OpenGL使用替身验证分类策略，未做live GUI渲染复用，不把它写成已验证画面。

按houdini-skill-governance进行UPDATE：主SOP替换一处方法路由，canonical module-quality
reference说明融合/独立表面边界及bgeo导出时间戳；无新skill、无对象配方、无参数答案。
证据来自e8轨迹及独立接触/融合/断开/开放/原生quadric反例和双版本测试；技术合同verified，
未见弱模型行为仍candidate，未released。治理前后5skills/5registrations/0issues。
如回滚须整体回到旧契约代际并同步生成器/Host，不能仅恢复丢连接义务或过度全量失效的文案。

当前agent surface4ddf94d5…，compatibility9fe334d6…，执行v8/目录e632778a…；baseline
runtimeVerification=false，冻结formal protocol/matrix/holdout未动。未重启live或改原HIP。
此接入阶段收口，不再要求用户重做同题。后续以正常未见任务中的验证成本/质量衡量，详细
边界见[运行时说明](trusted-delivery-runtime.md)。
