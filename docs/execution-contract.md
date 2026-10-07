# 执行与证据契约

本页维护工具链真实执行条件和返回事实的含义。用户目标、任务策略及领域方法见对应 [skills](../skills/)；公开工具、动词签名和执行版本见[工具设计](tool-design.md)。系统提供准确操作与反馈，模型决定方法及完成质量。

实现入口：[Bridge](../houdini/python3.11libs/dsh_bridge.py)、[执行内核](../houdini/python3.11libs/dsh_execution.py)、[执行结果](../houdini/python3.11libs/dsh_execution_results.py)、[helpers](../houdini/python3.11libs/dsh_hou_helpers.py)。

## DSH 与工具职责

DSH 提供模型、会话、通用 Agent 循环、提示词组合、压缩和原生工具能力。插件只注册一个 Houdini preset，并通过 [DSH 适配](../src/dsh-adapter.ts)和原生 context producer 提供 Houdini 事实。领域计划没有执行准入条件；生产工具没有产品要求账本或作者自报完成登记。

| 工具 | 执行范围 |
|---|---|
| houdini_exec | 在目标 Houdini 主线程执行修改或验证批次 |
| houdini_inspect | 只读 Python 与现场查询；不准备编辑 Undo 和创建登记 |
| houdini_job_submit/status/cancel | 提交长任务、等待实际状态、取消尚未运行的任务 |
| houdini_request | 查回原 request_ref 的接收/执行回执，不重发代码 |
| houdini_resource | 在 Host 读取用户来源或已保留结果的分页正文 |
| houdini_capabilities | 返回当前模型与附件通道的声明能力 |

[工具运行层](../src/tool-runtime.ts)负责身份、执行端路由和图像附件；[资源读取](../src/tool-query.ts)只消费历史材料。结果正文或来源不成为新的现场观察、授权或任务指令。DSH 已有的文件、终端、网络与会话工具按其原生职责使用。

## 主线程、执行端与归属

所有 HOM 调用经 Bridge 主线程队列串行执行。HTTP 线程只接收、排队和等候回包；泵不可用时拒绝，不退回网络线程执行。GUI 线程不得进行阻塞 socket、进程枚举或 netstat 探测。

执行端、会话和调用分别具有不同身份：executor ID 确定目标进程，owner_session 确定当前作者，owner_call 定位单次调用。身份来自 Host 与执行端登记，模型不自行填写。Bridge 在场景执行前核对目标与执行合同；错目标或版本不一致返回明确错误，不自动重启 live。

首次现场操作前，绑定记录通过 DSH 会话持久化确认；普通上下文组装承担消息插入，工具执行期不在 assistant 工具调用与结果之间插入消息。既有执行历史指定了目标时，不能把同一任务的代码或 job 发送到另一个执行端。回执和材料读取不构成重新绑定。

节点 ownership 来自 runtime 创建的 identity 和会话归属；路径、父网络、节点名称及可复制 userdata 都不授权。foreign 节点可以读和作为输入。单次写入仅在用户明确指定目标时使用非空 allow_foreign，不能形成长期所有权。持久 render 服务永不豁免；删除容器前检查其后代权限。HDA库权限与实例分开；整体销毁旧实例的replace拒绝，分叉只产生独立新类型和库。

## 查询、修改与 Raw Gate

inspect 使用只读 namespace 与同一 Python 语法分析结果；exec 提供修改能力。动词是主要修改接口，裸 hou 适用于只读查询及尚无对应动词的低层缺口。Raw Gate 默认开启；已覆盖的 create/set/cook/delete 等操作不能用 allow_raw 旁路。参数对象、tuple、绑定修改方法和HIP生命周期别名同样检查；Python set方法豁免只用于可确定为set且未重绑定的接收者。

低层逃生舱只接受单次明确用途；不隐式放开整段已覆盖修改。静态分析服务正常模型调用，不是任意 Python 沙箱。已观察的非终止 VEX 删除循环写前拒绝；其他 VEX 仍由原生编译与计算反馈判断。

每次请求解析一次 Python 语法树，分类、准入和执行证据共用结果。动词签名绑定失败返回实际 signature、dispatched=false 和 scene_writes=0；内部 TypeError 保留原始原因。零写入只说明该次未派发调用，不能抵消同批此前修改。

原生 OBJ parent/unparent 使用 set_object_parent，普通 connect/disconnect 表达数据流。set_object_parent 的 reason 是可选自由用途说明；任务可选择 OBJ、KineFX 或其他适用表示，执行层不强制建模方法。

