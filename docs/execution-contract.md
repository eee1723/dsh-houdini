# 执行与证据契约

共享参数控制的职责和推进顺序见[控制参数、界面与绑定](parameter-controls.md)。UI追加、HDA定义重建和持续绑定是独立修改：
create_spare_parms(layout)只追加单节点参数；bind_controls必须预览并核对源/目标状态计划，实际写入仍检查目标ownership。
旧动画/表达式默认保护，显式替换不扩大foreign授权。绑定回读只证明表达式及当前数值，领域输出需独立验证；
界面/绑定恢复仅覆盖声明的通道/模板范围，不恢复任意回调、文件、solver或外部进程副作用。

实现入口：[Bridge](../houdini/python3.11libs/dsh_bridge.py)、[helpers](../houdini/python3.11libs/dsh_hou_helpers.py)。
调用签名与版本以[工具设计](tool-design.md)及运行时verb_help为准；本页只维护跨动词边界。

## 安全与权限

启动器提供进程级executor ID，Host可由agent作用域配置executorId覆盖；每个请求携带目标头，Bridge先核对
再进入HTTP路由。错目标返回409，不排队/控制job/读媒体；相同端口与相同工具版本不证明相同Houdini。
该ID与Bridge runtime代际及节点ownership分离；缺少绑定的独立旧客户端仅兼容，不具备此保护。
配置覆盖属于宿主路由，不是模型自行认领执行端的接口，也不是本机恶意客户端认证机制。
canonical执行历史含executor_id时，工具入口禁止把原任务的代码/job操作发往不同或未绑定执行端；
回放结果、材料及回执查询不构成重新绑定。无身份的旧历史保留兼容但不推断目标，完整恢复授权入口尚未开放。
绑定Host首次现场调用前必须将目标作为plugin来源消息追加到DSH会话，并等待sessions.flush确认持久化监听器参与；
无后端/落盘失败/取消均不提交现场请求。并发首调用共享屏障，已追加未落盘的记录不删除、不重建第二份绑定文件。
普通任务通过agent/pre-step的正常消息批次接受绑定，工具执行阶段只能等待已有绑定落盘，不能在assistant工具调用与
尚未返回的tool结果之间插入user消息。插件须显式声明sessions依赖，不能用可选链绕过Cordis注入边界。
旧版自身绑定插入造成的顺序错误，只能对结果齐全、纯文本且无其他用户介入的完整工具交换追加摘要投影修正；
原始事件/结果/绑定保留，不伪造tool结果、不执行工具。缺结果、混合媒体或无关交错拒绝自动修正；修正落盘失败仍阻止下个模型请求。

- hou仅在Houdini主线程调用；HTTP线程只排队。泵不可用即拒绝，不退回网络线程执行。
- query使用只读namespace与AST预检；exec负责修改，job负责长操作。Raw Gate默认开启，
  已有动词覆盖的裸修改不能用allow_raw旁路；parameter/tuple及其set方法的词法赋值别名同样拒绝。
  同批重绑定保守处理；静态识别不等于任意Python的完整沙箱。仅独立、无动词等价的低层缺口允许单次明确理由。
- query的result_ref分支只读当前workspace中已返回的历史结果；source_ref只读当前session公开日志中的任务来源，
  两者不进入Bridge/HOM；request_ref只查Bridge同runtime回执、不执行HOM。四分支与code互斥，source_ref不接受JSON pointer或跨session路径，
  不能当现场新观察或ownership授权。新查询、修改和任务产物仍遵守原边界。
- ownership是runtime创建identity与session provenance，不是路径、父网络、名称或可复制userdata。
  foreign可读/作输入，不等于可写；单次allow_foreign必须绑定用户明确目标与非空授权说明。
  持久render服务不可豁免，layout默认仅本session节点。
- delete_node删除容器前检查全部后代权限；hda_create替换先检查全部实例/后代且拒绝销毁重建源的祖先，
  再开始删除。不能依赖Undo补救尚未完成的权限预检。
- 原生OBJ parent/unparent使用set_object_parent并说明reason；generic connect/disconnect只管数据流。
- loopback并不鉴别所有本地进程。AST和ownership面向正常agent，不是恶意Python安全沙箱。
  不应向不可信网络暴露Bridge。

