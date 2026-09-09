# 执行与证据契约

实现入口：[Bridge](../houdini/python3.11libs/dsh_bridge.py)、[helpers](../houdini/python3.11libs/dsh_hou_helpers.py)。
调用签名与版本以[工具设计](tool-design.md)及运行时verb_help为准；本页只维护跨动词边界。

## 安全与权限

- hou仅在Houdini主线程调用；HTTP线程只排队。泵不可用即拒绝，不退回网络线程执行。
- query使用只读namespace与AST预检；exec负责修改，job负责长操作。Raw Gate默认开启，
  已有动词覆盖的裸修改不能用allow_raw旁路；仅独立、无动词等价的低层缺口允许单次明确理由。
- query的result_ref分支只读当前workspace中已返回的历史结果；source_ref只读当前session公开日志中的任务来源。
  两者与code三路互斥，不进入Bridge/HOM，source_ref不接受JSON pointer或跨session路径，
  不能当现场新观察或ownership授权。新查询、修改和任务产物仍遵守原边界。
- ownership是runtime创建identity与session provenance，不是路径、父网络、名称或可复制userdata。
  foreign可读/作输入，不等于可写；单次allow_foreign必须绑定用户明确目标与非空授权说明。
  持久render服务不可豁免，layout默认仅本session节点。
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
每个Bridge执行返回execution.runtime_id/sequence/observed_at/frame和本次影响观察；运行实例与节点
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
exec的request_ref在进入主线程队列前登记，查回走固定只读/requests/status端点，不触发HOM或重新排队。
同runtime同身份同payload只返回原状态/结果；payload或owner不符拒绝，不更新原请求。状态not_executed
仅在已登记且确认主线程未开始时报告；断联、结果过期、换runtime和查不到回执均不等于未执行。
回执丢失/过期时需显式观察实际场景再决定下一步，不自动生成新request_ref重做原修改。
查回带retrieved标记，原执行sequence保留；执行状态投影解除已查明的unknown，离线动词核算不重复计数。
jobs提交复用同runtime回执但以job_submit类型单独绑定payload；查回jobId只解除提交未知，job仍可能排队/
运行中。terminal job不能被迟到的提交回执重置为排队。队列取消、过载拒绝和worker启动失败保持原执行边界。
Host历史已保留done/not_executed/job_submitted回执时，迟到的非终态或Bridge保留期结束不将同一引用降级为未知；
未查回过结果的过期引用仍保持不确定。该规则不把job提交当作执行完成，也不认证当前场景。
request_ref='index'仅列当前owner最近32条回执，以owner_call对齐Host未记录结果的原调用；无代码/结果正文，
不能用索引中缺记录自行授权重提。独立执行统计按canonical runtime/sequence去重，传输轮询仍计工具调用；
只有历史文本或没有序号的结果明确未测，不猜执行身份。

## 参数与创建

HDA section 的写后回读/hash仅证明文本写入；PythonModule语法预检不执行回调，任意命名的嵌入section
也不自动按Python编译。内部函数测试、真实回调、cook后的交付输出、隔离环境依赖验证分别取证，
不能互相替代。多section库修改不具备场景undo的原子恢复保证。SOP HDA维护方法见
[HDA维护路径](../skills/houdini-sop-workflow/references/hda-maintenance.md)。

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
