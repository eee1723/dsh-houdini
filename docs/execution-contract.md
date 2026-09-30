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

节点 ownership 来自 runtime 创建的 identity 和会话归属；路径、父网络、节点名称及可复制 userdata 都不授权。foreign 节点可以读和作为输入。单次写入仅在用户明确指定目标时使用非空 allow_foreign，不能形成长期所有权。持久 render 服务永不豁免；删除容器前检查其后代权限，HDA 替换前检查实际待销毁的实例和后代。

## 查询、修改与 Raw Gate

inspect 使用只读 namespace 与同一 Python 语法分析结果；exec 提供修改能力。动词是主要修改接口，裸 hou 适用于只读查询及尚无对应动词的低层缺口。Raw Gate 默认开启；已覆盖的 create/set/cook/delete 等操作不能用 allow_raw 旁路。参数对象、tuple 和绑定 setter 的别名同样检查。

低层逃生舱只接受单次明确用途；不隐式放开整段已覆盖修改。静态分析服务正常模型调用，不是任意 Python 沙箱。已观察的非终止 VEX 删除循环写前拒绝；其他 VEX 仍由原生编译与计算反馈判断。

每次请求解析一次 Python 语法树，分类、准入和执行证据共用结果。动词签名绑定失败返回实际 signature、dispatched=false 和 scene_writes=0；内部 TypeError 保留原始原因。零写入只说明该次未派发调用，不能抵消同批此前修改。

原生 OBJ parent/unparent 使用 set_object_parent，普通 connect/disconnect 表达数据流。set_object_parent 的 reason 是可选自由用途说明；任务可选择 OBJ、KineFX 或其他适用表示，执行层不强制建模方法。

## 事务、错误与长任务

exec 的未处理异常使批次失败并恢复 Houdini 可撤销状态。动词异常被代码捕获后仍记录失败；同一 exec 后续修改、cook、渲染及保存在派发前停止，只读诊断可以继续。修复在新批次提交，避免把半成品误报为成功。

读取 transaction 的最终状态：同批后项失败可能撤销前面成功的构建。headless 没有原生 Undo 时，不报告已完成整批回滚；动词内部清理和实际 rollback.applied 分别返回。补充清理只处理本调用准确登记的新 identity，foreign 后代不自动删除。Undo 复活节点后的原生初始化后代只按本批已登记删除身份、原生类型和存活祖先重新对账，不能认领旧作者节点。

文件写入、HDA 库和任意 Python/solver/外部进程副作用不属于场景 Undo 保证。参数与界面动词的内部恢复范围由各自结果说明；已成功的外部文件写入不会因后续批次失败而声称撤销。

长任务仍在同一主线程串行执行，不提供并发 HOM。queued 任务可在代码运行前取消；running 任务的取消依赖原生协作检查点，不能强杀用户进程。jobId 来自实际提交结果，状态/等待/取消只接受所属会话；后台提交成功不等于计算完成。

HTTP 请求使用一次性 request_ref。断联、超时或坏回包后先通过 houdini_request 读取原请求状态；缺回执表示未知，不能据此认定零执行。查回 jobId 只证明提交，后续仍读取 job 状态。运行实例改变或回执过期保留未知，不自动重复修改。

调用日志完整记录实际动词，不以日志条数拒绝批量操作。大结果可在 Host 保留并通过 resource 分页读取；显示压缩不改变执行事实。

## 事实、上下文与观察

每次执行返回 runtime_id、sequence、observed_at、frame、HIP 路径和实际影响记录。节点 identity 与运行实例共同解释；同路径重新创建的节点不是原节点。影响观察来自原生输出和最近计算可见依赖，truncated/unavailable/global 直接保留，不推断未列出的依赖不存在。

[execution-history](../src/execution-history.ts)统一关联公开调用、结果与回执；[execution-state](../src/execution-state.ts)只投影最近失败、待决请求和活动 job。几何检查和任务质量判断保留在原结果中，Host 不再用第二套完成状态解释器改变它们。开发评测中的 [delivery-audit](../tools/delivery-audit.mjs)只读取历史，生产上下文不注入评测完成门。

[scene-context](../src/scene-context.ts)在用户消息有“这个节点”“选中对象”“当前场景”等现场指代时采集一次元数据；明确路径和普通新建任务不采集环境选择。切换视角、网络、选择或 frame 不把新现场绑定到旧消息；当前状态需要显式 inspect。选择是指代线索，不是修改授权。

[context](../src/context.ts)通过 DSH 原生 context section 提供现场、待决执行和声明图像能力；通用历史压缩、消息更新和 token 管理由 DSH 完成。没有另一个可写任务账本或自建 surface 压缩器。

