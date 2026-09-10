# 工具设计与动词词表

Execution contract version: 30

本页是动词目录唯一真相源；构建从表格生成Host预期名称/hash与client目录。
实现以[helpers](../houdini/python3.11libs/dsh_hou_helpers.py)、
[Bridge注册表](../houdini/python3.11libs/dsh_bridge.py)及运行时verb_help相互校验。
执行边界详见[执行契约](execution-contract.md)，节点知识见[同源节点卡](node-operation-cards.md)。

## 设计原则

动词是稳定意图接口，不是hou的一对一包装；域只是导航，不是权限分类。
低层只读可用query中的HOM逃生舱，已覆盖的裸修改不得旁路。通用机制进入动词/guard，
方法进入按需skill，身份与风格进入preset，常驻guidance只放跨域稳定契约。
未知签名先verb_help，不以失败调用探索返回类型；类型发现、操作知识、运行状态分别查询。

- 新动词必须有跨任务独立意图、稳定参数/返回、错误与恢复边界，不能只为单个对象或提高目录覆盖率。
- 各参数接受Node/path的范围以实际签名为准；涉及foreign修改须单次用户明确授权。
- 写操作须严格设参、主线程执行、记录真实失败和最终事务状态，不catch失败后继续交付。
- 多节点setup与单节点创建分开：tab_apply面向受限真实Shelf组合，不把所有setup压进tab_create。
- 只读describe/list_parms/node_info不能为导航隐式创建或cook重型上游。
- 所有证据都要带范围，cook、关系、渲染像素和视觉语义不互相代替。

## 顶层工具

| 工具 | 作用 |
|---|---|
| houdini_query | code为Houdini只读观察；result_ref为Host历史结果读取（JSON pointer/offset/limit）；source_ref为当前session任务来源读取（index或来源hash，offset/limit）。三分支互斥，两个Host分支不执行HOM；没有allow_raw修改豁免 |
| houdini_exec | 场景修改与作者验证；code为必填，产图通过原生附件返回 |
| houdini_job_submit | 长操作排队异步提交 |
| houdini_job_status | 状态/结果及可选等待 |
| houdini_job_cancel | 协作式取消；不强杀已执行HOM |

工具schema在[src/tools.ts](../src/tools.ts)。Host在每次场景调用前核对Bridge实际词表hash和执行版本，
请求内再附expected_contract校验；失配拒绝并要求重载，不能信任旧成功缓存。
有Host会话身份的exec/jobs提交前带运行实例绑定的request_ref；HTTP断联、超时、坏JSON或错误状态码
返回unknown_transport时，用houdini_query(request_ref=...)查回，不重发code。该分支与code/result_ref/
source_ref互斥，不接受pointer或分页；返回queued/running/done/not_executed/unknown等状态，done回读原结果。
回执只在原runtime有效，结果保留10分钟且总量上限64MiB，最多4096个请求身份；结果过期或超限明确不可取回，
身份墓碑保留到runtime结束以拒绝重复执行，容量满拒绝新登记。未知/过期/换runtime都不能推断未执行。
jobs回执保存的是提交关联，不是完成证据；查回jobId后继续houdini_job_status。job关联在该runtime保留，
不因完整结果的10分钟期限丢失；job实际结果仍服从job registry自身期限。重复回执不启动第二个worker，
过载或worker未启动保留not_executed；队列取消仍阻止HOM运行，运行中取消不强杀。
Host若丢弃整个工具结果，用request_ref='index'查看当前Host会话最近32个已登记引用、owner_call、类型与状态，
按原调用ID选择；索引不暴露代码或结果正文。超范围、未到达Bridge、换runtime或缺失均不证明未执行。
没有跨runtime幂等、自动重提、无限期结果保留或强杀HOM保证；实际Host取消路径仍须新session验证。
兼容入口保留历史调用解释能力，不作为新guidance中的优先创建方式。
表达式设参分别报告language、write_status、evaluation和effect_status；合法零值不算错误。
H21/H22本次新增的原生求值错误明确指向当前参数，或结果为非有限数值时，抛CheckpointError并恢复原参数状态；
strict set_parms同时恢复本批前序参数和动画。failure_stage区分写入失败与求值失败，恢复结果另外报告。
缺失引用的warning、tuple共享warning和其他节点诊断保留范围，不把它们强行归因当前参数；可能前向引用
的表达式允许先写入，但返回warning/unverified。先前cook错误可能在表达式修正后仍缓存；与求值前相同的
错误不冒充本次新增失败，标unverified并要求显式cook/输出复验。read_parms同步返回表达式语言与求值诊断。
这些读取不额外cook或重复求值；表达式通过不证明非空几何、关系或控制效果，继续按显式输出验收。
大返回在当前workspace成功保存完整Bridge返回JSON后才精简默认文本；result-details提供SHA-256和
可用读取入口。`houdini_query(result_ref=hash,pointer='/evidence/0',offset=0,limit=6000)`分页返回选中
字段的JSON文本，limit为1..16000字符，offset为非负整数；pointer遵守JSON Pointer，不是任意路径或代码。
文件按内容hash命名并校验，不跟随单文件symlink；目录必须留在当前workspace。单份上限32MiB。
保存失败保持原有展示，不把已执行修改报成失败；读取缺失/损坏文件也不得重放原场景修改。
canonical metadata与模型文本分别保留：metadata供原生事件、UI、审计和状态投影；Code Mode仍按Host
协议返回完整canonical值，嵌套事件可能不含metadata，此时完整值须由result_ref读取，审计明确标缺口。