## 事务与异步

exec异常恢复Houdini可撤销状态；捕获动词异常不重新抛出会被caught-failure机制拦截。
同一exec已有失败动词后，后续修改、cook、渲染和保存动词在派发前拒绝，记录零写入证据；
只读诊断仍可运行，修复须在新exec提交。此前文件写入和任意Python外部副作用不属undo保证。
消费transaction最终状态：后项失败可能撤销同exec中前面成功的build，不能沿用已回滚节点。
失败补充清理仅限本调用journal的确切新建identity；foreign后代不自动删除。
可独立cook和验收的模块使用不同exec，集成引用已提交且仍存活的输出；不可分模块内仍批量原子执行。
独立query失败不撤销此前exec；同exec尾部只读错误仍使整批失败，不按异常类型猜测部分提交。
动词派发前做实际签名绑定，argument_binding失败附signature、dispatched=false与scene_writes=0；
该证据只覆盖未派发的当前调用，不能抵消同exec此前的修改。函数内部TypeError仍保留原始原因。
每个Bridge执行返回execution.runtime_id/sequence/observed_at/frame及hip_path/hip_dir和本次影响观察；
hip_dir仅在场景有命名路径时提供，Host直接投影工作区提醒，不为展示再次执行HOM。运行实例与节点
identity共同解释，路径不充当identity。影响包含有界原生outputs和上次cook可见的dependents，删除/改名
前观察后代，最多256身份；truncated/unavailable/global必须保留，动态/外部依赖和用户GUI修改不在覆盖内。
last_edit_ledger_index可识别同调用内检查之后的修改；outputs将检查条目绑定到末态节点identity/存活状态。
这些记录用于让旧证据失效，不证明未列出的依赖不存在，也不证明下一请求时场景未变。

Host的scene-context只在用户消息有“这个节点/HDA”“选中对象”“当前场景”等现场指代时采集一次；
明确节点路径和普通解释/新建任务不采集环境选择。文本匹配只是保守指代提示，未匹配时仍可显式查询。
选择不等于任务目标或修改授权，用户运行中切换选择、网络、视角和帧不会刷新或触发注入；
重启Host后只能复用旧消息原快照，不能把重启时的现场重新绑定到旧消息。

Host的execution-state从公开tool事件重建，独立于用户消息绑定的scene-context：按runtime/sequence
去重与排序，保留最近观察、删除、失败、in-flight/未知执行和有限检查范围。运行时或观察到的HIP路径改变不复活旧identity，
已回滚检查不作当前通过；已记录依赖变化或同调用后续修改使旧检查stale。非stale仍只是历史观察，
不能认证当前live状态或赋予foreign权限。没有第二份可写任务账本，不自动改写用户原始指代。
普通成功/失败回包由工具结果直接表达，不再按时间戳、执行序号、计数或节点清单追加摘要。
自动提醒仅投影未决修改请求、已记录检查失效及观测到的runtime/HIP身份变化；状态解除只表示
历史记录不再含该提醒，不证明场景通过。后台任务提交/完成由原工具结果表达，恢复摘要保留仍在运行的job。
各补充段经agent/pre-step作为独立、可审计的plugin消息加入；按公开session surface中保留的同名正文去重，
不进入Host整包runtime context，不因执行提醒重发权限或场景快照。拒绝/取消/未提交不消耗补充消息。
对话历史surface替换后可恢复一次有界执行事实和来源；仅缩短单条tool/result不触发整份恢复，
普通工具调用不持续重建恢复消息。

