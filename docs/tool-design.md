# 工具设计与动词词表

Execution contract version: 98

USD概览按原生角色统计；应用LightAPI的发光Mesh同时属于geometry和lights，角色计数之和不等于唯一prim总数。灯光不按类型名称后缀猜测，DomeLight_1保留实际类型名。

工程目录角色由[project-layout.json](../houdini/project-layout.json)统一维护，现场通过`scene_info().project_layout`返回实际HIP锚点；使用与生命周期见[工程文件](project-files.md)。目录位置不构成交付、清理许可或视觉验证。

本页是动词目录唯一真相源；构建从表格生成Host预期名称/hash与client目录。
实现以[helpers](../houdini/python3.11libs/dsh_hou_helpers.py)、
[Bridge注册表](../houdini/python3.11libs/dsh_bridge.py)及运行时verb_help相互校验。
执行边界详见[执行契约](execution-contract.md)，节点知识见[同源节点卡](node-operation-cards.md)。
动词的按需输入结构、稳定输出字段与例子维护在[verb-operation-contracts.json](../houdini/verb-operation-contracts.json)，
[结构合同](verb-contracts.md)由同源生成。Python签名来自真实运行函数；结构说明帮助发现能力，不作为新的执行校验或任务准入。

组件schema-2使用原生节点档案保存内部值，交换快照只比较根公开参数与节点/接线清单；引用/权限/输出检查保留。
旧schema-1导入拒绝并要求另存导出，不原地升级文件；替换计划仍检查内部状态，详细边界见[组件设计](component-collaboration.md)。

## 设计原则

动词是稳定意图接口，不是hou的一对一包装；域只是导航，不是权限分类。
低层只读可用query中的HOM逃生舱，已覆盖的裸修改不得旁路。通用机制进入动词/guard，
方法进入按需skill，身份与风格进入preset，常驻guidance只放跨域稳定契约。
未知签名先verb_help，不以失败调用探索返回类型；类型发现、操作知识、运行状态分别查询。

- 新动词必须有跨任务独立意图、稳定参数/返回、错误与恢复边界，不能只为单个对象或提高目录覆盖率。
- 各参数接受Node/path的范围以实际签名为准；涉及foreign修改须单次用户明确授权。
- 写操作须严格设参、主线程执行、记录真实失败和最终事务状态。捕获只读或零写入错误、以及明确恢复成功的错误后可继续操作；未确认恢复的修改失败必须终止当前批次。
- 多节点setup与单节点创建分开：tab_apply面向受限真实Shelf组合，不把所有setup压进tab_create。
- 只读describe/list_parms/node_info不能为导航隐式创建或cook重型上游。
- 所有证据都要带范围，cook、关系、渲染像素和视觉语义不互相代替。

Manual模式下describe只读metadata，cook_node返回not_cooked_manual；verify_network默认拒绝，
require_valid=False返回not_evaluated_manual，geometry/nonempty/output_fingerprint为null、checked_nodes为空，
不能把未计算当作空输出或新鲜证据。几何统计/关系/控制实验、实际build_module、camera_fit和渲染入口
在计算或修改前拒绝Manual；build_module的静态dry_run仍可用。不自动切Auto，也不强杀用户Houdini。
verify_network的显式output cook失败后不再用geometry/geometryAtFrame隐式重试；几何和nonempty保持未知，
不把中断/失败缓存认证为当前输出，也不把未知附加解释为empty_output。
test_controls的恢复cook也遵守同一边界：失败后不再读geometry触发重算，保留恢复诊断且restored为false。

## 顶层工具

read_parms的Ramp值为JSON对象：type=ramp、basis插值名称、keys控制点位置、values标量或RGB数组。
它是当前求值的回读格式，不是set_parms载荷，不证明动画/回调/完整状态恢复；普通标量返回保持不变。