## 动词目录

### vocabulary 域（回答「动词怎么调用」）

| 动词 | 语义 | 返回 |
|---|---|---|
| `verb_help(name)` | 返回已注入动词的准确 signature、return_type（无注解则null）、call_mode与docstring；未知名列相似项。Bridge对签名绑定错误返回真实signature和零写入证据，实施内部TypeError不冒充绑定失败。用于在调用前发现契约，不靠失败或读取仓库源码猜参数/返回形状 | dict |

### 类型目录（回答「能建什么」）

| 动词 | 语义 | 返回 |
|---|---|---|
| `search_tab_menu(category, query)` | 列出某 context 下匹配的节点族 + 最新版 | dict |
| `search_tab_entries(parent, query)` | 按真实父网络列当前可见的 node/tool entry；排除 hidden/deprecated，Material Library 根层只暴露 Builder tool；每项标 `kind` 与 dsh 是否可安全执行 | dict |
| `resolve_latest_type(category, base)` | 某族最新版全名（内部为主）；只以 namespace 注册的族返回带前缀全名（'rigdoctor' → 'kinefx::rigdoctor'），裸别名过不了 `createNode(exact_type_name=True)`；跨 namespace 同名按排序取第一个，recipe 需跨版本一致时应显式钉命名空间 | str |

### node 域（场景图）