## 事务、错误与长任务

exec 的未处理异常使批次失败并恢复 Houdini 可撤销状态。动词异常被代码捕获后仍记录失败；修改失败且恢复未确认时，同一 exec 后续修改、cook、渲染及保存在派发前停止，只读诊断可以继续。此类修复在新批次提交；零写入或已确认恢复的失败按实际回执处理，避免把半成品误报为成功。

结果投影的 `outcome` 分开报告批次完成/失败、动词异常次数和实际返回的验证状态。捕获只读查询错误后使用合法fallback，可保留批次成功与返回数据，但模型和Trace必须显示子操作失败。已被动词确认恢复、零写入的失败不冒充未恢复修改；既有mutation阻断规则仍按实际恢复事实判断。验证未通过、操作抛异常、传输未知分别表达，不合成为任务是否完成。

读取 transaction 的最终状态：同批后项失败可能撤销前面成功的构建。headless 没有原生 Undo 时，不报告已完成整批回滚；动词内部清理和实际 rollback.applied 分别返回。补充清理只处理本调用准确登记的新 identity，foreign 后代不自动删除。Undo 复活节点后的原生初始化后代只按本批已登记删除身份、原生类型和存活祖先重新对账，不能认领旧作者节点。

文件写入、HDA 库和任意 Python/solver/外部进程副作用不属于场景 Undo 保证。参数与界面动词的内部恢复范围由各自结果说明；已成功的外部文件写入不会因后续批次失败而声称撤销。

长任务仍在同一主线程串行执行，不提供并发 HOM。queued 任务可在代码运行前取消；running 任务的取消依赖原生协作检查点，不能强杀用户进程。jobId 来自实际提交结果，状态/等待/取消只接受所属会话；后台提交成功不等于计算完成。

HTTP 请求使用一次性 request_ref。断联、超时或坏回包后先通过 houdini_request 读取原请求状态；缺回执表示未知，不能据此认定零执行。查回 jobId 只证明提交，后续仍读取 job 状态。运行实例改变或回执过期保留未知，不自动重复修改。

调用日志完整记录实际动词，不以日志条数拒绝批量操作。大结果在 Host 保留并通过 resource 分页读取；模型正文优先返回显式选择的结果、检查与恢复事实，完整 canonical 仍供 Trace 和历史投影使用。重复帮助、已呈现的动词结果和稳定身份清单可用明确详情指针表示；未知诊断、失败与恢复异常不因体积大而静默丢弃。归档失败时保留完整反馈，显示精简不改变执行事实。

## 事实、上下文与观察

每次执行返回 runtime_id、sequence、observed_at、frame、HIP 路径和实际影响记录。节点 identity 与运行实例共同解释；同路径重新创建的节点不是原节点。影响观察来自原生输出和最近计算可见依赖，truncated/unavailable/global 直接保留，不推断未列出的依赖不存在。

[execution-history](../src/execution-history.ts)统一关联公开调用、结果与回执；[execution-state](../src/execution-state.ts)的完整观察保留最近失败，动态上下文只携带未决请求、活动 job 及原结果不可取得的恢复事实。已送达的普通同步错误留在原工具结果，后续成功不再触发整份现场快照重发；无关观察的sequence、时间和路径也不改变未决提醒。几何检查和任务质量判断保留在原结果中，Host 不建立第二套完成状态解释器。开发评测中的 [delivery-audit](../tools/delivery-audit.mjs)只读取历史，生产上下文不注入评测完成门。

[scene-context](../src/scene-context.ts)为每条收到的用户消息采集一次轻量元数据，帮助解释“这个节点”“选中对象”“当前场景”等现场指代。切换视角、网络、选择或 frame 不把新现场绑定到旧消息；当前状态需要显式 inspect。选择是指代线索，不是修改授权。

[context](../src/context.ts)通过 DSH 原生 context section 提供现场、待决执行和声明图像能力；通用历史压缩、消息更新和 token 管理由 DSH 完成。没有另一个可写任务账本或自建 surface 压缩器。

图像能力取当前模型 route 与附件服务元数据；houdini_capabilities 可显式查询。它不请求模型、不渲染、不自动换模型。文件传输、GUI 启动、图像显示及模型实际语义识图分别判断；没有成功内容级识图就保持视觉未验证。

## 类型、参数与网络操作

node_info 读取实际 parent 下的类型、端口和参数模板，不创建 scratch。真实 Tab/Shelf 初始化与静态默认值分别报告；操作卡关键参数保持可读。节点知识只有 [node-operation-contracts.json](../houdini/node-operation-contracts.json)一个来源，不从缺字段自动推导设计缺口。