render_view的H22后端为Flipbook/Vulkan，使用独立Work Lights与OCIO颜色空间；
H21保持既有OpenGL ROP和设置。两者共用显式SOP代理、相机/深度包络、状态恢复与新鲜度检查。
H22无旧gamma/LUT降级，缺少所需OCIO空间明确拒绝；不修改用户Flipbook节点，不删除旧持久服务。
后端分流不是因为H21缺少Flipbook：两版均有该节点，但参数和渲染行为不完全相同。
当前支持的H21.0.440在Flipbook Work Lights下不能正确合成几何Alpha，原OpenGL仍可；
只有新的H21候选构建通过真实透明物体/实体背板对照及状态恢复，才可取消该分流。
Flipbook没有OpenGL的旧LUT/gamma接口，不能按同名参数或不透明测试外推全部替代。
平台依据：[Flipbook](https://www.sidefx.com/docs/houdini/nodes/out/flipbook.html)、
[OpenGL退役说明](https://www.sidefx.com/docs/houdini/nodes/out/opengl.html)；本项目的稳定验证入口见[开发规范](development.md)。
render_view与viewport_screenshot默认把验证图分配到`$HIP/dsh-visual-checks/<run-id>/`；最终交付显式选
`output_policy='delivery'`写入`$HIP/dsh-render/`。两种分配只接收省略文件名或安全basename，禁止可执行路径表达式；
自定路径选explicit。返回实际路径供present使用；位置不证明质量，旧图不自动迁移/删除。正式render_frame/ROP按明确目标设置`$HIP/dsh-render/...`，已有用户指定输出保留。

顶层工具的作用、输入和返回见[工具说明](tools.md)，由[src/tool-catalog.ts](../src/tool-catalog.ts)生成。现场读取、执行、请求查回、资源读取、视觉能力与长任务控制各有独立接口；任务记录使用DSH已有能力。

工具注册在[src/tools.ts](../src/tools.ts)，结果展示在[src/tool-output.ts](../src/tool-output.ts)，来源/历史结果与查回在[src/tool-query.ts](../src/tool-query.ts)。保存与渲染使用执行工具中的动词，不额外提供产品计划或完成认证工具。

Host比对Bridge词表与合同，结果包含操作记录、执行状态、checks、evidence、图像和文件事实。失败保留具体阶段与恢复结果；模型据此决定下一步。

execution中的hip_dir来自同次场景观察，未命名场景为null；Host工作区提醒直接使用该字段，
不追加Python探测、维护另一HIP缓存或因提醒失败拖延原结果。路径差异通过Open Workspace处理。
Bridge每次启动同时建立新的请求注册表与执行runtime，回执和execution使用同一个runtime_id；
executor_id标识Houdini进程，不能与某次Bridge运行或DSH会话身份互换。
有Host会话身份的exec/query/jobs先调用POST /requests/prepare，以owner_session取得同runtime的单次票，
同时读取词表与执行合同；它替代普通health握手，不增加网络往返，也不进入HOM队列。GET /health不签票。
票仅在首次提交前保留120秒，未用票最多4096条；登记时在同锁内消费。只有Bridge签发的票可首次登记，
已消费且回执淘汰的旧票也不能重入队；保留窗口内的重复引用只查原结果，owner/payload不一致仍拒绝。
HTTP断联、超时、坏JSON或错误状态码
返回unknown_transport时，用houdini_request(request_ref=...)查回，不重发code。请求查回工具不接受code、pointer或分页；返回queued/running/done/not_executed/unknown等状态，done回读原结果。
回执窗口最多4096条：正在执行/排队的请求及活动job关联不可淘汰，已终结旧记录按容量轮转，不设累计请求寿命。
只有全部槽都仍活动时才拒绝新增登记。结果正文最多保留10分钟且总量上限64MiB，超预算先淘汰旧正文；
过期/预算淘汰明确为result_expired，单条超预算为result_unavailable；记录淘汰后为unknown，不能推断未执行。
jobs回执保存的是提交关联，不是完成证据；查回jobId后继续houdini_job_status。关联保持到job worker终态，
不受正文到期影响；终态后进入普通淘汰队列。job实际结果服从job registry自身期限。重复回执不启动第二个worker，
过载或worker未启动保留not_executed；队列取消仍阻止HOM运行，运行中取消不强杀。
Host若丢弃整个工具结果，用request_ref='index'查看当前Host会话最多32条引用，优先仍活动请求/job关联，再列最近终结记录。
按owner_call对齐原调用；索引不暴露代码或结果正文，省略数明确。超范围、未到达Bridge、换runtime或缺失均不证明未执行。
health的activeRequests由Registry活动槽推导，涵盖未返回exec和活动job关联，不是activeExecs，也不把未用票计入执行。
普通更新启用同时检查Host任务、Bridge jobs与activeRequests；显式强制Repair可中断DSH任务，但仍在停止前后
验证Bridge空闲，并在主线程重载前复查本地请求/jobs/队列。缺失/非法活动观察为unknown，不按0放行；
进程核验与操作边界见[安装合同](setup.md)，强制DSH退出不授权强杀HOM或重发未知请求。
没有跨runtime幂等、自动重提、无限期结果保留或强杀HOM保证。排队job取消以真实取消回执结束活动状态；
result_expired/result_unavailable表示原请求已终结但结果不可取得，outcome保持unverified，不继续当作活动请求轮询。
DSH的TOOL_OUTCOME_UNKNOWN保留为待查回，TOOL_NOT_STARTED不推断发生过HOM操作。
表达式设参分别报告language、write_status、evaluation和effect_status；合法零值不算错误。
H21/H22本次新增的原生求值错误明确指向当前参数，或结果为非有限数值时，抛CheckpointError并恢复原参数状态；
strict set_parms同时恢复本批前序参数和动画。failure_stage区分写入失败与求值失败，恢复结果另外报告。
缺失引用的warning、tuple共享warning和其他节点诊断保留范围，不把它们强行归因当前参数；可能前向引用
的表达式允许先写入，但返回warning/unverified。先前cook错误可能在表达式修正后仍缓存；与求值前相同的
错误不冒充本次新增失败，标unverified并要求显式cook/输出复验。read_parms同步返回表达式语言与求值诊断。
这些读取不额外cook或重复求值；表达式通过不证明非空几何、关系或控制效果，继续按显式输出验收。
控制实验与domain共用显式数值通道解析，支持普通spare和HDA定义参数，也支持显式命名的数值tuple分量；不接收tuple列表值。菜单/动态菜单、回调、multiparm成员、缺失/非数值参数写前拒绝，domain失败不通过删除判据核销。
大返回在当前workspace成功保存完整Bridge返回JSON后才精简默认文本；result-details提供SHA-256和
可用读取入口。`houdini_resource(kind="result", ref=hash,pointer='/evidence/0',offset=0,limit=6000)`分页返回选中
字段的JSON文本，limit为1..16000字符，offset为非负整数；pointer遵守JSON Pointer，不是任意路径或代码。
文件按内容hash命名并校验，不跟随单文件symlink；目录必须留在当前workspace。单份上限32MiB。
通用展示直接消费Bridge的outcome/checks/evidence/execution，不另推导控制、Polygon或接口结论。outcome区分批次是否完成、动词异常与验证结果，已捕获查询异常不改变合法fallback但必须可见。已归档结果的等价JSON子树使用引用，ledger省略可回读的参数；不同内容、诊断字段、状态与范围保持可见。verb_help默认返回简明调用资料，完整契约按需读取。保存失败显示完整返回；历史读取不会重放场景操作。对应回归见[结果投影](../tools/tests/compact-results.test.mjs)与[留存读取](../tools/tests/result-details.test.mjs)。
canonical是同一份完整工具返回，metadata供原生事件、UI、审计和状态投影，模型文本从它生成可读视图。
Code Mode仍按Host协议返回完整canonical值；原生及嵌套事件共用读取规则，取消等无execution字段的回执也保留完整值。
嵌套事件确实缺少完整值时须由result_ref读取，审计明确标缺口，不从展示文字猜状态。

## 动词目录

### vocabulary 域（回答「动词怎么调用」）

| 动词 | 语义 | 返回 |
|---|---|---|
| `verb_help(name, detail='brief')` | 按需发现动词。默认brief返回准确signature、return_type、call_mode与简短用途，并明确full_help入口；detail='full'返回完整doc及已有operation_contract（input_schema/output_schema/examples/notes），说明不参与执行校验。name可为1..16项唯一名称列表，批量返回items/count；未知名列相似项，任一未知整次明确失败。Bridge签名绑定错误给真实signature与零派发事实，内部TypeError保留真实原因 | dict |

### 类型目录（回答「能建什么」）

| 动词 | 语义 | 返回 |
|---|---|---|
| `search_tab_menu(category, query)` | 列出某 context 下匹配的节点族 + 最新版 | dict |
| `search_tab_entries(parent, query)` | 按真实父网络列当前可见的 node/tool entry；排除 hidden/deprecated，Material Library 根层只暴露 Builder tool；每项标 `kind` 与 dsh 是否可安全执行 | dict |
| `resolve_latest_type(category, base)` | 已注册节点族的最新版全名（内部为主）；只以 namespace 注册的族返回带前缀全名（'rigdoctor' → 'kinefx::rigdoctor'），裸别名过不了 `createNode(exact_type_name=True)`；跨 namespace 同名按排序取第一个，recipe 需跨版本一致时应显式钉命名空间；当前类别没有该族时明确失败，不回传未经验证的base | str |

### node 域（场景图）

| 动词 | 语义 | 返回 |
|---|---|---|
| `tab_create(parent, type_name, name=, inputs=[...], parms={...})` | 建**单个可见节点**：最新版 + 对应 shelf 初始化；类型、输入和参数形状先预检，静态失败返回零写入事实。inputs中的直属child名称相对实际parent解析，None保留空槽。可选非空`parms`在创建/接线后走严格set_parms，任一失败会连同 partial create 清理并报告恢复结果；拒绝 hidden/deprecated 和 Material Library 根层直建 shader，setup/builder 改用 tab_apply；parent 接受 Node/path。连完 inputs 后自动落位：有输入时放到所有输入下游（x = 输入 x 均值，y = min(输入 y) − 垂直间距）；无输入时放到父网络现有内容右侧新列（x = max(现有 x) + 水平间距，y = 现有最顶部 y，空网络落原点）；间距由节点实际网络尺寸（`Node.size()`）推导，不用拍脑袋常量 | `hou.Node` |
| `tab_apply(parent, tool_id)` | 应用 allowlist 内的非交互 Tab setup recipe，返回全部新增节点/输入；GUI 恢复 Network Editor pwd/selection，同一 exec 多次调用共享用户基线；headless 同语义。首批仅 Karma Setup / Karma Material Builder。SideFX recipe 自己摆节点，tab_apply 不做自动落位 | dict |
| `find_nodes(pattern="*", category=None, node_type=None, root=None)` | 找**已存在**节点（扁平清单） | path 列表 |
| `graph(node, depth=1, direction='both')` | 围绕**该数据节点**查 inputs / outputs / parm_refs；检查最终 SOP 网络应对 `OUT` 向上查，不要对父 OBJ 容器调用 | dict |
| `describe(node)` | 状态 + 几何摘要 + `attrib_delta`（相对 input 0 的属性增删——MMB 节点信息里「这个节点对数据干了什么」的固化）+ 帮助元数据 | dict |
| `node_provenance(node)` | 报告 runtime owner、可复制的 audit tag、当前 session 是否可写；`foreign`/`owned_current_session`/`owned_other_session`/`dsh_service` 分开 | dict |
| `connect(src, dst, index=0, *, output=0, allow_foreign=None)` | index为目标输入名/索引，output为源输出名/索引；精确名称不是label，先解析两端及原生兼容性再写入，回读实际源输出。output默认0，第4位置参数拒绝。mutation边界在dst；OBJ→OBJ拒绝并指向set_object_parent，跨parent拒绝，不猜端口或绕Gate。describe.ports提供有界名称/索引/类型；verified仅连接回读，不证明语义；连接后仅必要时调整落位 | dict |
| `node_info(parent, type_name, parm_filter='', limit=24)` | 创建前读取实际parent最新版类型、端口、参数默认值/组件名/menu token/set_value与帮助URL；parm_filter只作字面子串筛选。operation_card含决策/版本，operation_parameters保留不受筛选/limit裁切的关键设置，缺字段显式报告。不建临时节点/不运行Shelf；动态菜单需list_parms，truncated明示。没有delivery准入 | dict |
| `modeling_dimensions(quantities, require_meter_scene=True)` | 只读源单位换算：quantities={name:{value,unit,min?,max?,source?}}，最多64项；长度m/cm/mm/um/in/ft转米，面积/体积按平方/立方换算，rad转deg、count/ratio不按长度缩放。默认要求当前HIP=1m且不改单位；旧工程须显式False并消费scene_values。返回原始依据、canonical_values、scene_values及米制CTRL spec；不证明最终尺寸 | dict |
| `sop_recipe(kind, spec=None)` | 只读普通SOP配方，catalog给schema，kind单独调用给结构模板示例；hinge/slider/repeat共享origin/axis及CTRL标量，Merge源与附件→FRAME→Copy；sweep_tube/profile_shell为单中心线/平面薄片成形；guided_slider用真实source/guide投影推导位置并拒绝越界，surface_attach在指定面组投影并取法线frame；gusset/fastener提供带厚度肋板与头杆源。返回nodes/output/required_outputs交给build_module，不创建/cook；不猜坐标、不认领输入、不保证接合。字段、适用前提和反例见SOP配方reference | dict |
| `control_test_plan(controller, parameters, max_cases=16, domain=None)` | 只读数值参数规划；1..8标量各2..8显式levels，最多4096候选，贪心覆盖levels与两两组合，最多16case。domain只预筛独立无keys标量，记录排除数与missing；返回tests的expectations为空，须由作者补独立指标/状态接口后test_controls执行，不是全域证明 | dict |
| `build_module(parent, nodes, output, dry_run=False, interfaces=None, *, required_outputs=None)` | 批量新增{name,type,parms?,inputs?} SOP节点，列表非空；inputs可引用任意声明/现有直属child名，声明顺序自由，None保留空槽。先创建全部节点，再接线、设参，表达式可引用本批任意节点。独立静态错误汇总零创建拒绝；size=1/组件按标量校验，多分量tuple接受等长数值列表，与实际setter同源。dry_run只预检真实类型/参数/引用；操作知识按需读node_info，不从缺字段推断未决设计。required_outputs可显式检查必需新分支，可附实际interfaces。返回validation/interface_checks；失败清理本批新节点，不覆盖已有节点/flags | dict |
| `verify_network(parent, output=None, nodes=None, limit=512, require_valid=True, *, output_index=None)` | SOP checkpoint：必须显式output，不跟随display。output_index=0..63另验同父网络原生Output接线；默认检查直属范围，可nodes限域，error/空输出默认拒绝。geometry给bbox_min/max/size，所有显式输出均回scene_unit_length_meters与bbox_size_sop_local_mm，须结合OBJ变换核物理尺寸。handoff_output给出名称/type/Null/leaf、显示/渲染旗标及父网络当前出口。不按输出名称追加表面或上游Sweep检查；需要时显式调用geo_piece_stats等领域工具。它不自动发布，不证明OBJ可见、部件关系或艺术质量 | dict |
| `set_object_parent(child, parent, keep_world=True, reason='', index=0, allow_foreign=None)` | 显式 OBJ parenting/unparent（`parent=None`），自然参数序为 child→parent；普通父级用 input 0，Blend 等明确多输入对象可指定 index。`reason` 为可选自由用途说明，表示与方法由当前任务决定。拒绝非 OBJ、自环/层级环；mutation/ownership 边界在 child；默认恢复 child 原世界变换并回读 parent、local/world delta | dict |
| `disconnect_input(dst, index=0, *, allow_foreign=None)` | 断开普通网络 destination 输入；权限理由keyword-only非空字符串；OBJ unparent 拒绝并指向 `set_object_parent(child,None,...)`；ownership 边界在 dst，返回原 source path（若本来为空则为 null） | dict |
| `rename_node(node, name, allow_foreign=None)` | 重命名 | 新 path |
| `delete_node(node, allow_foreign=None)` | 删除前核对全部后代身份；返回外部参数引用及最多64项affected_connections（目标输入、原源输出及inputs_after），提示原生删除可能旁路重接，同名新节点不继承接线。拒绝删除owner-tagged render_view会话级基础设施。创建时同步新HDA的延迟定义后登记原生后代；不收养后来加入的foreign子节点 | dict |
| `cook_node(node, force=False, timeout_ms=30000)` | cook + error/warning，timeout_ms为1..120000的协作预算，仅原生中断检查点可响应，不保证强制停止/内存安全。Manual返回ok=False/status=not_cooked_manual，不自动切Auto；预检输入计数恒条件、平直删除语句组成的已知无界VEX循环，未知控制流不作安全认证。依赖规模本身不拒绝；verify_network的内部只读批次共享一次完整上游预检，不跨调用缓存。warning未解释不得当完成 | dict |
| `sop_set_output(node, render=True, allow_foreign=None, *, output_index=None)` | 默认仅移动SOP display/render旗标。显式output_index=0..63复用/创建同父网络原生Output并接线，将旗标设到它；重复索引/循环/foreign接口写入拒绝，逐层发布不猜祖先。返回public_output接线事实，不cook/保存HDA，须另验几何、新实例与根显示；不是render_view前置条件 | dict |
| `sop_output_node(parent)` | 报告 SOP 网络 display/render 输出；旗标不在链尾时提醒 | dict |
| `set_object_visible(node, visible=True, allow_foreign=None)` | 设置单个 OBJ 的 viewport visibility（OBJ 没有 SOP 式 render flag） | dict |
| `visible_objects(root='/obj')` | 列出 OBJ 层 plural visibility/effective visibility，并附每个对象的 provenance | dict |
| `layout_nodes(parent, nodes=None, horizontal_spacing=-1, vertical_spacing=-1, allow_foreign=None, mode='children', *, boxes=None, profile='comfortable', dry_run=False, expected_plan=None)` | `children`原生layoutChildren、`flow`节点拓扑分层；已有成员Network Box时，两者无显式nodes的整网重排写前拒绝，明确的局部nodes列表仍可用。盒布局用`handoff`处理叶子框，`component`处理一层组件容器，需显式boxes；可直接应用，也可dry_run取得plan_sha256，提供expected_plan时才检查计划仍新鲜。重复应用零写入。默认只移动当前session自有项，单次allow_foreign仅用户明确授权的既有项，持久service不豁免。未选节点/Box与Sticky Note/Dot是固定障碍；量测失败零写入。返回实际节点/盒重叠、containment和净距；只证明network-editor布局，不证明接线或艺术质量 | dict |
| `network_boxes(parent, groups, *, remove=None, dry_run=False, expected_plan=None, allow_foreign=None)` | 按显式groups整理Network Box：每项需要name，可选label/role/members/boxes/color；label默认name，role只提供颜色提示，未知role用中性色。members为parent直属节点，boxes可引用已有框或本批声明框，两类成员可共存，声明顺序自由，真实循环写前拒绝。可直接应用，dry_run为可选零写入预览，expected_plan仅在显式提供时核对新鲜度。已有框保留现色，显式RGB三元组才改色。移动显式成员时核对实际受影响的来源框和目标框权限；Box权限独立记录，foreign需单次授权，render服务不豁免。失败恢复成员、位置和外观；分组本身不cook、不证明布局或几何正确 | dict |
| `network_controls(parent, controls=None, *, remove=None, allow_foreign=None)` | 明确声明实际控制入口：controls为node/label对象列表，remove为显式节点列表，目标须在parent范围内且遵守ownership。声明保存在节点userData，随HIP保存、改名保留；省略controls/remove只读列出parent内的已声明入口，不按名字或参数数量猜角色、不cook。节点交付卡片复用同一控制声明；不证明联动或正确性 | dict |
| `network_notes(parent, notes=None, *, remove=None, allow_foreign=None)` | 读取或局部维护明确名称的Sticky Note；省略notes/remove只读返回实际text/position/size/color与归属。notes项需要name/text，可选position/size/color；默认新Note放在现有内容旁，显式remove不扫全网。Note按实际session identity独立归属，不因名称/parent认领，渲染服务永不豁免；预检及失败恢复保留事实。Note不隐式加入Box，是后续布局固定障碍；文字不证明业务正确或维护完成账本 | dict |
| `present_nodes(nodes, *, allow_foreign=None)` | 明确交付节点入口，nodes为node及可选label/role/description/new_identity的1..16项列表；role为control/output/node，只表达导航用途，description为<=200字符的单行操作说明。返回context来自真实节点类别，说明和路径属于交付时观察。缺少持久标识时在目标节点userData写UUID，真实修改遵守ownership；显式new_identity只用于续新标识，旧引用失效。成功批次从present_nodes动词回执显示节点卡片，不依赖__result__包装，与DSH文件交付并列。声明后保存同一HIP，重开/改名仍可定位；不存在或复制导致重复不按历史路径猜目标，不写独立交付账本 | dict |
| `focus_node(reference, *, expected_hip)` | 在Bridge主线程队列按持久id与原交付HIP进行显式界面导航，适用于节点卡片点击。定位同一实际节点并打开参数页、展开祖先框；不同HIP、缺失或重复id明确拒绝。只改变导航/框展开，不改模型参数/几何或加载保存HIP；历史runtime sessionId不作为持久节点身份 | dict |

### parm 域（依附 node）

| 动词 | 语义 | 返回 |
|---|---|---|
| `list_parms(node)` | 参数**目录**：名字/标签/类型/帮助/默认值及实际 menu token/index/label（不给当前值）；动态菜单以实际节点为准 | list |
| `read_parms(node, changed_only=True, *, names=None)` | 参数**值**：默认只看非默认 + 带表达式/动画 + 被引用的（意图解读）；names可选1..32个唯一标量或tuple字段，按请求顺序返回且不受changed_only过滤，tuple给聚合value/component_names及逐分量诊断，缺失报错。无动画string含原始UTF-8源码source_sha256，展开值不同于原文时另含raw_value；表达式附referenced_parm，被引用标referenced_by；动画附time_dependent/key_count/first_frame/last_frame/curves，不默认倾倒全部keys | list |
| `set_parm(node, name, value, allow_foreign=None)` | 设参（数值字符串=表达式）。已有表达式/keys在普通赋值时清除，note说明变化。字面string可传`{expected_sha256,patch:[{old,new,count}]}`：精确版本和次数、全部锚点先验，拒绝锁定/动画/表达式/callback/固定菜单；返回patch前后hash/字符数/次数及value_omitted，不回传整份源码。最多32项，source/result各524288字符、替换文本累计131072字符、count为1..256；不执行正则/脚本。文本通过不证明cook/几何通过 | dict |
| `set_parms(node, values, allow_foreign=None, strict=True)` | 默认严格批量设参：预检名称/重叠/锁定；value支持set_parm的string patch对象，本节点本批全部patch在任何设参前验证。patch只允许strict=True，set内返回变化摘要，patched列出字段；失败恢复本批值/表达式/keys。其他节点不在本批预检范围，参数回调/外部文件不属快照回滚。无patch的显式strict=False仍返回ok/set/failed；Menu string为精确token，数值string为HScript表达式，表达式对象可声明language | dict |
| `set_keyframes(node, channels, replace=True, allow_foreign=None)` | 批量写数值标量 channel keys；统一 frame 单位，有限曲线 `constant/linear/bezier`。全量预检包含锁定状态，失败恢复原值、表达式、keys和frame，并明确restored/restore_errors；提交后回读/采样并恢复用户frame。只负责channel数据，不代替路径依赖状态机或KineFX/APEX | dict |
| `create_spare_parms(node, code_parm='snippet', defaults=None, spec=None, allow_foreign=None, *, update_defaults=None, layout=None, dry_run=False)` | 缺省扫描代码参数的 `ch/chf/chi/chv/chs` 引用并创建缺失 spare parameters。`spec=[...]` 的精确条目为 folder `{type,name,label?,parms:[...]}` 或 scalar `{type:'toggle\|int\|float\|string',name,label?,default?,min?,max?,min_strict?,max_strict?,help?}`；spec必须用具名参数，严格上下限字段只接受min_strict/max_strict。spec 返回 `{node,mode,created,leaf_values}`；扫描返回 `{node,code_parm,references,created,existing,defaults_applied,unsupported}`；创建仍拒绝同名覆盖。新建接口后重新赋写code_parm原始源码/keys以刷新编译依赖，保留表达式与动画；返回refreshed_code_parm（未刷新为null），锁定源码在接口写入前拒绝。显式 `update_defaults={name:literal}` 仅更新1..32个已有scalar spare的默认值，与spec/defaults/非默认code_parm互斥；保留当前值/表达式/keys，返回updated前后值及current_state_preserved。支持float/int/toggle/string，拒绝内建/tuple/menu/callback/multiparm及表达式默认值；当前值另用set_parms。layout与spec/defaults/update_defaults互斥，复用共享UI组件，默认追加并拒绝已有模板/参数名冲突；dry_run仅layout有效，预览零写入。应用保持已有通道值/keys/locks，失败恢复节点接口及通道，不修改HDA定义或绑定 | dict |
| `parameter_ui(node, max_depth=6, include_state=False, analyze_ui=False)` | 任意节点参数界面只读自省：类型/可选定义文件与section、实例interface及definition.interface，含范围/默认表达式/回调/菜单生成器/条件/tags、tuple look和Ramp类型。include_state返回至多512通道raw值/keys/locks；analyze_ui返回非阻断结构建议。不执行菜单/表达式/cook，不自动修复或创建绑定 | dict |
| `bind_controls(controller, bindings, *, dry_run=False, expected_plan=None, replace_existing=False, allow_foreign=None)` | 1..32项明确数值绑定：source为控制节点参数名，target为目标参数绝对路径，可选scale/offset。dry_run返回plan_sha256；应用必须expected_plan匹配identity/值/keys/锁定/帧。默认拒绝已有驱动，replace_existing显式替换；拒绝非数值/菜单/回调/multiparm、任意表达式源、批次源目标交叠及重复目标。整数目标只接受整数源与映射系数。实际HScript引用和值回读，失败恢复本批目标通道；不保证领域输出或外部副作用 | dict |

| `set_update_mode(mode, expected_mode)` | 显式切换auto/manual/on_mouse_up，expected_mode防止覆盖过期用户状态；无GUI拒绝on_mouse_up（原生会降为auto）。after/changed取实际回读，未应用请求或setter失败会尝试恢复并报告结果；模式恢复不撤销触发的cook/外部副作用。切Auto可能触发全场景计算，不是取消接口 | dict |

### scene 域（工程/时间线）

| 动词 | 语义 | 返回 |
|---|---|---|
| `scene_info()` | 只读 HIP/version/fps/current frame/time/frame range/playback range/UI 状态及 `unit_length_meters`（1 个场景单位对应的米数，无法读取时为 null）；明确区分 `has_named_path`、`has_unsaved_changes`、`dirty_reliable`、`clean_on_disk`，不再用路径存在冒充保存完成；hython 的 dirty 不可靠时 clean=null；不移动 playbar、不遍历整张节点图 | dict |
| `scene_save(expected_path=None)` | 只保存当前已命名 HIP，不承担 Save As/open/new；可选 expected_path 作防串场断言，返回 dirty before/after/reliable、clean（headless=null）、bytes、mtime_ns | dict |
| `scene_save_as(path, expected_current_path, reason, overwrite=False)` | 用户授权的 Save As：明确绝对 HIP 路径，expected_current_path 防串场，reason 记录路径/覆盖授权；已存在目标必须 overwrite=True。拒绝插件仓库落盘，回报前后路径/dirty/file/workspace_changed。无 load/clear；文件写不可撤销，失败可能留部分新文件，跨目录后 Open Workspace 重新绑定 | dict |
| `set_timeline(fps=None, frame_range=None, playback_range=None, current_frame=None)` | 设置明确的时间线字段；至少一项，所有字段的有限数值/范围写前校验，成功回读scene_info。写入失败恢复fps、两种范围和当前frame并报告restored/restore_errors；不恢复触发的cook或外部副作用 | dict |
| `list_bookmarks()` | 列出 bookmark id/name/start/end/enabled/visible/comment | list |
| `create_bookmark(name, start, end, replace=False)` | 创建整数帧 bookmark；同名默认拒绝，replace 精确替换 | dict |
| `delete_bookmark(name_or_id)` | 按精确名称或 session id 删除，失败列现有项 | dict |

### geometry 域（几何数据）

| 动词 | 语义 | 返回 |
|---|---|---|
| `geo_attrib_stats(node, name, attrib_class='point', *, unique=False, max_elements=100000)` | 数值min/max/mean/count；unique=True全量检查精确完整tuple（含字符串），返回unique_count/duplicate_count/all_unique及至多8个重复样本。用P查精确重叠、用id查身份；超预算/非有限拒绝，无容差焊接或自动删除。point/prim/vertex/detail | dict |
| `geo_point_spacing(node, expected, tolerance, closed=False, order_attrib=None, max_points=10000)` | 全量相邻点弦长验收：默认point number顺序，或唯一数值order_attrib；closed含末→首，SOP local单位；返回全量min/max/failure_count及最多16个最差对与sequence hash。超预算拒绝不抽样；只证明该序列约束，不证明弧长、网格接线或实际零件关系 | dict |
| `geo_check_interfaces(output, interfaces, max_pairs=50000)` | 同一最终SOP内1..16实际关系。默认{id,source_group,target_group,max_distance,expected_points}测独立表面点到面距离；method=axis_gap用两个primitive组及axis/gap_range/min_overlap测投影间隙。method=solid_overlap用两个独立完整闭合朝外Polygon实体组和max_overlap_volume，在内存副本做Boolean Intersect量实体相交体积，非零有效交集返回SOP局部包围盒（多处交集仅为外包络）；实心轴穿实心铰耳fail，有孔且留间隙pass，开放/不完整/非Polygon/数值含糊为unverified。method=axis_passage用最终Polygon target_group、axis及SOP local start/end测一条跨越该组包络的轴线；碰到最终表面fail，无遮挡pass，缺组fail，非Polygon/未跨包络unverified。它不证明孔径、孔壁或其他轴；后续增材须复验。solid_overlap每组最多20000面；面包围盒扫描筛候选，共用max_pairs候选预算与2000000扫描访问预算，完整实体仍交Boolean处理包含关系；不建场景节点、不抽样。零交集不证明同轴或真实穿孔；三态分别检查，不证明连续运动、受力或公差。返回实际值/范围/几何hash | dict |

`geo_check_interfaces(method='physical_extent')`接受从资料独立核对的`target_group`、`axis=0..2`、`expected_mm>0`、`tolerance_mm>=0`。在最终闭合Polygon组测所选点的SOP局部逐轴跨度，按当前HIP unitlength换算毫米，超差或缺组fail；非Polygon、单位未知、非单位OBJ变换或超预算unverified。它检查声明组的一轴尺寸，不自动认定图纸尺寸归属、分组完整性或其他部件关系；后续编辑须复验，控制扰动可放在`test_controls`的interfaces中。
`geo_check_interfaces(method='bore_clearance')`接受最终闭合朝外Polygon `target_group`、SOP local `axis`、同轴`start/end`与正数`radius`。以外切24边棱柱覆盖声明圆形空域，只在声明的轴向区间与该组做有界Boolean Intersect；零交集pass，有效侵入fail并给交集包围盒，不完整组/模糊结果unverified。对带铰耳的叶片，区间应覆盖需要打孔的板厚，不能把整件总包围盒当板厚；通过不证明区间外通畅、孔位归属、周围材料或公差。预算为目标面数×24，受`max_pairs`与目标组4000面上限约束。
| `test_controls(controller, output, tests, interfaces=None, allow_foreign=None, *, domain=None, topology=None, baseline_interfaces=None, views=None, view_bounds=None)` | 可恢复数字控制测试，必须exec：1..16个 `{id,values:{parm:number},expectations:[{metric,axis?,group?,delta:[min,max]}],interfaces?}`，每个case最多16个expectations；同一扰动的大检查用相同values拆成多个case。metric支持bounds_size/center/min/max(axis)、point_count、primitive_count、area、point_mean(axis)、boundary_edges、piece_count、max_point_displacement/mean_point_displacement；max_transform_error另给16数row-major仿射transform，测实际点相对声明变换的最大残差。位移/变换要求稳定唯一id_attrib和相同Polygon拓扑。range验基准/扰动绝对范围，至少一项delta排除0。顶层interfaces在基准和全部case复查，baseline_interfaces只验基准，case内interfaces只验对应扰动；适合合盖接触与开盖分离等不同合同，均用geo_check_interfaces的schema和预算。control_summary区分已声明与实际执行的关系覆盖；基准失败时参数零写入且results=[]明确标not_run。domain/topology复查声明关系；恢复参数/keys/frame及完整bgeo内容（内嵌Packed临时地址转内容引用、忽略对应writer索引偏移；排除导出头date/派生group_summary，组目录按名规范排列；保留成员及组内顺序）。Polygon/Mesh/Sphere/Tube/点支持范围各指标明确，嵌入PackedGeometry在内存副本展开量测，原载荷/属性/变换按内容指纹验证恢复，其他写前unverified。拒绝callback/menu/button/multiparm/tuple列表值，foreign需单次授权；只证明声明case，非外部副作用恢复或艺术/强度认证 | dict |
| `geo_piece_stats(node, piece_attrib=None, sample=16, *, inspect=False, group=None, basis=None, integrity_only=False)` | 默认统计primitive piece局部bbox/extent/面积；无piece属性用内存Connectivity SOP Verb。inspect=True按精确primitive组观察有界Polygon边界/非流形/边连通、正交basis下extent、surface_area、duplicate_boundary_faces、closed_planar_components及center_axis_surface_hits。仅近看Polygon完整性时用inspect=True, integrity_only=True：跳过昂贵的中心线/截面诊断，最多100000 prim/400000顶点引用，返回非流形、相邻面朝向冲突、闭壳有向体积符号、显式N与几何朝向相反的样本、零面积/零边及完全重复面风险；平面大面以重复点桥接孔时另报planar_repeated_point_ngons/shading_review_status，提示同角度近景复核，不把合法布线判破面。负号提示核对整壳朝向，嵌套空腔的内壳可有意反向，不能自动判错。开放边单列open_boundary_unreviewed，可能是有意接口，需按设计核对。风险/超预算在Bridge摘要与执行提醒中保留；no_detected_integrity_risk只表示本检查未发现列出的风险，不认证任意重叠、自交、接触、外形、着色或强度。普通完整inspect仍保持原预算与语义；不支持或超预算为unverified | dict |
| `geo_frame_diff(node, frame_a, frame_b, attrib='P', sample=4096, tolerance=1e-6)` | 用geometryAtFrame比较两帧point数值属性，correspondence为point_number，不能证明跨拓扑变化的稳定身份。可比较时精确返回键`mean_delta`、`max_delta`、`delta_percentiles.{p50,p90,p99}`、`component_delta.{min,max,mean}`、`unchanged_pct`（另含sampled_points/tolerance/data_type/size），不是`mean/max`。不移动playbar；只证明所声明对应与抽样范围内的数据变化，不单独证明审美/运动语义 | dict |

`test_controls` 的顶层、基准及单个case接口均可声明`solid_overlap`；
有转轴的活动产品要逐状态检查实体禁穿插，并另验同轴与真实孔道。
同一接口还可声明`method=component_count`、`target_group`和`expected_components=1..32`：
在最终Polygon组上计共享边连通岛，缺组/数目不符fail，非Polygon/退化面unverified，
最多20000面/100000顶点引用。期望数量先从要求或独立核对事实得出；计数通过不证明
各岛的位置、身份、完整外形或与主体连接，仍需分别检查。

失败诊断：`verify_network`/`build_module` 的 `cook_details.source_context` 在能映射到Wrangle时返回编译行附近的有限源码摘录；编译行可能属于生成VEX，不能未经核对直接patch。`test_controls` 在基准显式强制cook失败时零参数写入；恢复时的 `geometry_restore` 给出完整bgeo签名与有界差异位置，参数通道匹配不能覆盖几何不匹配。已知字符串属性的内部名称表可因cook顺序重排；签名同步重映射索引并比较每个元素的真实字符串，不把等值表顺序误判为几何漂移。

接口距离检查按可用字符串 `name`/`part` 返回有界的源点/目标面身份分布；自我验证拒绝同时返回共享点数量与样本。身份标签只用于诊断，不能认证语义或ownership；共坐标的独立点不被当作共享身份。工具不自动过滤混入零件，也不放宽阈值。
`test_controls`所有可识别合同的结果（包括基准零写入失败与恢复异常）携带同一contract_sha256；标识包含控制器runtime节点identity，不同控制器的成功不会清除彼此失败，同控制器成功复测可匹配旧失败。
可选views最多两个iso/front/side/top，先生成baseline_captures，再在每个case复用同一framing/depth包络和frame。
view_bounds为世界坐标[min_xyz,max_xyz]，应覆盖全部测试状态；省略时锁定基准包络。超界不自动重新取景；
捕获缺失/失败使capture_status和整体状态保持unverified，数值case结果及恢复证据另保留。observed只证明捕获事实，语义仍未验证。

`test_controls`回执提供案例通过数和`relationship_scope`、接口/拓扑声明数；Host原样展示。关系为`not_checked`时，通过数只代表已声明测量。
`geo_piece_stats(...,inspect=True)`（含integrity_only）含`planar_face_crossings`：只检查单个近似平面闭合Polygon内非相邻边的严格内部交叉，返回面数、原始primitive/边索引/位置样本和检查覆盖。每面最多256顶点、每查询最多250000对边；超预算只使该诊断`status=unverified, coverage=partial`，其他已完成观察仍保留。三角形不可能严格自交，不计作覆盖缺口；非平面/退化面、端点接触、共线重合与跨面交叉不在此诊断范围。合法孔洞桥的重复边不因本项判错。命中加入非阻断`risk_reasons`，不修改`ok/healthy`；未命中不证明任意3D自交不存在。含不支持曲线/native/packed的混合输出须检查对应Polygon组或源模块。正反例与覆盖预算见[平面面内交叉回归](../tools/tests/dsh-planar-face-crossings.test.py)，证据展示见[模型回执回归](../tools/tests/houdini-tool-presentation.test.mjs)。

所有显式验证输出均回`bbox_size_sop_local_mm`（不依赖节点名称），用HIP的`scene_unit_length_meters`换算SOP局部包围盒逐轴跨度。仍须核对OBJ缩放及图纸尺寸归属，不凭包围盒认证部件。

`geo_piece_stats(...,group=...)`只检查显式组；局部组各自零风险不能覆盖组与组之间的完全重合面，Host不另推导整件通过。

### component 域（普通 SOP 组件交换）

| 动词 | 语义 | 返回 |
|---|---|---|
| `component_export(node, filename, contract)` | 候选：当前作者普通SOP subnet导出至已命名$HIP内新.dshcomponent；contract必含module_id/revision/units/outputs，可选inputs声明公共输入槽位（唯一0..63），输出索引须由sop_set_output发布。运行时verb_help提供可执行的最小示例和字段约束；检查公共输出、有限依赖与快照。同构建往返，不覆盖文件，不证明装配质量；文件写入不可Undo | dict |
| `component_import(parent, filename, expected_sha256, name, trusted=False)` | 候选：显式可信、hash固定、同构建普通subnet片段导入当前作者SOP父网络；SHA-256接受大小写十六进制并返回规范小写；新名字、不覆盖、不接管旧节点，返回待验收candidate。原生档案可执行代码，trusted不构成安全沙箱；尚非自动子作者交付通道 | dict |
| `component_replace(node, candidate, dry_run=True, expected_plan=None, expected_contract=None, migration=None)` | 候选：同作者同父普通subnet的显式替换；先预览，再用未过期plan提交。输出接线总是迁移；已连接根输入、公共参数值/keys及其外部表达式消费者只在migration显式声明时迁移（inputs逐槽映射、public_parms按名），未声明即拒绝，不按位置猜。保留旧网络不删除/改名；plan失配按侧命名（old手改=保留的本地分叉/candidate被改/消费者接线变化/身份重建/迁移面漂移）。expected_contract恰含module_id+正整数revision，把候选钉在本session导入记录的合同上，拒绝迟到的旧修订与无provenance候选。带表达式的keyframe、keyframed消费者、不可识别的表达式引用形态明确拒绝；任何失败逆序恢复接线/表达式/参数值（回滚账本先登记后变更，恢复失败聚合上报RuntimeError）。提交后仍须实际装配关系/视觉复验 | dict |

### runtime 域（运行时包自省）

| 动词 | 语义 | 返回 |
|---|---|---|
| `tool_catalog(query='', kind=None, category=None, origin=None, offset=0, limit=64)` | 当前Houdini实际node_type/Shelf/Panel/Viewer State/Radial注册目录，分页有界查名称/标签；category精确原生类别，origin按资源位置区分factory/external/embedded/unknown，不认证发行方。保留hidden/deprecated，GUI缺失明确unavailable，不扫描磁盘或执行工具；不是授权/安装账本 | dict |
| `tool_inspect(kind, name, category=None, include_code=False, max_chars=16000)` | 精确读取当前工具来源、HDA实际/候选定义、界面和实例，按需读取有界公开脚本；node_type/viewer_state要求category，不建临时实例。Package归属只报告原生root路径关系；编译节点内部实现、独立state源码未知不猜测。发现不授权修改 | dict |

### cop 域（Copernicus 图层与关系）

| 动词 | 语义 | 返回 |
|---|---|---|
| `cop_layer_stats(node, output=0, *, max_pixels=4194304)` | 必须exec：直接读取当前ImageLayer，output为源输出名/索引；完整buffer统计/指纹、类型/通道、data/display window、空间、pixel scale、frame、U/V梯度。max_pixels为1..16777216，超预算拒绝不抽样，预算不限制上游GPU cook分配。拒绝Manual、失败cook、非图层和未支持storage；非有限值fail，sticky Cache新鲜度unknown；不证明视觉或外部文件最新 | dict |
| `cop_compare_layers(before, after, *, before_output=0, after_output=0, expected_delta=None, tolerance=1e-6, max_pixels=4194304)` | 必须exec：测after-before，完整通道/窗口/空间对齐，不静默重采样；无expected_delta仅量测status=unverified。expected_delta={node,output?}时检验max(abs((after-before)-expected_delta))<=tolerance，返回实际操作数/公式/误差；非有限、错位拒绝，sticky Cache不认证通过；不判断作者选对了数学对象或艺术效果 | dict |
| `test_cop_controls(controller, output, tests, *, output_port=0, max_pixels=4194304, allow_foreign=None)` | 必须exec：1..16个{id,values:{parm:number},expectations:[{metric,channel,delta:[min,max],range?}]}；metric为mean/min/max/mean_abs_change/max_abs_change，变化指标基准0。每case至少一项非零预期，range验基准与扰动；复用参数/keys/frame恢复并比较完整图层/元数据指纹。拒绝菜单/回调/multiparm/tuple、Manual、sticky Cache和无效基准；恢复失败抛CheckpointError，已恢复的失败仍fail。仅声明case/输出范围，不恢复外部文件/Python/solver副作用，不替代语义读图 | dict |

### stage / USD 域（Solaris 只读自省）

| 动词 | 语义 | 返回 |
|---|---|---|
| `usd_stage_summary(node, max_paths=64)` | 概览某 LOP 输出 stage 的 geometry/material/light/camera/RenderSettings/Product/Var，材质绑定、time-sampled 属性及 cook warning；路径按组限量但计数完整 | dict |
| `usd_prim_info(node, prim_path, max_properties=200)` | 检查单个 USD prim 的属性、primvar、relationship、material binding、time samples；points/topology 等大数组只报结构不整段拉取 | dict |

### tool package 域（原生工具包开发与注册）

Package是原生加载配置，不是任意代码沙箱。默认JSON直接指向用户确认的唯一资源源码目录，不复制为构建/安装副本、不生成ZIP、不限定DSH名称或版本目录。工具创建/维护与归入旧包/新包分别选择；明确源码位置及注册JSON位置，已确认选择沿用。扩展旧包通常使用现有DSH文件工具及HDA动词维护相关文件，路径已覆盖时不修改注册JSON；未知字段/条件/依赖保留。发现、注册和当前进程动作分别报告事实，不建额外包账本。

| 动词 | 行为与边界 | 返回 |
|---|---|---|
| `package_catalog(directories=None, query='', offset=0, limit=64)` | 顶层原生JSON配置与当前Houdini加载记录合并查询；默认实际扫描目录或明确目录，区分磁盘配置/条件/加载，不读全部源码、不递归子目录。支持普通包名、多个资源位置和未加载包，未知动态条件不猜算 | dict |
| `package_inspect(package_file, *, files=None)` | 精确只读原生注册配置、hash、多资源路径、当前加载及浅资源/显式文件事实；兼容hpath/path/env写法，公共脱敏投影不能当原文件写回。注册名称冲突由action预览检查；实际来源不证明授权、可用性或完整依赖，条件未知明确unresolved | dict |
| `tool_package_create(resource_root, package_file, *, houdini_versions=None, enable=True)` | 仅创建全新原生JSON，追加指向明确的既有源目录；不复制源、不加载、不创建无用途目录，不覆盖已有JSON或写$HFS。兼容版本声明可选，是加载条件而非测试证书，返回真实注册和源码位置 | dict |
| `tool_package_action(package_file, action, *, dry_run=True, expected_sha256=None)` | 明确原生配置的当前进程load/activate/deactivate/unload，预览默认零写入，可核对配置hash；不改持久enable/条件/依赖，不删除注册或源，不强制清理缓存/窗口。保护当前HDA实例依赖，加载/根错位/部分失败保留真实状态；当前动作不证明下次启动状态 | dict |

### asset 域（HDA / 数字资产）

通用参数界面和绑定属于parm域，HDA入口保留资产语义。定义写入同时核对session创建库的真实指纹与全部受影响实例；已有库必须单次明确allow_foreign，不由自有新实例授予写入权。所有路径拒绝写$HFS；单次授权不认领已有定义。代码、界面与保存复用同一调用的定义/库恢复合同。

| 动词 | 语义 | 返回 |
|---|---|---|
| `hda_create(node, name, description=None, hda_file=None, min_inputs=0, max_inputs=0, replace=False, allow_foreign=None, *, max_outputs=None)` | 转为全新独立类型/库，默认 `$HIP/otls/<name>.hda`；已有类型/目标文件和replace=True拒绝，不破坏旧实例或多资产库。成功登记实际新库与定义的session写入来源，实例ownership不授予外部定义权限。max_outputs为1..64端口上限；spare迁移、新实例和公共输出仍须验证 | dict |
| `hda_fork(node, name, hda_file, description=None)` | 只读复制实际源HDA定义到不存在的新类型/独立库，保留源定义及所有实例；不自动建实例或迁移用户内容。成功登记新库/定义，返回category/type/source_library等真实身份；官方可见可编辑HDA也可分叉，编译实现不支持 | dict |
| `hda_version(node, version, *, dry_run=False, allow_foreign=None)` | 在实际来源库追加同scope/namespace/base的原生::version定义，旧版本/其他定义保持，不另存交付副本、不迁移实例；重复目标拒绝，本调用失败恢复库和新增类型。foreign库授权单次且不认领。仅复制已保存定义 | dict |
| `hda_switch_version(node, type_name, *, dry_run=False, allow_foreign=None)` | 指定单个已锁定实例切换同家族精确已安装HDA版本；原生保留名字/公共参数通道/连线，使用新版内部网络。未保存内容先hda_edit处理；根/被替换后代须授权。当前session自有实例仅登记本次切换新建的内部identity，不认领已有节点或foreign实例的后代。回调外部副作用不受scene undo保证 | dict |
| `hda_get_section(node, section='PythonModule')` | 读 HDA section 内容；section 不存在时列出现有 section 名供自纠 | dict |
| `hda_set_section(node, section, code, allow_foreign=None)` | 全量写section；先语法预检，核对库来源与共享实例，写后逐字回读，失败恢复本调用sections/库/根界面/通道。后续exec失败不撤销此前成功库写入，任意回调副作用不属恢复范围 | dict |
| `hda_patch_section(node, section, old, new, count=1, allow_foreign=None)` | 锚点局部替换：`old` 必须恰好出现 `count` 次（0 = 锚点没找到，>count = 锚点不唯一需加长），替换后同样过语法预检；**模块改局部时用它，不要全文重发** | dict |
| `hda_set_interface(node, spec=None, keep_std=True, hide_builtin_tabs=False, allow_foreign=None, *, edits=None, expected_sha256=None, dry_run=False, layout=None)` | spec/layout整组重建，均检查共享实例ownership；layout与spec/edits互斥，最多512条/12层。支持label/ramp、tuple、multiparm、条件及组件；SOP标准输入Label隐藏。dry_run各模式统一返回ok=true、dry_run=true、applied=false、scene_writes=0，只表示预检成功；spare冲突写前拒绝。edits成功保留旧通道，重建成功不保证旧通道；重建写后失败恢复本调用定义section、实例界面/通道及磁盘库（<=32MiB、64实例、每实例512通道），返回restored/restore_errors。定义写入独立于场景Undo，后续exec失败不撤销已成功的库写入，外部副作用不保证恢复 | dict |
| `hda_edit(node, action, *, dry_run=False, expected_plan=None, discard_changes=False, allow_foreign=None)` | 受控unlock/save/lock/promote，不拆包。先dry_run取得plan_sha256，应用须expected_plan匹配库/定义/源码/实例状态；<=32MiB库、512后代、64实例、2MiB源码。save要求解锁且无实例界面覆盖；promote显式提升源spare界面并保留已有根参数/keys/locks，拒绝其他实例覆盖与既有模板删除/变型。共享写入检查所有实例；lock丢弃内部修改须discard_changes=True且后代也获授权；unlock不授予后代ownership。save/promote写后失败恢复本调用定义/根界面/通道/磁盘，不保证外部副作用或后续exec失败恢复。返回状态/哈希不证明公共输出、回调、GUI或依赖通过 | dict |

#### HDA界面增量合同

`edits`逐项作用于同一份内存模板，所有项预检通过后才写入：

- `{"op":"update","name":"参数内部名","fields":{...}}`：fields支持label/help/hidden/join_next、min/max/min_strict/max_strict、hide_when/disable_when及字面标量default。默认值修改拒绝菜单、回调、表达式默认和非标量；条件使用原生大括号语法，空字符串清除条件。改变默认值保留已有实例当前值。
- `{"op":"add","spec":{...},"folder":"已有folder内部名"}`：spec采用现有创建条目；folder省略时追加到原始定义顶层。未知字段、重复名字和不存在的目标整批零写入拒绝。
- 当前不支持删除、改名、移动、类型转换、已有callback/menu更新、ramp/multiparm或实例独有界面覆盖；不是任意HDA接口迁移器。最多256模板、64实例、每实例512通道。
- 版本来自类型/库路径/原始DialogScript，写前拒绝过期版本。原始定义不含Houdini自动补齐的部分系统页签；这些页签只供自省，不能作为增量目标。原生序列化参数块保留资产头部、帮助和输入标签；不重建标准页，不运行回调或证明布局/输出。
- dry_run返回changes/affected_instances/applied=False/scene_writes=0；成功应用另返回after_sha256/current_state_preserved/preserved_channels。模板回读与通道保留失败时恢复本调用前DialogScript、通道及磁盘库；这是同步失败恢复，不是断电原子事务或后续exec失败的文件undo。

#### HDA布局创建合同

原始spec新增：label；ramp的ramp_type(float/color)、points(2..16)、basis(linear/constant/catmullrom/bspline)、show_controls；
float/int的components(1..4)、等长default和look(regular/vector/color)，color要求3/4分量。
folder_type增加multiparm_list/multiparm_tabs/multiparm_scroll，default为0..64实例；子字段每层重复需要一个#占位。
普通folder支持ends_tab_group与tab_hide_when/tab_disable_when（单页/单区），multiparm不支持tab条件；hide_when/disable_when为普通模板条件。
通用字段增加hidden/hide_label/disable_when。菜单条件核对实际token，不能从eval返回的索引猜条件值。
string的string_type为regular/node；node使用原生NodeReference并与file互斥。mode组件生成稳定token菜单与相应按需显示区；只是UI结构，不生成业务依赖。

layout组件的字段、选择标准和完整可编辑样例唯一维护于[UI组件参考](../skills/houdini-parameter-ui/references/ui-components.md)。
layout写后检查标签/顺序、类型、tags、默认、组件数、join及条件；原生归并后的folder-set名字需回读，不承诺提交名字原样保留。
ui_analysis只是非阻断建议：未解析引用可能是tuple分量、动态或外部路径，不能据此自动改名。
Ramp/multiparm的创建支持不意味着edits或test_controls已支持它们的状态迁移与恢复。

### render / sim 域（渲染产物）

| 动词 | 语义 | 返回 |
|---|---|---|
| `camera_fit(camera, target, direction='iso', coverage=0.82, width=None, height=None, frame=None, *, dry_run=False, allow_foreign=None)` | 将正式静态OBJ cam拟合到显式SOP世界包络；保留焦距，清lookatpath，求距离/正交宽度，实际矩阵投影回验；无渲染/视口改变。尺寸默认相机值，当前frame。拒绝动画/约束/窗口偏移/自定义lens，失败恢复。ownership与单次allow_foreign适用，持久preview服务永不豁免；dry_run仍exec。Solaris需导入并按实际RenderProduct预检 | dict |
| `render_frame(rop, picture=None, frame=None, timeout=110, *, framing=None)` | 渲染可执行hou.RopNode并验证新鲜产物；USD优先outputimage。可选framing={target:USD资产prim路径,coverage:.82}在renderer启动前检查实际stage所有产品的相机/有效画幅/裁切窗口；不通过或不支持时零渲染，不自动动相机。未传保持艺术裁切/通用ROP语义。临时picture/foreground/frame恢复；bytes/mtime/有界摘要确认fresh，旧文件失败；>110s走job。共享执行端模式取registry渲染单槽，被占即快速拒绝 | dict |
| `render_view(node, direction='iso', frame=None, width=1280, height=720, picture=None, framing='full', coverage=0.82, framing_frame=None, *, output_policy='managed', focus_group=None, isolate=False, projection='perspective', framing_bounds=None, depth_bounds=None)` | 显式SOP→持久proxy→服务相机及对应版本后端，恢复用户状态，服务不删除。output_policy默认managed用于验证；delivery分配最终图到`$HIP/dsh-render/`，两者picture省略或仅安全basename、唯一不覆盖；路径值选explicit，继续服从原$HIP/绝对路径保护。返回artifact含purpose/policy/actual/相对路径/root/run/capture/frame，旧output保留。full完整入镜；detail只缩正交宽度/透视视角，不推进相机，近远裁面错误始终零渲染失败。focus_group指定实际primitive组，可isolate；framing_bounds决定取景，depth_bounds决定全部渲染内容含上下文的深度。A/B用同framing_frame并复用返回framing.bounds/depth_bounds及方向/画幅/模式，越界不漂移。check像素事实与pixels兼容别名、framing.depth_check/crop_reasons、source指纹/stale分别报告；空/error拒绝；源/proxy有cook warning时保留诊断图片和warning，但返回ok=false，不能进入验收完成门。展示格式OCIO编码sRGB；H21缺少匹配空间时明确gamma近似，H22明确拒绝该缺口；EXR/HDR线性；output_color记录方法，不证明语义。共享执行端模式取registry渲染单槽，被占即快速拒绝 | dict |
| `render_check(path, ref=None)` | 亮度/非黑/主色/content bbox；A/B 另给高精度 mean、RMSE、changed/meaningful pixel %、max diff，微小非零不再被舍入成 0 | dict |

### viewport 域（视口/UI）

| 动词 | 语义 | 返回 |
|---|---|---|
| `viewport_screenshot(path=None, frame=None, clean=True, frame_target=None, textures=None, backface_cull=False, *, output_policy='managed')` | **用户屏幕诊断工具**：managed/delivery/explicit路径和artifact合同同render_view；delivery直接生成到`$HIP/dsh-render/`，无命名HIP时两种分配拒绝。PNG/JPEG/BMP/TGA为支持截图格式。用户切空display节点时截到空是正确结果，不能用来证明agent产物；和`render_view(explicit_sop)`对照可区分viewport漂移与真实几何错误。要求独立stash的flipbook/viewport camera；绑定相机先解锁并脱离，按请求frame读取bbox，恢复frame/视图后最后还原相机关联/锁定，setter失败与回读不符保留。候选需属于请求frame、连续稳定且可解码；旧/错误frame/无效/歧义文件不算fresh。flipbook派发已尝试但未确认完成的超时/异常/轮询中断保留managed reservation并标capture_unresolved，避免晚到写入与路径复用竞争；实际输出路径复验失败不登记附件。恢复失败以CheckpointError证据拒绝假成功 | dict |

## 自省、帮助与追踪

list_parms回答“参数叫什么”，read_parms回答“实际值/表达式与引用是什么”；node_info给创建前静态
模板和节点卡，describe给已有节点/数据/帮助元数据。filter是字面子串，不是regex。
静态模板和Shelf创建状态不同；动态菜单须list_parms，不假定stock节点内嵌完整帮助文本。
当前不提供全文离线帮助检索或node_help动词。

Bridge返回结构化verbs ledger、rawUsage、operation-evidence和transaction。Trace与离线报告分别保留
目录广度、调用含动词率、动词密度、成功exec修改覆盖、只读裸探针、Gate拦截与成功裸修改，
不把used/全部目录称为执行成功率。相关代码地图见[架构](architecture.md)。

执行中的geometry_fingerprint只覆盖点面计数、包围盒和最多257个抽样点的位置，signature_scope随结果返回。
未抽到的位置、属性值、primitive拓扑/intrinsics和OBJ变换不在该摘要范围；相等只表示未检测到所覆盖变化。
build_module与camera_fit的dry_run明确applied=false、scene_writes=0，不用动词类别把预览解释成实际修改。

内嵌Packed证据视图最多8层/4096实例，展开前按实例累计预算100000面/250000点/400000顶点/32MiB；只支持PackedGeometry，不加载PackedDisk/Alembic/Fragment或任意外部文件。保留组/属性和实际变换，超限/未知表示保持unverified。最终OUT_ASSET表面检查对part/name分区作完整覆盖，不能以各件健康推断件间连接。细节与边界见[配方参考](../skills/houdini-sop-workflow/references/procedural-recipes.md)。