| 动词 | 语义 | 返回 |
|---|---|---|
| `tab_create(parent, type_name, name=, inputs=[...])` | 建**单个可见节点**：最新版 + 对应 shelf 初始化；初始化失败会清理 partial create 并向外抛错，绝不静默降级成裸节点；拒绝 hidden/deprecated 和 Material Library 根层直建 shader，setup/builder 改用 tab_apply；parent 接受 Node/path。连完 inputs 后自动落位：有输入时放到所有输入下游（x = 输入 x 均值，y = min(输入 y) − 垂直间距）；无输入时放到父网络现有内容右侧新列（x = max(现有 x) + 水平间距，y = 现有最顶部 y，空网络落原点）；间距由节点实际网络尺寸（`Node.size()`）推导，不用拍脑袋常量 | `hou.Node` |
| `tab_apply(parent, tool_id)` | 应用 allowlist 内的非交互 Tab setup recipe，返回全部新增节点/输入；GUI 恢复 Network Editor pwd/selection，同一 exec 多次调用共享用户基线；headless 同语义。首批仅 Karma Setup / Karma Material Builder。SideFX recipe 自己摆节点，tab_apply 不做自动落位 | dict |
| `find_nodes(pattern="*", category=None, node_type=None, root=None)` | 找**已存在**节点（扁平清单） | path 列表 |
| `graph(node, depth=1, direction='both')` | 围绕**该数据节点**查 inputs / outputs / parm_refs；检查最终 SOP 网络应对 `OUT` 向上查，不要对父 OBJ 容器调用 | dict |
| `describe(node)` | 状态 + 几何摘要 + `attrib_delta`（相对 input 0 的属性增删——MMB 节点信息里「这个节点对数据干了什么」的固化）+ 帮助元数据 | dict |
| `node_provenance(node)` | 报告 runtime owner、可复制的 audit tag、当前 session 是否可写；`foreign`/`owned_current_session`/`owned_other_session`/`dsh_service` 分开 | dict |
| `connect(src, dst, index=0, *, allow_foreign=None)` | 严格数据流连线（src 输出 → dst 指定输入）；只有一个端口参数index，第4位置参数拒绝；权限理由必须显式keyword非空字符串。mutation 边界在 dst；**OBJ→OBJ 拒绝**，改用 `set_object_parent`。端口错误不再改接下一个输入；连接后仅在 dst 违反自顶向下流时调整落位 | dict |
| `node_info(parent, type_name, parm_filter='', limit=24)` | 创建前读取实际parent最新版类型、端口、参数默认值/组件名/menu token/set_value与帮助URL；operation_card含决策/版本，operation_parameters保留不受filter/limit裁切的关键设置，缺字段显式报告。不建临时节点/不运行Shelf；动态菜单需list_parms，truncated明示。没有delivery准入 | dict |
| `build_module(parent, nodes, output, dry_run=False, interfaces=None, *, required_outputs=None)` | 新增1..64个{name,type,parms?,inputs?} SOP节点，inputs为更早spec/现有child名，None跳输入。独立静态错误汇总零创建拒绝；size=1/组件按标量校验，只有多分量tuple接受等长数值列表，与实际setter同源。operation_advisories按类型/缺少显式决策合并，非阻断、不改默认值、不证明语义；dry_run用于未决设置。required_outputs可检查1..16必需新分支，可附实际interfaces。返回validation/interface_checks；失败清理新节点，不覆盖已有节点/flags | dict |
| `verify_network(parent, output=None, nodes=None, limit=512, require_valid=True)` | SOP checkpoint：必须显式 output，省略即报可操作错误，绝不跟随 display。默认检查 parent 直属范围，可 nodes 限域；error/空输出默认抛 CheckpointError 并保留结构证据，require_valid=False 仅供诊断。warning独立，scope/时间/frame/输出指纹与失败原因前置；不证明关系/视觉 | dict |
| `set_object_parent(child, parent, keep_world=True, reason='', index=0, allow_foreign=None)` | 显式 OBJ parenting/unparent（`parent=None`），自然参数序为 child→parent；普通父级用 input 0，Blend 等明确多输入对象可指定 index。`reason` 限 `scene_assembly/camera_light_null/existing_legacy/explicit_user/downstream_obj_delivery`，新建几何 FK 不属例外。拒绝非 OBJ、自环/层级环；mutation/ownership 边界在 child；默认恢复 child 原世界变换并回读 parent、local/world delta | dict |
| `disconnect_input(dst, index=0, *, allow_foreign=None)` | 断开普通网络 destination 输入；权限理由keyword-only非空字符串；OBJ unparent 拒绝并指向 `set_object_parent(child,None,...)`；ownership 边界在 dst，返回原 source path（若本来为空则为 null） | dict |
| `rename_node(node, name, allow_foreign=None)` | 重命名 | 新 path |
| `delete_node(node, allow_foreign=None)` | 删除（返回被表达式引用的上游）；拒绝删除 owner-tagged `render_view` 会话级基础设施，避免进入 H21 OpenGL teardown fatal 路径 | dict |
| `cook_node(node, force=False, timeout_ms=30000)` | cook + error/warning，timeout_ms为1..120000的协作预算，仅原生中断检查点可响应，不保证强制停止/内存安全。Manual返回ok=False/status=not_cooked_manual，不自动切Auto；预检至多512上游节点的已知VEX删除循环。warning未解释不得当完成 | dict |
| `sop_set_output(node, render=True, allow_foreign=None)` | 把 SOP singular display/render 旗标移到输出节点；属于用户 viewport/交付状态，不是 render_view 前置条件 | dict |
| `sop_output_node(parent)` | 报告 SOP 网络 display/render 输出；旗标不在链尾时提醒 | dict |
| `set_object_visible(node, visible=True, allow_foreign=None)` | 设置单个 OBJ 的 viewport visibility（OBJ 没有 SOP 式 render flag） | dict |
| `visible_objects(root='/obj')` | 列出 OBJ 层 plural visibility/effective visibility，并附每个对象的 provenance | dict |
| `layout_nodes(parent, nodes=None, horizontal_spacing=-1, vertical_spacing=-1, allow_foreign=None, mode='children')` | `mode='children'`（默认）= 原生 layoutChildren，行为不变；`mode='flow'` = 自研拓扑分层：按最长路径深度分行（深度 0 最上，y = −depth × 垂直间距），同深度按节点当前 x 排序保持左右阅读顺序、等距排开并整体居中，有环时按原顺序兜底不断裂；spacing 默认从节点实际尺寸推导，显式正值覆盖。host task 中 `nodes=None` 只布局当前 session 创建项并回报 `foreign_nodes_skipped`；显式列表逐项过 ownership guard。Python Shell 无 host owner 时保持传统全布局语义 | dict |