`verb_help(name)` 默认返回标注brief的真实签名、执行入口、返回类型和简短用途；`detail='full'`取得完整说明及已维护的结构契约。批量名称遵循同一规则。`node_info`要求现有创建网络，返回请求名称与解析后的实际类型；未知类型只提供真实可见名称候选，不自动替换为猜测的建模方法。

严格设参拒绝未知字段、非法菜单和不相符值形状。菜单使用真实 token/set_value；标量及单独组件接受有限数值、HScript 字符串或显式 expression/language；多分量 tuple 接受等长数值列表，表达式写组件名。multiparm 先设置 count 再写实例字段。

静态参数卡、批量预检与实时设参以原生模板维数为准，分量名称推导缺失不能把多分量误判成标量。内置BeginEnd、StartEnd、MinMax、MaxMin等命名按目标版本真实HOM回读验证；参数错误同时指出实际解析的节点类型，避免将旧版本参数用于新节点。

写入与求值分别报告。合法 0 不算失败；明确新参数诊断、非有限求值或实际写入失败恢复本调用参数及 keys。旧缓存或无法归属的诊断保留 warning/unverified，随后可显式 cook 检查修复。参数求值成功不证明几何响应正确。

read_parms(names=[...])读取明确字段，string 返回 source_sha256。字符串 patch 使用原文 expected_sha256、old/new 与精确 count，锚点不匹配时本批参数写前拒绝；它只做 literal replace，不执行脚本或正则。set_parms 的 patch 继续 strict，写后失败恢复本批值/keys。

connect 返回原生接线，None 保留空槽；subnet 间接输入不猜成普通 Node。disconnect 后输入可能压缩，后续读取 inputs_after。跨 subnet 使用 Object Merge 或明确端口，不猜输出口。delete/rename 返回实际影响，不因同名新节点推断引用恢复。

## SOP 批量构建与检查

[SOP contracts](../houdini/python3.11libs/dsh_sop_contracts.py)负责批量新增、静态检查、计算和清理。build_module 接受非空节点声明列表；inputs 可引用任意声明或现有直属 child。先创建全部节点，再连线和设参，声明顺序自由，表达式也可引用本批任意节点。None 保留空槽；不覆盖既有节点或输出旗标。

dry_run 只检查真实类型、参数和引用，独立静态错误汇总返回；不证明表达式、VEX 或计算结果。没有固定节点数量和 required_outputs 数量上限。实际构建显式指定新 output；required_outputs 和 interfaces 仅在调用方声明时检查。失败清理本批新节点并保留原错误。

verify_network 必须明确 output，默认拒绝 empty/error，require_valid=False 只作诊断。检查返回所选范围的 cook、非空、几何概要、显示/公共出口和单位事实，不按 OUT_ASSET 等名称追加领域检查。limit 是调用方声明的观察范围，不对任务网络大小设另一层硬上限。

Manual 模式不触发 geometry/camera/render 求值，不把缓存当作新鲜结果；需要计算时显式切换更新模式。失败 cook 后不经 geometry() 隐式重算。warning、计算成功和语义正确分别报告。

SOP subnet/HDA 的公共输出用 sop_set_output 发布原生 Output；普通 geo 只需明确最终 SOP 和 display/render。output_index 指定时检查真实公共接线，不自动猜祖先、调整 OBJ 可见性或保存定义。嵌入 Packed 的包装点/面不算实际内容；外部 Packed 或无法展开的表示保持 unverified。

## 几何、关系与控制

[geometry observation](../houdini/python3.11libs/dsh_geometry_observation.py)及 [quality contracts](../houdini/python3.11libs/dsh_quality_contracts.py)量测实际输出。作者按问题选择指标和关系；没有声明的关系不自动加入完成门。