图像能力取当前模型 route 与附件服务元数据；houdini_capabilities 可显式查询。它不请求模型、不渲染、不自动换模型。文件传输、GUI 启动、图像显示及模型实际语义识图分别判断；没有成功内容级识图就保持视觉未验证。

## 类型、参数与网络操作

node_info 读取实际 parent 下的类型、端口和参数模板，不创建 scratch。真实 Tab/Shelf 初始化与静态默认值分别报告；操作卡关键参数保持可读。节点知识只有 [node-operation-contracts.json](../houdini/node-operation-contracts.json)一个来源，不从缺字段自动推导设计缺口。

严格设参拒绝未知字段、非法菜单和不相符值形状。菜单使用真实 token/set_value；标量及单独组件接受有限数值、HScript 字符串或显式 expression/language；多分量 tuple 接受等长数值列表，表达式写组件名。multiparm 先设置 count 再写实例字段。

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

## HDA、界面与节点整理

HDA section 的写后回读/hash 只证明文本写入。PythonModule 语法检查不执行回调；真实按钮、内部函数、计算后的公共输出和新实例依赖分别观察。输入/输出上限不是接线证明；实例 spare 与定义界面分开管理。

界面重建与 hda_edit 的预览检查真实共享定义和实例状态；unlock 不授予后代 ownership。写后失败恢复本调用定义 section、实例界面/通道和磁盘库，范围由回执说明；后续 exec 失败不撤销已经成功的库写入。普通 spare 追加、定义重建及持续绑定分别使用对应动词，方法见[控制参数与绑定](parameter-controls.md)。

Network Box 和 layout 是编辑器 presentation mutation，不代表模型几何质量。节点与 Box 使用各自 identity registry；名字、颜色、成员与自有 parent 都不授权。显式两阶段计划绑定实际成员、接线、位置和障碍；应用只移动授权对象，失败恢复声明状态。layout 默认只处理当前会话节点，持久服务与未选障碍保持固定。详细用法见[网络整理](../skills/houdini-sop-workflow/references/network-handoff.md)。

## 渲染、构图与保存

[camera framing](../houdini/python3.11libs/dsh_camera_framing.py)按实际透视/正交投影求解。full 完整包络，detail 仅改变二维取景大小。A/B 使用同 framing_frame，并复用覆盖全部状态的 framing_bounds/depth_bounds、方向、画幅和模式；越界不能悄悄移动相机。

near/behind/far_clip 错误在渲染前拒绝；detail 的二维 intentional_crop 与深度错误分开。camera_fit 修改明确相机并保留其焦距合同；预览服务相机不改作正式相机。渲染或像素差异不证明模型外形和关系正确。

render_view(EXPLICIT_SOP)使用持久 __dsh_houdini_* 服务，任务结束复用不删除。服务和预览临时状态独立于作者建模 Undo；图片文件是外部效果。返回 source/framing/pixel/check/artifact 的实际事实，无法解码或旧文件不报新鲜图像。

渲染和缓存相对路径锚 $HIP，必须有后缀。render_view 与 viewport_screenshot 默认分配 `$HIP/dsh-visual-checks/<run-id>/` 唯一文件；managed 要求已命名 HIP，路径值选择 explicit。Save As 只影响后续 capture，不迁移或删除旧图。

viewport screenshot 在成功和失败后恢复视角、相机绑定、frame、selection/flags 等声明状态；异步捕获尚无完成证据时保留未知及本次 reservation。文件、传输、显示和语义识图分别返回；没有模型内容级观察时保持视觉未验证。

scene_save 只写当前明确路径；scene_save_as 需要用户授权的目标、expected_current_path 和用途说明。raw load/clear 不开放。保存回执是当时文件事实，重开检查、可编辑性与最终结果由对应观察确认。

## 验证入口

日常按改动选检查，完整方法见[开发维护](development.md)。执行内核核心回归覆盖 [Raw Gate](../tools/tests/dsh-bridge-raw-gate.test.py)、[节点归属](../tools/tests/dsh-node-ownership.test.py)、[捕获失败](../tools/tests/dsh-bridge-caught-failure.test.py)、[创建清理](../tools/tests/dsh-tab-create-failure.test.py)、[OBJ 父级](../tools/tests/dsh-object-parenting.test.py)和[场景/网络/渲染](../tools/tests/dsh-scene-network-render-contract.test.py)。

批量构建见 [module-preflight](../tools/tests/dsh-module-preflight.test.py)，参数恢复见 [control-state-restoration](../tools/tests/dsh-control-state-restoration.test.py)，请求未知与查回见 [request-recovery](../tools/tests/dsh-request-recovery.test.py)，实际节点知识见 [node-knowledge](../tools/tests/dsh-node-knowledge.test.py)。隔离机制检查不替代用户 live 加载或自然模型任务质量。