### compatibility 域（仅历史回放，不进新 guidance）

| 动词 | 语义 | 返回 |
|---|---|---|
| `set_display(node, render=True, allow_foreign=None)` | deprecated 兼容 wrapper：按节点 context 路由 SOP output / OBJ visibility | dict |
| `display_node(parent)` | deprecated 兼容 wrapper：按父网络 context 路由 SOP output / OBJ visibility | dict |

### parm 域（依附 node）

| 动词 | 语义 | 返回 |
|---|---|---|
| `list_parms(node)` | 参数**目录**：名字/标签/类型/帮助/默认值及实际 menu token/index/label（不给当前值）；动态菜单以实际节点为准 | list |
| `read_parms(node, changed_only=True, *, names=None)` | 参数**值**：默认只看非默认 + 带表达式/动画 + 被引用的（意图解读）；names可选1..32个唯一标量字段，按请求顺序返回且不受changed_only过滤，缺失报错。无动画string含原始UTF-8源码source_sha256，展开值不同于原文时另含raw_value；表达式附referenced_parm，被引用标referenced_by；动画附time_dependent/key_count/first_frame/last_frame/curves，不默认倾倒全部keys | list |
| `set_parm(node, name, value, allow_foreign=None)` | 设参（数值字符串=表达式）。已有表达式/keys在普通赋值时清除，note说明变化。字面string可传`{expected_sha256,patch:[{old,new,count}]}`：精确版本和次数、全部锚点先验，拒绝锁定/动画/表达式/callback/固定菜单；返回patch前后hash/字符数/次数及value_omitted，不回传整份源码。最多32项，source/result各524288字符、替换文本累计131072字符、count为1..256；不执行正则/脚本。文本通过不证明cook/几何通过 | dict |
| `set_parms(node, values, allow_foreign=None, strict=True)` | 默认严格批量设参：预检名称/重叠/锁定；value支持set_parm的string patch对象，本节点本批全部patch在任何设参前验证。patch只允许strict=True，set内返回变化摘要，patched列出字段；失败恢复本批值/表达式/keys。其他节点不在本批预检范围，参数回调/外部文件不属快照回滚。无patch的显式strict=False仍返回ok/set/failed；Menu string为精确token，数值string为HScript表达式，表达式对象可声明language | dict |
| `set_keyframes(node, channels, replace=True, allow_foreign=None)` | 批量写数值标量 channel keys；统一 frame 单位，有限曲线 `constant/linear/bezier`，全量预检、失败恢复原 keys、提交后回读/采样并恢复用户 frame。只负责 channel 数据，不代替路径依赖状态机或 KineFX/APEX | dict |
| `create_spare_parms(node, code_parm='snippet', defaults=None, spec=None, allow_foreign=None, *, update_defaults=None, layout=None, dry_run=False)` | 缺省扫描代码参数的 `ch/chf/chi/chv/chs` 引用并创建缺失 spare parameters；`spec=[...]` 的精确条目为 folder `{type,name,label?,parms:[...]}` 或 scalar `{type:'toggle\|int\|float\|string',name,label?,default?,min?,max?,min_strict?,max_strict?,help?}`。spec 返回 `{node,mode,created,leaf_values}`；扫描返回 `{node,code_parm,references,created,existing,defaults_applied,unsupported}`；创建仍拒绝同名覆盖。新建接口后重新赋写code_parm原始源码/keys以刷新编译依赖，保留表达式与动画；返回refreshed_code_parm（未刷新为null），锁定源码在接口写入前拒绝。显式 `update_defaults={name:literal}` 仅更新1..32个已有scalar spare的默认值，与spec/defaults/非默认code_parm互斥；保留当前值/表达式/keys，返回updated前后值及current_state_preserved。支持float/int/toggle/string，拒绝内建/tuple/menu/callback/multiparm及表达式默认值，遵守严格上下限；当前值另用set_parms 新增layout与spec/defaults/update_defaults互斥，复用共享UI组件，默认追加并拒绝已有模板/参数名冲突；dry_run仅layout有效，预览零写入。应用保持已有通道值/keys/locks，失败恢复节点接口及通道，不修改HDA定义或绑定 | dict |
| `parameter_ui(node, max_depth=6, include_state=False, analyze_ui=False)` | 任意节点参数界面只读自省，返回实例/可选定义树、可选raw状态和非阻断结构建议；不要求HDA，不cook/执行菜单，不创建绑定。hda_info保留同形兼容入口 | dict |
| `bind_controls(controller, bindings, *, dry_run=False, expected_plan=None, replace_existing=False, allow_foreign=None)` | 1..32项明确数值绑定：source为控制节点参数名，target为目标参数绝对路径，可选scale/offset。dry_run返回plan_sha256；应用必须expected_plan匹配identity/值/keys/锁定/帧。默认拒绝已有驱动，replace_existing显式替换；拒绝非数值/菜单/回调/multiparm、任意表达式源、批次源目标交叠及重复目标。整数目标只接受整数源与映射系数。实际HScript引用和值回读，失败恢复本批目标通道；不保证领域输出或外部副作用 | dict |