| 观察 | 实际范围 |
|---|---|
| Polygon inspect/integrity | 指定输出/组的边界、连通、非流形、朝向、局部退化和条件性壳体积；不证明任意自交或艺术质量 |
| center-axis surface hits | bbox中心轴与实际平面多边形边界的交点，覆盖凹面；非平面估算及共面射线保留unverified，不以扇形覆盖空洞证明表面存在 |
| planar face crossings | 单个近似平面 Polygon 非相邻边的严格内部交叉；不外推三维面间自交 |
| attrib unique / point spacing | 精确属性唯一性或显式有序点相邻弦长；不替代容差焊接或曲面接触 |
| named surface / section proximity | 声明实际表面及截面的距离与部件覆盖；不证明连续全表面关系 |
| axis_gap | 实际 primitive 组的轴向投影间隙及横向重叠 |
| solid_overlap | 完整闭合朝外 Polygon 操作数的实际 Boolean 交集体积；零交集不证明轴穿孔或接触 |
| axis_passage / bore_clearance | 显式轴线或声明区间、半径的空域；不从整件 bbox 推断孔径或板厚 |
| component_count / physical_extent | 声明最终组的连通件数或经 HIP 单位换算的轴向尺寸；组身份仍由作者核对 |
| stable-ID displacement/transform | 相同 Polygon 拓扑与唯一点 ID 下的位移和仿射残差；driver 点不替代实际成品 |

返回范围、预算和 unsupported/unverified，不能用 bbox、响应非零或无报错冒充实体关系。内嵌 Packed 可在受限副本上展开观察；磁盘/Alembic/Fragment 及超展开预算保持 unverified。

test_controls 必须 exec，声明数字控制、指标/关系和扰动；随后恢复参数值、表达式、keys、frame 及完整 bgeo。顶层 interfaces 适用于基准与所有 case，baseline_interfaces 只验基准，case.interfaces 只验该扰动。具体状态应声明适用关系。

基准计算失败返回 not_run；results=[] 不算通过。恢复前后回读通道和几何，任何不匹配都不能报告 restored=true。外部文件、Python 和 solver 副作用不属恢复保证。单个 case 不外推整个参数域，控制响应非零也不等于设计正确。

测量方法不支持所选表示时，`measurement_failure`指出实际case、判据与选择；area额外给不支持的primitive类型、编号和开闭样本。基准失败零参数写入，所有未执行case仍标not_run；扰动后出现同类问题仍执行原恢复流程。诊断帮助选择适用方法，不自动改变测量指标或把局部支持部分冒充整个选择。

## HDA、界面与节点整理

HDA section 的写后回读/hash 只证明文本写入。PythonModule 语法检查不执行回调；真实按钮、内部函数、计算后的公共输出和新实例依赖分别观察。输入/输出上限不是接线证明；实例 spare 与定义界面分开管理。

section、界面与save/promote复用共享定义写入保护：实际新库/定义的session登记及指纹、全部受影响实例同时检查。自建已有类型实例不授权原共享库；外部改写后的旧登记不继续有效。单次明确allow_foreign不永久认领定义；所有作者写入拒绝$HFS。unlock不授予后代ownership。写后失败恢复本调用定义section、实际变化的实例界面/通道和磁盘库，范围由回执说明；后续exec失败不撤销已经成功的库写入。普通spare追加、定义重建及持续绑定分别使用对应动词，方法见[控制参数与绑定](parameter-controls.md)。

原生工具Package默认JSON直接指向用户确认的唯一资源源目录，不复制或归档；开发前区分工具修改意图与已有包扩展/新包及两个存放位置。创建注册只写全新JSON；旧配置由明确目标的通用文件编辑最小维护，原有条件/依赖/未知字段保留。当前进程load/activate/deactivate/unload不编辑持久enable、不删除配置/源或强清模块缓存。配置文件与实际原生Package/定义分别回读，停用/卸载不能从磁盘文件存在与否推断场景依赖；部分失败保留真实文件、回读错误与加载状态，不承诺撤销任意回调效果。

Network Box、Sticky Note和layout是编辑器presentation mutation，不代表业务或几何质量。节点、Box和Note使用各自identity归属；名字、颜色、成员与自有parent都不授权。Note只局部维护明确对象，不隐式加入Box；已有Note是布局固定障碍。失败补偿和编辑事务恢复保留真实范围。layout默认只处理当前会话节点，持久服务与未选障碍保持固定。详细用法见[跨领域网络交接](../skills/houdini-network-handoff/SKILL.md)。

顶层houdini_ui_screenshot通过Bridge队列依次准备自有原生参数或网络pane、刷新目标绑定、抓图并清理；阶段之间返回正常GUI事件循环绘制，不截桌面、不修改模型参数或借截图保存工程。各阶段共享原请求票据及其完成事实，没有独立捕获登记表，不泵嵌套事件循环，不在同步Python批次内等待UI刷新。返回实际图片/尺寸/状态保持，并沿同源图片附件消费。原生pane注销可延至外层GUI事件循环，cleanup_pending/cleanup_scope与已完成图片分别报告。GUI不可用明确unsupported，捕获/传输与模型识图分别判断。方法在参数UI/网络交接skill，截图不替代参数绑定、输出或界面其他页的测试。

