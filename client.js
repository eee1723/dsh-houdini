// dsh-houdini client half — registers three things:
//  1. the "Houdini Trace" conversation view (parallel to the built-in "chat"
//     and "trajectory" views): a live verb-vocabulary observatory. Left column
//     is the full verb catalog by domain (generated from docs/tool-design.md
//     at build time by tools/gen-client-catalog.mjs) with per-session hit
//     counts lighting up in real time; right column is the true chronological
//     timeline of houdini_* tool results — timestamps, fail/raw-hou/advisory
//     badges, verb chips with durations, and collapsed per-call details
//     (code + full result). Same information architecture as the post-hoc
//     report (tools/trace-report.mjs).
//  2. a preset-aware watermark on the conversation window: sessions whose
//     agentPreset starts with "houdini" get the Houdini swirl + an orange
//     ambient glow, so the mode is recognizable at a glance.
//  3. a one-shot launcher session hint: after an explicit Repair and restart runtime,
//     refresh the public session list and open the Host-created/reused
//     Houdini-preset session. Plain Open Workspace supplies no hint and keeps
//     the user's current conversation untouched.
//
// Hand-written CJS factory matching the dsh client module system (no bundler):
// the bundle only REGISTERS its factory here; the body runs at materialization.
window.__ModuleLoader__.load({
  id: "dsh-houdini",
  factory: function (require) {
    var React = require("react");

    // --- houdini 模式水印 ---------------------------------------------------
    // 会话的 agentPreset 以 "houdini" 开头时，在对话窗口铺一层品牌水印：
    // 居中的 Houdini 旋涡（由官方 badge 的镂空旋涡反相提取，assets/houdini_swirl.png）
    // + 右下角一抹橙色氛围光。旋涡以 base64 内联（2.6 KB），webserver 不 serve
    // 插件静态目录，data URI 是单文件 client bundle 下最简的路子。
    var SWIRL_URI = "data:image/png;base64," +
      "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";

    // 官方先例（dsh-client-ui-agent-preset）：CSS 在 factory 体里注入，
    // 带 data-plugin-css 去重；样式不随 fiber 回收是平台已知限制。
    var watermarkCss =
      ".dsh-houdini-watermark{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden;" +
      "animation:dshHoudiniWmFade .9s ease-out both}" +
      ".dsh-houdini-watermark>.wm-swirl{position:absolute;left:50%;top:44%;width:min(58vmin,540px);" +
      "aspect-ratio:406/420;transform:translate(-50%,-50%);" +
      'background:url("' + SWIRL_URI + '") center/contain no-repeat;opacity:.055}' +
      ".dsh-houdini-watermark>.wm-glow{position:absolute;right:-14vmax;bottom:-16vmax;" +
      "width:48vmax;height:48vmax;border-radius:50%;" +
      "background:radial-gradient(circle,rgba(255,102,0,.09) 0%,rgba(255,102,0,.03) 45%,transparent 68%)}" +
      "@keyframes dshHoudiniWmFade{from{opacity:0}to{opacity:1}}";
    var watermarkCssId = "dsh-houdini/watermark.module.css";
    if (
      typeof document !== "undefined" &&
      document.querySelector("style[data-plugin-css=" + JSON.stringify(watermarkCssId) + "]") === null
    ) {
      var watermarkTag = document.createElement("style");
      watermarkTag.dataset.plugin = "dsh-houdini";
      watermarkTag.dataset.pluginCss = watermarkCssId;
      watermarkTag.textContent = watermarkCss;
      document.head.appendChild(watermarkTag);
    }

    // conversation.composer.dock 上的零占位条目：按当前会话 preset 决定
    // 是否铺水印。useSessions 由会话作用域插槽的标准 kit 提供；
    // ui-agent-preset 已把 agent-preset/selected 事件写回该 store，天然实时。
    function HoudiniWatermark(props) {
      var preset = props.useSessions(function (s) {
        var byId = s && s.byId;
        var sess = byId ? byId[props.sessionId] : null;
        return sess && typeof sess.agentPreset === "string" ? sess.agentPreset : "";
      });
      if (preset.indexOf("houdini") !== 0) return null;
      return React.createElement(
        "span",
        { style: { display: "contents" } },
        React.createElement(
          "div",
          { className: "dsh-houdini-watermark", "aria-hidden": "true" },
          React.createElement("div", { className: "wm-swirl" }),
          React.createElement("div", { className: "wm-glow" })
        )
      );
    }

    // --- 词表目录（构建期生成，勿手改） --------------------------------------
    // >>> houdini-catalog (generated by tools/gen-client-catalog.mjs — do not edit)
    var CATALOG = [{"domain":"vocabulary 域","note":"vocabulary 域（回答「动词怎么调用」）","verbs":[{"name":"verb_help","sig":"name","desc":"返回已注入动词的准确 signature 与 docstring；未知名列相似项。用于在调用前发现契约，不靠失败或读取仓库源码猜参数/返回形状"}]},{"domain":"类型目录","note":"类型目录（回答「能建什么」）","verbs":[{"name":"search_tab_menu","sig":"category, query","desc":"列出某 context 下匹配的节点族 + 最新版"},{"name":"search_tab_entries","sig":"parent, query","desc":"按真实父网络列当前可见的 node/tool entry；排除 hidden/deprecated，Material Library 根层只暴露 Builder tool；每项标 `kind` 与 dsh 是否可安全执行"},{"name":"resolve_latest_type","sig":"category, base","desc":"某族最新版全名（内部为主）；只以 namespace 注册的族返回带前缀全名（'rigdoctor' → 'kinefx::rigdoctor'），裸别名过不了 `createNode(exact_type_name=True)`；跨 namespace 同名按排序取第一个，recipe 需跨版本一致时应显式钉命名空间"}]},{"domain":"node 域","note":"node 域（场景图）","verbs":[{"name":"tab_create","sig":"parent, type_name, name=, inputs=[...]","desc":"建**单个可见节点**：最新版 + 对应 shelf 初始化；初始化失败会清理 partial create 并向外抛错，绝不静默降级成裸节点；拒绝 hidden/deprecated 和 Material Library 根层直建 shader，setup/builder 改用 tab_apply；parent 接受 Node/path。连完 inputs 后自动落位：有输入时放到所有输入下游（x = 输入 x 均值，y = min(输入 y) − 垂直间距）；无输入时放到父网络现有内容右侧新列（x = max(现有 x) + 水平间距，y = 现有最顶部 y，空网络落原点）；间距由节点实际网络尺寸（`Node.size()`）推导，不用拍脑袋常量"},{"name":"tab_apply","sig":"parent, tool_id","desc":"应用 allowlist 内的非交互 Tab setup recipe，返回全部新增节点/输入；GUI 恢复 Network Editor pwd/selection，同一 exec 多次调用共享用户基线；headless 同语义。首批仅 Karma Setup / Karma Material Builder。SideFX recipe 自己摆节点，tab_apply 不做自动落位"},{"name":"find_nodes","sig":"pattern=\"*\", category=None, node_type=None, root=None","desc":"找**已存在**节点（扁平清单）"},{"name":"graph","sig":"node, depth=1, direction='both'","desc":"围绕**该数据节点**查 inputs / outputs / parm_refs；检查最终 SOP 网络应对 `OUT` 向上查，不要对父 OBJ 容器调用"},{"name":"describe","sig":"node","desc":"状态 + 几何摘要 + `attrib_delta`（相对 input 0 的属性增删——MMB 节点信息里「这个节点对数据干了什么」的固化）+ 帮助元数据"},{"name":"node_provenance","sig":"node","desc":"报告 runtime owner、可复制的 audit tag、当前 session 是否可写；`foreign`/`owned_current_session`/`owned_other_session`/`dsh_service` 分开"},{"name":"connect","sig":"src, dst, index=0, *, allow_foreign=None","desc":"严格数据流连线（src 输出 → dst 指定输入）；只有一个端口参数index，第4位置参数拒绝；权限理由必须显式keyword非空字符串。mutation 边界在 dst；**OBJ→OBJ 拒绝**，改用 `set_object_parent`。端口错误不再改接下一个输入；连接后仅在 dst 违反自顶向下流时调整落位"},{"name":"node_info","sig":"parent, type_name, parm_filter='', limit=80","desc":"创建前读取实际 parent context 下最新版类型、端口数量、参数默认值/组件名/menu token/label 与帮助 URL；Boolean说明输入选择组和部件组传递；不建临时节点、不运行 shelf；动态菜单需创建后 list_parms，truncated 明示。没有delivery类型准入字段"},{"name":"build_module","sig":"parent, nodes, output, dry_run=False, interfaces=None","desc":"小型新增 SOP 模块：1..64 个 `{name,type,parms?,inputs?}`，inputs 为更早 spec/现有直属 child 名，None跳输入。预检后用既有verbs建图/cook；可附geo_check_interfaces合同，最终几何接口fail/unverified使本批失败并清理新增节点。dry_run只校验声明，不证明VEX/cook/接口；返回validation与interface_checks，不覆盖既有节点/flags"},{"name":"verify_network","sig":"parent, output=None, nodes=None, limit=512, require_valid=True","desc":"SOP checkpoint：必须显式 output，省略即报可操作错误，绝不跟随 display。默认检查 parent 直属范围，可 nodes 限域；error/空输出默认抛 CheckpointError 并保留结构证据，require_valid=False 仅供诊断。warning独立，scope/时间/frame/输出指纹与失败原因前置；不证明关系/视觉"},{"name":"set_object_parent","sig":"child, parent, keep_world=True, reason='', index=0, allow_foreign=None","desc":"显式 OBJ parenting/unparent（`parent=None`），自然参数序为 child→parent；普通父级用 input 0，Blend 等明确多输入对象可指定 index。`reason` 限 `scene_assembly/camera_light_null/existing_legacy/explicit_user/downstream_obj_delivery`，新建几何 FK 不属例外。拒绝非 OBJ、自环/层级环；mutation/ownership 边界在 child；默认恢复 child 原世界变换并回读 parent、local/world delta"},{"name":"disconnect_input","sig":"dst, index=0, *, allow_foreign=None","desc":"断开普通网络 destination 输入；权限理由keyword-only非空字符串；OBJ unparent 拒绝并指向 `set_object_parent(child,None,...)`；ownership 边界在 dst，返回原 source path（若本来为空则为 null）"},{"name":"rename_node","sig":"node, name, allow_foreign=None","desc":"重命名"},{"name":"delete_node","sig":"node, allow_foreign=None","desc":"删除（返回被表达式引用的上游）；拒绝删除 owner-tagged `render_view` 会话级基础设施，避免进入 H21 OpenGL teardown fatal 路径"},{"name":"cook_node","sig":"node, force=False","desc":"cook + error/warning；另给 `ok/warning_free/healthy`，warning 未解释不得当完成"},{"name":"sop_set_output","sig":"node, render=True, allow_foreign=None","desc":"把 SOP singular display/render 旗标移到输出节点；属于用户 viewport/交付状态，不是 render_view 前置条件"},{"name":"sop_output_node","sig":"parent","desc":"报告 SOP 网络 display/render 输出；旗标不在链尾时提醒"},{"name":"set_object_visible","sig":"node, visible=True, allow_foreign=None","desc":"设置单个 OBJ 的 viewport visibility（OBJ 没有 SOP 式 render flag）"},{"name":"visible_objects","sig":"root='/obj'","desc":"列出 OBJ 层 plural visibility/effective visibility，并附每个对象的 provenance"},{"name":"layout_nodes","sig":"parent, nodes=None, horizontal_spacing=-1, vertical_spacing=-1, allow_foreign=None, mode='children'","desc":"`mode='children'`（默认）= 原生 layoutChildren，行为不变；`mode='flow'` = 自研拓扑分层：按最长路径深度分行（深度 0 最上，y = −depth × 垂直间距），同深度按节点当前 x 排序保持左右阅读顺序、等距排开并整体居中，有环时按原顺序兜底不断裂；spacing 默认从节点实际尺寸推导，显式正值覆盖。host task 中 `nodes=None` 只布局当前 session 创建项并回报 `foreign_nodes_skipped`；显式列表逐项过 ownership guard。Python Shell 无 host owner 时保持传统全布局语义"}]},{"domain":"compatibility 域","note":"compatibility 域（仅历史回放，不进新 guidance）","verbs":[{"name":"set_display","sig":"node, render=True, allow_foreign=None","desc":"deprecated 兼容 wrapper：按节点 context 路由 SOP output / OBJ visibility"},{"name":"display_node","sig":"parent","desc":"deprecated 兼容 wrapper：按父网络 context 路由 SOP output / OBJ visibility"}]},{"domain":"parm 域","note":"parm 域（依附 node）","verbs":[{"name":"list_parms","sig":"node","desc":"参数**目录**：名字/标签/类型/帮助/默认值及实际 menu token/index/label（不给当前值）；动态菜单以实际节点为准"},{"name":"read_parms","sig":"node, changed_only=True","desc":"参数**值**：默认只看非默认 + 带表达式/动画 + 被引用的（意图解读）；表达式参数附 `referenced_parm`，被引用参数标 `referenced_by`；动画附 `time_dependent/key_count/first_frame/last_frame/curves` 摘要，不默认倾倒全部 keys"},{"name":"set_parm","sig":"node, name, value, allow_foreign=None","desc":"设参（数值参数收到字符串 = 设表达式；失败列相似名，自纠）。参数上有表达式/关键帧时**自动清除再设值**，返回带 `note` 说明清掉了什么（2026-08-20 起，OTL 会话 seq 28944：`$FEND` 表达式把 set 静默架空）；想保留动画就请显式用字符串表达式"},{"name":"set_parms","sig":"node, values, allow_foreign=None, strict=True","desc":"默认严格批量设参：预检名称/重叠/锁定；失败恢复本批参数值/表达式/关键帧并抛错。显式 strict=False 才逐项容错，返回 ok/set/failed；参数回调及外部文件不属快照回滚。Menu string 只接受精确 token；数值 string 是 HScript 表达式，显式表达式对象支持 language"},{"name":"set_keyframes","sig":"node, channels, replace=True, allow_foreign=None","desc":"批量写数值标量 channel keys；统一 frame 单位，有限曲线 `constant/linear/bezier`，全量预检、失败恢复原 keys、提交后回读/采样并恢复用户 frame。只负责 channel 数据，不代替路径依赖状态机或 KineFX/APEX"},{"name":"create_spare_parms","sig":"node, code_parm='snippet', defaults=None, spec=None, allow_foreign=None","desc":"缺省扫描代码参数的 `ch/chf/chi/chv/chs` 引用并创建缺失 spare parameters；`spec=[...]` 的精确条目为 folder `{type,name,label?,parms:[...]}` 或 scalar `{type:'toggle\\|int\\|float\\|string',name,label?,default?,min?,max?,min_strict?,max_strict?,help?}`。spec 返回 `{node,mode,created,leaf_values}`；扫描返回 `{node,code_parm,references,created,existing,defaults_applied,unsupported}`。同名拒绝，不隐式覆盖"}]},{"domain":"scene 域","note":"scene 域（工程/时间线）","verbs":[{"name":"scene_info","sig":"","desc":"只读 HIP/version/fps/current frame/time/frame range/playback range/UI 状态；明确区分 `has_named_path`、`has_unsaved_changes`、`dirty_reliable`、`clean_on_disk`，不再用路径存在冒充保存完成；hython 的 dirty 不可靠时 clean=null；不移动 playbar、不遍历整张节点图"},{"name":"scene_save","sig":"expected_path=None","desc":"只保存当前已命名 HIP，不承担 Save As/open/new；可选 expected_path 作防串场断言，返回 dirty before/after/reliable、clean（headless=null）、bytes、mtime_ns"},{"name":"scene_save_as","sig":"path, expected_current_path, reason, overwrite=False","desc":"用户授权的 Save As：明确绝对 HIP 路径，expected_current_path 防串场，reason 记录路径/覆盖授权；已存在目标必须 overwrite=True。拒绝插件仓库落盘，回报前后路径/dirty/file/workspace_changed。无 load/clear；文件写不可撤销，失败可能留部分新文件，跨目录后 Open Workspace 重新绑定"},{"name":"set_timeline","sig":"fps=None, frame_range=None, playback_range=None, current_frame=None","desc":"设置明确的时间线字段；至少一项，范围校验后回读 scene_info"},{"name":"list_bookmarks","sig":"","desc":"列出 bookmark id/name/start/end/enabled/visible/comment"},{"name":"create_bookmark","sig":"name, start, end, replace=False","desc":"创建整数帧 bookmark；同名默认拒绝，replace 精确替换"},{"name":"delete_bookmark","sig":"name_or_id","desc":"按精确名称或 session id 删除，失败列现有项"}]},{"domain":"geometry 域","note":"geometry 域（几何数据）","verbs":[{"name":"geo_attrib_stats","sig":"node, name, attrib_class='point'","desc":"属性**值**统计：min/max/mean/count（`describe` 只给属性名清单）；point/prim/vertex/detail，多分量按分量给"},{"name":"geo_point_spacing","sig":"node, expected, tolerance, closed=False, order_attrib=None, max_points=10000","desc":"全量相邻点弦长验收：默认point number顺序，或唯一数值order_attrib；closed含末→首，SOP local单位；返回全量min/max/failure_count及最多16个最差对与sequence hash。超预算拒绝不抽样；只证明该序列约束，不证明弧长、网格接线或实际零件关系"},{"name":"geo_check_interfaces","sig":"output, interfaces, max_pairs=50000","desc":"同一最终SOP内的实际接口点→表面距离：1..16个 `{id,source_group,target_group,max_distance,expected_points}`；source为命名point group且点必须属于最终Polygon/Mesh表面，target为独立primitive group（closed Polygon/Mesh/Sphere/Tube）；全部声明点须在容差内，空组/基数不符fail，自重叠拒绝假自证，不支持类型unverified；SOP local单位，有界全量不采样。只证明接口接近，不是碰撞/包含/强度认证；回报几何/合同hash"},{"name":"test_controls","sig":"controller, output, tests, interfaces=None, allow_foreign=None, *, domain=None, topology=None","desc":"可恢复数字控制测试，必须exec：1..16个 `{id,values:{parm:number},expectations:[{metric,axis?,group?,delta:[min,max]}]}`；metric精确为bounds_size、bounds_center、bounds_min、bounds_max（axis0..2）、point_count、primitive_count、area，至少一项delta排除0。可选domain标量比较；topology为 `{id,groups:[primitive组,...],require_closed:true}` 列表，检查融合Polygon共享边连通/闭合，不代替独立表面interfaces或形状/强度。基准/扰动均复查；恢复参数/keys/frame，以完整bgeo解码内容（只排除导出头info.date）核对。支持Polygon/Mesh/Sphere/Tube/点几何；其他写前unverified。禁callback/menu/button/multiparm/tuple，foreign需单次授权；只证明声明case，外部副作用不属恢复保证"},{"name":"geo_piece_stats","sig":"node, piece_attrib=None, sample=16","desc":"primitive piece 的局部 bbox/extent/面积与退化统计；无 piece 属性时用内存 Connectivity SOP Verb，不污染网络，能发现「全场 bbox 正常但每个实例零宽/零面积」"},{"name":"geo_frame_diff","sig":"node, frame_a, frame_b, attrib='P', sample=4096, tolerance=1e-6","desc":"用 geometryAtFrame 比较两帧 point 数值属性；可比较时精确返回键 `mean_delta`、`max_delta`、`delta_percentiles.{p50,p90,p99}`、`component_delta.{min,max,mean}`、`unchanged_pct`（另含 sampled_points/tolerance/data_type/size），不是 `mean/max`。不移动 playbar；证明数据是否随时间变化，不单独证明审美/运动语义"}]},{"domain":"stage / USD 域","note":"stage / USD 域（Solaris 只读自省）","verbs":[{"name":"usd_stage_summary","sig":"node, max_paths=64","desc":"概览某 LOP 输出 stage 的 geometry/material/light/camera/RenderSettings/Product/Var，材质绑定、time-sampled 属性及 cook warning；路径按组限量但计数完整"},{"name":"usd_prim_info","sig":"node, prim_path, max_properties=200","desc":"检查单个 USD prim 的属性、primvar、relationship、material binding、time samples；points/topology 等大数组只报结构不整段拉取"}]},{"domain":"asset 域","note":"asset 域（HDA / 数字资产，2026-08-20 落地）","verbs":[{"name":"hda_create","sig":"node, name, description=None, hda_file=None, min_inputs=0, max_inputs=0, replace=False, allow_foreign=None","desc":"把已有节点（通常 subnet）转为数字资产：自动建 otls 目录、默认 `$HIP/otls/<name>.hda`。`replace=True` = 整体重建：所有待销毁实例逐项通过 ownership guard 后，卸载旧定义并覆盖文件；否则同名冲突报错并提示 replace"},{"name":"hda_info","sig":"node, max_depth=6","desc":"资产/参数界面**只读自省**：类型名、定义文件、section 清单、参数模板树（名字/标签/类型/conditional/tags/嵌套 folder 递归）——替代手写 walk()（会话里重复写了 3 次）。普通节点也可用（只有 parm 树，无 section）"},{"name":"hda_get_section","sig":"node, section='PythonModule'","desc":"读 HDA section 内容；section 不存在时列出现有 section 名供自纠"},{"name":"hda_set_section","sig":"node, section, code, allow_foreign=None","desc":"全量写 section。`PythonModule` 先 `compile()` 预检语法（带行号报错，不写脏）；写后读回校验一致"},{"name":"hda_patch_section","sig":"node, section, old, new, count=1, allow_foreign=None","desc":"锚点局部替换：`old` 必须恰好出现 `count` 次（0 = 锚点没找到，>count = 锚点不唯一需加长），替换后同样过语法预检；**模块改局部时用它，不要全文重发**"},{"name":"hda_set_interface","sig":"node, spec, keep_std=True, hide_builtin_tabs=False, allow_foreign=None","desc":"**声明式参数面板**（已拍板：整组重建语义，非 merge）：`spec` 是条目列表（folder/separator/toggle/int/float/string/button/menu），重建自定义参数组；subnet HDA 的 Transform/Subnet 标准页从 Houdini 原生 subnet 类型重新取得，避免夹带旧自定义参数。`hide_when` 字段写 conditional，**提交后读回验证**——被 `setParmTemplateGroup` 吞掉就自动改走 DialogScript `hidewhen` 补丁兜底（seq 124609 的教训）；folder 上设 `hide_when` 直接报错（Houdini 不支持，seq 98973 实测）。`hide_builtin_tabs=True` 通过公开 `ParmTemplateGroup.hide` 生成 `invisibletab` 隐藏标准页"}]},{"domain":"render / sim 域","note":"render / sim 域（渲染产物）","verbs":[{"name":"render_frame","sig":"rop, picture=None, frame=None, timeout=110","desc":"渲染一个**可执行 hou.RopNode**并验证产物；USD Render ROP 优先 `outputimage` 而非其 USD `lopoutput`。调用期临时启用 foreground wait；`picture` 覆盖和目标 frame 均在 `finally` 恢复。渲染前后记录 bytes/mtime/有界内容摘要，只有目标新建或指纹变化才算 `fresh=true`，沿用旧文件会失败。普通 LOP 在 job 前拒绝；>110s 走 job"},{"name":"render_view","sig":"node, direction='iso', frame=None, width=1280, height=720, picture=None, framing='full', coverage=0.82, framing_frame=None","desc":"**视觉验证主干 v2**：显式 SOP → agent-owned Object Merge proxy → agent camera/OpenGL ROP `forceobjects` 只渲染 proxy；不依赖/不改变用户 SOP output、OBJ visibility、selection、viewport 或 frame。PNG/JPEG/TIFF 等展示格式从当前 `scene_linear` 经 OCIO 写为编码 sRGB，EXR/HDR 保持线性供 Nuke/合成；返回 `output_color` 记录实际方法/空间，找不到 sRGB OCIO space 时显式标记 gamma 2.2 近似兜底。基础设施是会话级持久服务，OBJ/OUT 两侧分别收进带说明的 Network Box，任务收尾不得删除；空闲 proxy 会清空真实引用。传 OBJ 时只在调用开始解析一次 SOP并提醒。preflight 拒绝空/error 几何；返回 source fingerprint 前后、`stale`、eye/direction、ROP 设置、service metadata 和 render_check。动画 A/B 给所有调用传相同 `framing_frame`，用同一 bbox 锁定相机"},{"name":"render_check","sig":"path, ref=None","desc":"亮度/非黑/主色/content bbox；A/B 另给高精度 mean、RMSE、changed/meaningful pixel %、max diff，微小非零不再被舍入成 0"}]},{"domain":"viewport 域","note":"viewport 域（视口/UI）","verbs":[{"name":"viewport_screenshot","sig":"path=None, frame=None, clean=True, frame_target=None, textures=None, backface_cull=False","desc":"**用户屏幕诊断工具**：用户切空 display 节点时截到空是正确结果，不能用来证明 agent 产物；和 `render_view(explicit_sop)` 对照可区分 viewport 漂移与真实几何错误。flipbook 异步，设置/相机在落盘后恢复"}]}];
    // <<< houdini-catalog

    // --- houdinitrace 视图样式与解析 ------------------------------------------
    // 视觉方向：Houdini 检查台。橙色执行轨道是唯一强品牌元素；读取、Gate、
    // 豁免与回滚分别用中性蓝/红/琥珀标记，不再把所有直接 HOM 语法染成错误。
    var monoFont = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
    var displayFont = "Arial Narrow, Roboto Condensed, Segoe UI, sans-serif";
    var dimColor = "var(--dsw-alias-label-secondary, #9aa0aa)";
    var borderColor = "var(--dsw-alias-border-l2, #343943)";
    var surfaceColor = "var(--dsw-alias-bg-layer-2, #1b1e24)";
    var insetColor = "var(--dsw-alias-bg-layer-1, #14171c)";
    var orange = "#ff7a1a";
    var green = "#58c884";
    var blue = "#72a7ff";
    var amber = "#e5ad57";
    var red = "#f26d6d";
    var traceCss =
      ".dsh-htrace{background:linear-gradient(180deg,rgba(255,122,26,.035),transparent 180px)}" +
      ".dsh-htrace *{box-sizing:border-box}" +
      ".dsh-htrace-scroll{scrollbar-width:thin;scrollbar-color:#555b66 transparent}" +
      ".dsh-htrace-entry summary::-webkit-details-marker{display:none}" +
      ".dsh-htrace-entry summary{list-style:none}" +
      ".dsh-htrace-entry[open] .dsh-htrace-chevron{transform:rotate(90deg)}" +
      ".dsh-htrace-chevron{display:inline-block;transition:transform .16s ease}" +
      ".dsh-htrace-verb[open]{border-color:rgba(114,167,255,.5)!important}" +
      "@media(max-width:900px){.dsh-htrace-body{grid-template-columns:1fr!important}.dsh-htrace-catalog{display:none!important}}" +
      "@media(prefers-reduced-motion:reduce){.dsh-htrace-chevron{transition:none}}";
    var traceCssId = "dsh-houdini/houdinitrace.module.css";
    if (
      typeof document !== "undefined" &&
      document.querySelector("style[data-plugin-css=" + JSON.stringify(traceCssId) + "]") === null
    ) {
      var traceTag = document.createElement("style");
      traceTag.dataset.plugin = "dsh-houdini";
      traceTag.dataset.pluginCss = traceCssId;
      traceTag.textContent = traceCss;
      document.head.appendChild(traceTag);
    }

    var rootStyle = {
      display: "flex", flexDirection: "column", gap: "12px",
      padding: "16px 18px", height: "calc(100dvh - 250px)", minHeight: "320px",
      maxHeight: "820px", flex: "1 1 auto", overflow: "hidden",
      color: "var(--dsw-alias-label-primary, #edf0f4)",
    };
    var heroStyle = {
      display: "flex", justifyContent: "space-between", alignItems: "flex-end",
      gap: "18px", flexWrap: "wrap", flexShrink: "0",
    };
    var eyebrowStyle = {
      color: orange, fontFamily: monoFont, fontSize: "10px", fontWeight: "700",
      letterSpacing: ".14em", textTransform: "uppercase",
    };
    var titleStyle = {
      margin: "3px 0 0", fontFamily: displayFont, fontSize: "25px",
      lineHeight: 1.05, fontWeight: "760", letterSpacing: ".015em",
    };
    var heroNoteStyle = { color: dimColor, fontSize: "11px", maxWidth: "430px", lineHeight: 1.55 };
    var metricGridStyle = {
      display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(112px,1fr))",
      gap: "1px", overflow: "hidden", border: "1px solid " + borderColor,
      borderRadius: "9px", background: borderColor, flexShrink: "0",
    };
    var metricStyle = { padding: "8px 10px", background: surfaceColor, minWidth: 0 };
    var metricValueStyle = { fontFamily: monoFont, fontSize: "15px", fontWeight: "750", lineHeight: 1.15 };
    var metricLabelStyle = { marginTop: "3px", color: dimColor, fontSize: "10px", lineHeight: 1.25 };
    var bodyStyle = {
      display: "grid", gridTemplateColumns: "286px minmax(0,1fr)",
      gap: "12px", flex: "1", minHeight: "0",
    };
    var catalogColStyle = {
      overflowY: "auto", border: "1px solid " + borderColor, borderRadius: "9px",
      background: surfaceColor, padding: "10px 11px",
    };
    var catalogHeadStyle = {
      position: "sticky", top: 0, zIndex: 1, margin: "-10px -11px 8px",
      padding: "10px 11px 8px", background: surfaceColor,
      borderBottom: "1px solid " + borderColor,
    };
    var catalogTitleStyle = { fontFamily: displayFont, fontSize: "14px", fontWeight: "750" };
    var catalogMetaStyle = { color: dimColor, fontSize: "10px", marginTop: "2px" };
    var timelineColStyle = {
      minWidth: 0, overflowY: "auto", display: "flex", flexDirection: "column",
      gap: "9px", paddingRight: "3px", paddingBottom: "12px",
    };
    var domainStyle = { marginBottom: "11px" };
    var domainNameStyle = {
      fontFamily: displayFont, fontWeight: "750", fontSize: "11px",
      letterSpacing: ".035em", color: "var(--dsw-alias-label-primary, #e8e8e8)",
      marginBottom: "4px",
    };
    var catVerbStyle = {
      display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "7px",
      padding: "5px 2px", borderTop: "1px solid rgba(128,135,148,.16)", fontSize: "11px",
    };
    var catVerbNameStyle = { fontFamily: monoFont, fontWeight: "650", overflow: "hidden", textOverflow: "ellipsis" };
    var catSigStyle = {
      display: "block", marginTop: "1px", fontFamily: monoFont, fontSize: "9px",
      color: dimColor, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
    };
    var badgeBase = {
      display: "inline-flex", alignItems: "center", flexShrink: "0", fontSize: "10px",
      borderRadius: "999px", padding: "2px 7px", border: "1px solid", lineHeight: 1.2,
    };
    var badgeUsed = { color: green, borderColor: "rgba(88,200,132,.48)", background: "rgba(88,200,132,.08)" };
    var badgeUnused = { color: dimColor, borderColor: borderColor, background: "transparent" };
    var entryShellStyle = {
      display: "grid", gridTemplateColumns: "5px minmax(0,1fr)", overflow: "hidden",
      border: "1px solid " + borderColor, borderRadius: "9px", background: surfaceColor,
      flexShrink: "0",
    };
    var entryBodyStyle = { minWidth: 0, padding: "10px 12px 9px" };
    var entryHeadStyle = {
      display: "flex", alignItems: "center", justifyContent: "space-between",
      gap: "10px", flexWrap: "wrap",
    };
    var entryIdentityStyle = { display: "flex", alignItems: "center", flexWrap: "wrap", gap: "7px", minWidth: 0 };
    var timeStyle = { fontFamily: monoFont, fontWeight: "700", color: orange, fontSize: "11px" };
    var seqStyle = { color: dimColor, fontFamily: monoFont, fontSize: "10px" };
    var toolChipStyle = {
      fontFamily: monoFont, fontSize: "10px", color: "#d7dce3",
      border: "1px solid " + borderColor, borderRadius: "4px", padding: "2px 6px",
    };
    var chipOk = { color: green, borderColor: "rgba(88,200,132,.5)", background: "rgba(88,200,132,.08)" };
    var chipInfo = { color: blue, borderColor: "rgba(114,167,255,.5)", background: "rgba(114,167,255,.08)" };
    var chipWarn = { color: amber, borderColor: "rgba(229,173,87,.55)", background: "rgba(229,173,87,.08)" };
    var chipBad = { color: red, borderColor: "rgba(242,109,109,.55)", background: "rgba(242,109,109,.08)" };
    var entrySummaryStyle = { marginTop: "7px", fontSize: "12px", lineHeight: 1.45, color: "#d4d8df" };
    var detailsStyle = { marginTop: "8px", borderTop: "1px solid " + borderColor, paddingTop: "7px" };
    var detailsSummaryStyle = {
      cursor: "pointer", display: "flex", alignItems: "center", gap: "6px",
      color: blue, fontSize: "11px", fontWeight: "650", userSelect: "none",
    };
    var detailGridStyle = { display: "grid", gap: "8px", marginTop: "9px" };
    var detailSectionStyle = {
      border: "1px solid " + borderColor, borderRadius: "7px", overflow: "hidden",
      background: insetColor,
    };
    var detailLabelStyle = {
      display: "flex", justifyContent: "space-between", gap: "8px", padding: "6px 8px",
      color: dimColor, fontFamily: monoFont, fontSize: "9px", fontWeight: "700",
      letterSpacing: ".08em", textTransform: "uppercase", borderBottom: "1px solid " + borderColor,
    };
    var preStyle = {
      margin: 0, fontFamily: monoFont, fontSize: "10.5px", lineHeight: 1.55,
      whiteSpace: "pre-wrap", wordBreak: "break-word", padding: "8px 9px",
      maxHeight: "340px", overflow: "auto", color: "#d9dde3",
    };
    var verbRowStyle = {
      border: "1px solid " + borderColor, borderRadius: "6px", background: "rgba(255,255,255,.015)",
      overflow: "hidden",
    };
    var verbSummaryStyle = {
      cursor: "pointer", display: "grid", gridTemplateColumns: "22px minmax(0,1fr) auto",
      alignItems: "center", gap: "7px", padding: "6px 8px", fontFamily: monoFont, fontSize: "10.5px",
    };
    var emptyStyle = {
      color: dimColor, padding: "34px", textAlign: "center", border: "1px dashed " + borderColor,
      borderRadius: "9px", lineHeight: 1.6,
    };

    // `verbs (N):` 块里的一行（host renderVerbs 的渲染格式）：
    // `i. [ok|FAIL] verb(args, kwargs) -> detail (Xms)`
    function parseVerbLedgerLine(line) {
      var prefix = /^(\d+)\. \[(ok|FAIL)\] (\w+)\(/.exec(line);
      var tail = / \(([\d.]+)ms\)\s*$/.exec(line);
      if (!prefix || !tail || typeof tail.index !== "number") return null;
      var body = line.slice(prefix[0].length, tail.index);
      var inString = false;
      var escaped = false;
      var square = 0;
      var curly = 0;
      for (var index = 0; index < body.length; index++) {
        var ch = body[index];
        if (inString) {
          if (escaped) escaped = false;
          else if (ch === "\\") escaped = true;
          else if (ch === '"') inString = false;
          continue;
        }
        if (ch === '"') { inString = true; continue; }
        if (ch === "[") square++;
        else if (ch === "]") square--;
        else if (ch === "{") curly++;
        else if (ch === "}") curly--;
        else if (ch === ")" && square === 0 && curly === 0 && body.slice(index, index + 5) === ") -> ") {
          return {
            n: Number(prefix[1]), ok: prefix[2] === "ok", verb: prefix[3],
            argsText: body.slice(0, index), detail: body.slice(index + 5), ms: Number(tail[1]),
          };
        }
        if (square < 0 || curly < 0) return null;
      }
      return null;
    }

    function tryJson(text) {
      try { return JSON.parse(text); } catch (_error) { return null; }
    }

    function prettyValue(value, fallback) {
      if (value !== null && value !== undefined) {
        if (typeof value === "string") return value;
        try { return JSON.stringify(value, null, 2); } catch (_error) { /* use fallback */ }
      }
      return fallback || "";
    }

    // Host 输出由空行分隔，每个区块有稳定标题。按标题边界切分，避免 stdout
    // 自己包含空行时把后续 rollback/raw-usage/verbs 吞进一个大文本块。
    function parseResultSections(text) {
      var marker = /(?:^|\n\n)(stdout|stderr|__result__|rollback|raw-usage|hint|verbs \(\d+\)|media(?: [^\n:]*)?):\n/g;
      var matches = [];
      var match;
      while ((match = marker.exec(text)) !== null) {
        matches.push({ key: match[1], markerStart: match.index, bodyStart: marker.lastIndex });
      }
      var out = { status: matches.length ? text.slice(0, matches[0].markerStart).trim() : text.trim() };
      for (var i = 0; i < matches.length; i++) {
        var current = matches[i];
        var end = i + 1 < matches.length ? matches[i + 1].markerStart : text.length;
        var key = current.key;
        if (key.indexOf("verbs (") === 0) key = "verbs";
        else if (key.indexOf("media") === 0) key = "media";
        out[key] = text.slice(current.bodyStart, end).trim();
      }
      return out;
    }

    function legacyDirectHouCalls(code) {
      var counts = {};
      var re = /\bhou(?:\.\w+)+\s*\(/g;
      var match;
      while ((match = re.exec(code || "")) !== null) {
        var name = match[0].replace(/\s*\($/, "");
        counts[name] = (counts[name] || 0) + 1;
      }
      return Object.keys(counts).sort().map(function (name) {
        return { name: name, count: counts[name] };
      });
    }

    function countRows(rows) {
      var total = 0;
      for (var i = 0; i < (rows || []).length; i++) total += Number(rows[i].count) || 0;
      return total;
    }

    function errorSummary(text) {
      var value = String(text || "").trim();
      if (!value) return "执行失败，但没有返回错误说明。";
      if (/raw-hou gate: blocked BEFORE execution/i.test(value)) return "Raw Gate 在执行前拦截了这段代码，场景没有发生副作用。";
      var lines = value.split("\n").map(function (line) { return line.trim(); }).filter(Boolean);
      for (var i = lines.length - 1; i >= 0; i--) {
        if (!/^File |^Traceback|^rollback:|^\^+$/.test(lines[i])) return lines[i];
      }
      return lines[lines.length - 1] || "执行失败。";
    }

    function cleanStdout(text) {
      return String(text || "").split("\n").filter(function (line) {
        return line.indexOf("[verb]") !== 0;
      }).join("\n").trim();
    }

    function classifyRaw(info) {
      var usage = info.rawUsage || {};
      var outcome = usage.gateOutcome;
      if (info.gateBlocked || outcome === "blocked" || outcome === "forbidden") return "blocked";
      if (outcome === "exempted" || info.exemptionReason) return "exempted";
      if (outcome === "disabled") return "gate_disabled";
      if ((usage.coveredMutations || []).length || (usage.suspectedMutations || []).length) return "mutation";
      if ((usage.directCalls || []).length) return "read_only";
      if (info.hint && /raw hou call\(s\) bypassed/i.test(info.hint)) return "legacy_bypass";
      return "none";
    }

    // 把一个 tool-result 节点拆成可展示的执行证据。新 trace 优先读取 Bridge
    // AST 生成的 rawUsage；旧 trace 只把源码正则结果称作“直接 HOM”，不再冒充
    // mutation 或安全结论。
    function parseEntry(node) {
      var call = node.call || {};
      var args = {};
      try { args = JSON.parse(call.argsRaw || "{}"); } catch (_error) { /* 非 JSON */ }
      var text = "";
      var blocks = node.content || [];
      for (var j = 0; j < blocks.length; j++) {
        var block = blocks[j];
        if (block && block.type === "text" && typeof block.text === "string") text += block.text + "\n";
      }
      text = text.replace(/\n+$/, "");
      var sections = parseResultSections(text);
      var rollback = tryJson(sections.rollback || "");
      var rawUsage = tryJson(sections["raw-usage"] || "");
      var resultValue = tryJson(sections.__result__ || "");
      var status = sections.status || "";
      var failed = status.indexOf("Execution failed") === 0 || status.indexOf("Job failed") === 0;
      var info = {
        key: String(node.seq),
        time: node.time || node.callTime || null,
        name: typeof call.name === "string" ? call.name : "?",
        code: typeof args.code === "string" ? args.code : null,
        args: args,
        verbs: [],
        hint: sections.hint || null,
        stdout: cleanStdout(sections.stdout),
        stderr: sections.stderr || null,
        resultText: sections.__result__ || null,
        resultValue: resultValue,
        media: sections.media || null,
        rollback: rollback,
        rawUsage: rawUsage,
        failed: failed,
        statusText: status,
        errorText: failed ? status.replace(/^Execution failed:\s*/i, "").replace(/^Job failed:\s*/i, "") : null,
        text: text,
      };
      if (!info.rawUsage && info.code) {
        var direct = legacyDirectHouCalls(info.code);
        if (direct.length) info.rawUsage = { directCalls: direct, gateOutcome: "legacy" };
      }
      var verbText = sections.verbs || "";
      var lines = verbText.split("\n");
      for (var k = 0; k < lines.length; k++) {
        var parsed = parseVerbLedgerLine(lines[k]);
        if (parsed) info.verbs.push({
          verb: parsed.verb, ok: parsed.ok, argsText: parsed.argsText,
          detail: parsed.detail, ms: parsed.ms,
        });
      }
      info.gateBlocked = /raw-hou gate: blocked BEFORE execution/i.test(text);
      info.exemptionReason = typeof args.allow_raw === "string" && args.allow_raw
        ? args.allow_raw
        : (info.rawUsage && info.rawUsage.exemptionReason) || null;
      info.rawMode = classifyRaw(info);
      info.directHouCount = countRows(info.rawUsage && info.rawUsage.directCalls);
      info.rollbackApplied = Boolean(info.rollback && info.rollback.applied === true);
      info.committed = !info.failed && !info.rollbackApplied;
      if (info.rollbackApplied) info.summary = "执行失败；本批次可撤销的场景修改已经回滚。";
      else if (info.gateBlocked) info.summary = errorSummary(info.errorText);
      else if (info.failed) info.summary = errorSummary(info.errorText);
      else if (args.review) info.summary = "独立资产评审已返回；查看报告与未验证边界。";
      else if (args.review_test) info.summary = "受控评审实验；查看本批测量、图片与恢复结果。";
      else if (info.rawMode === "exempted") info.summary = "低层修改通过一次性豁免执行；理由已记录。";
      else if (info.verbs.length && info.rawMode === "read_only") info.summary = info.verbs.length + " 个动词已提交，同时进行了只读 HOM 检查。";
      else if (info.verbs.length) info.summary = info.verbs.length + " 个动词已提交。";
      else if (info.rawMode === "read_only") info.summary = "只读 HOM 探针；没有检测到场景修改。";
      else info.summary = "调用已完成，没有记录动词。";
      return info;
    }

    function pad2(n) { return (n < 10 ? "0" : "") + n; }
    function fmtTime(ms) {
      if (!ms) return "--:--:--";
      var d = new Date(ms);
      return pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" + pad2(d.getSeconds());
    }

    function metricNode(key, value, label, color) {
      return React.createElement(
        "div", { key: key, style: metricStyle },
        React.createElement("div", { style: Object.assign({}, metricValueStyle, color ? { color: color } : null) }, value),
        React.createElement("div", { style: metricLabelStyle }, label)
      );
    }

    function badgeNode(key, text, tone, title) {
      return React.createElement(
        "span",
        { key: key, style: Object.assign({}, badgeBase, tone), title: title || undefined },
        text
      );
    }

    function detailSection(key, label, meta, content, tone) {
      if (content === null || content === undefined || content === "") return null;
      return React.createElement(
        "section",
        { key: key, style: Object.assign({}, detailSectionStyle, tone ? { borderColor: tone } : null) },
        React.createElement(
          "div", { style: detailLabelStyle },
          React.createElement("span", null, label),
          meta ? React.createElement("span", { style: { letterSpacing: 0, textTransform: "none", fontWeight: "500" } }, meta) : null
        ),
        React.createElement("pre", { style: preStyle }, content)
      );
    }

    function rawUsageText(entry) {
      var usage = entry.rawUsage || {};
      var lines = [];
      if (entry.rawMode === "blocked") lines.push("判定：Raw Gate 已在执行前拦截，场景无副作用");
      else if (entry.rawMode === "exempted") lines.push("判定：已批准一次性低层豁免");
      else if (entry.rawMode === "read_only") lines.push("判定：直接 HOM 读取，不代表绕过词表修改场景");
      else if (entry.rawMode === "gate_disabled") lines.push("判定：Raw Gate 当时关闭，需要人工审计");
      else if (entry.rawMode === "legacy_bypass") lines.push("判定：旧 trace advisory 指出词表绕过");
      else if (entry.rawMode === "mutation") lines.push("判定：检测到低层修改语法");
      if (entry.exemptionReason) lines.push("豁免理由：" + entry.exemptionReason);
      var groups = [
        ["直接 HOM", usage.directCalls],
        ["已有动词覆盖", usage.coveredMutations],
        ["疑似低层修改", usage.suspectedMutations],
      ];
      for (var i = 0; i < groups.length; i++) {
        var rows = groups[i][1] || [];
        if (!rows.length) continue;
        lines.push(groups[i][0] + "：" + rows.map(function (row) {
          return row.name + " ×" + row.count + (row.verb ? " → " + row.verb : "");
        }).join("，"));
      }
      return lines.join("\n");
    }

    function renderVerbEvidence(entry) {
      if (!entry.verbs.length) return null;
      var rows = entry.verbs.map(function (verb, index) {
        var detailValue = tryJson(verb.detail);
        var body = "参数\n" + (verb.argsText || "(无)") + "\n\n返回\n" + prettyValue(detailValue, verb.detail || "(无返回)");
        return React.createElement(
          "details", { key: index, className: "dsh-htrace-verb", style: verbRowStyle },
          React.createElement(
            "summary", { style: verbSummaryStyle, title: verb.argsText + " -> " + verb.detail },
            React.createElement("span", { style: { color: verb.ok ? green : red, fontWeight: "800" } }, verb.ok ? "✓" : "×"),
            React.createElement("span", { style: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, verb.verb),
            React.createElement("span", { style: { color: dimColor, fontSize: "9px" } }, verb.ms + "ms")
          ),
          React.createElement("pre", { style: Object.assign({}, preStyle, { borderTop: "1px solid " + borderColor }) }, body)
        );
      });
      return React.createElement(
        "section", { key: "verbs", style: detailSectionStyle },
        React.createElement(
          "div", { style: detailLabelStyle },
          React.createElement("span", null, "动词证据"),
          React.createElement("span", { style: { letterSpacing: 0, textTransform: "none" } }, entry.verbs.length + " 次调用")
        ),
        React.createElement("div", { style: { display: "grid", gap: "5px", padding: "7px" } }, rows)
      );
    }

    function installLaunchSessionHint(ctx) {
      if (
        typeof window === "undefined" ||
        typeof URL === "undefined" ||
        typeof ctx.inject !== "function"
      ) return;
      var launchUrl;
      var sessionId;
      try {
        launchUrl = new URL(window.location.href);
        sessionId = launchUrl.searchParams.get("dsh-houdini-session");
      } catch (_error) {
        return;
      }
      if (!sessionId) return;

      ctx.inject(["sessions"], function (scope) {
        var sessions = scope.get("sessions");
        if (
          sessions === undefined ||
          typeof sessions.refresh !== "function" ||
          typeof sessions.open !== "function"
        ) return;
        Promise.resolve(sessions.refresh()).then(function () {
          sessions.open(sessionId);
          // Consume only after a successful refresh/open. A transient failure
          // leaves the hint in the URL so a manual reload can retry it.
          launchUrl.searchParams.delete("dsh-houdini-session");
          var cleanUrl = launchUrl.pathname + launchUrl.search + launchUrl.hash;
          window.history.replaceState(window.history.state, "", cleanUrl);
        }).catch(function (error) {
          console.warn("dsh-houdini: could not open launcher session", error);
        });
      });
    }

    function apply(ctx) {
      installLaunchSessionHint(ctx);
      var slots = ctx.get("slots");
      if (slots === undefined) return;

      slots.inject("conversation.view", function () {
        return slots.register(
          { name: "conversation.view", id: "houdinitrace", order: 5, label: "Houdini Trace" },
          function HoudiniTraceView(props) {
            // DSH 0.1.2 split the active Trajectory target into its own
            // standard selector hook. DSH 0.1.1 kept the same snapshot under
            // Session.views; the original s.nodes access was an undeclared
            // internal shape and silently became empty after the host update.
            // Select one stable adapter per browser composition so hook order
            // never changes during a render generation.
            var nodes = typeof props.useTrajectory === "function"
              ? props.useTrajectory(function (snapshot) {
                  return snapshot && snapshot.eventNodes ? snapshot.eventNodes : [];
                })
              : props.useSession(function (snapshot) {
                  var views = snapshot && snapshot.views;
                  var trajectory = views && typeof views.get === "function"
                    ? views.get("trajectory")
                    : null;
                  if (trajectory && trajectory.eventNodes) return trajectory.eventNodes;
                  // Compatibility only for DSH builds predating the ViewMap.
                  return snapshot && snapshot.nodes ? snapshot.nodes : [];
                });
            var list = nodes || [];
            var entries = [];
            var usedMap = {};
            var totalVerbCalls = 0;
            var committedVerbCalls = 0;
            var rolledBackVerbCalls = 0;
            var callsWithVerbs = 0;
            var withHint = 0;
            var failedCount = 0;
            var rawReadOnlyCount = 0;
            var gateBlockedCount = 0;
            var exemptionCount = 0;
            var rollbackCount = 0;
            var successfulExec = 0;
            var successfulExecWithVerbs = 0;
            for (var i = 0; i < list.length; i++) {
              var node = list[i];
              if (node.kind !== "tool-result") continue;
              var nm = node.call && node.call.name;
              if (typeof nm !== "string" || nm.indexOf("houdini") !== 0) continue;
              var info = parseEntry(node);
              for (var v = 0; v < info.verbs.length; v++) {
                var vn = info.verbs[v].verb;
                usedMap[vn] = (usedMap[vn] || 0) + 1;
              }
              totalVerbCalls += info.verbs.length;
              if (info.verbs.length) callsWithVerbs++;
              if (info.committed) committedVerbCalls += info.verbs.length;
              if (info.rollbackApplied) {
                rollbackCount++;
                rolledBackVerbCalls += info.verbs.filter(function (verb) { return verb.ok; }).length;
              }
              if (info.hint) withHint++;
              if (info.failed) failedCount++;
              if (info.rawMode === "read_only" && info.verbs.length === 0) rawReadOnlyCount++;
              if (info.rawMode === "blocked") gateBlockedCount++;
              if (info.rawMode === "exempted") exemptionCount++;
              if (info.name === "houdini_exec" && !info.failed) {
                successfulExec++;
                if (info.verbs.length) successfulExecWithVerbs++;
              }
              entries.push(info);
            }

            // 左栏：词表目录——按域分组，命中数随会话推进实时点亮。
            var catalogChildren = [];
            var distinctUsed = 0;
            var catalogTotal = 0;
            for (var d = 0; d < CATALOG.length; d++) {
              (function (dom) {
                var rows = [];
                for (var w = 0; w < dom.verbs.length; w++) {
                  (function (verb) {
                    catalogTotal++;
                    var used = usedMap[verb.name] || 0;
                    if (used > 0) distinctUsed++;
                    rows.push(
                      React.createElement(
                        "div",
                        {
                          key: verb.name,
                          style: Object.assign({}, catVerbStyle, used ? null : { opacity: ".55" }),
                          title: verb.name + "(" + verb.sig + ")\n" + verb.desc,
                        },
                        React.createElement(
                          "div", { style: { minWidth: 0 } },
                          React.createElement("span", { style: catVerbNameStyle }, verb.name),
                          React.createElement("span", { style: catSigStyle }, verb.sig)
                        ),
                        React.createElement(
                          "span",
                          { style: Object.assign({}, badgeBase, used ? badgeUsed : badgeUnused) },
                          used ? "×" + used : "未用"
                        )
                      )
                    );
                  })(dom.verbs[w]);
                }
                catalogChildren.push(
                  React.createElement(
                    "div",
                    { key: dom.domain, style: domainStyle },
                    React.createElement("div", { style: domainNameStyle }, dom.note || dom.domain),
                    rows
                  )
                );
              })(CATALOG[d]);
            }

            // 右栏：真实时序时间线——时间戳 + 徽章 + 动词 chip，详情折叠。
            var timelineChildren = [];
            if (entries.length === 0) {
              timelineChildren.push(
                React.createElement(
                  "div",
                  { key: "empty", style: emptyStyle },
                  "还没有 houdini 工具调用——agent 开始操作后会实时出现在这里。"
                )
              );
            }
            for (var k = 0; k < entries.length; k++) {
              (function (e, idx) {
                var badges = [];
                if (e.gateBlocked) badges.push(badgeNode("gate", "Gate 拦截", chipBad));
                else if (e.rollbackApplied) badges.push(badgeNode("rollback", "已回滚", chipWarn));
                else if (e.failed) badges.push(badgeNode("failed", "失败", chipBad));
                if (e.rawMode === "exempted") badges.push(badgeNode("exempt", "低层豁免", chipWarn, e.exemptionReason));
                if (e.rawMode === "gate_disabled") badges.push(badgeNode("disabled", "Gate 关闭", chipBad));
                if (e.rawMode === "legacy_bypass" || e.rawMode === "mutation") badges.push(badgeNode("bypass", "低层修改", chipBad));
                if (e.rawMode === "read_only") badges.push(badgeNode(
                  "read", "HOM 读取" + (e.directHouCount ? " ×" + e.directHouCount : ""), chipInfo,
                  "直接 HOM 读取不是词表绕过修改"
                ));
                if (e.verbs.length) badges.push(badgeNode("verbs", "动词 ×" + e.verbs.length, chipOk));
                if (e.hint) badges.push(badgeNode("hint", "提示", chipWarn));

                var detailChildren = [];
                if (e.code) detailChildren.push(detailSection("code", "执行代码", e.code.split("\n").length + " 行", e.code));
                if (e.errorText) detailChildren.push(detailSection("error", "失败原因", e.gateBlocked ? "执行前" : "运行时", e.errorText, red));
                if (e.rawMode !== "none") detailChildren.push(detailSection("raw", "HOM / Raw Gate", e.rawMode, rawUsageText(e), e.rawMode === "blocked" ? red : e.rawMode === "read_only" ? blue : amber));
                if (e.rollback) detailChildren.push(detailSection(
                  "rollback", "事务状态", e.rollbackApplied ? "已撤销" : "未撤销",
                  prettyValue(e.rollback, e.rollbackApplied ? "场景修改已回滚" : "未应用回滚"),
                  e.rollbackApplied ? amber : red
                ));
                var verbEvidence = renderVerbEvidence(e);
                if (verbEvidence) detailChildren.push(verbEvidence);
                if (e.resultText) detailChildren.push(detailSection("result", "结构化返回", "__result__", prettyValue(e.resultValue, e.resultText)));
                if (e.stdout) detailChildren.push(detailSection("stdout", "程序输出", "已隐藏重复 verb ledger", e.stdout));
                if (e.stderr) detailChildren.push(detailSection("stderr", "标准错误", null, e.stderr, red));
                if (e.media) detailChildren.push(detailSection("media", "媒体产物", null, e.media));
                if (e.hint) detailChildren.push(detailSection("hint", "执行提示", null, e.hint, amber));
                detailChildren.push(
                  React.createElement(
                    "details", { key: "original", style: detailSectionStyle },
                    React.createElement(
                      "summary", { style: Object.assign({}, detailsSummaryStyle, { padding: "7px 9px", color: dimColor }) },
                      React.createElement("span", { className: "dsh-htrace-chevron" }, "›"),
                      "查看原始工具结果"
                    ),
                    React.createElement("pre", { style: Object.assign({}, preStyle, { borderTop: "1px solid " + borderColor }) }, e.text || "(无输出)")
                  )
                );
                var railColor = e.gateBlocked || (e.failed && !e.rollbackApplied)
                  ? red
                  : e.rollbackApplied || e.rawMode === "exempted"
                    ? amber
                    : e.rawMode === "read_only" && !e.verbs.length
                      ? blue
                      : e.verbs.length
                        ? green
                        : orange;
                timelineChildren.push(
                  React.createElement(
                    "div",
                    { key: e.key, style: entryShellStyle },
                    React.createElement("div", { style: { background: railColor } }),
                    React.createElement(
                      "div", { style: entryBodyStyle },
                      React.createElement(
                        "div", { style: entryHeadStyle },
                        React.createElement(
                          "div", { style: entryIdentityStyle },
                          React.createElement("span", { style: timeStyle }, fmtTime(e.time)),
                          React.createElement("span", { style: seqStyle }, "#" + idx),
                          React.createElement("span", { style: toolChipStyle }, e.name)
                        ),
                        React.createElement("div", { style: { display: "flex", gap: "5px", flexWrap: "wrap" } }, badges)
                      ),
                      React.createElement("div", { style: entrySummaryStyle }, e.summary),
                      React.createElement(
                        "details", { className: "dsh-htrace-entry", style: detailsStyle },
                        React.createElement(
                          "summary", { style: detailsSummaryStyle },
                          React.createElement("span", { className: "dsh-htrace-chevron" }, "›"),
                          "展开执行证据"
                        ),
                        React.createElement("div", { style: detailGridStyle }, detailChildren)
                      )
                    )
                  )
                );
              })(entries[k], k + 1);
            }

            var callCoverage = entries.length ? Math.round(callsWithVerbs * 1000 / entries.length) / 10 : 0;
            var execCoverage = successfulExec ? Math.round(successfulExecWithVerbs * 1000 / successfulExec) / 10 : null;
            var metrics = [
              metricNode("calls", String(entries.length), "Houdini 调用"),
              metricNode("coverage", callsWithVerbs + " / " + entries.length, "调用含动词 · " + callCoverage + "%", green),
              metricNode("exec", successfulExec ? successfulExecWithVerbs + " / " + successfulExec : "—", "成功修改含动词" + (execCoverage === null ? "" : " · " + execCoverage + "%"), green),
              metricNode("reads", String(rawReadOnlyCount), "无动词只读探针", blue),
              metricNode("gate", String(gateBlockedCount), "Raw Gate 拦截", gateBlockedCount ? red : dimColor),
              metricNode("exempt", String(exemptionCount), "低层豁免", exemptionCount ? amber : dimColor),
              metricNode("rollback", rolledBackVerbCalls ? rolledBackVerbCalls + " verbs" : String(rollbackCount), "回滚工作量", rolledBackVerbCalls ? amber : dimColor),
            ];

            return React.createElement(
              "div",
              { className: "dsh-htrace", style: rootStyle },
              React.createElement(
                "header", { style: heroStyle },
                React.createElement(
                  "div", null,
                  React.createElement("div", { style: eyebrowStyle }, "DSH / HOUDINI EXECUTION TRACE"),
                  React.createElement("h2", { style: titleStyle }, "执行证据")
                ),
                React.createElement(
                  "div", { style: heroNoteStyle },
                  "这里区分动词、只读 HOM、Raw Gate、一次性豁免与回滚。目录命中只表示触达能力，不代表任务完成度。"
                )
              ),
              React.createElement("div", { style: metricGridStyle }, metrics),
              React.createElement(
                "div",
                { className: "dsh-htrace-body", style: bodyStyle },
                React.createElement(
                  "aside", { className: "dsh-htrace-catalog dsh-htrace-scroll", style: catalogColStyle },
                  React.createElement(
                    "div", { style: catalogHeadStyle },
                    React.createElement("div", { style: catalogTitleStyle }, "动词目录"),
                    React.createElement("div", { style: catalogMetaStyle }, "命中 " + distinctUsed + "/" + catalogTotal + " · 已提交 " + committedVerbCalls + "/" + totalVerbCalls)
                  ),
                  catalogChildren
                ),
                React.createElement("main", { className: "dsh-htrace-scroll", style: timelineColStyle }, timelineChildren)
              )
            );
          }
        );
      });

      slots.inject("conversation.composer.dock", function () {
        return slots.register(
          { name: "conversation.composer.dock", id: "houdini-watermark", order: 99 },
          HoudiniWatermark
        );
      });
    }

    return { apply: apply };
  },
});