| `set_update_mode(mode, expected_mode)` | 显式切换auto/manual/on_mouse_up，expected_mode防止覆盖过期用户状态；切Auto可能触发全场景计算，不是取消接口 | dict |

### scene 域（工程/时间线）

| 动词 | 语义 | 返回 |
|---|---|---|
| `scene_info()` | 只读 HIP/version/fps/current frame/time/frame range/playback range/UI 状态；明确区分 `has_named_path`、`has_unsaved_changes`、`dirty_reliable`、`clean_on_disk`，不再用路径存在冒充保存完成；hython 的 dirty 不可靠时 clean=null；不移动 playbar、不遍历整张节点图 | dict |
| `scene_save(expected_path=None)` | 只保存当前已命名 HIP，不承担 Save As/open/new；可选 expected_path 作防串场断言，返回 dirty before/after/reliable、clean（headless=null）、bytes、mtime_ns | dict |
| `scene_save_as(path, expected_current_path, reason, overwrite=False)` | 用户授权的 Save As：明确绝对 HIP 路径，expected_current_path 防串场，reason 记录路径/覆盖授权；已存在目标必须 overwrite=True。拒绝插件仓库落盘，回报前后路径/dirty/file/workspace_changed。无 load/clear；文件写不可撤销，失败可能留部分新文件，跨目录后 Open Workspace 重新绑定 | dict |
| `set_timeline(fps=None, frame_range=None, playback_range=None, current_frame=None)` | 设置明确的时间线字段；至少一项，范围校验后回读 scene_info | dict |
| `list_bookmarks()` | 列出 bookmark id/name/start/end/enabled/visible/comment | list |
| `create_bookmark(name, start, end, replace=False)` | 创建整数帧 bookmark；同名默认拒绝，replace 精确替换 | dict |
| `delete_bookmark(name_or_id)` | 按精确名称或 session id 删除，失败列现有项 | dict |