参数截图显示当前参数页，不替用户按按钮或切换业务模式；原生显示可能求值控件现有表达式/动态菜单，任意自定义脚本副作用不属于截图恢复保证。scene_writes=0说明截图接口没有直接设参或保存，不认证未知回调无副作用。

自有临时窗口可能短暂可见，使用无激活显示而非自动切换用户前台。Windows H21/H22都按原生窗口句柄截取，只读这次自有窗口。阶段就绪由外层GUI回调通知：H21使用Qt事件，H22等待原生空闲；回调只设置Event，注册/注销和全部HOM仍在Bridge队列。未初始化的原生GUI可能返回黑/纯色图，此类捕获明确失败，不用文件存在冒充已显示界面。真正用户键鼠、额外字体/主题配置与模型自然采用另行验证。

窗口捕获会读取该窗口所在的屏幕区域，按[Qt接口](https://doc.qt.io/qt-6/qscreen.html#grabWindow)的实际条件要求目标完整在屏内且无遮挡；采样前后核对上方可见窗口，遮挡或出屏明确拒绝，不移除外部窗口或以系统置顶绕开。请求尺寸、实际尺寸与捕获方法均保留在回执，不把窄面板通过外推任意宽度和桌面状态。

## 渲染、构图与保存

[camera framing](../houdini/python3.11libs/dsh_camera_framing.py)按实际透视/正交投影求解。full 完整包络，detail 仅改变二维取景大小。A/B 使用同 framing_frame，并复用覆盖全部状态的 framing_bounds/depth_bounds、方向、画幅和模式；越界不能悄悄移动相机。

near/behind/far_clip 错误在渲染前拒绝；detail 的二维 intentional_crop 与深度错误分开。camera_fit 修改明确相机并保留其焦距合同；预览服务相机不改作正式相机。渲染或像素差异不证明模型外形和关系正确。

render_view(EXPLICIT_SOP)使用持久 __dsh_houdini_* 服务，任务结束复用不删除。服务和预览临时状态独立于作者建模 Undo；图片文件是外部效果。返回 source/framing/pixel/check/artifact 的实际事实，无法解码或旧文件不报新鲜图像。

渲染和缓存相对路径锚 $HIP，必须有后缀。render_view 与 viewport_screenshot 默认将验证图分配到 `$HIP/dsh-visual-checks/<run-id>/`；最终图片可选 delivery，直接分配到 `$HIP/dsh-render/`。两种分配要求已命名 HIP，只接受省略文件名或安全 basename，拒绝可执行表达式，并返回唯一、不覆盖已有文件的实际路径；自定路径选择 explicit。输出位置不证明视觉质量或完成。正式 render_frame/ROP 使用明确的输出目标，用户已有指定路径优先。Save As 只影响后续 capture，不迁移或删除旧图。

viewport screenshot 在成功和失败后恢复视角、相机绑定、frame、selection/flags 等声明状态；异步捕获尚无完成证据时保留未知及本次 reservation。文件、传输、显示和语义识图分别返回；没有模型内容级观察时保持视觉未验证。

scene_save 只写当前明确路径；scene_save_as 需要用户授权的目标、expected_current_path 和用途说明。raw load/clear 不开放。保存回执是当时文件事实，重开检查、可编辑性与最终结果由对应观察确认。

## 验证入口

日常按改动选检查，完整方法见[开发维护](development.md)。执行内核核心回归覆盖 [Raw Gate](../tools/tests/dsh-bridge-raw-gate.test.py)、[节点归属](../tools/tests/dsh-node-ownership.test.py)、[捕获失败](../tools/tests/dsh-bridge-caught-failure.test.py)、[创建清理](../tools/tests/dsh-tab-create-failure.test.py)、[OBJ 父级](../tools/tests/dsh-object-parenting.test.py)和[场景/网络/渲染](../tools/tests/dsh-scene-network-render-contract.test.py)。

批量构建见 [module-preflight](../tools/tests/dsh-module-preflight.test.py)，参数恢复见 [control-state-restoration](../tools/tests/dsh-control-state-restoration.test.py)，请求未知与查回见 [request-recovery](../tools/tests/dsh-request-recovery.test.py)，实际节点知识见 [node-knowledge](../tools/tests/dsh-node-knowledge.test.py)。隔离机制检查不替代用户 live 加载或自然模型任务质量。