Host的task-sources只从source.kind=user消息和已关联的ask_user_question问答建立来源锚；
注入上下文、自动goal续接和作者自述不提升为用户要求，缺source的历史消息不猜测为用户原文。
原始消息、澄清答案和目标变化不触发额外全文副本；历史surface替换后的恢复可提供首条与最近来源的有限摘录，
遗漏数和截断显式报告，目标始终标为作者计划。普通步骤仍可按需回读来源。
source_ref=index列出可用来源，来源hash分页回读完整文本；非文本仅保留类型标记，不声称读取了图片。
作用域仅当前session可见的公开日志，不保证被裁除的历史仍存在；不存在的来源明确拒绝而不替换成摘要。
goal/change只标为报告的计划状态，不覆盖原文或证明完成；来源顺序也不推导用户是否替代旧任务。
复杂任务的需求/默认/未知、模块依赖风险及续接摘要由preset约定维护，Host不建另一份可写需求库，
不强制简单编辑建表。来源可回读和提示注入不等于模型已采纳或最终provider输入保留已验证。
SOP聚焦模块流程复用现有计划和工具事实，方法在[模块合同](../skills/houdini-sop-workflow/references/module-quality-contracts.md#模块聚焦与交接)。
局部检查与最终输出成员/实际实例关系分别验证；此工作流没有新增Host自动调度、模块通过证书或多作者权限。

job仍通过同一主线程队列串行执行。排队取消可阻止执行；已开始的代码不能强杀，
客户端超时/取消不能保证场景未改。重试前检查job结果和实际场景。
HIP保存、render/cache和HDA库等外部I/O不属于undo保证，失败要单独报告外部副作用。
Host经POST /requests/prepare取得带owner的单次票和当前合同，不额外增加握手往返。exec的request_ref在进入主线程队列前消费并登记，
查回走固定只读/requests/status端点，不触发HOM或重新排队。签票不意味着已提交代码，也不进入HOM队列。
同runtime同身份同payload只返回原状态/结果；payload或owner不符拒绝，不更新原请求。状态not_executed
仅在Registry同锁确认仍queued时报告，不能将running降级；断联、结果过期、换runtime和查不到回执均不等于未执行。
结果正文与终结记录有界轮转，不保留无限墓碑；旧票离开待用票池后不能因回执被淘汰而重新执行。仍活动请求不可淘汰。
Host超时/取消后仍可能存在活动Bridge请求；health/Repair用Registry活动槽观察补足这一边界，缺字段不当空闲。
回执丢失/过期时需显式观察实际场景再决定下一步，不自动生成新request_ref重做原修改。
查回带retrieved标记，原执行sequence保留；执行状态投影解除已查明的unknown，离线动词核算不重复计数。
jobs提交复用同runtime回执但以job_submit类型单独绑定payload；查回jobId只解除提交未知，job仍可能排队/
运行中。活动job的关联保持到worker终态；worker先结束、后记录admission的顺序同样可释放保护，避免永久占槽。
terminal job不能被迟到的提交回执重置为排队。队列取消、过载拒绝和worker启动失败保持原执行边界。
Host历史已保留done/not_executed/job_submitted回执时，迟到的非终态或Bridge保留期结束不将同一引用降级为未知；
未查回过结果的过期引用仍保持不确定。该规则不把job提交当作执行完成，也不认证当前场景。
request_ref='index'仅列当前owner最多32条回执，优先活动请求/job关联，再列最近终结记录，以owner_call对齐原调用；无代码/结果正文，
不能用索引中缺记录自行授权重提。独立执行统计按canonical runtime/sequence去重，传输轮询仍计工具调用；
只有历史文本或没有序号的结果明确未测，不猜执行身份。

## 参数与创建

普通set_parm(s)在快照/写入前拒绝Data参数，内嵌Geometry等需其原生初始化流程，不能进入数字恢复。
新建HDA同步展开延迟定义后登记其初始化后代；后续用户加入的子节点不因父级owned而获得身份。
delete_node返回受影响消费者与原生删除后的接线；重新创建同名节点不证明恢复了引用、连线或控制关系。

COP观察/关系/控制动词必须exec，经同一Bridge主线程编组；直接读取ImageLayer而非Geometry代理。
Manual、失败cook、非图层、预算超限明确拒绝；统计完整buffer但不限制上游GPU cook内存，不隐式抽样。
层间差值必须相同通道/窗口/空间/帧，公式与操作数随结果保留；未声明预期只量测，不认证语义。
控制实验复用通道恢复并核对frame、完整buffer及已列元数据；sticky Cache不能认证控制/恢复，
恢复失败抛CheckpointError并使执行影响保持未知。外部文件/Python/solver状态不在恢复保证内。
具名connect只验证实际边与端口选择；动态undef签名由原生连线求解。USD Material COP对原生预检假阴性
仅允许两端具体图层类型完全相同的连线，并回读实际端口；不隐式转换通道，cook/类型通过仍不证明角色正确。
COP缓存依赖检查保留全部原生input/reference路径，入队去重；上限4096节点、32768条边、两秒检查预算，
超限拒绝并保留新鲜度未知，不截断冒充通过。预算在原生调用之间检查，不承诺中断阻塞HOM或限制GPU cook。
COP差值证据绑定before/after/expected_delta的identity与输出口；任一已记录操作数变化都会使旧检查失效。
不同输出口的统计分别保留；依赖失效仍是历史投影，不监听未记录GUI或外部文件修改。

HDA section 的写后回读/hash仅证明文本写入；PythonModule语法预检不执行回调，任意命名的嵌入section
也不自动按Python编译。内部函数测试、真实回调、cook后的交付输出、隔离环境依赖验证分别取证，
不能互相替代。多section库修改不具备场景undo的原子恢复保证。SOP HDA维护方法见
[HDA维护路径](../skills/houdini-sop-workflow/references/hda-maintenance.md)。

HDA创建的输入/输出上限不是接线证明；实例spare、定义界面、公共端口输出与隔离新实例分别验证。
界面整组重建遇实例spare同名覆盖时在库写前拒绝；显式spare提升走hda_edit(promote)。
界面重建及hda_edit(save/promote)写后失败恢复本调用的定义section、根实例界面/通道和磁盘库，
定义写入与场景Undo分离，避免外层Undo再次撤销恢复。后续同exec失败不撤销已经成功的库写入，外部副作用不保证。
hda_edit预览绑定源码/库/定义与共享实例状态；解锁不授予后代ownership，锁定丢弃内容须显式确认及逐后代授权。
SOP subnet标准输入Label管理字段保留但隐藏，不删除端口或用户自定义标题。
connect的inputs_before/after保留subnet间接输入为source=null、source_kind=subnet_indirect_input，
不把非Node连接猜成普通节点；source_output仍为原生连接索引。

真实Tab/Shelf初始化与静态类型模板不同。node_info提供实际parent下解析的类型、端口和模板，
不创建scratch；操作卡关键参数不受普通筛选裁切，见[节点卡](node-operation-cards.md)。
精确菜单用token/set_value；数值表达式字符串是HScript，显式Python要声明语言；
VEX仅在snippet内。tuple表达式用组件字段，严格设参不允许跳过未知/无效字段假报成功。
表达式写入和求值分别留证：原生setExpression失败标write/not_run；Parm.eval即使返回0，也检查H21/H22
原生节点诊断是否新增且明确指向该参数，新增明确错误/非有限值拒绝并恢复原值与keys。不能把合法0当失败。
旧cook错误在修正后可能仍缓存；无法区分新旧时返回unverified，允许通过显式cook/输出检查验证修复。
warning和无法精确归属的节点诊断为有范围的warning/unverified，不用旧的其他节点cook错误拒绝合法设参。
返回的parameter_state_restored/batch_parameter_state_restored仅指本次参数快照；外部Python副作用仍不保证恢复。
evaluation描述当前frame的求值读取，effect_status保持unverified；空输出或错误实体关系需后续同层验收。
build_module静态预检与实际数值setter共用值形状校验：size=1及单独组件是标量，接受有限数值、
HScript字符串或显式expression/language；不接受单元素列表。只有多分量tuple整体值接受等长有限
数值列表，表达式必须写组件名；菜单继续使用token/set_value策略。静态通过不证明表达式可求值或cook通过。
默认值和当前值分别修改：create_spare_parms(update_defaults=...)仅更新显式已有scalar spare的
字面默认值，预检整批再应用，回读默认值并保留当前值/表达式/keys；失败恢复模板与参数状态。
不更新内建、菜单、tuple、callback、multiparm或表达式默认值，不隐式改变已有创建模式。
字面字符串局部修改复用set_parm/set_parms的patch对象，必须带原始UTF-8源码expected_sha256和
每个old/new的精确count；缺锚点、次数不符、版本过期在本节点本批values开始写入前拒绝。
read_parms(names=[...])按指定字段读取，提供source_sha256；有变量展开时raw_value保留原文。
patch只支持无动画/表达式的可编辑scalar string，拒绝锁定/callback/固定菜单；Wrangle的代码片段
StringReplace菜单不执行、不阻止源码修改。补丁限定literal replace、不执行脚本/正则；原文和
结果不超过524288字符，1..32项替换、old/new累计131072字符，每项count为1..256。
set_parms的patch只允许strict=True，写入失败恢复本批值/keys。其他节点不在本批预检范围内；
跨节点调用仍遵循exec的undo与外部副作用边界。返回前后hash、字符数和次数，不重复整份源码；
hash/写入回读证明文本变化，VEX/cook/几何/关系仍需独立的同层验收。
静态multiparm先设置父/子count，再设置实例；动态或超预算情况用原生动词回读，不猜编号。
connect替换既有输入，断开后输入可能压缩，后续使用inputs_after而不是旧索引。

## 小模块构建

[SOP contracts](../houdini/python3.11libs/dsh_sop_contracts.py)负责新增节点的静态检查、构建、cook与清理。
build_module只新增1..64个SOP，不覆盖既有节点或输出旗标；inputs引用更早声明/现有直属子节点，
None为空槽，跨subnet用Object Merge或明确端口。独立静态错误汇总后零创建拒绝。
类型/参数/输入/输出静态拒绝统一携带phase=static_preflight及scene_writes=0；零写入仅针对
该模块，同exec内的其他修改、创建后的cook失败仍由事务恢复规则判定。
operation_advisories只描述缺少显式选择：不替用户封口、选边或转类型；没有提示也不证明正确。

output必须是明确新建非空交付；空CTRL/helper用tab_create。required_outputs检查必需分支，
防止非空Merge掩盖丢件。可附实际interfaces；失败或unsupported会使该构建失败并清理新节点。
dry_run只有静态效力。verify_network必须明确output，默认拒绝empty/error；
require_valid=False仅诊断，不能用来完成验收。warning、cook成功和语义正确分别报告。
subnet/HDA公共交付使用sop_set_output(node,output_index=0..63)在同父网络发布原生Output，
普通geo仅明确最终SOP并设置display/render，不要求创建Output；显式选择发布的旧调用保持兼容。
verify_network(...,output_index=同索引)检查其直接接线；不指定索引仍是内部构建/显示操作，
不自动猜祖先、改变OBJ可见性或保存定义。重复索引、成环和未授权foreign出口写入拒绝。
嵌入Packed的包装点/面不算实际内容：检查器有界访问内嵌几何，空内容拒绝，外部Packed或超限
无法取证时保持unverified。非空仅说明存在内容，不证明每个必需模块都进入输出；多实例、
根层显示、颜色/材质与实际关系仍须对应验收。

## 几何、接口与控制

[geometry observation](../houdini/python3.11libs/dsh_geometry_observation.py)和
[quality contracts](../houdini/python3.11libs/dsh_quality_contracts.py)对实际输出做有界检查：

| 方法 | 能证明的范围 | 不能替代 |
|---|---|---|
| Polygon inspect | 指定输出/组的边界、共享边连通、非流形、朝向冲突、逐壳条件性有向体积 | 目标外形、自交、实体强度；分组切口可有意开放 |
| attrib unique | 全量精确tuple唯一性、基数和有限重复样本 | 容差焊接；bbox不变不能排除复制重叠 |
| point spacing | 明确有序点的全量相邻弦长 | 曲面关系、弧长、实体间隙 |
| named surface proximity | 指定实际表面点到目标表面的最近距离与声明基数 | 实体插入深度、全表面无穿插、强度 |
| axis_gap | 实际primitive组沿指定轴的投影间隙和横向重叠 | 任意曲面真实接触 |
| section_proximity | 实际Polygon截面样本对目标表面距离、声明部件覆盖 | 连续全表面接触 |
| stable-ID displacement/transform | 相同Polygon拓扑与唯一point ID下的位移/声明仿射残差 | packed/native primitive内部状态；混合点均值不是设计中心 |

test_controls必须exec：临时数字控制、声明指标/关系/domain，随后恢复参数、keys、frame和完整bgeo。
恢复不仅比较bgeo：恢复写入后及最终cook后均回读被测参数的值/表达式/keys，最终核对frame。
parameter_restore列出快照参数身份、前后字面值或动画匹配及错误；任何不匹配都不能报告restored=true。
这些字段证明该次回读，不保证稍后GUI/外部代码不会改值；未采集历史不能据此归因为用户undo。
恢复指纹排除导出头date和派生group_summary，并按组名整理已知bgeo组目录记录；
组名、组成员、ordered group内部顺序、用户属性、拓扑和原生primitive数据仍完整比较。
重复组名或无法识别的组目录结构拒绝，不通过忽略真实选择或几何差异放行。
不支持的表示/菜单/副作用保持unverified；文件/Python/solver副作用不属于恢复保证。
控制响应非零不等于设计正确，单次case不证明所有参数组合。相关修改使旧证据失效。
test_controls的control_summary和Bridge证据保留顶层status/reason、失败判据及case_counts。
逐case还保留output_data_changed、measured_groups、whole_output_measurements和接口/拓扑状态；
coverage明确只通过声明检查，未请求关系时为not_checked。输出指纹变化但指标失败不证明控制未接线，
变化也可能来自属性；先查实际受影响部件与预期依赖。全局bounds/count不证明连接、间隙或均匀变换。
需要均匀/刚体变换时声明stable-ID max_transform_error；需要连接时声明适用的实际表面接口，
不以范围提示替代关系执行，也不强制简单尺寸调整运行不相关关系检查。
基准失败可零写返回results=[]，相关case标not_run；range同时约束基准和扰动绝对值，delta约束变化。
Host在详细证据和stdout前展示摘要；纠正判据后须复跑，不能把未运行或解释过的失败当成通过。

## 渲染、构图与保存

[camera framing](../houdini/python3.11libs/dsh_camera_framing.py)按八角点在实际普通透视/正交相机中的投影求解；
coverage=.82表示每侧9%的中央安全框，不是面积。full必须完整包络，detail可主动裁切。
A/B复用同framing_frame以及覆盖所有状态的framing_bounds与depth_bounds；前者决定取景，
后者只约束全部实际渲染内容（包含未隔离上下文）的深度。默认depth_bounds取framing_frame的
proxy全包络；只传framing_bounds时两者使用同一包络，独立关注范围应同时传两者。
复用返回framing.bounds/depth_bounds并保持方向/画幅/模式不变；越界零渲染失败，不悄悄移动相机。

detail通过正交宽度或透视镜头视角放大，不靠推进相机。服务相机可调整自身焦距以保持关注范围，
不改变camera_fit保留正式相机焦距的合同。二维outside_safe_frame可标intentional_crop，
near_or_behind_camera/far_clip始终失败；返回depth_check报告全部渲染内容的深度范围，
crop_reasons与错误reasons分开。full中的局部framing_bounds不是ROI，局部观察用focus_group或detail。
Python返回与Bridge证据均以check承载像素事实，pixels为兼容别名；EXR等未支持像素检查时可为null。
图像访问成功不等于异常归因正确；拓扑闭合不能排除相机裁切，也不能由另一视角无缺口推断着色原因。

render_view(EXPLICIT_SOP)使用持久__dsh_houdini_*服务，任务结束复用不删除；不改作正式交付相机。
camera_fit只修改明确授权的静态OBJ cam，保留焦距、清lookatpath、世界空间拟合并回读，
拒绝动画/表达式/约束/偏移窗口/lens shader等未支持状态；dry_run仍属于exec。
render_frame可用framing检查实际USD RenderProduct相机、画幅/裁切/像素比例；
未传保留艺术裁切语义，不隐式调整正式相机。预检不保证位移/运动模糊/遮挡或视觉质量。

渲染相对路径锚定$HIP，缺后缀拒绝；render_check仅证明文件新鲜度/像素事实。
transport、bootstrap、presentation、semantic inspection四层独立；没有成功语义识图就写视觉未验证。
viewport_screenshot用于用户屏幕诊断，不能把视口漂移当成最终模型错误。

scene_save_as需授权的目标路径及expected_current_path，不开放raw load/clear。
资产库修改不是普通场景撤销；create_spare_parms/update_hda的写后回读与锁定定义边界以动词合同为准。