### geometry 域（几何数据）

| 动词 | 语义 | 返回 |
|---|---|---|
| `geo_attrib_stats(node, name, attrib_class='point', *, unique=False, max_elements=100000)` | 数值min/max/mean/count；unique=True全量检查精确完整tuple（含字符串），返回unique_count/duplicate_count/all_unique及至多8个重复样本。用P查精确重叠、用id查身份；超预算/非有限拒绝，无容差焊接或自动删除。point/prim/vertex/detail | dict |
| `geo_point_spacing(node, expected, tolerance, closed=False, order_attrib=None, max_points=10000)` | 全量相邻点弦长验收：默认point number顺序，或唯一数值order_attrib；closed含末→首，SOP local单位；返回全量min/max/failure_count及最多16个最差对与sequence hash。超预算拒绝不抽样；只证明该序列约束，不证明弧长、网格接线或实际零件关系 | dict |
| `geo_check_interfaces(output, interfaces, max_pairs=50000)` | 同一最终SOP内1..16实际关系。默认{id,source_group,target_group,max_distance,expected_points}测独立表面点到面距离；method=axis_gap改用两个primitive组及axis/gap_range/min_overlap，测source.min−target.max与横向区间重叠。空组/自重叠fail，不支持unverified；SOP local有界不抽样。距离/投影范围不是接触、实体插入、碰撞或强度认证；返回实际值/范围/几何hash | dict |
| `test_controls(controller, output, tests, interfaces=None, allow_foreign=None, *, domain=None, topology=None)` | 可恢复数字控制测试，必须exec：1..16个 `{id,values:{parm:number},expectations:[{metric,axis?,group?,delta:[min,max]}]}`。metric支持bounds_size/center/min/max(axis)、point_count、primitive_count、area、point_mean(axis)、boundary_edges、piece_count、max_point_displacement/mean_point_displacement；max_transform_error另给16数row-major仿射transform，测实际点相对声明变换的最大残差。位移/变换要求稳定唯一id_attrib和相同Polygon拓扑。range验基准/扰动绝对范围，至少一项delta排除0。control_summary保留顶层失败原因、失败测量与逐case状态；基准失败的results=[]明确标not_run，不作通过。domain/interfaces/topology复查声明关系；恢复参数/keys/frame及完整bgeo内容（排除导出头date/派生group_summary，组目录按名规范排列；保留成员及组内顺序）。Polygon/Mesh/Sphere/Tube/点支持范围各指标明确，其他写前unverified。拒绝callback/menu/button/multiparm/tuple，foreign需单次授权；只证明声明case，非外部副作用恢复或艺术/强度认证 | dict |
| `geo_piece_stats(node, piece_attrib=None, sample=16, *, inspect=False, group=None, basis=None)` | primitive piece 的局部 bbox/extent/面积与退化统计；无 piece 属性时用内存 Connectivity SOP Verb，不污染网络，能发现「全场 bbox 正常但每个实例零宽/零面积」；inspect=True按精确primitive组观察有界Polygon边界/非流形/边连通及正交basis下extent，observed仅为量测完成，方法不支持保持unverified | dict |
| `geo_frame_diff(node, frame_a, frame_b, attrib='P', sample=4096, tolerance=1e-6)` | 用 geometryAtFrame 比较两帧 point 数值属性；可比较时精确返回键 `mean_delta`、`max_delta`、`delta_percentiles.{p50,p90,p99}`、`component_delta.{min,max,mean}`、`unchanged_pct`（另含 sampled_points/tolerance/data_type/size），不是 `mean/max`。不移动 playbar；证明数据是否随时间变化，不单独证明审美/运动语义 | dict |

### stage / USD 域（Solaris 只读自省）

| 动词 | 语义 | 返回 |
|---|---|---|
| `usd_stage_summary(node, max_paths=64)` | 概览某 LOP 输出 stage 的 geometry/material/light/camera/RenderSettings/Product/Var，材质绑定、time-sampled 属性及 cook warning；路径按组限量但计数完整 | dict |
| `usd_prim_info(node, prim_path, max_properties=200)` | 检查单个 USD prim 的属性、primvar、relationship、material binding、time samples；points/topology 等大数组只报结构不整段拉取 | dict |

### asset 域（HDA / 数字资产）

通用参数界面和绑定属于parm域，HDA入口保留资产语义。

| 动词 | 语义 | 返回 |
|---|---|---|
| `hda_create(node, name, description=None, hda_file=None, min_inputs=0, max_inputs=0, replace=False, allow_foreign=None)` | 把已有节点（通常 subnet）转为数字资产：自动建 otls 目录、默认 `$HIP/otls/<name>.hda`。`replace=True` = 整体重建：所有待销毁实例逐项通过 ownership guard 后，卸载旧定义并覆盖文件；否则同名冲突报错并提示 replace | dict |
| `hda_info(node, max_depth=6, include_state=False, analyze_ui=False)` | 资产/参数界面只读自省：类型/定义文件/section、实例interface与definition.interface，含范围/默认表达式/回调/菜单生成器/条件/tags、单页tab_conditionals、tuple look与Ramp类型。interface_sha256绑定类型/库路径/DialogScript；include_state返回至多512通道的raw_value/keyframes/locked。analyze_ui返回树计数/深度/截断及非阻断引用、标题和密集行建议，不执行菜单/表达式/cook，不自动修复或认证视觉。普通节点也可用 | dict |
| `hda_get_section(node, section='PythonModule')` | 读 HDA section 内容；section 不存在时列出现有 section 名供自纠 | dict |
| `hda_set_section(node, section, code, allow_foreign=None)` | 全量写 section。`PythonModule` 先 `compile()` 预检语法（带行号报错，不写脏）；写后读回校验一致 | dict |
| `hda_patch_section(node, section, old, new, count=1, allow_foreign=None)` | 锚点局部替换：`old` 必须恰好出现 `count` 次（0 = 锚点没找到，>count = 锚点不唯一需加长），替换后同样过语法预检；**模块改局部时用它，不要全文重发** | dict |
| `hda_set_interface(node, spec=None, keep_std=True, hide_builtin_tabs=False, allow_foreign=None, *, edits=None, expected_sha256=None, dry_run=False, layout=None)` | spec/layout为整组重建；layout与spec/edits互斥，展开可选section/row/remap/repeater为原始spec，最多512条/12层，检查所有同定义实例ownership。支持原有控件及label/ramp、数值components(1..4)/look、multiparm folder与tab条件；布局指南见工具开发skill。dry_run对三种模式均零写入预览，仍须exec。只有edits模式提供旧通道状态保留与同步失败文件恢复，范围见下方；layout/spec不是兼容迁移器，写后失败须按实际文件恢复，不扩大undo保证 | dict |

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

layout组件的字段、选择标准和完整可编辑样例唯一维护于[UI组件参考](../skills/houdini-parameter-ui/references/ui-components.md)。
layout写后检查标签/顺序、类型、tags、默认、组件数、join及条件；原生归并后的folder-set名字需回读，不承诺提交名字原样保留。
ui_analysis只是非阻断建议：未解析引用可能是tuple分量、动态或外部路径，不能据此自动改名。
Ramp/multiparm的创建支持不意味着edits或test_controls已支持它们的状态迁移与恢复。

### render / sim 域（渲染产物）

| 动词 | 语义 | 返回 |
|---|---|---|
| `camera_fit(camera, target, direction='iso', coverage=0.82, width=None, height=None, frame=None, *, dry_run=False, allow_foreign=None)` | 将正式静态OBJ cam拟合到显式SOP世界包络；保留焦距，清lookatpath，求距离/正交宽度，实际矩阵投影回验；无渲染/视口改变。尺寸默认相机值，当前frame。拒绝动画/约束/窗口偏移/自定义lens，失败恢复。ownership与单次allow_foreign适用，持久preview服务永不豁免；dry_run仍exec。Solaris需导入并按实际RenderProduct预检 | dict |
| `render_frame(rop, picture=None, frame=None, timeout=110, *, framing=None)` | 渲染可执行hou.RopNode并验证新鲜产物；USD优先outputimage。可选framing={target:USD资产prim路径,coverage:.82}在renderer启动前检查实际stage所有产品的相机/有效画幅/裁切窗口；不通过或不支持时零渲染，不自动动相机。未传保持艺术裁切/通用ROP语义。临时picture/foreground/frame恢复；bytes/mtime/有界摘要确认fresh，旧文件失败；>110s走job | dict |
| `render_view(node, direction='iso', frame=None, width=1280, height=720, picture=None, framing='full', coverage=0.82, framing_frame=None, *, focus_group=None, isolate=False, projection='perspective', framing_bounds=None, depth_bounds=None)` | 显式SOP→持久proxy→服务相机/OpenGL，恢复用户状态，服务不删除。full完整入镜；detail只缩正交宽度/透视视角，不推进相机，近远裁面错误始终零渲染失败。focus_group指定实际primitive组，可isolate；framing_bounds决定取景，depth_bounds决定全部渲染内容含上下文的深度。A/B用同framing_frame并复用返回framing.bounds/depth_bounds及方向/画幅/模式，越界不漂移。check像素事实与pixels兼容别名、framing.depth_check/crop_reasons、source指纹/stale分别报告；空/error拒绝。展示格式OCIO编码sRGB（无匹配空间时明确gamma近似），EXR/HDR线性；output_color记录方法，不证明语义 | dict |
| `render_check(path, ref=None)` | 亮度/非黑/主色/content bbox；A/B 另给高精度 mean、RMSE、changed/meaningful pixel %、max diff，微小非零不再被舍入成 0 | dict |

### viewport 域（视口/UI）

| 动词 | 语义 | 返回 |
|---|---|---|
| `viewport_screenshot(path=None, frame=None, clean=True, frame_target=None, textures=None, backface_cull=False)` | **用户屏幕诊断工具**：用户切空 display 节点时截到空是正确结果，不能用来证明 agent 产物；和 `render_view(explicit_sop)` 对照可区分 viewport 漂移与真实几何错误。flipbook 异步，设置/相机在落盘后恢复 | dict |

## 自省、帮助与追踪

list_parms回答“参数叫什么”，read_parms回答“实际值/表达式与引用是什么”；node_info给创建前静态
模板和节点卡，describe给已有节点/数据/帮助元数据。filter是字面子串，不是regex。
静态模板和Shelf创建状态不同；动态菜单须list_parms，不假定stock节点内嵌完整帮助文本。
当前不提供全文离线帮助检索或node_help动词。

Bridge返回结构化verbs ledger、rawUsage、operation-evidence和transaction。Trace与离线报告分别保留
目录广度、调用含动词率、动词密度、成功exec修改覆盖、只读裸探针、Gate拦截与成功裸修改，
不把used/全部目录称为执行成功率。相关代码地图见[架构](architecture.md)。
