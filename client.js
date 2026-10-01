// dsh-houdini client half — registers four things:
//  1. Houdini Trace: five boards over public trajectory requests/calls.
//     Handwritten view/model/runtime under client/; initialized on opening Trace.
//     Build carries source identities, not complete skill/reference bodies.
//  2. a preset-aware watermark on the conversation window: sessions whose
//     agentPreset is "houdini" get the Houdini swirl + an orange
//     ambient glow, so the mode is recognizable at a glance.
//  3. one-shot workspace navigation through the native DSH session/workspace
//     stores: reuse the current eligible Houdini task, exclude archived tasks,
//     and create with the Houdini preset only when needed. Same-HIP reopening
//     keeps the existing page; actual DSH navigation supersedes a pending launch.
//  4. the shared-executor picker for Houdini sessions when that Host service is mounted.
//
// Hand-written CJS factory matching the dsh client module system (no bundler):
// the bundle only REGISTERS its factory here; the body runs at materialization.
window.__ModuleLoader__.load({
  id: "dsh-houdini",
  factory: function (require) {
    var React = require("react");

    // --- houdini 模式水印 ---------------------------------------------------
    // 会话的 agentPreset 为 "houdini" 时，在对话窗口铺一层品牌水印：
    // 居中的 Houdini 旋涡（由官方 badge 的镂空旋涡反相提取，assets/houdini_swirl.png）
    // + 右下角一抹橙色氛围光。旋涡以 base64 内联（2.6 KB），webserver 不 serve
    // 插件静态目录，data URI 是单文件 client bundle 下最简的路子。
    var SWIRL_URI = "data:image/png;base64," +
      "iVBORw0KGgoAAAANSUhEUgAAAZYAAAGkCAMAAAAllPMCAAAAwFBMVEX+ZgD/ZgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADWJhSQAAAAQHRSTlP+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA5vJXKAAACPZJREFUeNrt3YsB4zYMA1Bg/6XbBXq9JBIFgNAClv1CO/6IABUH/m4wdsCNYgcR3DkyeRDjEaWDOJAIHKSKeNsgWsTWBgtIDGmwhMSMBotIjGiwjMREBgtNDGiwk0RdBntNlGWw2kRWBttNNGFQE0UZFEVRBjVRhEFNFGVQFEUYFEURBjVRlEFRFGFQFEUY1EQRBkVRhEFRFGFQFEUYFEURBkVRdEFRFGFQFUUYFEURBkVRdEFRFGFQFEUXVEURBkVRhEFRFF1QFUUYFEXRBVVRhEFRFF1QFEUXVEURBkVRdEFVFF1QFUUYFEXRBVVRdEFRFF1QFUUYVEXRBUVRdOnhlHTp0ZR08duzFTDOOxPsErAPiS4xt8VZLlGvwHNc4j5IzHDJXB1i7xK7WNfbJboVhK9LeKshV5cFHdMcXVa05PRz2dJZ2MxlT4d0K5ddgQI2LsuSUVxc1iUJebgsDN5a8iqJdkPfZWm0YzgLbYe2y+KEWmWX1ZnOui7Lc9BVXdan02u6LEdRddmOMgNzf0pMHHIuRZF0KcoQzL3ZkHWRY2H8EHIpiqRLVSRdiiL5OWNV" +
      "JF2KMglzbg5kXeZdijLqcmYGZF2euBRFciVDVYZdft06WZdnLkWRdKnKuMv3mxY8GLtcZNJiNd8wvHJ5j6L9SZQMi9NPMdbF/1fo6PLxRj1PDHEu41lkjhk389O1Px9MTP8ty9JFC4ouvqeBUZl3LDn9IwJc7qdcoT1Kv2eJa4Hn7eJ1Qn6a3TE5Qaez8evwjmmW3G7Rri4ep+HQ+I4/bikZRTy/4w8bCkc5CzPGwg3hSXYuW6KT9rIAGyKiZmaFPSljkvt5mQVYk6k2MSesyuMTdLnIAqwKIRyYEbZFV3qUC/bliTq4YGHKq5jLeRZgacqtNAtQlzuzwdKUaiWXoyzAape7c8HaRHfpcsFSFHEXrFVRSrs7wwLU5e4aHexFUYoh/J0FqIseC1CX+y5YrqLi8hsLUBc9FqAuIy5YjyISp/o1C8oylqeKqiiWC6oi4vIVC1CXu4fmGxagLpPlgqqouHzMAtRFjwVlmXZBVRTLBVWRcfmEBajLfLmgKorlUhahcvlrFqAuL1xQlSMukywoiyALUJdHLqjKGZeyBJfL/7MAddFjQVkeuqAqiuVSlmMuAyyax2RBufyRRfk3uqJcIKEit5rjdbm8Z9FcUyvIsnA1lgGLVXOvUBc4XVPVslQnWdr8/vs53mOxTL1JKpc3LCQzUtVGWVzD7qbjiC6fxSB/M7DOZZiFNMu1lGGxRpnq6B3EQrIu37LYqww095wpF6jeMLu6nGeJULnd3DOEhfMj4OKCPJXHLodZYlAuNi7KYCHdXV5dXBCpYu5ylYVl+ZklC+VSJxZ/FnKty0GWPJULi+XHNnyLhWURZCFzXF6yRKo8czmwzQssLMsZllCVo0sbZs9ix1nIMJdnLLkqND2LnWYh2XKRY2FZjrEkF8upL1GsWViWMxv9lyVbxZMFYLaK6VmsLJos6SrLWchYF2MWlqUsZbFXOXAX4crCsii6ZLO4lgvLUpayRKgsveazLGUpS4pKWQ4ewrIo" +
      "9mtrtSiwXC3CfSy3DluvLY9ZDLom7mOxaGZpx3LpePUPsmR76bK8U4GLyioWlGW1SlnOTLssioHZfQ0mGWPeTywkA3ECisWRBYg/hzEvNbMsK1hQlhMTLssGlbIcmW5ZVrCgLCdmWxbJRLP2SJJsPx9RLGVpsYxMtiz5LOil5dRcy5LOYtsJmWVZzuIa2c6ylOU3lptT9Y8KMWJ5v2LGqg+y4Cc6TW0ri+QTMUkWmBdLWUKDWsdYJNaY2fwRE2XB7nD2TBZ3la9Z7k9VRKUsM8sByvLjVCVUyiL5aQPLAsFFWHzzR0yaBe/f1b5auAHtxYSPX6CzLD9uCSjL5FxffmpSll+2higVF5b/2R6AtGIxYfnvTQIoy9s7iulvF1kWxVGWHBaUJbZYxlhYlvssG8rl6XLzspQlX6UsoSwsi2yxKC6kKEtZZvs9lsW6WMoiWSyCK43LUhY1lbIoF8skC9NVyhKq8jMLypLCwmyVkz1kyyKk8oiFZbnNElouGirDLMxVKUtqsbxjYYvlMktguVDlHDbOwqpIsjBSRYglrFyUVB6wMFAlgYVVucqCstxaVIWWi2CxEHXRaPZHARZWRZKFQSp6LAkuiiplYSKLvQs1cy/MH4W/V7kTdGX/2PUxyqWQGP8nfIkqxFoXsiwhmcxjiUrY6UJKFwtTnl04q9xhsXOhvAqxzoUsix6MhQrBpJtlvxzrqywmLiQ9ioUgZXbYyeRygiJkLi+CLY3fJSjiZSLzGAzNVAhKlYtMBksKCygJQzqqEBR0UZzRbAgsZA+CrMlENC+Uf5ySJiPRvLh+ZzR+CHh7DFz5QHGXjybHiTHxfwQDt6wjB4NTA4MslGf573lydMz8eQddykVjYJalLlJ3upi6b63KVyx1EVK5wYKqHGSpi47KHRZU5ccjBNblxWugNyyoyk+HB6yLngrBusy/yH7Igqp8f2Tw8O/GUpTnLKjKl0cFrIueCsG6DH9OqMCConxzQGD6VWO2" +
      "CsG66KmMsHjCAFosdXm/dACsy9xCG6qxeMFAkmW5C56rEN6LskJVCNGTax7KR/sO1bNrGspnew7lUg5COcXitBibcW0BoF/QCSif7jEcStoe5ePdRUyzD+V2MzzJQqyAAcxY5GrbE+WL3cTrScebfLWLSOvypdfyj54sb2QAYRXC+Cdl0bOUd1jEf1ahfWQR8NMS7rnMeyyEa5/i5+3JeZPFt63341b+vMtC53SCd6kXvM3CzYmQT3KgDHbQM3iMEywKAWt0ShnlDItozL3q4BRLXSYviqyLYiAv66IY/cq6KEa/si6KKaOsi+DTCbAugo+MwLooBlqyLoqJlqyL4kNvsjCCkZasi+C7O7AuipmWrIti1JPpq79olJ9Y6nIx1pJ1UfxQh3VRTBt1/rYkVoXe3/yEohxgWQ1DYRYWRZKFVZFk2QhDGrCwKpIsu2BIG5Y9MKQVC6siybIBhjRkSYchTVlYlQPjH7ZeIDVEzPRbAAAAAElFTkSuQmCC";

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
      ".dsh-houdini-workspace-warning{font-size:11px;color:var(--dsw-alias-label-secondary);border-left:2px solid #f70;padding-left:6px;max-width:min(650px,80vw)}" +
      ".dsh-houdini-workspace-warning summary{cursor:pointer}" +
      ".dsh-houdini-workspace-warning code{overflow-wrap:anywhere}" +
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
        var projected = sess && sess.projectionValues && sess.projectionValues.agentPreset;
        return typeof projected === "string" ? projected : "";
      });
      if (preset !== "houdini") return null;
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

    // Both Trace and the workspace warning consume this same execution record.
    // Native calls carry meta; DSH PTC subcalls carry a call-bound log record.
    function readHoudiniCanonical(node) {
      var name = node && (node.call && node.call.name || node.name);
      if (typeof name !== "string" || name.indexOf("houdini_") !== 0) return null;
      if (node.meta && node.meta.canonical) return node.meta.canonical;
      for (var block of node.content || []) {
        if (!block || block.type !== "text") continue;
        var record;
        try { record = JSON.parse(block.text); } catch (_error) { continue; }
        if (record && record.kind === "dsh-houdini/execution-v1" &&
            record.callId === node.callId && record.tool === name) return record.value;
      }
      return null;
    }

    // This is a last-observed fact from a Houdini tool result, not a live HOM
    // query. A changed HIP cannot be inferred until another result arrives.
    function HoudiniWorkspaceStatus(props) {
      var row = props.useSessions(function (s) { return s && s.byId && s.byId[props.sessionId] || null; });
      var trajectory = props.useTrajectory(function (s) { return s; });
      var cwd = row && row.cwd;
      var preset = row && row.projectionValues && row.projectionValues.agentPreset;
      if (preset !== "houdini" || typeof cwd !== "string") return null;
      var nodes = [];
      function collect(node) {
        nodes.push(node);
        for (var child of node && node.subCalls || []) collect(child);
      }
      (trajectory && trajectory.eventNodes || []).forEach(collect);
      nodes.sort(function (a, b) { return (a.seq || 0) - (b.seq || 0); });
      var hip = null;
      for (var i = nodes.length - 1; i >= 0; i--) {
        var node = nodes[i];
        var canonical = readHoudiniCanonical(node);
        var observed = canonical && canonical.execution;
        if (observed && "hip_dir" in observed) {
          hip = typeof observed.hip_dir === "string" ? observed.hip_dir : null; break;
        }
      }
      var norm = function (path) { return path.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase(); };
      if (!hip || norm(cwd) === norm(hip)) return null;
      return React.createElement("details", { className: "dsh-houdini-workspace-warning", role: "status" },
        React.createElement("summary", null, "Session workspace 与最近一次 $HIP 目录不一致 · 点击查看"),
        React.createElement("div", null, "Session workspace: ", React.createElement("code", null, cwd)),
        React.createElement("div", null, "最近观察到的 $HIP 目录: ", React.createElement("code", null, hip)),
        React.createElement("div", null, "切换 HIP 后使用 DSH-Houdini → Open Workspace；交付时采用回执中的绝对路径。"));
    }

    // --- 词表目录（构建期生成，勿手改） --------------------------------------
    // >>> houdini-catalog (generated by tools/gen-client-catalog.mjs — do not edit)
    function getTraceCatalog() { return [{"domain":"vocabulary 域","note":"vocabulary 域（回答「动词怎么调用」）","verbs":[{"name":"verb_help","sig":"name","desc":"返回已注入动词的准确signature、return_type（无注解则null）、call_mode与docstring；已维护结构合同的动词另返回operation_contract，包含input_schema/output_schema/examples/notes及schema/execution范围。name也可为1..16项唯一名称列表，批量返回items/count。未知名列相似项，批次任一未知则整次明确失败。Bridge对签名绑定错误返回真实signature和零写入证据，实施内部TypeError不冒充绑定失败。用于在调用前发现契约，不靠失败或读取仓库源码猜参数/返回形状；未维护的结构不伪造完整schema","returns":"dict"}]},{"domain":"类型目录","note":"类型目录（回答「能建什么」）","verbs":[{"name":"search_tab_menu","sig":"category, query","desc":"列出某 context 下匹配的节点族 + 最新版","returns":"dict"},{"name":"search_tab_entries","sig":"parent, query","desc":"按真实父网络列当前可见的 node/tool entry；排除 hidden/deprecated，Material Library 根层只暴露 Builder tool；每项标 `kind` 与 dsh 是否可安全执行","returns":"dict"},{"name":"resolve_latest_type","sig":"category, base","desc":"已注册节点族的最新版全名（内部为主）；只以 namespace 注册的族返回带前缀全名（'rigdoctor' → 'kinefx::rigdoctor'），裸别名过不了 `createNode(exact_type_name=True)`；跨 namespace 同名按排序取第一个，recipe 需跨版本一致时应显式钉命名空间；当前类别没有该族时明确失败，不回传未经验证的base","returns":"str"}]},{"domain":"node 域","note":"node 域（场景图）","verbs":[{"name":"tab_create","sig":"parent, type_name, name=, inputs=[...], parms={...}","desc":"建**单个可见节点**：最新版 + 对应 shelf 初始化；类型、输入和参数形状先预检，静态失败返回零写入事实。inputs中的直属child名称相对实际parent解析，None保留空槽。可选非空`parms`在创建/接线后走严格set_parms，任一失败会连同 partial create 清理并报告恢复结果；拒绝 hidden/deprecated 和 Material Library 根层直建 shader，setup/builder 改用 tab_apply；parent 接受 Node/path。连完 inputs 后自动落位：有输入时放到所有输入下游（x = 输入 x 均值，y = min(输入 y) − 垂直间距）；无输入时放到父网络现有内容右侧新列（x = max(现有 x) + 水平间距，y = 现有最顶部 y，空网络落原点）；间距由节点实际网络尺寸（`Node.size()`）推导，不用拍脑袋常量","returns":"`hou.Node`"},{"name":"tab_apply","sig":"parent, tool_id","desc":"应用 allowlist 内的非交互 Tab setup recipe，返回全部新增节点/输入；GUI 恢复 Network Editor pwd/selection，同一 exec 多次调用共享用户基线；headless 同语义。首批仅 Karma Setup / Karma Material Builder。SideFX recipe 自己摆节点，tab_apply 不做自动落位","returns":"dict"},{"name":"find_nodes","sig":"pattern=\"*\", category=None, node_type=None, root=None","desc":"找**已存在**节点（扁平清单）","returns":"path 列表"},{"name":"graph","sig":"node, depth=1, direction='both'","desc":"围绕**该数据节点**查 inputs / outputs / parm_refs；检查最终 SOP 网络应对 `OUT` 向上查，不要对父 OBJ 容器调用","returns":"dict"},{"name":"describe","sig":"node","desc":"状态 + 几何摘要 + `attrib_delta`（相对 input 0 的属性增删——MMB 节点信息里「这个节点对数据干了什么」的固化）+ 帮助元数据","returns":"dict"},{"name":"node_provenance","sig":"node","desc":"报告 runtime owner、可复制的 audit tag、当前 session 是否可写；`foreign`/`owned_current_session`/`owned_other_session`/`dsh_service` 分开","returns":"dict"},{"name":"connect","sig":"src, dst, index=0, *, output=0, allow_foreign=None","desc":"index为目标输入名/索引，output为源输出名/索引；精确名称不是label，先解析两端及原生兼容性再写入，回读实际源输出。output默认0，第4位置参数拒绝。mutation边界在dst；OBJ→OBJ拒绝并指向set_object_parent，跨parent拒绝，不猜端口或绕Gate。describe.ports提供有界名称/索引/类型；verified仅连接回读，不证明语义；连接后仅必要时调整落位","returns":"dict"},{"name":"node_info","sig":"parent, type_name, parm_filter='', limit=24","desc":"创建前读取实际parent最新版类型、端口、参数默认值/组件名/menu token/set_value与帮助URL；parm_filter只作字面子串筛选。operation_card含决策/版本，operation_parameters保留不受筛选/limit裁切的关键设置，缺字段显式报告。不建临时节点/不运行Shelf；动态菜单需list_parms，truncated明示。没有delivery准入","returns":"dict"},{"name":"modeling_dimensions","sig":"quantities, require_meter_scene=True","desc":"只读源单位换算：quantities={name:{value,unit,min?,max?,source?}}，最多64项；长度m/cm/mm/um/in/ft转米，面积/体积按平方/立方换算，rad转deg、count/ratio不按长度缩放。默认要求当前HIP=1m且不改单位；旧工程须显式False并消费scene_values。返回原始依据、canonical_values、scene_values及米制CTRL spec；不证明最终尺寸","returns":"dict"},{"name":"sop_recipe","sig":"kind, spec=None","desc":"只读普通SOP配方，catalog给schema，kind单独调用给结构模板示例；hinge/slider/repeat共享origin/axis及CTRL标量，Merge源与附件→FRAME→Copy；sweep_tube/profile_shell为单中心线/平面薄片成形；guided_slider用真实source/guide投影推导位置并拒绝越界，surface_attach在指定面组投影并取法线frame；gusset/fastener提供带厚度肋板与头杆源。返回nodes/output/required_outputs交给build_module，不创建/cook；不猜坐标、不认领输入、不保证接合。字段、适用前提和反例见SOP配方reference","returns":"dict"},{"name":"control_test_plan","sig":"controller, parameters, max_cases=16, domain=None","desc":"只读数值参数规划；1..8标量各2..8显式levels，最多4096候选，贪心覆盖levels与两两组合，最多16case。domain只预筛独立无keys标量，记录排除数与missing；返回tests的expectations为空，须由作者补独立指标/状态接口后test_controls执行，不是全域证明","returns":"dict"},{"name":"build_module","sig":"parent, nodes, output, dry_run=False, interfaces=None, *, required_outputs=None","desc":"批量新增{name,type,parms?,inputs?} SOP节点，列表非空；inputs可引用任意声明/现有直属child名，声明顺序自由，None保留空槽。先创建全部节点，再接线、设参，表达式可引用本批任意节点。独立静态错误汇总零创建拒绝；size=1/组件按标量校验，多分量tuple接受等长数值列表，与实际setter同源。dry_run只预检真实类型/参数/引用；操作知识按需读node_info，不从缺字段推断未决设计。required_outputs可显式检查必需新分支，可附实际interfaces。返回validation/interface_checks；失败清理本批新节点，不覆盖已有节点/flags","returns":"dict"},{"name":"verify_network","sig":"parent, output=None, nodes=None, limit=512, require_valid=True, *, output_index=None","desc":"SOP checkpoint：必须显式output，不跟随display。output_index=0..63另验同父网络原生Output接线；默认检查直属范围，可nodes限域，error/空输出默认拒绝。geometry给bbox_min/max/size，所有显式输出均回scene_unit_length_meters与bbox_size_sop_local_mm，须结合OBJ变换核物理尺寸。handoff_output给出名称/type/Null/leaf、显示/渲染旗标及父网络当前出口。不按输出名称追加表面或上游Sweep检查；需要时显式调用geo_piece_stats等领域工具。它不自动发布，不证明OBJ可见、部件关系或艺术质量","returns":"dict"},{"name":"set_object_parent","sig":"child, parent, keep_world=True, reason='', index=0, allow_foreign=None","desc":"显式 OBJ parenting/unparent（`parent=None`），自然参数序为 child→parent；普通父级用 input 0，Blend 等明确多输入对象可指定 index。`reason` 为可选自由用途说明，表示与方法由当前任务决定。拒绝非 OBJ、自环/层级环；mutation/ownership 边界在 child；默认恢复 child 原世界变换并回读 parent、local/world delta","returns":"dict"},{"name":"disconnect_input","sig":"dst, index=0, *, allow_foreign=None","desc":"断开普通网络 destination 输入；权限理由keyword-only非空字符串；OBJ unparent 拒绝并指向 `set_object_parent(child,None,...)`；ownership 边界在 dst，返回原 source path（若本来为空则为 null）","returns":"dict"},{"name":"rename_node","sig":"node, name, allow_foreign=None","desc":"重命名","returns":"新 path"},{"name":"delete_node","sig":"node, allow_foreign=None","desc":"删除前核对全部后代身份；返回外部参数引用及最多64项affected_connections（目标输入、原源输出及inputs_after），提示原生删除可能旁路重接，同名新节点不继承接线。拒绝删除owner-tagged render_view会话级基础设施。创建时同步新HDA的延迟定义后登记原生后代；不收养后来加入的foreign子节点","returns":"dict"},{"name":"cook_node","sig":"node, force=False, timeout_ms=30000","desc":"cook + error/warning，timeout_ms为1..120000的协作预算，仅原生中断检查点可响应，不保证强制停止/内存安全。Manual返回ok=False/status=not_cooked_manual，不自动切Auto；预检输入计数恒条件、平直删除语句组成的已知无界VEX循环，未知控制流不作安全认证。依赖规模本身不拒绝；verify_network的内部只读批次共享一次完整上游预检，不跨调用缓存。warning未解释不得当完成","returns":"dict"},{"name":"sop_set_output","sig":"node, render=True, allow_foreign=None, *, output_index=None","desc":"默认仅移动SOP display/render旗标。显式output_index=0..63复用/创建同父网络原生Output并接线，将旗标设到它；重复索引/循环/foreign接口写入拒绝，逐层发布不猜祖先。返回public_output接线事实，不cook/保存HDA，须另验几何、新实例与根显示；不是render_view前置条件","returns":"dict"},{"name":"sop_output_node","sig":"parent","desc":"报告 SOP 网络 display/render 输出；旗标不在链尾时提醒","returns":"dict"},{"name":"set_object_visible","sig":"node, visible=True, allow_foreign=None","desc":"设置单个 OBJ 的 viewport visibility（OBJ 没有 SOP 式 render flag）","returns":"dict"},{"name":"visible_objects","sig":"root='/obj'","desc":"列出 OBJ 层 plural visibility/effective visibility，并附每个对象的 provenance","returns":"dict"},{"name":"layout_nodes","sig":"parent, nodes=None, horizontal_spacing=-1, vertical_spacing=-1, allow_foreign=None, mode='children', *, boxes=None, profile='comfortable', dry_run=False, expected_plan=None","desc":"`children`原生layoutChildren、`flow`节点拓扑分层；已有成员Network Box时，两者无显式nodes的整网重排写前拒绝，明确的局部nodes列表仍可用。盒布局用`handoff`处理叶子框，`component`处理一层组件容器，需显式boxes；可直接应用，也可dry_run取得plan_sha256，提供expected_plan时才检查计划仍新鲜。重复应用零写入。默认只移动当前session自有项，单次allow_foreign仅用户明确授权的既有项，持久service不豁免。未选节点/Box与Sticky Note/Dot是固定障碍；量测失败零写入。返回实际节点/盒重叠、containment和净距；只证明network-editor布局，不证明接线或艺术质量","returns":"dict"},{"name":"network_boxes","sig":"parent, groups, *, remove=None, dry_run=False, expected_plan=None, allow_foreign=None","desc":"按显式groups整理Network Box：每项需要name，可选label/role/members/boxes/color；label默认name，role只提供颜色提示，未知role用中性色。members为parent直属节点，boxes可引用已有框或本批声明框，两类成员可共存，声明顺序自由，真实循环写前拒绝。可直接应用，dry_run为可选零写入预览，expected_plan仅在显式提供时核对新鲜度。已有框保留现色，显式RGB三元组才改色。移动显式成员时核对实际受影响的来源框和目标框权限；Box权限独立记录，foreign需单次授权，render服务不豁免。失败恢复成员、位置和外观；分组本身不cook、不证明布局或几何正确","returns":"dict"}]},{"domain":"parm 域","note":"parm 域（依附 node）","verbs":[{"name":"list_parms","sig":"node","desc":"参数**目录**：名字/标签/类型/帮助/默认值及实际 menu token/index/label（不给当前值）；动态菜单以实际节点为准","returns":"list"},{"name":"read_parms","sig":"node, changed_only=True, *, names=None","desc":"参数**值**：默认只看非默认 + 带表达式/动画 + 被引用的（意图解读）；names可选1..32个唯一标量或tuple字段，按请求顺序返回且不受changed_only过滤，tuple给聚合value/component_names及逐分量诊断，缺失报错。无动画string含原始UTF-8源码source_sha256，展开值不同于原文时另含raw_value；表达式附referenced_parm，被引用标referenced_by；动画附time_dependent/key_count/first_frame/last_frame/curves，不默认倾倒全部keys","returns":"list"},{"name":"set_parm","sig":"node, name, value, allow_foreign=None","desc":"设参（数值字符串=表达式）。已有表达式/keys在普通赋值时清除，note说明变化。字面string可传`{expected_sha256,patch:[{old,new,count}]}`：精确版本和次数、全部锚点先验，拒绝锁定/动画/表达式/callback/固定菜单；返回patch前后hash/字符数/次数及value_omitted，不回传整份源码。最多32项，source/result各524288字符、替换文本累计131072字符、count为1..256；不执行正则/脚本。文本通过不证明cook/几何通过","returns":"dict"},{"name":"set_parms","sig":"node, values, allow_foreign=None, strict=True","desc":"默认严格批量设参：预检名称/重叠/锁定；value支持set_parm的string patch对象，本节点本批全部patch在任何设参前验证。patch只允许strict=True，set内返回变化摘要，patched列出字段；失败恢复本批值/表达式/keys。其他节点不在本批预检范围，参数回调/外部文件不属快照回滚。无patch的显式strict=False仍返回ok/set/failed；Menu string为精确token，数值string为HScript表达式，表达式对象可声明language","returns":"dict"},{"name":"set_keyframes","sig":"node, channels, replace=True, allow_foreign=None","desc":"批量写数值标量 channel keys；统一 frame 单位，有限曲线 `constant/linear/bezier`。全量预检包含锁定状态，失败恢复原值、表达式、keys和frame，并明确restored/restore_errors；提交后回读/采样并恢复用户frame。只负责channel数据，不代替路径依赖状态机或KineFX/APEX","returns":"dict"},{"name":"create_spare_parms","sig":"node, code_parm='snippet', defaults=None, spec=None, allow_foreign=None, *, update_defaults=None, layout=None, dry_run=False","desc":"缺省扫描代码参数的 `ch/chf/chi/chv/chs` 引用并创建缺失 spare parameters。`spec=[...]` 的精确条目为 folder `{type,name,label?,parms:[...]}` 或 scalar `{type:'toggle\\|int\\|float\\|string',name,label?,default?,min?,max?,min_strict?,max_strict?,help?}`；spec必须用具名参数，严格上下限字段只接受min_strict/max_strict。spec 返回 `{node,mode,created,leaf_values}`；扫描返回 `{node,code_parm,references,created,existing,defaults_applied,unsupported}`；创建仍拒绝同名覆盖。新建接口后重新赋写code_parm原始源码/keys以刷新编译依赖，保留表达式与动画；返回refreshed_code_parm（未刷新为null），锁定源码在接口写入前拒绝。显式 `update_defaults={name:literal}` 仅更新1..32个已有scalar spare的默认值，与spec/defaults/非默认code_parm互斥；保留当前值/表达式/keys，返回updated前后值及current_state_preserved。支持float/int/toggle/string，拒绝内建/tuple/menu/callback/multiparm及表达式默认值；当前值另用set_parms。layout与spec/defaults/update_defaults互斥，复用共享UI组件，默认追加并拒绝已有模板/参数名冲突；dry_run仅layout有效，预览零写入。应用保持已有通道值/keys/locks，失败恢复节点接口及通道，不修改HDA定义或绑定","returns":"dict"},{"name":"parameter_ui","sig":"node, max_depth=6, include_state=False, analyze_ui=False","desc":"任意节点参数界面只读自省：类型/可选定义文件与section、实例interface及definition.interface，含范围/默认表达式/回调/菜单生成器/条件/tags、tuple look和Ramp类型。include_state返回至多512通道raw值/keys/locks；analyze_ui返回非阻断结构建议。不执行菜单/表达式/cook，不自动修复或创建绑定","returns":"dict"},{"name":"bind_controls","sig":"controller, bindings, *, dry_run=False, expected_plan=None, replace_existing=False, allow_foreign=None","desc":"1..32项明确数值绑定：source为控制节点参数名，target为目标参数绝对路径，可选scale/offset。dry_run返回plan_sha256；应用必须expected_plan匹配identity/值/keys/锁定/帧。默认拒绝已有驱动，replace_existing显式替换；拒绝非数值/菜单/回调/multiparm、任意表达式源、批次源目标交叠及重复目标。整数目标只接受整数源与映射系数。实际HScript引用和值回读，失败恢复本批目标通道；不保证领域输出或外部副作用","returns":"dict"},{"name":"set_update_mode","sig":"mode, expected_mode","desc":"显式切换auto/manual/on_mouse_up，expected_mode防止覆盖过期用户状态；无GUI拒绝on_mouse_up（原生会降为auto）。after/changed取实际回读，未应用请求或setter失败会尝试恢复并报告结果；模式恢复不撤销触发的cook/外部副作用。切Auto可能触发全场景计算，不是取消接口","returns":"dict"}]},{"domain":"scene 域","note":"scene 域（工程/时间线）","verbs":[{"name":"scene_info","sig":"","desc":"只读 HIP/version/fps/current frame/time/frame range/playback range/UI 状态及 `unit_length_meters`（1 个场景单位对应的米数，无法读取时为 null）；明确区分 `has_named_path`、`has_unsaved_changes`、`dirty_reliable`、`clean_on_disk`，不再用路径存在冒充保存完成；hython 的 dirty 不可靠时 clean=null；不移动 playbar、不遍历整张节点图","returns":"dict"},{"name":"scene_save","sig":"expected_path=None","desc":"只保存当前已命名 HIP，不承担 Save As/open/new；可选 expected_path 作防串场断言，返回 dirty before/after/reliable、clean（headless=null）、bytes、mtime_ns","returns":"dict"},{"name":"scene_save_as","sig":"path, expected_current_path, reason, overwrite=False","desc":"用户授权的 Save As：明确绝对 HIP 路径，expected_current_path 防串场，reason 记录路径/覆盖授权；已存在目标必须 overwrite=True。拒绝插件仓库落盘，回报前后路径/dirty/file/workspace_changed。无 load/clear；文件写不可撤销，失败可能留部分新文件，跨目录后 Open Workspace 重新绑定","returns":"dict"},{"name":"set_timeline","sig":"fps=None, frame_range=None, playback_range=None, current_frame=None","desc":"设置明确的时间线字段；至少一项，所有字段的有限数值/范围写前校验，成功回读scene_info。写入失败恢复fps、两种范围和当前frame并报告restored/restore_errors；不恢复触发的cook或外部副作用","returns":"dict"},{"name":"list_bookmarks","sig":"","desc":"列出 bookmark id/name/start/end/enabled/visible/comment","returns":"list"},{"name":"create_bookmark","sig":"name, start, end, replace=False","desc":"创建整数帧 bookmark；同名默认拒绝，replace 精确替换","returns":"dict"},{"name":"delete_bookmark","sig":"name_or_id","desc":"按精确名称或 session id 删除，失败列现有项","returns":"dict"}]},{"domain":"geometry 域","note":"geometry 域（几何数据）","verbs":[{"name":"geo_attrib_stats","sig":"node, name, attrib_class='point', *, unique=False, max_elements=100000","desc":"数值min/max/mean/count；unique=True全量检查精确完整tuple（含字符串），返回unique_count/duplicate_count/all_unique及至多8个重复样本。用P查精确重叠、用id查身份；超预算/非有限拒绝，无容差焊接或自动删除。point/prim/vertex/detail","returns":"dict"},{"name":"geo_point_spacing","sig":"node, expected, tolerance, closed=False, order_attrib=None, max_points=10000","desc":"全量相邻点弦长验收：默认point number顺序，或唯一数值order_attrib；closed含末→首，SOP local单位；返回全量min/max/failure_count及最多16个最差对与sequence hash。超预算拒绝不抽样；只证明该序列约束，不证明弧长、网格接线或实际零件关系","returns":"dict"},{"name":"geo_check_interfaces","sig":"output, interfaces, max_pairs=50000","desc":"同一最终SOP内1..16实际关系。默认{id,source_group,target_group,max_distance,expected_points}测独立表面点到面距离；method=axis_gap用两个primitive组及axis/gap_range/min_overlap测投影间隙。method=solid_overlap用两个独立完整闭合朝外Polygon实体组和max_overlap_volume，在内存副本做Boolean Intersect量实体相交体积，非零有效交集返回SOP局部包围盒（多处交集仅为外包络）；实心轴穿实心铰耳fail，有孔且留间隙pass，开放/不完整/非Polygon/数值含糊为unverified。method=axis_passage用最终Polygon target_group、axis及SOP local start/end测一条跨越该组包络的轴线；碰到最终表面fail，无遮挡pass，缺组fail，非Polygon/未跨包络unverified。它不证明孔径、孔壁或其他轴；后续增材须复验。solid_overlap每组最多20000面；面包围盒扫描筛候选，共用max_pairs候选预算与2000000扫描访问预算，完整实体仍交Boolean处理包含关系；不建场景节点、不抽样。零交集不证明同轴或真实穿孔；三态分别检查，不证明连续运动、受力或公差。返回实际值/范围/几何hash","returns":"dict"},{"name":"test_controls","sig":"controller, output, tests, interfaces=None, allow_foreign=None, *, domain=None, topology=None, baseline_interfaces=None, views=None, view_bounds=None","desc":"可恢复数字控制测试，必须exec：1..16个 `{id,values:{parm:number},expectations:[{metric,axis?,group?,delta:[min,max]}],interfaces?}`，每个case最多16个expectations；同一扰动的大检查用相同values拆成多个case。metric支持bounds_size/center/min/max(axis)、point_count、primitive_count、area、point_mean(axis)、boundary_edges、piece_count、max_point_displacement/mean_point_displacement；max_transform_error另给16数row-major仿射transform，测实际点相对声明变换的最大残差。位移/变换要求稳定唯一id_attrib和相同Polygon拓扑。range验基准/扰动绝对范围，至少一项delta排除0。顶层interfaces在基准和全部case复查，baseline_interfaces只验基准，case内interfaces只验对应扰动；适合合盖接触与开盖分离等不同合同，均用geo_check_interfaces的schema和预算。control_summary区分已声明与实际执行的关系覆盖；基准失败时参数零写入且results=[]明确标not_run。domain/topology复查声明关系；恢复参数/keys/frame及完整bgeo内容（内嵌Packed临时地址转内容引用、忽略对应writer索引偏移；排除导出头date/派生group_summary，组目录按名规范排列；保留成员及组内顺序）。Polygon/Mesh/Sphere/Tube/点支持范围各指标明确，嵌入PackedGeometry在内存副本展开量测，原载荷/属性/变换按内容指纹验证恢复，其他写前unverified。拒绝callback/menu/button/multiparm/tuple列表值，foreign需单次授权；只证明声明case，非外部副作用恢复或艺术/强度认证","returns":"dict"},{"name":"geo_piece_stats","sig":"node, piece_attrib=None, sample=16, *, inspect=False, group=None, basis=None, integrity_only=False","desc":"默认统计primitive piece局部bbox/extent/面积；无piece属性用内存Connectivity SOP Verb。inspect=True按精确primitive组观察有界Polygon边界/非流形/边连通、正交basis下extent、surface_area、duplicate_boundary_faces、closed_planar_components及center_axis_surface_hits。仅近看Polygon完整性时用inspect=True, integrity_only=True：跳过昂贵的中心线/截面诊断，最多100000 prim/400000顶点引用，返回非流形、相邻面朝向冲突、闭壳有向体积符号、显式N与几何朝向相反的样本、零面积/零边及完全重复面风险；平面大面以重复点桥接孔时另报planar_repeated_point_ngons/shading_review_status，提示同角度近景复核，不把合法布线判破面。负号提示核对整壳朝向，嵌套空腔的内壳可有意反向，不能自动判错。开放边单列open_boundary_unreviewed，可能是有意接口，需按设计核对。风险/超预算在Bridge摘要与执行提醒中保留；no_detected_integrity_risk只表示本检查未发现列出的风险，不认证任意重叠、自交、接触、外形、着色或强度。普通完整inspect仍保持原预算与语义；不支持或超预算为unverified","returns":"dict"},{"name":"geo_frame_diff","sig":"node, frame_a, frame_b, attrib='P', sample=4096, tolerance=1e-6","desc":"用geometryAtFrame比较两帧point数值属性，correspondence为point_number，不能证明跨拓扑变化的稳定身份。可比较时精确返回键`mean_delta`、`max_delta`、`delta_percentiles.{p50,p90,p99}`、`component_delta.{min,max,mean}`、`unchanged_pct`（另含sampled_points/tolerance/data_type/size），不是`mean/max`。不移动playbar；只证明所声明对应与抽样范围内的数据变化，不单独证明审美/运动语义","returns":"dict"}]},{"domain":"component 域","note":"component 域（普通 SOP 组件交换）","verbs":[{"name":"component_export","sig":"node, filename, contract","desc":"候选：当前作者普通SOP subnet导出至已命名$HIP内新.dshcomponent；contract必含module_id/revision/units/outputs，可选inputs声明公共输入槽位（唯一0..63），输出索引须由sop_set_output发布。运行时verb_help提供可执行的最小示例和字段约束；检查公共输出、有限依赖与快照。同构建往返，不覆盖文件，不证明装配质量；文件写入不可Undo","returns":"dict"},{"name":"component_import","sig":"parent, filename, expected_sha256, name, trusted=False","desc":"候选：显式可信、hash固定、同构建普通subnet片段导入当前作者SOP父网络；SHA-256接受大小写十六进制并返回规范小写；新名字、不覆盖、不接管旧节点，返回待验收candidate。原生档案可执行代码，trusted不构成安全沙箱；尚非自动子作者交付通道","returns":"dict"},{"name":"component_replace","sig":"node, candidate, dry_run=True, expected_plan=None, expected_contract=None, migration=None","desc":"候选：同作者同父普通subnet的显式替换；先预览，再用未过期plan提交。输出接线总是迁移；已连接根输入、公共参数值/keys及其外部表达式消费者只在migration显式声明时迁移（inputs逐槽映射、public_parms按名），未声明即拒绝，不按位置猜。保留旧网络不删除/改名；plan失配按侧命名（old手改=保留的本地分叉/candidate被改/消费者接线变化/身份重建/迁移面漂移）。expected_contract恰含module_id+正整数revision，把候选钉在本session导入记录的合同上，拒绝迟到的旧修订与无provenance候选。带表达式的keyframe、keyframed消费者、不可识别的表达式引用形态明确拒绝；任何失败逆序恢复接线/表达式/参数值（回滚账本先登记后变更，恢复失败聚合上报RuntimeError）。提交后仍须实际装配关系/视觉复验","returns":"dict"}]},{"domain":"runtime 域","note":"runtime 域（运行时包自省）","verbs":[{"name":"package_info","sig":"name=None, limit=64","desc":"官方运行态package清单；精确name另给有界资源路径。省略环境变量值，不扫磁盘、不加载或改包；GUI接口不可用返回unavailable而非空清单。Active不证明兼容/授权，publisher未验证；Bridge回执提供runtime身份","returns":"dict"}]},{"domain":"cop 域","note":"cop 域（Copernicus 图层与关系）","verbs":[{"name":"cop_layer_stats","sig":"node, output=0, *, max_pixels=4194304","desc":"必须exec：直接读取当前ImageLayer，output为源输出名/索引；完整buffer统计/指纹、类型/通道、data/display window、空间、pixel scale、frame、U/V梯度。max_pixels为1..16777216，超预算拒绝不抽样，预算不限制上游GPU cook分配。拒绝Manual、失败cook、非图层和未支持storage；非有限值fail，sticky Cache新鲜度unknown；不证明视觉或外部文件最新","returns":"dict"},{"name":"cop_compare_layers","sig":"before, after, *, before_output=0, after_output=0, expected_delta=None, tolerance=1e-6, max_pixels=4194304","desc":"必须exec：测after-before，完整通道/窗口/空间对齐，不静默重采样；无expected_delta仅量测status=unverified。expected_delta={node,output?}时检验max(abs((after-before)-expected_delta))<=tolerance，返回实际操作数/公式/误差；非有限、错位拒绝，sticky Cache不认证通过；不判断作者选对了数学对象或艺术效果","returns":"dict"},{"name":"test_cop_controls","sig":"controller, output, tests, *, output_port=0, max_pixels=4194304, allow_foreign=None","desc":"必须exec：1..16个{id,values:{parm:number},expectations:[{metric,channel,delta:[min,max],range?}]}；metric为mean/min/max/mean_abs_change/max_abs_change，变化指标基准0。每case至少一项非零预期，range验基准与扰动；复用参数/keys/frame恢复并比较完整图层/元数据指纹。拒绝菜单/回调/multiparm/tuple、Manual、sticky Cache和无效基准；恢复失败抛CheckpointError，已恢复的失败仍fail。仅声明case/输出范围，不恢复外部文件/Python/solver副作用，不替代语义读图","returns":"dict"}]},{"domain":"stage / USD 域","note":"stage / USD 域（Solaris 只读自省）","verbs":[{"name":"usd_stage_summary","sig":"node, max_paths=64","desc":"概览某 LOP 输出 stage 的 geometry/material/light/camera/RenderSettings/Product/Var，材质绑定、time-sampled 属性及 cook warning；路径按组限量但计数完整","returns":"dict"},{"name":"usd_prim_info","sig":"node, prim_path, max_properties=200","desc":"检查单个 USD prim 的属性、primvar、relationship、material binding、time samples；points/topology 等大数组只报结构不整段拉取","returns":"dict"}]},{"domain":"asset 域","note":"asset 域（HDA / 数字资产）","verbs":[{"name":"hda_create","sig":"node, name, description=None, hda_file=None, min_inputs=0, max_inputs=0, replace=False, allow_foreign=None, *, max_outputs=None","desc":"把已有节点（通常 subnet）转为数字资产：自动建 otls 目录、默认 `$HIP/otls/<name>.hda`。max_outputs可显式声明1..64个输出上限，None保留原生默认；非法值写前拒绝。返回输入/输出上限、实例/定义顶层参数条目数和verification_scope，不承诺spare自动迁移或公共输出正确。`replace=True` = 整体重建：所有待销毁实例逐项通过 ownership guard 后，卸载旧定义并覆盖文件；否则同名冲突报错并提示 replace","returns":"dict"},{"name":"hda_get_section","sig":"node, section='PythonModule'","desc":"读 HDA section 内容；section 不存在时列出现有 section 名供自纠","returns":"dict"},{"name":"hda_set_section","sig":"node, section, code, allow_foreign=None","desc":"全量写 section。`PythonModule` 先 `compile()` 预检语法（带行号报错，不写脏）；写后读回校验一致","returns":"dict"},{"name":"hda_patch_section","sig":"node, section, old, new, count=1, allow_foreign=None","desc":"锚点局部替换：`old` 必须恰好出现 `count` 次（0 = 锚点没找到，>count = 锚点不唯一需加长），替换后同样过语法预检；**模块改局部时用它，不要全文重发**","returns":"dict"},{"name":"hda_set_interface","sig":"node, spec=None, keep_std=True, hide_builtin_tabs=False, allow_foreign=None, *, edits=None, expected_sha256=None, dry_run=False, layout=None","desc":"spec/layout整组重建，均检查共享实例ownership；layout与spec/edits互斥，最多512条/12层。支持label/ramp、tuple、multiparm、条件及组件；SOP标准输入Label隐藏。dry_run各模式统一返回ok=true、dry_run=true、applied=false、scene_writes=0，只表示预检成功；spare冲突写前拒绝。edits成功保留旧通道，重建成功不保证旧通道；重建写后失败恢复本调用定义section、实例界面/通道及磁盘库（<=32MiB、64实例、每实例512通道），返回restored/restore_errors。定义写入独立于场景Undo，后续exec失败不撤销已成功的库写入，外部副作用不保证恢复","returns":"dict"},{"name":"hda_edit","sig":"node, action, *, dry_run=False, expected_plan=None, discard_changes=False, allow_foreign=None","desc":"受控unlock/save/lock/promote，不拆包。先dry_run取得plan_sha256，应用须expected_plan匹配库/定义/源码/实例状态；<=32MiB库、512后代、64实例、2MiB源码。save要求解锁且无实例界面覆盖；promote显式提升源spare界面并保留已有根参数/keys/locks，拒绝其他实例覆盖与既有模板删除/变型。共享写入检查所有实例；lock丢弃内部修改须discard_changes=True且后代也获授权；unlock不授予后代ownership。save/promote写后失败恢复本调用定义/根界面/通道/磁盘，不保证外部副作用或后续exec失败恢复。返回状态/哈希不证明公共输出、回调、GUI或依赖通过","returns":"dict"}]},{"domain":"render / sim 域","note":"render / sim 域（渲染产物）","verbs":[{"name":"camera_fit","sig":"camera, target, direction='iso', coverage=0.82, width=None, height=None, frame=None, *, dry_run=False, allow_foreign=None","desc":"将正式静态OBJ cam拟合到显式SOP世界包络；保留焦距，清lookatpath，求距离/正交宽度，实际矩阵投影回验；无渲染/视口改变。尺寸默认相机值，当前frame。拒绝动画/约束/窗口偏移/自定义lens，失败恢复。ownership与单次allow_foreign适用，持久preview服务永不豁免；dry_run仍exec。Solaris需导入并按实际RenderProduct预检","returns":"dict"},{"name":"render_frame","sig":"rop, picture=None, frame=None, timeout=110, *, framing=None","desc":"渲染可执行hou.RopNode并验证新鲜产物；USD优先outputimage。可选framing={target:USD资产prim路径,coverage:.82}在renderer启动前检查实际stage所有产品的相机/有效画幅/裁切窗口；不通过或不支持时零渲染，不自动动相机。未传保持艺术裁切/通用ROP语义。临时picture/foreground/frame恢复；bytes/mtime/有界摘要确认fresh，旧文件失败；>110s走job。共享执行端模式取registry渲染单槽，被占即快速拒绝","returns":"dict"},{"name":"render_view","sig":"node, direction='iso', frame=None, width=1280, height=720, picture=None, framing='full', coverage=0.82, framing_frame=None, *, output_policy='managed', focus_group=None, isolate=False, projection='perspective', framing_bounds=None, depth_bounds=None","desc":"显式SOP→持久proxy→服务相机及对应版本后端，恢复用户状态，服务不删除。output_policy默认managed：picture省略或仅安全basename，唯一文件落`$HIP/dsh-visual-checks/<run-id>/`；路径值必须选explicit，继续服从原$HIP/绝对路径保护。返回artifact含purpose/policy/actual/相对路径/root/run/capture/frame，旧output保留。full完整入镜；detail只缩正交宽度/透视视角，不推进相机，近远裁面错误始终零渲染失败。focus_group指定实际primitive组，可isolate；framing_bounds决定取景，depth_bounds决定全部渲染内容含上下文的深度。A/B用同framing_frame并复用返回framing.bounds/depth_bounds及方向/画幅/模式，越界不漂移。check像素事实与pixels兼容别名、framing.depth_check/crop_reasons、source指纹/stale分别报告；空/error拒绝；源/proxy有cook warning时保留诊断图片和warning，但返回ok=false，不能进入验收完成门。展示格式OCIO编码sRGB；H21缺少匹配空间时明确gamma近似，H22明确拒绝该缺口；EXR/HDR线性；output_color记录方法，不证明语义。共享执行端模式取registry渲染单槽，被占即快速拒绝","returns":"dict"},{"name":"render_check","sig":"path, ref=None","desc":"亮度/非黑/主色/content bbox；A/B 另给高精度 mean、RMSE、changed/meaningful pixel %、max diff，微小非零不再被舍入成 0","returns":"dict"}]},{"domain":"viewport 域","note":"viewport 域（视口/UI）","verbs":[{"name":"viewport_screenshot","sig":"path=None, frame=None, clean=True, frame_target=None, textures=None, backface_cull=False, *, output_policy='managed'","desc":"**用户屏幕诊断工具**：managed/explicit路径和artifact合同同render_view；无命名HIP时managed零状态修改拒绝。PNG/JPEG/BMP/TGA为支持截图格式。用户切空display节点时截到空是正确结果，不能用来证明agent产物；和`render_view(explicit_sop)`对照可区分viewport漂移与真实几何错误。要求独立stash的flipbook/viewport camera；绑定相机先解锁并脱离，按请求frame读取bbox，恢复frame/视图后最后还原相机关联/锁定，setter失败与回读不符保留。候选需属于请求frame、连续稳定且可解码；旧/错误frame/无效/歧义文件不算fresh。flipbook派发已尝试但未确认完成的超时/异常/轮询中断保留managed reservation并标capture_unresolved，避免晚到写入与路径复用竞争；实际输出路径复验失败不登记附件。恢复失败以CheckpointError证据拒绝假成功","returns":"dict"}]}]; }
    // <<< houdini-catalog

    // >>> houdini-trace (generated by tools/gen-trace-client.mjs — do not edit)
    var houdiniToolCatalog = {"houdini_inspect":{"label":"观察现场","purpose":"读取真实Houdini场景、节点、参数和能力资料。","input":"只读Python代码；hou与动词已导入。","output":"读取结果、诊断及本次观察的场景身份。","execution":"Houdini主线程，只读"},"houdini_exec":{"label":"执行操作","purpose":"批量创建、修改、检查、保存或出图。","input":"Python代码，可组合动词；__result__返回结构数据。","output":"结果、真实错误、操作记录、事务状态、图像和文件。","execution":"Houdini主线程，串行"},"houdini_request":{"label":"查回执行","purpose":"回答某个未知响应的请求是否执行、是否完成；避免重复修改。","input":"request_ref，或index列出本会话可查回请求。","output":"原执行状态与可取得的原始结果；不会重发代码。","execution":"Bridge请求记录，无HOM"},"houdini_resource":{"label":"读取资料","purpose":"按需读取原始用户资料与完整历史工具结果。","input":"kind=source/result、ref及可选分页；result可选JSON Pointer。","output":"原文或JSON分页及继续读取位置。","execution":"DSH Host，无HOM"},"houdini_capabilities":{"label":"观察通道","purpose":"确认当前模型能否接收图片，以及附件通道是否可用。","input":"无需参数。","output":"当前模型与附件能力事实；不会渲染或判断画面。","execution":"DSH Host，无HOM"},"houdini_job_submit":{"label":"提交长任务","purpose":"把渲染、模拟或长计算放入Houdini队列并立即返回。","input":"Python代码；与exec相同的操作能力。","output":"jobId及提交回执。","execution":"Houdini串行队列"},"houdini_job_status":{"label":"等待长任务","purpose":"读取或等待长任务状态和结果。","input":"jobId及可选wait秒数。","output":"queued/running/done/failed/cancelled及实际结果。","execution":"Bridge任务记录"},"houdini_job_cancel":{"label":"取消长任务","purpose":"取消尚未执行的任务，并对运行中的任务发出取消意图。","input":"jobId。","output":"实际取消状态；运行中的HOM操作不会被强杀。","execution":"Bridge任务控制"}};
    var traceView;
    function getTraceView(React) {
      if (traceView) return traceView;
      var sources = {"guidance":{"name":"dsh-houdini:guidance","order":150,"hash":"7635a6ab39787fd1fb41249cc8e0b5de724bc11c19fe2a46b4b5f42fa974db3f","bytes":2787,"paragraphStarts":["Use houdini_inspect for live read-only scene and API information, houdini_exec for batched","Compose the injected Python verbs for edits. Raw hou is a read/low-level escape hatch; Raw","Current catalog: vocabulary 域: verb_help | 类型目录: search_tab_menu, search_tab_entries, reso","Tool results report execution, checks, restoration and files separately. Read failed or un","Load domain skills as needed for SOP, COP, HDA/tools, controls, rigging, Solaris or tutori","Outputs belong under $HIP. Saving to a new path requires the requested target and expected"],"source":"src/index.ts"},"skills":[{"name":"houdini-trace-analysis","description":"分析 dsh-houdini 与 DeepSeek Harness 的原始会话日志，定位 Houdini 任务的完成差距、运行与工作区错位、工具合同、执行反馈、观察和性能问题。用户要求复盘指定或最新 trace、比较会话或据证据调整工具与审计技能时使用。","base":"skills/houdini-trace-analysis","files":[{"path":"agents/openai.yaml","hash":"334a2a7948a5fa607f4c2013deb13bf44398d75e1bf0bb1916707e4659a8ddb0","bytes":278},{"path":"references/audit-rubric.md","hash":"3cee7986662fe0e5f0bf8d94e20a1221ff2de10991e9be18aa63fca2714d534a","bytes":5727},{"path":"references/known-patterns.md","hash":"a435ede38dcc1ef4694cfaf70118561f44eecc10a443a53f5ba3290bbf51e879","bytes":2290},{"path":"scripts/evidence-helpers.mjs","hash":"ad1a35c5185385da0f1305a0d759e0b9c4bd235f0c57f51e2e53859600091b56","bytes":66635},{"path":"scripts/extract-trace-evidence.mjs","hash":"301a44387bd84fe6c272bba390a2fb5ee9a94da9f8fbdddb738a2c3a9f2a04b9","bytes":24680},{"path":"SKILL.md","hash":"bc74932e488f34e2e33fa3f1dfd572817b0bd7094518863b00586a4370581be6","bytes":5656}]},{"name":"houdini-sop-workflow","description":"设计、构建、修改和交付可编辑的Houdini SOP程序化网络。适用于建模、散布、属性、VEX、曲线成形、模块装配和SOP动画；按任务读取构造方法、控制和观察资料。纯场景查询直接用工具；HDA界面、回调、打包、rig和Solaris使用对应领域技能。","base":"skills/houdini-sop-workflow","files":[{"path":"agents/openai.yaml","hash":"8628b8dfd3d0765ba6691fcaa0d168df2bcc30d4f464ac40862d86ed70c160e0","bytes":264},{"path":"references/execution-checkpoints.md","hash":"64bb2d80fe333c291708564c2388885ec13dc8b86f442244d45132e518ed91a7","bytes":18982},{"path":"references/modeling-methods.md","hash":"ce143a1ae4c3150d854426ebe076f84f2bde749dda4e3c8bd2cfd83c0110fc54","bytes":16724},{"path":"references/module-design-collaboration.md","hash":"ac5104807d3e0c1df4b3d7bb83b288559f4945fb10b14ffac162ef518d8fd7b2","bytes":1099},{"path":"references/module-quality-contracts.md","hash":"3c2ece863448747aa78b211ccd57dc8b82e75680d9089bb8660745c53202e821","bytes":22343},{"path":"references/network-handoff.md","hash":"fb0bb972c249650bc97f987af8e17af56d971cd4c086e36b40a1aacbf459ca2a","bytes":4226},{"path":"references/procedural-quality-contract.md","hash":"415f7fc93cbb29ba0413abbea6d5d3b41549b937263569ee44c67bd80fc69f14","bytes":10336},{"path":"references/procedural-recipes.md","hash":"fa7147b2348feba8a03bfc36a6292502a856a4d693afedbcd30722dfb837f7b6","bytes":7188},{"path":"references/sop-patterns.md","hash":"31058365ba7e476a318fda4eddae5b5f346df601c3635fe45bfb3f18fa56484c","bytes":12157},{"path":"SKILL.md","hash":"f130cdc1d31ce69f3382c0d8840713af47601a643c3394c8b4a5b1658a93973d","bytes":4263}]},{"name":"houdini-cop-workflow","description":"在 Houdini Copernicus 中构建、诊断和验证程序纹理与图像处理网络，包括 COP 教程复现、图层关系、材质贴图和导出。仅在需要操作或检查 COP 数据流时加载；不用于只解析视频、仅消费现有贴图的 Karma 渲染或普通 SOP 建模。","base":"skills/houdini-cop-workflow","files":[{"path":"references/cache-and-delivery.md","hash":"3090300fd83df79293e3e963be5bff652f69b2c4d4be14fa61f1c4f42c0945aa","bytes":4684},{"path":"references/evidence-and-validation.md","hash":"72978e6863271674b32abdcff27e9d34e3ea58e447c0c5ff409c01fbdb09f2c1","bytes":5661},{"path":"references/layers-and-ports.md","hash":"7adcd143eba07f73240284efea7ada0ade980fd7d200faff6fd36a4bca4d854a","bytes":3902},{"path":"references/relations-and-controls.md","hash":"4941a611b7c2fd2842c20c2d993e22fd069b9b664bad43f2473e8c909c875766","bytes":6096},{"path":"SKILL.md","hash":"2beaa3a638aeeaa32f238d38b592e2b865afb1ef3e47a7556e80e8130f039cb0","bytes":4845}]},{"name":"houdini-tool-development","description":"开发、维护和交付Houdini HDA/OTL、Python回调、Shelf/Tab工具、快捷键及Python Panel/Viewer State入口，管理脚本与打包依赖。用于用户明确要求的HDA、共享节点类型/安装分发或既有工具维护；普通可调模型、独立保存HIP不触发，纯控制面板/总控布局走houdini-parameter-ui。","base":"skills/houdini-tool-development","files":[{"path":"references/evidence-and-validation.md","hash":"0ba00209563b5579753dc6aa6d980a4fac11e1149b458aa1dfa87e3be63f9538","bytes":5822},{"path":"references/hda-maintenance.md","hash":"0690657ef991e70c6aab760ef1be7cb428fa0637f164c978979e491754733632","bytes":10795},{"path":"references/hda-ui.md","hash":"856872286a1c9acec59ac7bdd7be7e08b09986b5849b0bf4a8efcd6e9c45c248","bytes":262},{"path":"references/scripts-and-packaging.md","hash":"f040123f7c670de079b15a594becc4f7c34784b5643d336c7c42c64bf1c7602c","bytes":6922},{"path":"references/shelf-and-hotkeys.md","hash":"efba051470b6733eff9005435d471d7ac147715d5ffc5ac38acd8a62d30957aa","bytes":3726},{"path":"references/ui-components.md","hash":"25d24be85f8a46d6db870278795c0ff68c325150071411f1d2def59bced689b4","bytes":303},{"path":"SKILL.md","hash":"8a3d434ff63a9d4aea3ca97f45c0530196bb58c4dc1bcd756d25e18d2c846db5","bytes":5639}]},{"name":"houdini-parameter-ui","description":"设计、建立和维护Houdini参数面板、程序化模型控制节点与场景总控；定义控制含义、选择spare或HDA载体、组合UI组件并规划验证参数绑定。适用于从零先做控制接口、已有场景提炼总控或改善布局；普通赋值、纯模型构建和Python Panel/WebView开发不单独触发。","base":"skills/houdini-parameter-ui","files":[{"path":"assets/ui-component-gallery.json","hash":"77972fb7001584605a7728935979a8926ae4a135d1bb7c3eb7aed622f4372877","bytes":4488},{"path":"references/control-bindings.md","hash":"291f88852929d3ebb58c1a30607d62c0aa64f2948adbf93d781df0e657889224","bytes":8043},{"path":"references/hda-ui.md","hash":"81eb9f7824a628b1d387c44bd60222ca1fc08bccabea40d8522e5d50ccba0ddb","bytes":4758},{"path":"references/ui-components.md","hash":"9b58f546620464c48f22d9dfce3707e7df04edc4dffac6785f0dfa8a20f65093","bytes":7904},{"path":"scripts/build-ui-gallery.py","hash":"3701333da3f0b140fa77c1b5092a90fe1d0fd3bf5ab378cb45999741961e1e6c","bytes":2500},{"path":"SKILL.md","hash":"06d5c14e2842d5a6082120cdffc7b8d0687739e971bcd2c5906fc56556a53639","bytes":4726}]},{"name":"houdini-solaris-karma-workflow","description":"在 Houdini Solaris/LOPs 中设计、构建、检查和交付 Karma 材质与渲染网络。用于用户要求最终渲染、Karma CPU/XPU、MaterialX、USD 材质绑定、Render Settings、AOV、USD Render ROP，或把 SOP/COP 结果接入 /stage；不用于仅需 render_view 的快速 SOP 视觉验证。","base":"skills/houdini-solaris-karma-workflow","files":[{"path":"references/karma-patterns.md","hash":"3d1f84316c8d9ebdc9fb3b7b093408c0740d608a1065a70ab275a0833543630a","bytes":6764},{"path":"SKILL.md","hash":"ce455c3b72f0e59a19220c9cf2dc36bf82eed215f56e2a80e230e5e2e80346cb","bytes":4145}]},{"name":"houdini-rig-animation-workflow","description":"在 Houdini 中设计、构建、调试和交付参数动画、刚体 piece 序列、机械层级、KineFX skeleton/skin 与 animator-facing rig。用于任务涉及 keyframes、绑定、FK/IK、capture/deform、非交换多步骤或可复用控制器；不用于普通静态 SOP 建模，也不把所有“绑定”默认路由到 KineFX/APEX。","base":"skills/houdini-rig-animation-workflow","files":[{"path":"references/rig-animation-patterns.md","hash":"c37a562e7e5776f688a7c730c6ea9d77899b97dd86979b6d4a3b8d8e7524a3a2","bytes":15473},{"path":"SKILL.md","hash":"ea68994b649174747b84a268679e8ca39cd506dcf852c3218d3d8f8cf916c0f4","bytes":7965}]},{"name":"houdini-skill-governance","description":"创建、审查、维护和演化 dsh-houdini 的领域 skills。用于新增 COP/SIM/rig/project-analysis 等 skill，或依据 Houdini trace、SideFX 官方文档、本机版本、用户视频/工程更新现有 skill；不用于普通内容制作，也不允许未经授权或未经证据门自动修改生产 skill。","base":"skills/houdini-skill-governance","files":[{"path":"references/eval-cases.md","hash":"8879565f2fc285302da560c81db962259843fc45a445e26b8be6e471a51a67d0","bytes":9393},{"path":"references/evidence-ingestion.md","hash":"2a357a87bb8dbd57be960d60ba32882de2f83ed486f372d9057b9d2bfc957f43","bytes":5813},{"path":"references/maintenance-lifecycle.md","hash":"ea9e7f39d8099c7ed3597cb19ee76a72226ab9056a05406e1c8c58f6f7d6b9e1","bytes":5783},{"path":"references/quality-standard.md","hash":"a87a24bbe016951ed40e1039e4bc4d858a62027008a2b686ac59d5df9b9c4c6f","bytes":12063},{"path":"scripts/audit-houdini-skills.mjs","hash":"75f21220d500afb7be4875907a7e445f306334d4f7d2559e1495cb6f16cb08e0","bytes":6524},{"path":"SKILL.md","hash":"187328f17f3cbb777e7b4272e5e71ab3d0abd9707e5d8203762bae810d3641e8","bytes":5673}]},{"name":"houdini-video-tutorial","description":"解析 Houdini 视频教程，结合云端语音转录与本地画面核对，提取带时间依据的步骤、设置、冲突和复现缺口。用于用户提供视频文件或要求从视频准备教学工程；不用于图文教程、普通建模、会议转录或自动知识沉淀。","base":"skills/houdini-video-tutorial","files":[{"path":"references/reconstruction.md","hash":"bfc319d4abaa9ce4a4cc80750163553c0875e8da6410929b225f0dcee378b546","bytes":11423},{"path":"references/video-processing.md","hash":"bb912038ab046f8ea1e443ac6044d540db0b87deaf8719f800087728b0665e58","bytes":36941},{"path":"scripts/video_tutorial.py","hash":"7cc4793941a2c816f676d777050724d58977a0032b40b6c4a3dc9cec35cfb3c3","bytes":96779},{"path":"SKILL.md","hash":"8e1b2bf1b773145dc9c0df246471dd12777d4a49d76cf18fa158200e4e2ef9dd","bytes":11794}]}],"presets":[{"name":"houdini","file":"presets/houdini/persona.md","presetFile":"presets/houdini/cordis.patch.yml","hash":"c0569ab686bee58664802b8331d63a87eb6ff9e969b93b71f79b42264cda5408","bytes":1690,"paragraphStarts":["You are a Houdini automation agent powered by the ","Turn the user's requirements, references and tutorials into editable Houdini projects and ","Inspect the relevant scene and available APIs, then act on the user's goal. Resolve discov","Use actual outputs and images to judge progress. Verify the properties that matter to this","Reply in the user's language with clear, short sentences. Lead with the result, what can b"]}],"tools":{"houdini_inspect":{"label":"观察现场","purpose":"读取真实Houdini场景、节点、参数和能力资料。","input":"只读Python代码；hou与动词已导入。","output":"读取结果、诊断及本次观察的场景身份。","execution":"Houdini主线程，只读"},"houdini_exec":{"label":"执行操作","purpose":"批量创建、修改、检查、保存或出图。","input":"Python代码，可组合动词；__result__返回结构数据。","output":"结果、真实错误、操作记录、事务状态、图像和文件。","execution":"Houdini主线程，串行"},"houdini_request":{"label":"查回执行","purpose":"回答某个未知响应的请求是否执行、是否完成；避免重复修改。","input":"request_ref，或index列出本会话可查回请求。","output":"原执行状态与可取得的原始结果；不会重发代码。","execution":"Bridge请求记录，无HOM"},"houdini_resource":{"label":"读取资料","purpose":"按需读取原始用户资料与完整历史工具结果。","input":"kind=source/result、ref及可选分页；result可选JSON Pointer。","output":"原文或JSON分页及继续读取位置。","execution":"DSH Host，无HOM"},"houdini_capabilities":{"label":"观察通道","purpose":"确认当前模型能否接收图片，以及附件通道是否可用。","input":"无需参数。","output":"当前模型与附件能力事实；不会渲染或判断画面。","execution":"DSH Host，无HOM"},"houdini_job_submit":{"label":"提交长任务","purpose":"把渲染、模拟或长计算放入Houdini队列并立即返回。","input":"Python代码；与exec相同的操作能力。","output":"jobId及提交回执。","execution":"Houdini串行队列"},"houdini_job_status":{"label":"等待长任务","purpose":"读取或等待长任务状态和结果。","input":"jobId及可选wait秒数。","output":"queued/running/done/failed/cancelled及实际结果。","execution":"Bridge任务记录"},"houdini_job_cancel":{"label":"取消长任务","purpose":"取消尚未执行的任务，并对运行中的任务发出取消意图。","input":"jobId。","output":"实际取消状态；运行中的HOM操作不会被强杀。","execution":"Bridge任务控制"}}};
      var css = ".dsh-trace .tr-prompt-group { border: 1px solid var(--tr-line); border-radius: 6px; margin: 10px 0; padding: 12px 14px; }\n.dsh-trace .tr-prompt-group > summary { cursor: pointer; font-weight: 600; }\n.dsh-trace .tr-prompt-section { border-top: 1px solid var(--tr-line); margin-top: 12px; padding-top: 10px; }\n.dsh-trace .tr-prompt-section > summary { cursor: pointer; }\n.dsh-trace .tr-prompt-source { display: block; margin: 5px 0 0 18px; color: var(--tr-muted); overflow-wrap: anywhere; font-weight: 400; }\n.dsh-trace .tr-prompt-raw { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.65; font-size: 12px; }\n.dsh-trace {\n  --tr-bg: var(--dsw-alias-bg-layer-1, #171b20);\n  --tr-panel: var(--dsw-alias-bg-layer-2, #20252b);\n  --tr-fg: var(--dsw-alias-label-primary, #e5e9ed);\n  --tr-muted: var(--dsw-alias-label-secondary, #a9b4bf);\n  --tr-line: var(--dsw-alias-border-l2, #38414a);\n  --tr-orange: #ba692c;\n  --tr-blue: #568bb8;\n  --tr-purple: #9978bd;\n  --tr-read: #8298ab;\n  --tr-red: var(--dsw-alias-state-error-primary, #da706b);\n  color: var(--tr-fg);\n  background: var(--tr-bg);\n  font:\n    14px/1.65 \"Segoe UI\",\n    \"Microsoft YaHei\",\n    sans-serif;\n  min-height: 360px;\n  height: calc(100dvh - 120px);\n  display: flex;\n  flex-direction: column;\n  overflow: hidden;\n}\n.dsh-trace * {\n  box-sizing: border-box;\n}\n.dsh-trace button,\n.dsh-trace input,\n.dsh-trace select {\n  font: inherit;\n  color: inherit;\n}\n.dsh-trace button {\n  cursor: pointer;\n  border: 1px solid var(--tr-line);\n  background: transparent;\n  border-radius: 4px;\n  padding: 6px 10px;\n  text-align: left;\n}\n.dsh-trace button:focus-visible,\n.dsh-trace summary:focus-visible {\n  outline: 2px solid var(--tr-orange);\n  outline-offset: 2px;\n}\n.dsh-trace button[aria-pressed=\"true\"] {\n  background: color-mix(in srgb, var(--tr-orange) 12%, var(--tr-panel));\n  border-color: var(--tr-orange);\n}\n.dsh-trace header {\n  padding: 16px 22px 8px;\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  gap: 12px;\n  flex-wrap: wrap;\n}\n.dsh-trace h2 {\n  font-size: 20px;\n  font-weight: 500;\n  margin: 0;\n}\n.dsh-trace h3 {\n  font-size: 17px;\n  font-weight: 500;\n  margin: 0 0 10px;\n}\n.dsh-trace h4 {\n  font-size: 13px;\n  margin: 18px 0 7px;\n  font-weight: 500;\n}\n.dsh-trace nav {\n  display: flex;\n  gap: 6px;\n  flex-wrap: wrap;\n  padding: 8px 22px;\n  border-bottom: 1px solid var(--tr-line);\n}\n.dsh-trace nav button {\n  border: 0;\n  border-bottom: 2px solid transparent;\n  border-radius: 0;\n}\n.dsh-trace nav button[aria-pressed=\"true\"] {\n  border-color: var(--tr-orange);\n  background: transparent;\n}\n.dsh-trace .tr-status {\n  font-size: 12px;\n  padding: 8px 22px;\n  color: var(--tr-muted);\n  border-bottom: 1px solid var(--tr-line);\n}\n.dsh-trace .tr-content {\n  overflow: auto;\n  min-height: 0;\n  flex: 1;\n}\n.dsh-trace .tr-board {\n  padding: 20px 22px;\n}\n.dsh-trace .tr-toolbar {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  gap: 10px;\n  flex-wrap: wrap;\n  margin-bottom: 16px;\n}\n.dsh-trace .tr-buttons {\n  display: flex;\n  gap: 6px;\n  align-items: center;\n  flex-wrap: wrap;\n}\n.dsh-trace .tr-buttons button {\n  font-size: 12px;\n}\n.dsh-trace .tr-split {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);\n  gap: 18px;\n  align-items: start;\n}\n.dsh-trace .tr-inspector {\n  grid-template-columns: minmax(220px, 0.7fr) minmax(0, 1.5fr);\n}\n.dsh-trace .tr-detail {\n  min-width: 0;\n  background: var(--tr-panel);\n  border: 1px solid var(--tr-line);\n  padding: 18px;\n  border-radius: 5px;\n}\n.dsh-trace .tr-list {\n  min-width: 0;\n}\n.dsh-trace .tr-row {\n  display: block;\n  width: 100%;\n  padding: 12px;\n  border: 0;\n  border-left: 3px solid transparent;\n  border-bottom: 1px solid var(--tr-line);\n  border-radius: 0;\n}\n.dsh-trace .tr-row[aria-pressed=\"true\"] {\n  border-left-color: var(--tr-kind, var(--tr-orange));\n  background: color-mix(\n    in srgb,\n    var(--tr-kind, var(--tr-orange)) 9%,\n    var(--tr-panel)\n  );\n}\n.dsh-trace .tr-rowhead {\n  display: flex;\n  gap: 8px;\n  justify-content: space-between;\n  align-items: start;\n}\n.dsh-trace .tr-meta,\n.dsh-trace small {\n  font-size: 12px;\n  color: var(--tr-muted);\n  overflow-wrap: anywhere;\n}\n.dsh-trace .tr-meta {\n  display: block;\n  margin-top: 4px;\n}\n.dsh-trace .tr-title {\n  overflow-wrap: anywhere;\n}\n.dsh-trace .tr-pill {\n  display: inline-block;\n  font-size: 11px;\n  border: 1px solid var(--tr-line);\n  border-radius: 3px;\n  padding: 1px 5px;\n  white-space: normal;\n}\n.dsh-trace .tr-bad {\n  color: var(--tr-red);\n}\n.dsh-trace [data-kind=\"skill\"] {\n  --tr-kind: var(--tr-purple);\n}\n.dsh-trace [data-kind=\"read\"] {\n  --tr-kind: var(--tr-read);\n}\n.dsh-trace [data-kind=\"query\"] {\n  --tr-kind: var(--tr-blue);\n}\n.dsh-trace [data-kind=\"exec\"] {\n  --tr-kind: var(--tr-orange);\n}\n.dsh-trace [data-kind=\"other\"] {\n  --tr-kind: #8d83b8;\n}\n.dsh-trace [data-kind=\"planning\"] {\n  --tr-kind: #459b91;\n}\n.dsh-trace [data-kind=\"shell\"] {\n  --tr-kind: #a99b4d;\n}\n.dsh-trace [data-kind=\"write\"] {\n  --tr-kind: #b37492;\n}\n.dsh-trace [data-kind=\"search\"] {\n  --tr-kind: #528eb5;\n}\n.dsh-trace [data-kind=\"interaction\"] {\n  --tr-kind: #9c82c2;\n}\n.dsh-trace .tr-type {\n  color: var(--tr-kind);\n  font-size: 11px;\n  background: color-mix(in srgb, var(--tr-kind) 10%, var(--tr-panel));\n  padding: 2px 5px;\n  border-radius: 3px;\n}\n.dsh-trace .tr-type:before {\n  content: \"●\";\n  margin-right: 4px;\n  font-size: 8px;\n}\n.dsh-trace table {\n  border-collapse: collapse;\n  width: 100%;\n  table-layout: fixed;\n  font-size: 12px;\n}\n.dsh-trace th,\n.dsh-trace td {\n  text-align: left;\n  padding: 9px 8px;\n  vertical-align: top;\n  border-bottom: 1px solid var(--tr-line);\n  overflow-wrap: anywhere;\n}\n.dsh-trace th {\n  font-weight: 500;\n  color: var(--tr-muted);\n  background: var(--tr-bg);\n}\n.dsh-trace code {\n  font:\n    12px/1.65 Consolas,\n    monospace;\n  overflow-wrap: anywhere;\n}\n.dsh-trace pre {\n  font:\n    12px/1.75 Consolas,\n    monospace;\n  white-space: pre-wrap;\n  overflow-wrap: anywhere;\n  background: var(--tr-bg);\n  padding: 12px;\n  border-radius: 4px;\n  margin: 8px 0;\n}\n.dsh-trace details {\n  border-top: 1px solid var(--tr-line);\n  padding: 10px 0;\n  margin-top: 8px;\n}\n.dsh-trace summary {\n  cursor: pointer;\n  overflow-wrap: anywhere;\n  font-size: 12px;\n}\n.dsh-trace .tr-note {\n  border-left: 2px solid var(--tr-line);\n  padding: 8px 12px;\n  color: var(--tr-muted);\n  font-size: 12px;\n  margin: 12px 0;\n}\n.dsh-trace .tr-prose {\n  white-space: pre-wrap;\n  overflow-wrap: anywhere;\n  font-size: 13px;\n  line-height: 1.8;\n}\n.dsh-trace .tr-prose p {\n  margin: 8px 0;\n}\n.dsh-trace .tr-empty {\n  padding: 24px;\n  color: var(--tr-muted);\n  border: 1px dashed var(--tr-line);\n}\n.dsh-trace select {\n  padding: 6px;\n  background: var(--tr-panel);\n  border: 1px solid var(--tr-line);\n  border-radius: 4px;\n  max-width: 100%;\n}\n.dsh-trace .tr-metrics {\n  display: flex;\n  flex-wrap: wrap;\n  gap: 22px;\n  margin: 16px 0;\n}\n.dsh-trace .tr-metrics strong {\n  display: block;\n  font-size: 22px;\n  font-weight: 500;\n}\n.dsh-trace .tr-domains {\n  margin-bottom: 18px;\n}\n.dsh-trace .tr-legend {\n  display: flex;\n  gap: 12px;\n  flex-wrap: wrap;\n  margin-bottom: 10px;\n}\n.dsh-trace .tr-key {\n  color: var(--tr-muted);\n}\n.dsh-trace .tr-tree {\n  margin-left: 8px;\n  border-left: 1px solid var(--tr-line);\n  padding-left: 10px;\n}\n.dsh-trace .tr-raw {\n  color: var(--tr-muted);\n}\n.dsh-trace {\n  position: relative;\n  z-index: 1;\n  isolation: isolate;\n}\n.dsh-trace header {\n  padding: 10px 16px 3px;\n  flex-shrink: 0;\n}\n.dsh-trace h2 {\n  font-size: 17px;\n}\n.dsh-trace nav {\n  padding: 4px 16px;\n  gap: 4px;\n  flex-shrink: 0;\n}\n.dsh-trace .tr-status {\n  padding: 5px 16px;\n  flex-shrink: 0;\n}\n.dsh-trace button:disabled {\n  opacity: 0.4;\n  cursor: default;\n}\n.dsh-trace .tr-content-timeline {\n  overflow: hidden;\n}\n.dsh-trace .tr-timeline {\n  height: 100%;\n  min-height: 0;\n  display: flex;\n  flex-direction: column;\n  background: var(--tr-bg);\n}\n.dsh-trace .tr-timeline-toolbar {\n  flex: none;\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  flex-wrap: wrap;\n  gap: 6px 12px;\n  padding: 8px 12px;\n  background: var(--tr-panel);\n  border-bottom: 1px solid var(--tr-line);\n}\n.dsh-trace .tr-timeline-toolbar button,\n.dsh-trace .tr-pager select {\n  font-size: 12px;\n  padding: 4px 8px;\n  line-height: 1.5;\n}\n.dsh-trace .tr-pager {\n  display: flex;\n  align-items: center;\n  flex-wrap: wrap;\n  gap: 5px;\n  font-size: 12px;\n}\n.dsh-trace .tr-range {\n  font-variant-numeric: tabular-nums;\n  color: var(--tr-muted);\n  margin-right: 6px;\n}\n.dsh-trace .tr-timeline-body {\n  display: grid;\n  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);\n  flex: 1;\n  min-height: 0;\n  overflow: hidden;\n}\n.dsh-trace .tr-call-list,\n.dsh-trace .tr-call-detail {\n  min-width: 0;\n  min-height: 0;\n  overflow: auto;\n  overscroll-behavior: contain;\n  scrollbar-width: thin;\n}\n.dsh-trace .tr-call-list {\n  background: var(--tr-bg);\n}\n.dsh-trace .tr-call-detail {\n  background: var(--tr-panel);\n  border-left: 1px solid var(--tr-line);\n}\n.dsh-trace .tr-call-detail > .tr-detail {\n  border: 0;\n  border-radius: 0;\n  padding: 14px 16px;\n  background: var(--tr-panel);\n}\n.dsh-trace .tr-call-row {\n  display: block;\n  width: 100%;\n  border: 0;\n  border-left: 3px solid var(--tr-kind);\n  border-bottom: 1px solid var(--tr-line);\n  border-radius: 0;\n  padding: 6px 10px 5px;\n  background: var(--tr-bg);\n  line-height: 1.4;\n}\n.dsh-trace .tr-call-row[aria-pressed=\"true\"] {\n  border-left-color: var(--tr-kind);\n  background: color-mix(in srgb, var(--tr-kind) 12%, var(--tr-panel));\n}\n.dsh-trace .tr-call-row:hover {\n  background: color-mix(in srgb, var(--tr-kind) 7%, var(--tr-panel));\n}\n.dsh-trace .tr-call-head {\n  display: grid;\n  grid-template-columns: 35px minmax(0, 1fr) auto 43px;\n  gap: 7px;\n  align-items: center;\n  min-height: 19px;\n}\n.dsh-trace .tr-call-index {\n  font:\n    11px Consolas,\n    monospace;\n  color: var(--tr-muted);\n}\n.dsh-trace .tr-call-title {\n  white-space: nowrap;\n  overflow: hidden;\n  text-overflow: ellipsis;\n  font-size: 13px;\n}\n.dsh-trace .tr-call-state {\n  font-size: 11px;\n  color: var(--tr-muted);\n  white-space: nowrap;\n}\n.dsh-trace .tr-call-state.tr-bad {\n  color: var(--tr-red);\n}\n.dsh-trace .tr-call-time {\n  font:\n    11px Consolas,\n    monospace;\n  color: var(--tr-muted);\n  text-align: right;\n}\n.dsh-trace .tr-call-meta {\n  display: flex;\n  gap: 8px;\n  align-items: center;\n  margin-top: 4px;\n  min-height: 16px;\n  font-size: 11px;\n  min-width: 0;\n}\n.dsh-trace .tr-call-kind {\n  color: var(--tr-kind);\n  overflow: hidden;\n  text-overflow: ellipsis;\n  white-space: nowrap;\n  max-width: 40%;\n  flex-shrink: 1;\n}\n.dsh-trace .tr-call-kind:before,\n.dsh-trace .tr-kind-legend:before {\n  content: \"●\";\n  font-size: 7px;\n  margin-right: 4px;\n}\n.dsh-trace .tr-call-target {\n  flex: 1;\n  min-width: 0;\n  overflow: hidden;\n  text-overflow: ellipsis;\n  white-space: nowrap;\n  color: var(--tr-muted);\n}\n.dsh-trace .tr-call-tokens {\n  font:\n    11px Consolas,\n    monospace;\n  white-space: nowrap;\n  color: var(--tr-muted);\n  margin-left: auto;\n}\n.dsh-trace .tr-timeline-footer {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  flex-wrap: wrap;\n  gap: 4px 12px;\n  flex: none;\n  padding: 5px 12px;\n  font-size: 11px;\n  color: var(--tr-muted);\n  border-top: 1px solid var(--tr-line);\n  background: var(--tr-panel);\n}\n.dsh-trace .tr-kind-legend {\n  display: inline-block;\n  color: var(--tr-kind);\n  margin-right: 9px;\n  white-space: nowrap;\n}\n.dsh-trace .tr-back-list {\n  display: none;\n}\n.dsh-trace .tr-sr-only {\n  position: absolute;\n  width: 1px;\n  height: 1px;\n  overflow: hidden;\n  clip: rect(0, 0, 0, 0);\n  white-space: nowrap;\n}\n@media (max-width: 850px) {\n  .dsh-trace .tr-split {\n    grid-template-columns: 1fr;\n  }\n  .dsh-trace .tr-board {\n    padding: 14px;\n  }\n  .dsh-trace header,\n  .dsh-trace nav,\n  .dsh-trace .tr-status {\n    padding-left: 14px;\n    padding-right: 14px;\n  }\n  .dsh-trace {\n    height: auto;\n    max-height: none;\n    overflow: visible;\n  }\n  .dsh-trace .tr-content {\n    overflow: visible;\n  }\n  .dsh-trace:has(.tr-timeline) {\n    height: calc(100dvh - 130px);\n    min-height: 360px;\n    overflow: hidden;\n  }\n  .dsh-trace .tr-content-timeline {\n    overflow: hidden;\n  }\n  .dsh-trace .tr-timeline-body {\n    display: block;\n    position: relative;\n  }\n  .dsh-trace .tr-call-list {\n    height: 100%;\n  }\n  .dsh-trace .tr-call-detail {\n    display: none;\n    height: 100%;\n    border: 0;\n  }\n  .dsh-trace .tr-detail-open .tr-call-list {\n    display: none;\n  }\n  .dsh-trace .tr-detail-open .tr-call-detail {\n    display: block;\n  }\n  .dsh-trace .tr-back-list {\n    display: block;\n    position: sticky;\n    top: 0;\n    z-index: 1;\n    width: 100%;\n    background: var(--tr-panel);\n    border-radius: 0;\n    border: 0;\n    border-bottom: 1px solid var(--tr-line);\n    padding: 8px 14px;\n  }\n  .dsh-trace .tr-timeline-footer > span:last-child {\n    display: none;\n  }\n}\n@media (pointer: coarse) {\n  .dsh-trace button,\n  .dsh-trace summary,\n  .dsh-trace select {\n    min-height: 44px;\n  }\n}\n";
      var classifyRawEffect = (function classifyRawEffect(step) {
  const usage = step.canonical?.rawUsage ?? step.rawUsage;
  const failed = step.failed || step.canonical?.ok === false;
  const outcome = usage?.gateOutcome;
  const text = String(step.resultText ?? step.resultPreview ?? '');
  if (outcome === 'blocked' || outcome === 'read_only_blocked'
    || (failed && /raw-hou gate: blocked BEFORE execution|houdini_(?:inspect|query) is read-only and rejected this code BEFORE execution/i.test(text))) return 'gate_blocked';
  // Canonical/raw-usage arrays take precedence over method-name heuristics.
  if (usage && !usage._raw) {
    if (usage.coveredMutations?.length) return 'mutation_candidate';
    if (usage.suspectedMutations?.length || outcome === 'exempted') return 'suspected_effect';
  } else if (step.mutatingRawMethods?.length) return 'mutation_candidate';
  if (failed) return 'failed';
  if (['houdini_inspect', 'houdini_query'].includes(step.tool) && step.canonical?.execution?.read_only !== false) return 'read_only_query';
  return 'unknown';
});
    var isHoudiniDetailRead = (function isHoudiniDetailRead(step) {
  return ['houdini_resource', 'houdini_request'].includes(step.tool)
    || (step.tool === 'houdini_query' && Boolean(step.args?.result_ref || step.args?.request_ref || step.args?.source_ref));
});
    var isHoudiniHostCall = (function isHoudiniHostCall(step) {
  return isHoudiniDetailRead(step) || ['houdini_capabilities', 'houdini_job_cancel'].includes(step.tool) || step.tool === 'houdini_product'
    || (step.tool === 'houdini_query' && Boolean(step.args?.capabilities));
});
    var isStructuredHoudiniCall = (function isStructuredHoudiniCall(step) {
  return step.tool==='houdini_exec' && !step.code && Boolean(step.args?.delivery || step.args?.review || step.args?.review_test)
});
    var collectVerbAdoption = (function collectVerbAdoption(steps) {
  const detailReads = steps.filter(isHoudiniDetailRead);
  const hostProducts = steps.filter(step => step.tool === 'houdini_product');
  const hostCapabilities = steps.filter(step => step.tool === 'houdini_capabilities'
    || (step.tool === 'houdini_query' && step.args?.capabilities));
  const houdini = steps.filter((step) => step.isHoudini && !isHoudiniHostCall(step));
  const structured = houdini.filter(isStructuredHoudiniCall);
  const python = houdini.filter(step=>!isStructuredHoudiniCall(step));
  const withVerbs = houdini.filter((step) => (step.verbs || []).length > 0);
  const verbCalls = houdini.reduce((sum, step) => sum + (step.verbs || []).length, 0);
  const raw = python.filter(step => !(step.verbs || []).length);
  const rawReadOnly = raw.filter(step => classifyRawEffect(step) === 'read_only_query');
  const exec = python.filter((step) => step.tool === 'houdini_exec');
  const successfulExec = exec.filter((step) => !step.failed);
  const successfulExecWithVerbs = successfulExec.filter((step) => (step.verbs || []).length > 0);
  const blockedRawMutation = raw.filter(step => classifyRawEffect(step) === 'gate_blocked');
  const successfulRawMutation = raw.filter(step => !step.failed && classifyRawEffect(step) === 'mutation_candidate');
  const pct = (part, total) => total ? Math.round((part / total) * 1000) / 10 : null;
  return {
    houdiniCalls: houdini.length,
    hostResultDetailReads: detailReads.length,
    ...(hostProducts.length ? {hostProductCalls:hostProducts.length} : {}),
    ...(hostCapabilities.length ? {hostCapabilityReads:hostCapabilities.length} : {}),
    callsWithVerbs: withVerbs.length,
    callCoveragePct: pct(withVerbs.length, houdini.length),
    verbCalls,
    verbDensity: houdini.length ? Math.round((verbCalls / houdini.length) * 100) / 100 : 0,
    rawReadOnlyCalls: rawReadOnly.length,
    rawSuspectedEffectCalls: raw.filter(step => classifyRawEffect(step) === 'suspected_effect').length,
    rawUnknownEffectCalls: raw.filter(step => classifyRawEffect(step) === 'unknown').length,
    rawFailedCalls: raw.filter(step => classifyRawEffect(step) === 'failed').length,
    execCalls: exec.length,
    successfulExecCalls: successfulExec.length,
    successfulExecWithVerbs: successfulExecWithVerbs.length,
    successfulExecVerbCoveragePct: pct(successfulExecWithVerbs.length, successfulExec.length),
    blockedVerblessRawMutationCalls: blockedRawMutation.length,
    successfulVerblessRawMutationCalls: successfulRawMutation.length,
    ...(structured.length ? {structuredCalls:structured.length,pythonCalls:python.length,
      pythonCallCoveragePct:pct(withVerbs.length,python.length)} : {}),
  };
});
      var analysis = { classifyRawEffect, isHoudiniDetailRead, isHoudiniHostCall, isStructuredHoudiniCall, collectVerbAdoption };
      var createModel = (// Public trajectory projection and accounting, independent of React rendering.
function createTraceModel(catalog, sources, parseEntry, analysis) {
  "use strict";
  const { classifyRawEffect, isHoudiniHostCall, collectVerbAdoption } = analysis;
  const array = (value) => (Array.isArray(value) ? value : []);
  const json = (value) => {
    try {
      return JSON.parse(value);
    } catch {
      return null;
    }
  };
  const text = (blocks) =>
    array(blocks)
      .filter((b) => b && (b.type === "text" || b.kind === "text"))
      .map((b) => b.text || "")
      .join("\n");
  const format = (n) =>
    typeof n === "number" && Number.isFinite(n) ? n.toLocaleString() : "未采集";
  const stamp = (n) =>
    typeof n === "number" ? new Date(n).toLocaleTimeString() : "时间未采集";
  const requestKey = (r) => r.purpose + ":" + r.startSeq;
  const pairKey = (turn, step) => turn + ":" + step;
  const own = (v, k) => v != null && Object.prototype.hasOwnProperty.call(v, k);
  // Reading groups inferred from recognizable text, never runtime provenance.
  // Bodies always come from the selected historical request, including unknowns.
  const promptRules = [
    ["DSH 身份与运行环境", "框架身份", "You are an AI agent powered by DeepSeek Harness.", "@deepseek-ai/dsh-system-prompt · packages/core/system-prompt/src/index.ts"],
    ["DSH 身份与运行环境", "实现目录", "The DeepSeek Harness implementation checkout", "@deepseek-ai/dsh-app-boot · packages/boot/app-boot/src/index.ts"],
    ["DSH 身份与运行环境", "Web GUI", "You are interacting with the user through the DeepSeek Harness Web GUI", "@deepseek-ai/dsh-web-app · packages/bundle/web-app/src/index.ts"],
    ["Houdini 身份与工作方式", "Houdini persona", "You are a Houdini automation agent", "presets/houdini/persona.md"],
    ["Houdini 工具执行规则", "插件 guidance", "houdini_* tools operate", "src/index.ts · dsh-houdini:guidance"],
    ["通用文件、进程与搜索", "文件引用", "Tokens prefixed with @", "@deepseek-ai/dsh-file-reference · lib/index.js"],
    ["通用文件、进程与搜索", "进程退出码", "Non-zero exits are reported", "packages/shell/tool-pwsh/src/index.ts"],
    ["通用文件、进程与搜索", "读取文件", "Use the read tool", "packages/fs/tool-fs/src/read.ts"],
    ["通用文件、进程与搜索", "写入文件", "Use the write tool", "packages/fs/tool-fs/src/write.ts"],
    ["通用文件、进程与搜索", "编辑文件", "Use the edit tool", "packages/fs/tool-fs/src/edit.ts"],
    ["通用文件、进程与搜索", "查找文件", "Use the glob tool", "packages/fs/tool-fs-search/src/glob.ts"],
    ["通用文件、进程与搜索", "搜索内容", "Use the grep tool", "packages/fs/tool-fs-search/src/grep.ts"],
    ["通用文件、进程与搜索", "后台任务", "Track every background job id", "packages/jobs/tool-jobs/src/index.ts"],
    ["通用文件、进程与搜索", "联网搜索", "Use the web_search tool", "packages/web/tool-web/src/search.ts"],
    ["长期目标与多 agent", "Goal", "Use goal tools", "packages/goal/tool-goal/src/index.ts"],
    ["长期目标与多 agent", "Workflow", "Use the workflow tool ONLY", "packages/workflow/tool-workflow/src/index.ts"],
    ["长期目标与多 agent", "Ralph", "Use the ralph tool ONLY", "packages/workflow/tool-ralph/src/index.ts"],
    ["长期目标与多 agent", "Subagent", "Use subagent in the background", "packages/subagent/tool-subagent/src/index.ts · toolName=subagent"],
    ["长期目标与多 agent", "Subagent fork", "Use subagent_fork in the background", "packages/subagent/tool-subagent/src/index.ts · toolName=subagent_fork"],
    ["交付展示", "输出文件引用", "When you successfully create or modify files", "packages/client/ui-deliverables/src/index.ts"],
  ];
  const promptPrefix = s => s.replaceAll("`", "").trimStart();
  function systemSections(system) {
    const parts = String(system ?? "").split(/(\r?\n[ \t]*\r?\n)/);
    const definitions = [
      {rule: promptRules[4], starts: sources.guidance?.paragraphStarts || []},
      ...array(sources.presets).map(p => ({
        rule: ["Houdini 身份与工作方式", "Persona · " + p.name, "", p.file], starts: p.paragraphStarts || [],
      })),
    ];
    const sections = [];
    for (let i = 0; i < parts.length; i += 2) {
      const body = parts[i] + (parts[i + 1] || "");
      if (!body) continue;
      const prefix = promptPrefix(parts[i]);
      let rule = promptRules.find(r => prefix.startsWith(r[2]));
      if (!rule && prefix.startsWith("Houdini outputs belong under")) rule = promptRules[4];
      if (!rule) {
        // Match known paragraph openings, without copying current text into history.
        const definition = definitions.find(d => d.starts.some(start => prefix.startsWith(start)));
        rule = definition?.rule;
      }
      const category = rule?.[0] || "其他／来源未识别";
      const source = rule?.[3] || "未采集；保留实际请求原文";
      const last = sections.at(-1);
      if (last?.source === source && rule) last.text += body;
      else sections.push({category, title: rule?.[1] || "未知系统片段", source, text: body, index: sections.length + 1});
    }
    return sections;
  }
  // UI categories only: these colors do not confer execution permissions.
  const toolKind = (name) => {
    if (name === "skill") return "skill";
    if (["houdini_inspect", "houdini_request", "houdini_resource", "houdini_capabilities", "houdini_query", "houdini_job_status"].includes(name)) return "query";
    if (name.startsWith("houdini_")) return "exec";
    if (["read", "read_file", "glob", "grep", "ls"].includes(name))
      return "read";
    if (
      [
        "get_goal",
        "create_goal",
        "update_goal",
        "todo_write",
        "todo",
        "write_todos",
        "update_plan",
      ].includes(name)
    )
      return "planning";
    if (["bash", "pwsh", "shell", "exec_command", "write_stdin"].includes(name))
      return "shell";
    if (
      [
        "write",
        "write_file",
        "edit",
        "edit_file",
        "apply_patch",
        "multiedit",
      ].includes(name)
    )
      return "write";
    if (["web", "web_search", "web_fetch", "search", "fetch"].includes(name))
      return "search";
    if (["ask_user", "ask_user_question", "request_user_input"].includes(name))
      return "interaction";
    return "other";
  };
  const kindNames = {
    skill: "技能读取",
    read: "文件读取",
    query: "Houdini 查询",
    exec: "Houdini 执行",
    planning: "目标与计划",
    shell: "终端执行",
    write: "文件写入",
    search: "搜索与网页",
    interaction: "用户交互",
    other: "其他工具",
  };
  const domainLabel = (name) =>
    ({
      "vocabulary 域": "签名与帮助",
      类型目录: "类型发现",
      "node 域": "节点与网络",
      "parm 域": "参数与动画",
      "scene 域": "工程与时间线",
      "geometry 域": "几何与关系",
      "stage / USD 域": "Solaris / USD",
      "asset 域": "HDA 资产",
      "render / sim 域": "渲染与模拟",
      "viewport 域": "视口与界面",
    })[name] || name;
  const verbTitles = {
    tab_create: "创建节点",
    tab_apply: "应用节点组合",
    build_module: "构建模块",
    set_parm: "修改参数",
    set_parms: "批量修改参数",
    verify_network: "检查网络输出",
    node_info: "查询节点参数",
    scene_info: "读取场景",
    render_view: "生成预览",
    render_check: "检查图像",
    connect: "连接节点",
    delete_node: "删除节点",
    layout_nodes: "整理网络",
    read_parms: "读取参数",
    geo_check_interfaces: "检查实体接口",
    test_controls: "测试控制参数",
  };
  function usage(u) {
    if (
      !u ||
      typeof u.inputTokens !== "number" ||
      typeof u.outputTokens !== "number"
    )
      return null;
    if (
      ![
        u.inputTokens,
        u.outputTokens,
        u.cacheReadTokens ?? 0,
        u.cacheWriteTokens ?? 0,
      ].every((n) => Number.isFinite(n) && n >= 0)
    )
      return null;
    // DSH TokenUsage buckets are DISJOINT: inputTokens excludes cache reads/writes.
    return {
      input:
        u.inputTokens + (u.cacheReadTokens || 0) + (u.cacheWriteTokens || 0),
      output: u.outputTokens,
      raw: u,
    };
  }
  function resourcePath(value) {
    if (typeof value !== "string") return null;
    const path = value.replaceAll("\\", "/");
    if (
      !/^(?:[A-Za-z]:\/|\/)/.test(path) ||
      path.split("/").some((s) => s === "." || s === "..")
    )
      return null;
    return /^[A-Za-z]:/.test(path)
      ? path.toLowerCase().replace(/\/+$/, "")
      : path.replace(/\/+$/, "");
  }
  function model(snapshot) {
    snapshot = snapshot || {};
    const nodes = array(snapshot.eventNodes);
    const requests = [];
    const seenRequests = new Set();
    for (const r of array(snapshot.requests)) {
      const key = requestKey(r);
      if (!seenRequests.has(key)) {
        requests.push({ ...r, key, accounting: usage(r.usage) });
        seenRequests.add(key);
      }
    }
    requests.sort((a, b) => a.startSeq - b.startSeq);
    // One request index per snapshot. Calls sharing a model step reuse its
    // request group instead of rescanning every request for each result.
    const requestsByStep = new Map();
    const requestsByKey = new Map();
    let latestAssistant = null;
    for (const request of requests) {
      requestsByKey.set(request.key, request);
      if (request.purpose !== "assistant") continue;
      latestAssistant = request;
      const key = pairKey(request.turn, request.step);
      let group = requestsByStep.get(key);
      if (!group) {
        group = { rows: [], complete: [], resultSeq: new Map() };
        requestsByStep.set(key, group);
      }
      group.rows.push(request);
      group.complete.push(request.status === "complete" ? request : group.complete.at(-1) || null);
      if (Number.isFinite(request.resultSeq) && !group.resultSeq.has(request.resultSeq))
        group.resultSeq.set(request.resultSeq, request);
    }
    const requestFor = (turn, step, seq) => {
      const group = requestsByStep.get(pairKey(turn, step));
      if (!group) return null;
      let end = group.rows.length;
      if (seq != null) {
        let low = 0;
        while (low < end) {
          const mid = (low + end) >>> 1;
          if (group.rows[mid].startSeq <= seq) low = mid + 1;
          else end = mid;
        }
        end = low;
      }
      if (!end) return null;
      const exact = group.resultSeq.get(seq);
      if (exact && (seq == null || exact.startSeq <= seq)) return exact;
      return group.complete[end - 1] || group.rows[end - 1];
    };
    const calls = new Map();
    nodes.forEach((n) => {
      if (n.kind === "assistant")
        for (const b of array(n.blocks))
          if (b.kind === "tool-call" && b.callId)
            calls.set(b.callId, {
              ...b,
              turn: n.turn,
              step: n.step,
              seq: n.seq,
              time: n.time,
              request: requestFor(n.turn, n.step, n.seq),
              assistantUsage: usage(n.usage),
              interrupted: n.interrupted,
            });
    });
    const entries = [];
    const entriesById = new Map();
    const seenExecutions = new Set();
    const seen = new Set();
    function add(n, pending, parent) {
      const id = n.callId || "unpaired:" + n.seq;
      if (seen.has(id)) return;
      seen.add(id);
      const c = calls.get(id);
      const location = snapshot.eventLocations?.get?.(n.seq);
      const turn = c?.turn ?? n.turn ?? location?.step?.turn;
      const step = c?.step ?? n.step ?? location?.step?.step;
      const name = (pending ? n.name : n.call?.name) || c?.name || "未知工具";
      const argsRaw =
        (pending ? n.argsRaw : n.call?.argsRaw) ?? c?.argsRaw ?? "";
      const info = parseEntry({ ...n, call: { name, argsRaw } });
      const parts = info.parts;
      const canonical = name.startsWith("houdini_") ? info.canonical : null;
      const transaction = canonical?.transaction ?? json(parts.transaction);
      const req =
        c?.request ||
        requestFor(turn, step, n.seq) ||
        entriesById.get(parent)?.request ||
        null;
      const account = req?.accounting || c?.assistantUsage || null;
      const failed = !pending && (Boolean(n.isError) || info.failed);
      const executionKey = canonical?.execution?.runtime_id && Number.isFinite(canonical.execution.sequence)
        ? canonical.execution.runtime_id + ':' + canonical.execution.sequence : null;
      const repeatedExecution = executionKey && seenExecutions.has(executionKey);
      if(executionKey)seenExecutions.add(executionKey);
      const verbs = canonical?.requestReceipt?.retrieved || repeatedExecution ? [] : info.verbs;
      const parsedArgs = json(argsRaw);
      const args =
        parsedArgs &&
        typeof parsedArgs === "object" &&
        !Array.isArray(parsedArgs)
          ? parsedArgs
          : {};
      const analysisStep = {tool: name, isHoudini: name.startsWith('houdini_'),
        args, code: args.code || '', verbs, failed, canonical,
        rawUsage: info.rawUsage, resultText: info.text};
      const rawEffect = isHoudiniHostCall(analysisStep) ? null : classifyRawEffect(analysisStep);
      const gateBlocked = rawEffect === 'gate_blocked';
      const title =
        name === "skill"
          ? "读取技能 · " + (args.name || "名称缺失")
          : verbs.length
            ? [...new Set(verbs.map((v) => verbTitles[v.verb] || v.verb))].join(
                " / ",
              )
            : args.request_ref
              ? "查回原请求"
              : name === "houdini_resource"
              ? args.kind === "source" ? "读取原始任务来源" : "读取历史工具结果"
              : args.source_ref
              ? "读取原始任务来源"
              : args.result_ref
              ? "读取历史工具结果"
              : args.review
              ? "复核输出"
              : args.review_test
                ? "受控复核实验"
                : sources.tools?.[name]?.label || name;
      const rollback = transaction
        ? transaction.status === "rolled_back"
        : Boolean(info.rollback?.applied && !info.rollback.error);
      const state = pending
        ? "执行中（最后快照）"
        : gateBlocked
          ? "Gate 拦截"
          : rollback
            ? "已回滚"
            : failed
              ? "失败"
              : transaction?.status === "committed"
                ? "已提交"
                : "已成功";
      const start = pending ? n.time : (n.callTime ?? c?.time ?? null);
      const end = pending ? null : n.time;
      const result = canonical ? canonical.result : json(parts.__result__) ?? info.resultValue;
      const targets = [
        ...new Set(
          verbs.flatMap((v) => {
            const decoded =
              json(v.argsText) || json("[" + v.argsText + "]")?.[0];
            return array(decoded).filter(
              (x) => typeof x === "string" && x.startsWith("/"),
            );
          }),
        ),
      ];
      const target = [
        args.path,
        args.file_path,
        args.node,
        args.parent,
        result?.output,
        ...targets,
      ]
        .filter((x) => typeof x === "string" && x)
        .slice(0, 3)
        .join(" · ");
      const entry = {
        ...info,
        id,
        key: id,
        name,
        args,
        argsRaw,
        analysisStep,
        rawEffect,
        gateBlocked,
        title,
        target,
        verbs,
        failed,
        pending,
        parent: parent || n.parentCallId || null,
        transaction,
        rollbackApplied: rollback,
        state,
        kind: args.request_ref || args.result_ref || args.source_ref ? "read" : toolKind(name),
        request: req,
        requestKey: req?.key || (c ? "assistant:" + pairKey(turn, step) : null),
        accounting: account,
        start,
        end,
        seq: c?.seq ?? n.seq ?? Number.MAX_SAFE_INTEGER,
        resultSeq: n.seq,
        duration:
          typeof start === "number" && typeof end === "number"
            ? Math.max(0, end - start)
            : null,
        resultValue: result,
        evidence: canonical?.evidence ?? json(parts["operation-evidence"]),
        parts,
        blocks: n.content || [],
        meta: n.meta,
        committed: !pending && !failed && !rollback,
        jobId: args.jobId || result?.jobId || null,
      };
      entries.push(entry);
      entriesById.set(id, entry);
      array(n.subCalls).forEach((child) =>
        add(child, child.kind !== "tool-result", id),
      );
    }
    // Collect settlements before pending descendants, even when an earlier parent
    // snapshot still contains a running child. A replay never replaces the original.
    const settled = [];
    const pending = [];
    const parentHints = new Map();
    function collect(n, parent) {
      if (parent && n.callId) parentHints.set(n.callId, parent);
      (n.kind === "tool-result" ? settled : pending).push({ node: n, parent });
      array(n.subCalls).forEach((child) => collect(child, n.callId));
    }
    nodes.filter((n) => n.kind === "tool-result").forEach((n) => collect(n));
    array(snapshot.runningCalls).forEach((n) => collect(n));
    settled
      .sort((a, b) => a.node.seq - b.node.seq)
      .forEach(({ node, parent }) =>
        add(
          { ...node, subCalls: [] },
          false,
          parent || parentHints.get(node.callId),
        ),
      );
    pending.forEach(({ node, parent }) =>
      add({ ...node, subCalls: [] }, true, parent),
    );
    entries.forEach((e) => {
      if (e.parent && !e.request) {
        const parent = entriesById.get(e.parent);
        if (parent) {
          e.request = parent.request;
          e.requestKey = parent.requestKey;
          e.accounting = parent.accounting;
        }
      }
    });
    entries.sort(
      (a, b) =>
        (a.start ?? a.end ?? Infinity) - (b.start ?? b.end ?? Infinity) ||
        a.seq - b.seq,
    );
    entries.forEach((e, i) => (e.index = i + 1));
    const contexts = nodes
      .filter(
        (n) =>
          n.kind === "context" || n.kind === "user" || n.kind === "steering",
      )
      .sort((a, b) => a.seq - b.seq);
    const skillCatalogs = contexts.filter(
      (n) =>
        n.source?.kind === "skill-catalog" && Array.isArray(n.source.entries),
    );
    const skillLoads = [];
    function loaded(name, body, seq, callId) {
      const match = body.match(/^Base directory for this skill: (.+)$/m);
      const base = resourcePath(
        match?.[1]
          ?.replaceAll("&lt;", "<")
          .replaceAll("&gt;", ">")
          .replaceAll("&amp;", "&"),
      );
      if (base) skillLoads.push({ name, base, seq, callId });
    }
    entries
      .filter(
        (e) =>
          e.name === "skill" &&
          !e.failed &&
          !e.pending &&
          typeof e.args.name === "string",
      )
      .forEach((e) => loaded(e.args.name, e.text, e.resultSeq, e.id));
    contexts
      .filter((n) => n.source?.kind === "skill-invocation")
      .forEach((n) => loaded(n.source.name, text(n.content), n.seq, null));
    const resourceReads = [];
    entries
      .filter((e) => e.name === "read" && !e.failed && !e.pending)
      .forEach((e) => {
        const path =
          resourcePath(e.meta?.path) || resourcePath(e.args.file_path);
        if (!path) return;
        const candidates = skillLoads.filter(
          (s) => s.seq < e.resultSeq && path.startsWith(s.base + "/"),
        );
        const identities = [...new Set(candidates.map((s) => s.name))];
        if (identities.length !== 1) return;
        const binding = candidates[candidates.length - 1];
        resourceReads.push({
          name: binding.name,
          path: path.slice(binding.base.length + 1),
          entry: e,
          version: "未采集",
        });
      });
    return {
      entries,
      requests,
      contexts,
      skillCatalogs,
      resourceReads,
      nodes,
      partial: snapshot.partial,
      entriesById,
      requestsByKey,
      latestAssistant,
      statistics: summarize(entries, requests),
      pendingCount: entries.reduce((count, entry) => count + Number(entry.pending), 0),
      recent: nodes.reduce((max, node) => Math.max(max, node.time || 0), 0),
    };
  }
  function summarize(entries, requests) {
    const returned = entries.filter(entry => entry.name.startsWith("houdini_") && !entry.pending);
    const used = new Set(returned.flatMap(entry => entry.verbs.map(verb => verb.verb)));
    const known = catalog.flatMap(domain => domain.verbs.map(verb => verb.name));
    const accounts = requests.map(request => request.accounting).filter(Boolean);
    const rawEffectCounts = new Map();
    let gateBlockedCalls = 0, rolledBackCalls = 0, rolledBackVerbCalls = 0;
    for (const entry of returned) {
      if (entry.gateBlocked) gateBlockedCalls++;
      if (entry.rollbackApplied) {
        rolledBackCalls++;
        rolledBackVerbCalls += entry.verbs.reduce((count, verb) => count + Number(verb.ok), 0);
      }
      if (!entry.verbs.length)
        rawEffectCounts.set(entry.rawEffect, (rawEffectCounts.get(entry.rawEffect) || 0) + 1);
    }
    return {
      adoption: collectVerbAdoption(returned.map(entry => entry.analysisStep)),
      knownVerbCount: known.length,
      usedVerbCount: known.reduce((count, name) => count + Number(used.has(name)), 0),
      gateBlockedCalls,
      rolledBackCalls,
      rolledBackVerbCalls,
      rawEffectCounts,
      failures: entries.filter(entry => entry.failed || entry.rollbackApplied),
      requestUsage: {
        reported: accounts.length,
        total: requests.length,
        input: accounts.reduce((total, account) => total + account.input, 0),
        output: accounts.reduce((total, account) => total + account.output, 0),
      },
    };
  }
  return { model, usage, systemSections, array, json, text, format, stamp, requestKey, own, toolKind, kindNames, domainLabel, verbTitles };
});
      var createView = (function createTraceView(React, catalog, sources, trace, css) {
  "use strict";
  const h = React.createElement;
  const { model, usage, systemSections, array, json, text, format, stamp, requestKey, own, toolKind, kindNames, domainLabel, verbTitles } = trace;
  const button = (label, action, active, key) =>
    h(
      "button",
      {
        type: "button",
        onClick: action,
        "aria-pressed": active,
        key: key || label,
      },
      label,
    );
  const note = (s) => h("div", { className: "tr-note" }, s);
  const empty = (s) => h("div", { className: "tr-empty" }, s);
  const tag = (s, bad = false) =>
    h("span", { className: "tr-pill" + (bad ? " tr-bad" : "") }, s);
  const typeTag = (name) =>
    h(
      "span",
      { className: "tr-type", "data-kind": toolKind(name) },
      kindNames[toolKind(name)] + " · " + name,
    );
  const table = (heads, rows) =>
    h(
      "table",
      null,
      h(
        "thead",
        null,
        h(
          "tr",
          null,
          heads.map((s, i) => h("th", { key: i }, s)),
        ),
      ),
      h(
        "tbody",
        null,
        rows.map((r, i) =>
          h(
            "tr",
            { key: i },
            r.map((s, j) => h("td", { key: j }, s)),
          ),
        ),
      ),
    );
  function prose(value) {
    const chunks = String(value ?? "").split(/(```[\s\S]*?```)/);
    const inline = (p) =>
      p
        .split(/(`[^`]+`|\*\*[^*]+\*\*)/)
        .map((s, j) =>
          s.startsWith("`") && s.endsWith("`")
            ? h("code", { key: j }, s.slice(1, -1))
            : s.startsWith("**") && s.endsWith("**")
              ? h("strong", { key: j }, s.slice(2, -2))
              : s,
        );
    return h(
      "div",
      { className: "tr-prose" },
      chunks.map((chunk, i) =>
        chunk.startsWith("```")
          ? h(
              "pre",
              { key: i },
              chunk.replace(/^```[^\n]*\n?/, "").replace(/```$/, ""),
            )
          : h(
              "div",
              { key: i },
              chunk
                .split(/\n\s*\n/)
                .filter(Boolean)
                .map((p, j) =>
                  /^#{1,6} /.test(p)
                    ? h("h4", { key: j }, inline(p.replace(/^#{1,6} /, "")))
                    : h("p", { key: j }, inline(p)),
                ),
            ),
      ),
    );
  }
  function structured(value, depth = 0) {
    if (value == null)
      return h(
        "span",
        { className: "tr-meta" },
        value === null ? "null" : "未采集",
      );
    if (typeof value !== "object")
      return typeof value === "string" ? prose(value) : String(value);
    if (depth > 5)
      return h(
        "details",
        null,
        h("summary", null, "展开深层数据"),
        h("pre", null, JSON.stringify(value, null, 2)),
      );
    if (
      Array.isArray(value) &&
      value.length &&
      value.every((v) => v && typeof v === "object" && !Array.isArray(v))
    ) {
      const keys = [...new Set(value.flatMap((v) => Object.keys(v)))];
      if (keys.length > 0 && keys.length <= 8)
        return h(
          "div",
          null,
          table(
            keys,
            value
              .slice(0, 50)
              .map((v) =>
                keys.map((k) =>
                  own(v, k) ? structured(v[k], depth + 1) : "未采集",
                ),
              ),
          ),
          value.length > 50
            ? h(
                "details",
                null,
                h("summary", null, "其余项目 · 完整返回"),
                h("pre", null, JSON.stringify(value, null, 2)),
              )
            : null,
        );
    }
    const entries = Array.isArray(value)
      ? value.map((v, i) => [String(i + 1), v])
      : Object.entries(value);
    if (!entries.length)
      return h(
        "span",
        { className: "tr-meta" },
        Array.isArray(value) ? "空列表" : "空对象",
      );
    const page = entries.slice(0, 50);
    return h(
      "div",
      { className: "tr-tree" },
      table(
        ["字段 / 序号", "值"],
        page.map(([k, v]) => [
          k,
          typeof v === "object" && v !== null
            ? h(
                "details",
                null,
                h(
                  "summary",
                  null,
                  Array.isArray(v)
                    ? v.length + " 项"
                    : Object.keys(v).length + " 个字段",
                ),
                structured(v, depth + 1),
              )
            : structured(v, depth + 1),
        ]),
      ),
      entries.length > 50
        ? h(
            "details",
            null,
            h(
              "summary",
              null,
              "其余 " + (entries.length - 50) + " 项 · 完整原文",
            ),
            h("pre", null, JSON.stringify(value, null, 2)),
          )
        : null,
    );
  }
  function usageView(account) {
    if (!account)
      return note("输入 / 输出 tokens：未采集。工具返回内容不是模型输出。");
    const u = account.raw;
    return h(
      "div",
      null,
      table(
        ["模型请求输入", "模型请求输出"],
        [[format(account.input), format(account.output)]],
      ),
      h(
        "div",
        { className: "tr-meta" },
        "未缓存 " +
          format(u.inputTokens) +
          " · 缓存读 " +
          format(u.cacheReadTokens) +
          " · 缓存写 " +
          format(u.cacheWriteTokens) +
          " · 推理 " +
          format(u.reasoningTokens),
      ),
      note(
        "DSH 输入总量 = 未缓存输入 + 已报告缓存读/写。该 usage 属于整个模型请求，多调用共享；推理量不再次加到输出。",
      ),
    );
  }
  function verbArguments(value) {
    const direct = json(value);
    const wrapped = json("[" + value + "]");
    if (
      Array.isArray(wrapped) &&
      Array.isArray(wrapped[0]) &&
      wrapped.length === 2 &&
      wrapped[1] &&
      typeof wrapped[1] === "object"
    ) {
      return structured({ 位置参数: wrapped[0], 命名参数: wrapped[1] });
    }
    return structured(direct ?? value);
  }
  function View(props) {
    const snapshot = props.useTrajectory((s) => s);
    const data = React.useMemo(() => model(snapshot), [snapshot]);
    const [tab, setTab] = React.useState("timeline");
    const [filter, setFilter] = React.useState("all");
    const [selected, setSelected] = React.useState(null);
    const [chosenRequest, setRequest] = React.useState(null);
    const [domain, setDomain] = React.useState("node 域");
    const [chosenVerb, setVerb] = React.useState("build_module");
    const [toolPage, setToolPage] = React.useState("verbs");
    const [promptPage, setPromptPage] = React.useState("actual");
    const [sourceKey, setSourceKey] = React.useState("guidance");
    const [skillName, setSkill] = React.useState(null);
    const [skillFile, setSkillFile] = React.useState("SKILL.md");
    const [page, setPage] = React.useState(-1);
    const [detailOpen, setDetailOpen] = React.useState(false);
    const listElement = React.useRef(null);
    const latestScroll = React.useRef({ sessionId: props.sessionId, pending: true });
    React.useEffect(() => {
      setSelected(null);
      setRequest(null);
      setPage(-1);
      setDetailOpen(false);
    }, [props.sessionId]);
    const request =
      data.requestsByKey.get(chosenRequest) ||
      data.latestAssistant ||
      null;
    const entry =
      data.entriesById.get(selected) ||
      data.entries[data.entries.length - 1];
    const goCall = (e) => {
      setSelected(e.id);
      setFilter("all");
      setPage(Math.floor((e.index - 1) / 50));
      setTab("timeline");
      setDetailOpen(true);
    };
    const goPrompt = (e) => {
      setRequest(e.request?.key || null);
      setTab("prompt");
    };
    const goVerb = (name) => {
      const d = catalog.find((d) => d.verbs.some((v) => v.name === name));
      if (d) {
        setDomain(d.domain);
        setVerb(name);
        setToolPage("verbs");
        setTab("tools");
      }
    };
    const requestPicker = () =>
      h(
        "label",
        { className: "tr-meta" },
        "请求 ",
        h(
          "select",
          {
            value: request?.key || "",
            onChange: (e) => setRequest(e.target.value),
            "aria-label": "选择模型请求",
          },
          !data.requests.length
            ? h("option", { value: "" }, "请求快照未采集")
            : null,
          data.requests.map((r, i) =>
            h(
              "option",
              { key: r.key, value: r.key },
              "#" +
                (i + 1) +
                " · " +
                (r.purpose === "assistant"
                  ? "轮次 " + r.turn + " / step " + r.step
                  : "压缩") +
                " · " +
                r.status,
            ),
          ),
        ),
      );
    const openCallLink = (e) =>
      button("#" + e.index + " " + e.name, () => goCall(e));
    function details(e) {
      if (!e) return empty("选择一个调用查看详情。");
      const raw = e.parts;
      const verbRows = e.verbs.map((v, i) =>
        h(
          "details",
          { key: i, open: e.verbs.length <= 3 },
          h(
            "summary",
            { title: v.argsText + " -> " + v.detail },
            i +
              1 +
              ". " +
              v.verb +
              " · " +
              (v.ok
                ? e.rollbackApplied
                  ? "已执行后回滚"
                  : "动作返回成功"
                : "动作失败") +
              " · " +
              v.ms +
              " ms",
          ),
          h("h4", null, "参数"),
          verbArguments(v.argsText),
          v.error != null ? h("h4", null, "错误") : null,
          v.error != null ? structured(v.error) : null,
          h("h4", null, "返回"),
          v.detail == null ? note("返回值未记录；失败原因和补充证据不等于成功返回。")
            : structured(json(v.detail) ?? v.detail),
          v.summary != null ? h("h4", null, "补充证据") : null,
          v.summary != null ? structured(v.summary) : null,
          typeof v.detail === "string" && v.detail.endsWith("…")
            ? note("Host 动词摘要已截断；完整证据以操作证据和结构化返回为准。")
            : null,
          button("查看动词契约 →", () => goVerb(v.verb)),
        ),
      );
      return h(
        "aside",
        { className: "tr-detail" },
        h("div", { className: "tr-meta" }, "调用 #" + e.index + " · " + e.id),
        h("h3", null, e.title),
        h(
          "div",
          { className: "tr-buttons" },
          typeTag(e.name),
          tag(e.state, e.failed),
          e.rawEffect === "read_only_query"
            ? tag(
                "只读 query（守卫范围）",
              )
            : null,
          !e.verbs.length && e.rawEffect === "unknown" ? tag("副作用未知") : null,
          e.exemptionReason ? tag("低层豁免") : null,
          e.verbs.length ? tag("动词 ×" + e.verbs.length) : null,
        ),
        h(
          "div",
          { className: "tr-meta" },
          stamp(e.start ?? e.end) +
            " · " +
            (e.duration == null ? "执行耗时未采集" : e.duration + " ms"),
        ),
        e.failed
          ? h(
              "section",
              null,
              h("h4", null, "失败原因"),
              prose(e.errorText || e.statusText || "工具返回错误"),
              e.rollbackApplied
                ? note("可撤销范围已回滚；外部文件等副作用不属于恢复保证。")
                : e.gateBlocked
                  ? note("Raw Gate 在执行前拒绝。")
                  : note("场景影响按事务与操作证据判断。"),
            )
          : null,
        h("h4", null, "请求参数"),
        Object.keys(e.args).some((k) => k !== "code")
          ? structured(
              Object.fromEntries(
                Object.entries(e.args).filter(([k]) => k !== "code"),
              ),
            )
          : note(
              e.code
                ? "Python 执行请求 · " +
                    e.code.split("\n").length +
                    " 行；具体动作见下方动词证据，完整代码在末层展开。"
                : "未记录额外参数。",
            ),
        e.transaction
          ? h(
              "section",
              null,
              h("h4", null, "事务最终状态"),
              structured(e.transaction),
            )
          : null,
        e.evidence
          ? h(
              "section",
              null,
              h("h4", null, "操作与检查证据"),
              structured(e.evidence),
            )
          : null,
        raw["control-test-summary (not_run is not pass)"]
          ? h(
              "section",
              null,
              h("h4", null, "控制测试摘要"),
              structured(
                json(raw["control-test-summary (not_run is not pass)"]),
              ),
            )
          : null,
        raw[
          "CHECKS NEED ATTENTION (execution success is not validation success)"
        ]
          ? h(
              "section",
              null,
              h("h4", { className: "tr-bad" }, "检查需要关注"),
              structured(
                json(
                  raw[
                    "CHECKS NEED ATTENTION (execution success is not validation success)"
                  ],
                ),
              ),
              note("执行成功不代表验证通过。"),
            )
          : null,
        e.verbs.length
          ? h("section", null, h("h4", null, "动词证据"), verbRows)
          : null,
        e.resultValue != null
          ? h(
              "section",
              null,
              h("h4", null, "结构化返回"),
              structured(e.resultValue),
            )
          : null,
        !e.name.startsWith("houdini_") && e.text
          ? h(
              "section",
              null,
              h("h4", null, "工具返回"),
              structured(json(e.text) ?? e.text),
            )
          : null,
        raw.stdout
          ? h(
              "details",
              null,
              h("summary", null, "程序输出"),
              prose(
                raw.stdout
                  .split("\n")
                  .filter((l) => !l.startsWith("[verb]"))
                  .join("\n"),
              ),
            )
          : null,
        e.hint
          ? h("section", null, h("h4", null, "执行提示"), prose(e.hint))
          : null,
        e.rawUsage || e.exemptionReason
          ? h(
              "details",
              null,
              h("summary", null, "HOM / Raw Gate · " + (e.rawUsage?.gateOutcome || e.rawEffect || "未采集")),
              structured(e.rawUsage),
              e.exemptionReason ? prose(e.exemptionReason) : null,
            )
          : null,
        e.rollback
          ? h(
              "details",
              null,
              h("summary", null, "回滚范围"),
              structured(e.rollback),
            )
          : null,
        e.blocks.some((b) => b.type !== "text")
          ? h(
              "details",
              null,
              h("summary", null, "媒体与其他内容块"),
              structured(e.blocks.filter((b) => b.type !== "text")),
            )
          : null,
        e.imageAttachments || e.canonical?.imageAttachments
          ? h("details", null, h("summary", null, "原生图像附件 · 传递状态"),
              structured(e.canonical?.imageAttachments || json(e.imageAttachments) || e.imageAttachments))
          : null,
        e.media
          ? h(
              "section",
              null,
              h("h4", null, "媒体产物"),
              structured(json(e.media) ?? e.media),
              note(
                "产物转交不证明语义识图成功；视觉未验证，除非另有识图调用证据。",
              ),
            )
          : null,
        e.jobId
          ? h(
              "section",
              null,
              h("h4", null, "关联后台任务 · " + e.jobId),
              h(
                "div",
                { className: "tr-buttons" },
                data.entries
                  .filter((x) => x.id !== e.id && x.jobId === e.jobId)
                  .map(openCallLink),
              ),
            )
          : null,
        e.parent ? note("子调用 · 父 callId " + e.parent) : null,
        h("h4", null, "关联模型请求 tokens"),
        usageView(e.accounting),
        h(
          "div",
          { className: "tr-meta" },
          "工具返回 " + e.text.length + " 字符 · token长度未估算",
        ),
        e.request
          ? button("查看本步提示词与上下文 →", () => goPrompt(e))
          : note("请求关联未采集，不按相邻时间猜测。"),
        h(
          "details",
          { className: "tr-raw" },
          h("summary", null, "原始请求与结果 · 开发排查"),
          h("h4", null, "执行代码"),
          h("pre", null, e.code || e.argsRaw),
          h("h4", null, "查看原始工具结果"),
          h("pre", null, e.text || "尚无结果"),
        ),
      );
    }
    function timeline() {
      const visible = data.entries.filter(
        (e) =>
          filter === "all" ||
          (filter === "houdini" && e.name.startsWith("houdini_")) ||
          (filter === "error" && (e.failed || e.gateBlocked)),
      );
      const pages = Math.max(1, Math.ceil(visible.length / 50));
      const safePage = Math.min(page < 0 ? pages - 1 : page, pages - 1);
      const listed = visible.slice(safePage * 50, safePage * 50 + 50);
      const visibleEntry = listed.find((e) => e.id === entry?.id) || listed[0];
      const jumpLatest = () => {
        latestScroll.current = { sessionId: props.sessionId, pending: true };
        movePage(-1);
        // Clicking Latest again may not trigger a render if state is unchanged.
        if (safePage === pages - 1 && listElement.current) {
          listElement.current.scrollTop = listElement.current.scrollHeight;
          latestScroll.current.pending = false;
        }
      };
      const compactNumber = (n) =>
        n < 1000
          ? String(n)
          : (n / 1000).toFixed(n < 10000 ? 2 : 1).replace(/\.?0+$/, "") + "k";
      const movePage = (next) => {
        setPage(next);
        setSelected(null);
        setDetailOpen(false);
      };
      const pagerButton = (label, next, disabled) =>
        h(
          "button",
          { type: "button", onClick: () => movePage(next), disabled },
          label,
        );
      const shortState = (e) => (e.pending ? "执行中" : e.state);
      return h(
        "div",
        { className: "tr-timeline" + (detailOpen ? " tr-detail-open" : "") },
        h(
          "div",
          { className: "tr-timeline-toolbar" },
          h(
            "div",
            { className: "tr-buttons", "aria-label": "调用范围" },
            [
              ["all", "全部"],
              ["houdini", "Houdini"],
              ["error", "失败 / 拦截"],
            ].map(([k, label]) =>
              button(
                label,
                () => {
                  setFilter(k);
                  movePage(0);
                },
                filter === k,
              ),
            ),
          ),
          h(
            "div",
            { className: "tr-pager", "aria-label": "步骤分页" },
            h(
              "span",
              { className: "tr-range" },
              visible.length
                ? `${safePage * 50 + 1}–${safePage * 50 + listed.length} / ${visible.length}`
                : "0 个调用",
            ),
            pagerButton("上一页", safePage - 1, safePage === 0),
            h(
              "label",
              null,
              h("span", { className: "tr-sr-only" }, "选择步骤页码"),
              h(
                "select",
                {
                  "aria-label": "选择步骤页码",
                  value: String(safePage),
                  onChange: (e) => movePage(Number(e.target.value)),
                },
                Array.from({ length: pages }, (_, i) =>
                  h(
                    "option",
                    { key: i, value: String(i) },
                    `${i + 1} / ${pages} 页`,
                  ),
                ),
              ),
            ),
            pagerButton("下一页", safePage + 1, safePage === pages - 1),
            h(
              "button",
              {
                type: "button",
                onClick: jumpLatest,
                "aria-pressed": page === -1,
              },
              "最新",
            ),
          ),
        ),
        h(
          "div",
          { className: "tr-timeline-body" },
          h(
            "div",
            {
              className: "tr-call-list",
              ref: el => {
                listElement.current = el;
                if (!el) return;
                if (latestScroll.current.sessionId !== props.sessionId) {
                  latestScroll.current = { sessionId: props.sessionId, pending: true };
                }
                if (page === -1 && listed.length && latestScroll.current.pending) {
                  el.scrollTop = el.scrollHeight;
                  latestScroll.current.pending = false;
                }
              },
              onWheel: event => {
                if (page === -1 && event.deltaY < 0) setPage(safePage);
              },
              onScroll: event => {
                const el = event.currentTarget;
                if (page === -1 && el.scrollHeight - el.clientHeight - el.scrollTop > 8) {
                  setPage(safePage);
                }
              },
              key: filter + ":" + safePage,
              role: "region",
              "aria-label": "工具调用步骤列表",
            },
            !listed.length
              ? empty("此范围尚无调用记录。")
              : listed.map((e) => {
                  const target =
                    e.target ||
                    e.args.name ||
                    e.args.jobId ||
                    e.verbs.map((v) => v.verb).join(" · ") ||
                    "";
                  const time =
                    e.duration == null
                      ? e.pending
                        ? "…"
                        : "—"
                      : e.duration < 1000
                        ? e.duration + "ms"
                        : (e.duration / 1000).toFixed(1) + "s";
                  const tokens = e.accounting
                    ? `↑${compactNumber(e.accounting.input)} ↓${compactNumber(e.accounting.output)}`
                    : "tokens —";
                  return h(
                    "button",
                    {
                      type: "button",
                      className: "tr-call-row",
                      key: e.id,
                      "data-kind": e.kind,
                      "aria-pressed": visibleEntry?.id === e.id,
                      "aria-label": `调用 #${e.index} · ${e.title} · ${e.name} · ${e.state}`,
                      onClick: () => {
                        setSelected(e.id);
                        setDetailOpen(true);
                      },
                    },
                    h(
                      "span",
                      { className: "tr-call-head" },
                      h("span", { className: "tr-call-index" }, "#" + e.index),
                      h(
                        "span",
                        { className: "tr-call-title", title: e.title },
                        e.title,
                      ),
                      h(
                        "span",
                        {
                          className:
                            "tr-call-state" + (e.failed ? " tr-bad" : ""),
                        },
                        shortState(e),
                      ),
                      h(
                        "span",
                        { className: "tr-call-time", title: "工具执行耗时" },
                        time,
                      ),
                    ),
                    h(
                      "span",
                      { className: "tr-call-meta" },
                      h(
                        "span",
                        {
                          className: "tr-call-kind",
                          title: kindNames[e.kind] + " · " + e.name,
                        },
                        e.name,
                      ),
                      h(
                        "span",
                        { className: "tr-call-target", title: target },
                        target,
                      ),
                      h(
                        "span",
                        {
                          className: "tr-call-tokens",
                          title: e.accounting
                            ? `关联模型请求输入 ${format(e.accounting.input)} / 输出 ${format(e.accounting.output)} tokens；多个工具可能共享本次请求。`
                            : "模型请求 usage 未采集",
                        },
                        tokens,
                      ),
                    ),
                  );
                }),
          ),
          h(
            "div",
            {
              className: "tr-call-detail",
              key: visibleEntry?.id || "empty",
              role: "region",
              "aria-label": "所选调用详情",
            },
            h(
              "button",
              {
                type: "button",
                className: "tr-back-list",
                onClick: () => setDetailOpen(false),
              },
              "← 返回步骤列表",
            ),
            details(visibleEntry),
          ),
        ),
        h(
          "div",
          { className: "tr-timeline-footer" },
          h(
            "span",
            null,
            "颜色区分工具用途 · ",
            [...new Set(listed.map((e) => e.kind))].map((kind) =>
              h(
                "span",
                { className: "tr-kind-legend", "data-kind": kind, key: kind },
                kindNames[kind],
              ),
            ),
          ),
          h("span", null, "↑ 输入 / ↓ 输出 tokens · 共享请求不重复累计"),
        ),
      );
    }

    function prompt() {
      const p = request?.prompt;
      const sections = systemSections(p?.system);
      const g = sources.guidance;
      const sourceItems = [
        {
          key: "guidance",
          title: "Houdini 插件系统提示词",
          label: g.name,
          hash: g.hash,
          bytes: g.bytes,
          source: g.source,
          order: g.order,
        },
        ...sources.presets.map((p) => ({
          key: "preset:" + p.name,
          title: "Preset · " + p.name,
          label: "persona 模板",
          hash: p.hash,
          bytes: p.bytes,
          source: p.file,
          presetFile: p.presetFile,
          order: 0,
        })),
      ];
      const s = sourceItems.find((s) => s.key === sourceKey) || sourceItems[0];
      const sourceSections = sections.filter(section => section.source === s.source
        || (s.key === "guidance" && section.source === s.source + " · " + s.label));
      const contexts = data.contexts.filter(
        (n) => !request || n.seq < request.startSeq,
      );
      return h(
        "div",
        { className: "tr-board" },
        h(
          "div",
          { className: "tr-toolbar" },
          h("h3", null, "提示词完整构成"),
          requestPicker(),
        ),
        h(
          "div",
          { className: "tr-buttons" },
          [
            ["actual", "实际 System"],
            ["sources", "插件来源与组成"],
            ["tools", "本次工具定义"],
            ["context", "上下文记录"],
          ].map(([k, s]) =>
            button(s, () => setPromptPage(k), promptPage === k),
          ),
        ),
        promptPage === "actual"
          ? h(
              "section",
              null,
              h("h4", null, "最终 System · 按请求记录原文"),
              p
                ? h("div", {className:"tr-prompt-groups", key: requestKey(request)},
                    note("按职责与已知来源规则分组，默认折叠。来源为文本匹配提示，未采集运行时注册 provenance；正文始终来自所选请求，未知内容完整保留。"),
                    [...new Set(sections.map(s => s.category))].map(category => {
                      const items = sections.filter(s => s.category === category);
                      return h("details", {className:"tr-prompt-group", key:category},
                        h("summary", null, category, h("span", {className:"tr-muted"}, ` · ${items.length} 个片段 · ${items.reduce((n,s)=>n+s.text.length,0)} 字符`)),
                        items.map(s => h("details", {className:"tr-prompt-section", key:s.index},
                          h("summary", null, `#${s.index} ${s.title}`, h("small", {className:"tr-prompt-source"}, s.source)),
                          h("pre", {className:"tr-prompt-raw"}, s.text))));
                    }),
                    h("details", {className:"tr-prompt-group"},
                      h("summary", null, "完整 System 原文 · 原始顺序"),
                      h("pre", {className:"tr-prompt-raw"}, p.system || "此请求未包含 System 正文")))
                : empty("此请求没有公开的提示词快照。"),
              request?.promptChange
                ? note("相对前一已加载状态：" + request.promptChange.kind)
                : null,
              p
                ? h(
                    "details",
                    null,
                    h("summary", null, "模型与请求配置"),
                    structured(p.config),
                  )
                : null,
              request?.promptChange?.previous
                ? h(
                    "details",
                    null,
                    h("summary", null, "变化前的 System 原文"),
                    prose(request.promptChange.previous.system),
                  )
                : null,
              note(
                "分类不改变实际 System 顺序。展开完整原文可核对；不能用当前源码替换历史请求，也不能将匹配来源当作已验证加载版本。",
              ),
            )
          : null,
        promptPage === "sources"
          ? h(
              "section",
              null,
              note(
                "来源路径与摘要来自当前构建包；正文来自所选历史请求。片段前缀只用于阅读定位，不认证历史加载版本。",
              ),
              h(
                "div",
                { className: "tr-split tr-inspector" },
                h(
                  "div",
                  { className: "tr-list" },
                  sourceItems.map((s) =>
                    h(
                      "button",
                      {
                        type: "button",
                        key: s.key,
                        className: "tr-row",
                        "aria-pressed": sourceKey === s.key,
                        onClick: () => setSourceKey(s.key),
                      },
                      s.title,
                      h("span", { className: "tr-meta" }, s.label),
                    ),
                  ),
                ),
                h(
                  "article",
                  { className: "tr-detail" },
                  h("h3", null, s.title),
                  table(
                    ["属性", "值"],
                    [
                      ["来源", s.source],
                      ...(s.presetFile ? [["生成的 preset", s.presetFile]] : []),
                      ["注册 / 模板", s.label],
                      ["定义 order", String(s.order)],
                      [
                        "历史片段定位",
                        sourceSections.length ? sourceSections.length + " 个可识别片段" : "未识别",
                      ],
                      ["当前模板大小", String(s.bytes) + " bytes"],
                      ["当前模板摘要", s.hash.slice(0, 16)],
                    ],
                  ),
                  note("当前模板在来源文件维护；下方保留本次请求中的实际片段。"),
                  sourceSections.length
                    ? sourceSections.map(section => h("details", {key: section.index},
                        h("summary", null, section.title + " · " + section.text.length + " 字符"),
                        h("pre", null, section.text)))
                    : note("该请求中没有可定位的片段；完整正文可在“实际 System”查看。"),
                ),
              ),
              h("h4", null, "DSH 与其他插件"),
              note(
                "完整内容在“实际 System”；其他插件的逐段来源与注册状态未由公开接口提供，不将配置名单冒充生效段。",
              ),
            )
          : null,
        promptPage === "tools"
          ? h(
              "section",
              null,
              h("h4", null, "本次可见工具 · " + (p?.tools?.length ?? "未采集")),
              p
                ? array(p.tools).map((t, i) =>
                    h(
                      "details",
                      { key: t.name || i },
                      h("summary", null, t.name),
                      prose(t.description),
                      structured(t.parameters || t),
                    ),
                  )
                : empty("工具快照未采集。"),
              note("工具 schema 是请求独立字段，不并入 System 正文。"),
            )
          : null,
        promptPage === "context"
          ? h(
              "section",
              null,
              note(
                "以下是请求开始前已记录的上下文消息，按事件顺序。公开快照不包含最终 messages 可见集合；历史存在不证明压缩/裁剪后仍保留。",
              ),
              !contexts.length
                ? empty("上下文记录未采集。")
                : contexts.map((n) =>
                    h(
                      "details",
                      { key: n.seq },
                      h(
                        "summary",
                        null,
                        "事件 " +
                          n.seq +
                          " · " +
                          (n.source?.kind || n.kind) +
                          " · " +
                          stamp(n.time),
                      ),
                      structured(n.source),
                      prose(text(n.content)),
                    ),
                  ),
              data.nodes
                .filter(
                  (n) =>
                    n.kind === "compaction" &&
                    (!request || n.seq < request.startSeq),
                )
                .map((n) =>
                  h(
                    "details",
                    { key: "c" + n.seq },
                    h("summary", null, "压缩记录 · " + n.seq),
                    prose(n.summary || "摘要未采集"),
                  ),
                ),
            )
          : null,
      );
    }
    function tools() {
      const d = catalog.find((d) => d.domain === domain) || catalog[0];
      const v = d?.verbs.find((v) => v.name === chosenVerb) || d?.verbs[0];
      const schemas = array(request?.prompt?.tools);
      const total = catalog.reduce((n, d) => n + d.verbs.length, 0);
      return h(
        "div",
        { className: "tr-board" },
        h(
          "div",
          { className: "tr-toolbar" },
          h("h3", null, "工具与动词设计"),
          requestPicker(),
        ),
        h(
          "div",
          { className: "tr-buttons tr-domains" },
          [
            ["verbs", "动词目录"],
            ["entry", "工具入口与可见性"],
            ["principles", "设计原则"],
          ].map(([k, s]) => button(s, () => setToolPage(k), toolPage === k)),
        ),
        toolPage === "verbs"
          ? h(
              "section",
              null,
              note(
                "模型工具入口 → 动词意图接口 → Bridge 主线程 → HOM。当前构建目录 " +
                  total +
                  " 个动词 / " +
                  catalog.length +
                  " 个分组，含历史兼容项；目录不是 live 版本证明。",
              ),
              h(
                "div",
                { className: "tr-buttons tr-domains" },
                catalog.map((d) =>
                  button(
                    domainLabel(d.domain) + " " + d.verbs.length,
                    () => {
                      setDomain(d.domain);
                      setVerb(d.verbs[0]?.name);
                    },
                    domain === d.domain,
                  ),
                ),
              ),
              d && v
                ? h(
                    "div",
                    { className: "tr-split tr-inspector" },
                    h(
                      "div",
                      null,
                      d.verbs.map((v) =>
                        h(
                          "button",
                          {
                            type: "button",
                            className: "tr-row",
                            key: v.name,
                            "aria-pressed": v.name === chosenVerb,
                            onClick: () => setVerb(v.name),
                          },
                          h("code", null, v.name),
                          h(
                            "span",
                            { className: "tr-meta" },
                            v.desc.replace(/[`*]/g, "").split(/[；。]/)[0],
                          ),
                        ),
                      ),
                    ),
                    h(
                      "article",
                      { className: "tr-detail" },
                      h("h3", null, v.name),
                      d.domain.includes("compatibility")
                        ? tag("仅历史兼容")
                        : null,
                      h("pre", null, v.name + "(" + v.sig + ")"),
                      h("h4", null, "用途与行为契约"),
                      prose(v.desc),
                      h("h4", null, "返回类型"),
                      prose(v.returns || "目录未提供"),
                      note(
                        "领域不代表只读/修改权限。参数、影响、失败与恢复以本动词契约为准；准确运行签名用 verb_help 查询。",
                      ),
                      h("h4", null, "实际调用记录"),
                      h(
                        "div",
                        { className: "tr-buttons" },
                        data.entries
                          .filter((e) => e.verbs.some((x) => x.verb === v.name))
                          .map(openCallLink),
                      ),
                      h(
                        "div",
                        { className: "tr-meta" },
                        "维护源：docs/tool-design.md · 随构建生成，签名和说明不在前端另抄。",
                      ),
                    ),
                  )
                : null,
            )
          : null,
        toolPage === "entry"
          ? h(
              "section",
              null,
              note(
                "“模型可见”来自所选请求的完整 schema。注册但被隐藏的工具清单未采集；调用历史与可见性分开。",
              ),
              table(
                ["工具", "本次模型可见", "加载窗口内调用"],
                [
                  ...new Set([
                    ...schemas.map((t) => t.name),
                    ...data.entries.map((e) => e.name),
                  ]),
                ].map((name) => [
                  typeTag(name),
                  request?.prompt
                    ? schemas.some((t) => t.name === name)
                      ? "可见"
                      : "未在本次集合中"
                    : "未采集",
                  String(data.entries.filter((e) => e.name === name).length),
                ]),
              ),
              schemas.map((t) =>
                h(
                  "details",
                  { key: t.name },
                  h("summary", null, t.name + " · schema"),
                  prose(t.description),
                  structured(t.parameters || t),
                ),
              ),
            )
          : null,
        toolPage === "principles"
          ? h(
              "section",
              null,
              table(
                ["层", "职责"],
                [
                  ["Preset", "身份、工作方式"],
                  ["Guidance", "跨领域稳定契约"],
                  ["Skill", "按需领域方法和完成范围"],
                  ["工具入口", "请求编组、只读/执行/异步生命周期"],
                  ["动词与 guard", "稳定意图、严格参数、权限及恢复边界"],
                  ["节点卡", "节点类型、关键操作决策"],
                ],
              ),
              note(
                "一次工具调用可执行多个动词，一个动词可创建多个节点。已覆盖修改不能以裸 hou 旁路；只读 HOM 保留观察能力。",
              ),
              table(
                ["入口", "职责"],
                Object.entries(sources.tools).map(([name, tool]) => [name, tool.purpose]),
              ),
            )
          : null,
      );
    }
    function skills() {
      const catalogs = data.skillCatalogs.filter(
        (n) => !request || n.seq < request.startSeq,
      );
      const latest = catalogs[catalogs.length - 1];
      const observed = array(latest?.source?.entries);
      const names = [
        ...new Set([
          ...observed.map((s) => s.name),
          ...sources.skills.map((s) => s.name),
          ...data.entries
            .filter((e) => e.name === "skill")
            .map((e) => e.args.name)
            .filter(Boolean),
        ]),
      ];
      const name = names.includes(skillName) ? skillName : names[0];
      const source = sources.skills.find((s) => s.name === name);
      const file =
        source?.files.find((f) => f.path === skillFile) || source?.files[0];
      const reads = data.entries.filter(
        (e) => e.name === "skill" && e.args.name === name,
      );
      const injections = data.contexts.filter(
        (n) => n.source?.kind === "skill-invocation" && n.source.name === name,
      );
      return h(
        "div",
        { className: "tr-board" },
        h(
          "div",
          { className: "tr-toolbar" },
          h("h3", null, "技能组成与读取证据"),
          requestPicker(),
        ),
        note(
          "可发现目录取所选请求之前最近的记录；读取记录展示会话全部已加载调用，不表示该请求之前已经读入。文件组成来自当前构建包，保留状态与规则遵守分别判断。",
        ),
        h(
          "div",
          { className: "tr-split tr-inspector" },
          h(
            "div",
            { className: "tr-list" },
            names.map((n) =>
              h(
                "button",
                {
                  type: "button",
                  className: "tr-row",
                  key: n,
                  "data-kind": "skill",
                  "aria-pressed": n === name,
                  onClick: () => {
                    setSkill(n);
                    setSkillFile("SKILL.md");
                  },
                },
                n,
                h(
                  "span",
                  { className: "tr-meta" },
                  observed.some((s) => s.name === n)
                    ? "最近目录可发现"
                    : latest
                      ? "不在最近目录中"
                      : "运行目录未采集",
                ),
                h(
                  "span",
                  { className: "tr-meta" },
                  data.entries.some(
                    (e) =>
                      e.name === "skill" &&
                      e.args.name === n &&
                      !e.failed &&
                      !e.pending,
                  )
                    ? "会话中正文已返回"
                    : "未见成功读取",
                ),
              ),
            ),
          ),
          name
            ? h(
                "article",
                { className: "tr-detail" },
                h("h3", null, name),
                prose(
                  observed.find((s) => s.name === name)?.description ||
                    source?.description ||
                    "",
                ),
                h("h4", null, "正文读取记录 · 会话全部已加载调用"),
                !reads.length && !injections.length
                  ? note("未见读取；记录可能不完整，不断言未使用。")
                  : null,
                h("div", { className: "tr-buttons" }, reads.map(openCallLink)),
                injections.map((n) =>
                  h(
                    "details",
                    { key: n.seq },
                    h("summary", null, "用户调用注入 · 事件 " + n.seq),
                    prose(text(n.content)),
                  ),
                ),
                reads
                  .filter((e) => !e.failed && !e.pending)
                  .map((e) =>
                    h(
                      "details",
                      { key: e.id },
                      h("summary", null, "当时返回正文 · 调用 #" + e.index),
                      prose(e.text),
                    ),
                  ),
                note(
                  "当前上下文保留状态未采集；读取证据不证明规则已全部遵守。",
                ),
                h("h4", null, "参考资源读取"),
                data.resourceReads
                  .filter((r) => r.name === name)
                  .map((r) =>
                    h(
                      "div",
                      { key: r.entry.id },
                      openCallLink(r.entry),
                      h(
                        "span",
                        { className: "tr-meta" },
                        r.path + " · 资源目录与路径匹配；版本未采集",
                      ),
                    ),
                  ),
                h("h4", null, "当前包资源组成"),
                source
                  ? h(
                      "div",
                      null,
                      h(
                        "div",
                        { className: "tr-buttons" },
                        source.files.map((f) =>
                          button(
                            f.path,
                            () => setSkillFile(f.path),
                            file?.path === f.path,
                          ),
                        ),
                      ),
                      file
                        ? h(
                            "section",
                            null,
                            h("h4", null, file.path),
                            h(
                              "div",
                              { className: "tr-meta" },
                              file.bytes +
                                " bytes · hash " +
                                file.hash.slice(0, 16),
                            ),
                            note(
                              "来源文件：" + source.base + "/" + file.path + "。正文在会话读取记录中查看。",
                            ),
                          )
                        : null,
                    )
                  : note("此技能不是随包资源，文件清单未采集。"),
              )
            : empty("暂无技能资料。"),
        ),
      );
    }
    function analysis() {
      const stats = data.statistics;
      const adoption = stats.adoption;
      const requestUsage = stats.requestUsage;
      const metrics = [
        ["Houdini 已返回调用（排除历史回读）", adoption.houdiniCalls],
        ["Host 历史结果 / 来源回读", adoption.hostResultDetailReads],
        [
          "调用含动词",
          adoption.callsWithVerbs + " / " + adoption.houdiniCalls,
        ],
        [
          "成功 exec 含动词 · " +
            (adoption.successfulExecVerbCoveragePct ?? '—') +
            "%",
          adoption.successfulExecWithVerbs + " / " + adoption.successfulExecCalls,
        ],
        [
          "无动词只读 query（守卫范围）", adoption.rawReadOnlyCalls,
        ],
        ["无动词疑似副作用 / 外部操作", adoption.rawSuspectedEffectCalls],
        ["无动词副作用未知", adoption.rawUnknownEffectCalls],
        ["无动词失败（未证明只读）", adoption.rawFailedCalls],
        ["Raw Gate 拦截", stats.gateBlockedCalls],
        ["回滚调用", stats.rolledBackCalls],
        [
          "目录广度（当前包）",
          stats.usedVerbCount + " / " + stats.knownVerbCount,
        ],
        [
          "动词密度（每次Houdini调用）",
          adoption.verbDensity,
        ],
        [
          "回滚动作工作量",
          stats.rolledBackVerbCalls,
        ],
      ];
      return h(
        "div",
        { className: "tr-board" },
        h("h3", null, "执行分析 · 当前加载记录"),
        h(
          "div",
          { className: "tr-metrics" },
          metrics.map(([label, value]) =>
            h(
              "div",
              { key: label },
              h("small", null, label),
              h("strong", null, String(value)),
            ),
          ),
        ),
        note(
          "含动词率描述调用形态，成功 exec 包含验证和动态函数，不代表修改采用率或任务完成度。Gate read_only 是静态扫描结果；no_scene_change 不排除文件或 Python 全局副作用。",
        ),
        h("h4", null, "模型请求 usage · 请求去重"),
        requestUsage.reported
          ? table(
              ["已报告 / 已加载请求", "输入合计", "输出合计"],
              [
                [
                  requestUsage.reported + " / " + requestUsage.total,
                  format(requestUsage.input),
                  format(requestUsage.output),
                ],
              ],
            )
          : note("请求 usage 未采集。"),
        note(
          "包含已加载的 assistant / compaction 请求；缺失 usage 不按0补齐。输入合并 DSH 的未缓存和缓存分桶。",
        ),
        h("h4", null, "失败、拦截与回滚"),
        stats.failures
          .map((e) =>
            h(
              "div",
              { key: e.id, className: "tr-row" },
              openCallLink(e),
              " ",
              tag(e.state, true),
              h("div", { className: "tr-meta" }, e.errorText || e.statusText),
            ),
          ),
        h("h4", null, "无动词调用的副作用证据"),
        table(
          ["分类", "调用数"],
          [
            "read_only_query",
            "gate_blocked",
            "suspected_effect",
            "mutation_candidate",
            "unknown",
            "failed",
          ].map((mode) => [
            mode,
            String(stats.rawEffectCounts.get(mode) || 0),
          ]),
        ),
        note(
          "历史回读不计新执行。unknown 包含动态 exec；疑似外部副作用与裸修改候选不证明实际发生，失败也不证明没有副作用。原始 Gate 回包在调用详情保留。",
        ),
      );
    }
    return h(
      "section",
      { className: "dsh-trace" },
      h("style", null, css),
      h(
        "header",
        null,
        h("h2", null, "H / Houdini Trace"),
        h("small", null, "执行记录与能力来源"),
      ),
      h(
        "nav",
        { "aria-label": "Trace 看板" },
        [
          ["timeline", "执行过程"],
          ["prompt", "提示词与上下文"],
          ["tools", "工具"],
          ["skills", "技能"],
          ["analysis", "分析"],
        ].map(([k, s]) => button(s, () => setTab(k), tab === k)),
      ),
      h(
        "div",
        { className: "tr-status" },
        data.pendingCount
          ? "快照中 " + data.pendingCount + " 个调用执行中"
          : data.partial
            ? "模型正在输出（最后快照）"
            : "已加载 " +
              data.entries.length +
              " 个调用；当前运行状态以 Host 为准",
        " · 最近记录 " + stamp(data.recent || null),
      ),
      h(
        "main",
        {
          className:
            "tr-content" + (tab === "timeline" ? " tr-content-timeline" : ""),
        },
        { timeline, prompt, tools, skills, analysis }[tab](),
      ),
    );
  }
  View.model = model;
  View.usage = usage;
  View.systemSections = systemSections;
  return View;
});
      var createRuntime = (// Trace is materialized only when its conversation view opens. DSH ships one
// package client bundle; this factory owns its diagnostic parser and view.
function createTraceRuntime(React, catalog, sources, css, createModel, createView, analysis, readHoudiniCanonical) {
  "use strict";
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

  // Host 输出由空行分隔，每个区块有稳定标题。按标题边界切分，避免 stdout
  // 自己包含空行时把后续 rollback/raw-usage/verbs 吞进一个大文本块。
  function parseResultSections(text) {
    var marker = /(?:^|\n\n)(stdout|stderr|__result__|rollback|transaction|operation-evidence|control-test-summary \(not_run is not pass\)|CHECKS NEED ATTENTION \(execution success is not validation success\)|raw-usage|image-attachments|artifact-candidates \(not delivered; verify requested final files, then call present\)|hint|verbs \(\d+\)|media(?: [^\n:]*)?):\n/g;
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

  function cleanStdout(text) {
    return String(text || "").split("\n").filter(function (line) {
      return line.indexOf("[verb]") !== 0;
    }).join("\n").trim();
  }

  // 把一个 tool-result 节点拆成可展示的执行证据。新 trace 优先读取 Bridge
  // AST 生成的 rawUsage；旧 trace 只把源码正则结果称作“直接 HOM”，不再冒充
  // mutation 或安全结论。
  function parseEntry(node) {
    var call = node.call || {};
    var args = {};
    try { args = JSON.parse(call.argsRaw || "{}"); } catch (_error) { /* 非 JSON */ }
    if (args === null || typeof args !== "object" || Array.isArray(args)) args = {};
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
    var failed = node.isError === true || status.indexOf("Execution failed") === 0 || status.indexOf("Job failed") === 0;
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
      imageAttachments: sections["image-attachments"] || null,
      rollback: rollback,
      rawUsage: rawUsage,
      failed: failed,
      statusText: status,
      errorText: failed ? status.replace(/^Execution failed:\s*/i, "").replace(/^Job failed:\s*/i, "") : null,
      text: text,
      parts: sections,
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
    var canonical = readHoudiniCanonical(node);
    info.canonical = canonical;
    if (info.name.indexOf("houdini_") === 0 && canonical && typeof canonical.ok === "boolean") {
      info.resultValue = canonical.result;
      info.resultText = canonical.result === undefined ? null : JSON.stringify(canonical.result, null, 2);
      info.rollback = canonical.rollback || null;
      info.rawUsage = canonical.rawUsage || info.rawUsage;
      info.stdout = cleanStdout(canonical.stdout);
      info.stderr = canonical.stderr || null;
      info.failed = info.failed || (canonical.status ? canonical.status === "failed" : canonical.ok === false);
      if (canonical.error) info.errorText = canonical.error;
      if (Array.isArray(canonical.verbs)) info.verbs = canonical.verbs.map(function (v) {
        return {verb:v.verb,ok:v.ok,argsText:(JSON.stringify(v.args) || "") +
          (v.kwargs && Object.keys(v.kwargs).length ? ", " + JSON.stringify(v.kwargs) : ""),
          // Failed ledger entries have error/summary but no result. Preserve
          // absence separately from explicit null/false/0; never hide errors.
          detail:JSON.stringify(v.result) ?? null,
          error:v.error ?? null,summary:v.summary ?? null,ms:v.ms};
      });
    }
    info.exemptionReason = typeof args.allow_raw === "string" && args.allow_raw
      ? args.allow_raw
      : (info.rawUsage && info.rawUsage.exemptionReason) || null;
    return info;
  }
  const trace = createModel(catalog, sources, parseEntry, analysis);
  return createView(React, catalog, sources, trace, css);
});
      traceView = createRuntime(React, getTraceCatalog(), sources, css, createModel, createView, analysis, readHoudiniCanonical);
      return traceView;
    }
    // <<< houdini-trace

    function installLaunchSessionHint(ctx) {
      if (typeof ctx.inject !== "function") return;
      var keys = ["dsh-houdini-workspace", "dsh-houdini-session", "dsh-houdini-request"];
      var serviceScope = null, current = null, waitingNotice = null;
      function intent() {
        var url = new URL(window.location.href);
        var workspacePath = url.searchParams.get(keys[0]);
        var sessionId = url.searchParams.get(keys[1]);
        if (!workspacePath && !sessionId) return null;
        var requestId = url.searchParams.get(keys[2]);
        if (!requestId) {
          requestId = "dsh-houdini-" + window.crypto.randomUUID();
          url.searchParams.set(keys[2], requestId);
          window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
        }
        return { workspacePath: workspacePath, sessionId: sessionId, requestId: requestId };
      }
      function matches(target) {
        var latest = intent();
        return latest && latest.requestId === target.requestId && latest.workspacePath === target.workspacePath && latest.sessionId === target.sessionId;
      }
      function consume(target) {
        if (!matches(target)) return;
        var url = new URL(window.location.href);
        keys.forEach(function (key) { url.searchParams.delete(key); });
        window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
      }
      function notice() {
        var node = document.createElement("div");
        node.id = "dsh-houdini-navigation";
        node.style.cssText = "position:fixed;right:16px;top:16px;z-index:2147483647;max-width:min(480px,calc(100vw - 32px));box-sizing:border-box;overflow-wrap:anywhere;padding:12px 16px;border:1px solid #555;border-left:3px solid #ff8a2a;border-radius:8px;background:#23262b;color:#eef0f2;font:13px/1.5 'Segoe UI',sans-serif;box-shadow:0 4px 20px #0005";
        node.setAttribute("role", "status");
        document.body.appendChild(node);
        return node;
      }
      function requested() {
        var target = intent();
        if (current) { current.stop("superseded"); current = null; }
        if (waitingNotice) { waitingNotice.remove(); waitingNotice = null; }
        if (!target) return;
        if (!serviceScope) {
          waitingNotice = notice();
          waitingNotice.textContent = "正在等待 DSH 工作区导航服务…";
          return;
        }
        current = navigateIntent(serviceScope, target);
      }
      // Qt also issues new intents into an already loaded page. No reload is
      // required, and neither the requested directory nor ordinary input is
      // evidence that DSH selected or abandoned a workspace.
      window.addEventListener("dsh-houdini-open-workspace", requested);
      requested();
      ctx.inject(["sessions", "workspaces", "remote", "remote.session", "uiSession", "uiWorkspace", "layout"], function (scope) {
        scope.effect(function () {
          serviceScope = scope;
          var sessions = scope.get("sessions"), uiSession = scope.get("uiSession");
          var readSelection = function () {
            var binding = uiSession.adapter.current.getSnapshot();
            var row = binding && sessions.list.getSnapshot().byId[binding.key];
            return row ? { sessionId: row.id, cwd: row.cwd, agentPreset: row.projectionValues && row.projectionValues.agentPreset } : null;
          };
          // Read-only access to the actual DSH selection, no second registry.
          window.__dshHoudiniSelection = readSelection;
          requested();
          return function () {
            serviceScope = null;
            if (current) { current.stop("scope-disposed"); current = null; }
            if (window.__dshHoudiniSelection === readSelection) delete window.__dshHoudiniSelection;
            if (waitingNotice) waitingNotice.remove();
          };
        }, "dsh-houdini:workspace-navigation");
      });
      ctx.effect(function () { return function () {
        window.removeEventListener("dsh-houdini-open-workspace", requested);
        if (current) current.stop("scope-disposed");
        if (waitingNotice) waitingNotice.remove();
      }; });

      function navigateIntent(scope, target) {
        var sessions = scope.get("sessions"), workspaces = scope.get("workspaces");
        var remote = scope.get("remote"), uiSession = scope.get("uiSession");
        var uiWorkspace = scope.get("uiWorkspace"), layout = scope.get("layout");
        var node = notice(), controller = null, running = false, stopped = false, detachNavigation = function () {};
        function stop(reason) {
          stopped = true;
          detachNavigation();
          if (controller) controller.abort(reason);
          node.remove();
          if (reason === "user-navigation") consume(target);
        }
        function active(attempt) {
          if (stopped || controller !== attempt || attempt.signal.aborted) return false;
          if (!matches(target)) { stop("superseded"); return false; }
          return true;
        }
        function fail(error, attempt) {
          if (stopped || controller !== attempt) return;
          node.setAttribute("role", "alert");
          node.textContent = "Houdini 工作区未打开：" + (error.message || String(error)) + " ";
          var retry = document.createElement("button");
          retry.type = "button";
          retry.textContent = "重试打开工作区";
          retry.onclick = start;
          node.appendChild(retry);
        }
        function snapshotWhen(read, attempt) {
          return new Promise(function (resolve, reject) {
            var subscriptions = [], finished = false, signal = attempt.signal;
            function settle(error, value) {
              if (finished) return;
              finished = true;
              subscriptions.forEach(function (dispose) { dispose(); });
              signal.removeEventListener("abort", aborted);
              if (error) reject(error); else resolve(value);
            }
            function aborted() { settle(new Error("Houdini navigation was superseded")); }
            function check() {
              if (!active(attempt)) { aborted(); return; }
              try {
                var w = workspaces.list.getSnapshot(), s = sessions.list.getSnapshot();
                if (w.state === "error") throw new Error(w.error.message);
                if (w.phase !== "ready" || w.state !== "idle" || s.phase !== "ready") return;
                var value = read(w, s);
                if (value !== undefined) settle(null, value);
              } catch (error) { settle(error); }
            }
            subscriptions.push(workspaces.list.subscribe(check), sessions.list.subscribe(check), uiSession.adapter.current.subscribe(check));
            signal.addEventListener("abort", aborted, { once: true });
            check();
          });
        }
        function pathKey(path) { return String(path || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase(); }
        function eligible(row, workspace, archived) {
          return row && row.origin !== "subagent" && workspace.sessionIds.includes(row.id) && !archived.includes(row.id) &&
            pathKey(row.cwd) === pathKey(workspace.path) && row.projectionValues && row.projectionValues.agentPreset === "houdini";
        }
        async function navigate(attempt, refresh) {
          var sessionId = target.sessionId;
          var workspace = target.workspacePath ? await workspaces.create({ path: target.workspacePath }) : null;
          if (!active(attempt)) return;
          if (refresh) await sessions.refresh();
          var snapshot = await snapshotWhen(function (w, s) {
            var found = workspace && w.items.find(function (item) { return item.workspaceId === workspace.workspaceId; });
            if (found && found.sessionIds.some(function (id) { return !w.archivedSessionIds.includes(id) && !s.byId[id]; })) return;
            return { workspaces: w, sessions: s };
          }, attempt);
          if (!active(attempt)) return;
          var w = snapshot.workspaces, s = snapshot.sessions;
          if (!workspace) {
            if (!s.byId[sessionId] || w.archivedSessionIds.includes(sessionId)) throw new Error("指定任务不存在或已归档。");
            if (s.byId[sessionId].projectionValues.agentPreset !== "houdini") throw new Error("指定任务没有使用 Houdini preset。");
          } else {
            workspace = w.items.find(function (item) { return item.workspaceId === workspace.workspaceId; });
            if (!workspace) throw new Error("工作区已被移除。");
            var binding = uiSession.adapter.current.getSnapshot();
            var currentRow = binding && s.byId[binding.key];
            var choices = s.ids.map(function (id) { return s.byId[id]; }).filter(function (row) { return eligible(row, workspace, w.archivedSessionIds); });
            choices.sort(function (a, b) { return b.updatedAt - a.updatedAt; });
            var selected = eligible(currentRow, workspace, w.archivedSessionIds) ? currentRow : choices[0];
            sessionId = selected && selected.id;
            if (!sessionId) {
              node.textContent = "正在创建 Houdini 任务…";
              var created = await remote.session.create({ workspaceId: workspace.workspaceId, sessionId: target.requestId, agentPreset: "houdini" });
              if (!active(attempt)) return;
              if (!created.ok) throw new Error(created.error.message);
              if (created.value.sessionId !== target.requestId ||
                  (created.value.agentPreset !== undefined && created.value.agentPreset !== "houdini")) throw new Error("DSH 没有创建请求的 Houdini 任务。");
              await sessions.refresh();
              sessionId = await snapshotWhen(function (latestW, latestS) {
                var latest = latestW.items.find(function (item) { return item.workspaceId === workspace.workspaceId; });
                if (!latest || latestW.archivedSessionIds.includes(target.requestId)) throw new Error("新任务或工作区已被移除/归档。");
                var row = latestS.byId[target.requestId];
                var preset = row && row.projectionValues && row.projectionValues.agentPreset;
                if (preset !== undefined && preset !== "houdini") throw new Error("新任务没有激活 Houdini preset。");
                return eligible(row, latest, latestW.archivedSessionIds) ? target.requestId : undefined;
              }, attempt);
            }
          }
          if (!active(attempt)) return;
          // openSession reveals Conversation and aborts layout's pending signal.
          // Its own commit is not a competing user navigation.
          detachNavigation();
          uiWorkspace.openSession(sessionId);
          var actual = uiSession.adapter.current.getSnapshot();
          var latestS = sessions.list.getSnapshot(), latestW = workspaces.list.getSnapshot();
          if (!actual || actual.key !== sessionId) throw new Error("DSH 未选中请求的任务。");
          var row = latestS.byId[actual.key];
          if (!row || row.projectionValues.agentPreset !== "houdini") throw new Error("选中的任务未激活 Houdini preset。");
          var confirmedWorkspace = workspace && latestW.items.find(function (item) { return item.workspaceId === workspace.workspaceId; });
          if (workspace && (!confirmedWorkspace || !eligible(row, confirmedWorkspace, latestW.archivedSessionIds) || pathKey(row.cwd) !== pathKey(target.workspacePath))) throw new Error("DSH 当前任务的工作目录与请求的 HIP 目录不一致。");
          if (!active(attempt)) return;
          consume(target);
          stop("complete");
        }
        function start() {
          if (stopped || running) return;
          if (!matches(target)) { stop("superseded"); return; }
          detachNavigation();
          var refresh = controller !== null, attempt = new AbortController();
          controller = attempt; running = true;
          var signal = layout.beginNavigation();
          var superseded = function () { stop("user-navigation"); };
          signal.addEventListener("abort", superseded, { once: true });
          detachNavigation = function () { signal.removeEventListener("abort", superseded); };
          node.setAttribute("role", "status");
          node.textContent = "正在打开 Houdini 工作区…";
          var timeout = setTimeout(function () {
            if (!active(attempt)) return;
            attempt.abort("timeout"); running = false;
            fail(new Error("DSH 导航状态未就绪，请检查连接后重试。"), attempt);
          }, 30000);
          attempt.signal.addEventListener("abort", function () { clearTimeout(timeout); }, { once: true });
          navigate(attempt, refresh).catch(function (error) {
            if (active(attempt)) fail(error, attempt);
          }).finally(function () { clearTimeout(timeout); if (controller === attempt) running = false; });
        }
        start();
        return { stop: stop };
      }
    }

    // --- shared executor picker (handwritten; no direct Bridge/browser requests) ---
    function createExecutorPicker(connection) {
      var buttonStyle = { font: "inherit", fontSize: 12, padding: "6px 10px", border: "1px solid #c8cdd3",
        borderRadius: 6, background: "transparent", color: "inherit", cursor: "pointer", minHeight: 32, maxWidth: "100%" };
      return function ExecutorPicker(props) {
        var preset = props.useSessions(function (s) {
          var row = s && s.byId && s.byId[props.sessionId];
          return row && row.projectionValues && row.projectionValues.agentPreset || "";
        });
        var state = React.useState({ open: false, busy: false, rows: [], message: "" });
        var value = state[0], set = state[1];
        var pending = React.useRef(null), generation = React.useRef(0), current = React.useRef(props.sessionId);
        current.current = props.sessionId;
        React.useEffect(function () {
          generation.current++;
          if (pending.current) pending.current.abort();
          set({ open: false, busy: false, rows: [], message: "" });
          return function () { generation.current++; if (pending.current) pending.current.abort(); };
        }, [props.sessionId]);
        if (preset !== "houdini") return null;
        async function request(method, input) {
          var task = props.sessionId, ticket = ++generation.current;
          if (pending.current) pending.current.abort();
          var controller = new AbortController(); pending.current = controller;
          var timeout = setTimeout(function () { controller.abort(); }, 10000);
          set(function (old) { return Object.assign({}, old, { open: true, busy: true, message: "正在核对执行端…" }); });
          try {
            var response = await connection.rpc.call("/api", "houdiniTargets/" + method,
              { args: input ? { input: input } : {} }, controller.signal);
            if (current.current !== task || generation.current !== ticket) return;
            if (!response.ok) throw new Error(response.error && response.error.message || "共享执行端服务不可用");
            if (method === "list") {
              var rows = response.value && response.value.candidates;
              if (!Array.isArray(rows)) throw new Error("执行端列表格式无效");
              var recovery = response.value && response.value.recovery;
              var inventory = rows.length ? "登记不代表在线；绑定时会核对当前 HIP 和执行端身份。" : "没有已登记的 Houdini。请先在对应 Houdini 注册共享执行端。";
              set({ open: true, busy: false, rows: rows,
                message: (recovery && recovery.message ? recovery.message + " " : "") + inventory });
            } else {
              set(function (old) { return Object.assign({}, old, { busy: false,
                message: "本任务已绑定所选 Houdini。未加载、保存或验证工程内容。" }); });
            }
          } catch (error) {
            if (current.current === task && generation.current === ticket) set(function (old) {
              return Object.assign({}, old, { busy: false, message: "未完成绑定：" + String(error.message || error) + "。若共享服务未启用，请勿重启正在工作的实例。" });
            });
          } finally { clearTimeout(timeout); }
        }
        function choose(row) {
          if (value.busy || current.current !== props.sessionId) return;
          request("select", { sessionId: props.sessionId, executorId: row.executor_id,
            registrationId: row.registration_id, expectedHip: row.hip_path });
        }
        return React.createElement("section", { "aria-label": "Houdini 执行端", style: { width: "calc(100% - 32px)", margin: "0 auto", fontFamily: "system-ui, Microsoft YaHei, sans-serif", fontSize: 13, lineHeight: 1.5 } },
          React.createElement("button", { type: "button", style: buttonStyle, disabled: value.busy, "aria-expanded": value.open,
            onClick: function () { if (value.open) set(Object.assign({}, value, { open: false })); else request("list", { sessionId: props.sessionId }); } }, "Houdini 执行端"),
          value.open && React.createElement("div", { style: { padding: "10px 0", borderTop: "1px solid #c8cdd3", marginTop: 8 } },
            React.createElement("p", { role: "status", style: { margin: "0 0 8px", fontSize: 12 } }, value.message),
            React.createElement("div", { style: { maxHeight: 260, overflowY: "auto" } }, value.rows.map(function (row) {
              var other = row.task_id && row.task_id !== props.sessionId;
              var bound = row.task_id === props.sessionId && row.binding_status === "bound";
              var disabled = value.busy || other || bound || row.state !== "registered" || !row.hip_path;
              return React.createElement("div", { key: row.executor_id, style: { display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", padding: "8px 0" } },
                React.createElement("div", { style: { minWidth: 0, flex: 1 } },
                  React.createElement("strong", null, "Houdini " + row.houdini_version),
                  React.createElement("div", { style: { fontFamily: "Consolas, monospace", fontSize: 12, overflowWrap: "anywhere" } }, row.hip_path || "未保存的工程"),
                  React.createElement("small", null, row.state === "disconnected" ? "已断开" : other ? "其他任务已预留" : bound ? "本任务已绑定" : "待握手核验")),
                React.createElement("button", { type: "button", style: buttonStyle, disabled: !!disabled, onClick: function () { choose(row); } }, bound ? "已绑定" : "选择并绑定"));
            })),
            React.createElement("button", { type: "button", style: buttonStyle, disabled: value.busy, onClick: function () { request("list", { sessionId: props.sessionId }); } }, "刷新执行端")));
      };
    }

    function HoudiniTrace(props) {
      return React.createElement(getTraceView(React), props);
    }

    function HoudiniTools() {
      var h = React.createElement;
      return h("section", { "aria-label": "Houdini 工具说明", style: { padding: "24px", maxWidth: 1000, margin: "0 auto", fontFamily: "system-ui, Microsoft YaHei, sans-serif", lineHeight: 1.6 } },
        h("h2", null, "Houdini 工具"),
        h("p", null, "模型通过这些工具观察现场、组织批量操作、读取完整反馈和管理长任务。具体建模方法由模型按任务选择，领域知识按需读取。"),
        Object.entries(houdiniToolCatalog).map(function (entry) {
          var name = entry[0], tool = entry[1];
          return h("article", { key: name, style: { padding: "16px 0", borderTop: "1px solid #8884" } },
            h("h3", { style: { margin: "0 0 8px" } }, tool.label, " · ", h("code", { style: { fontSize: ".85em" } }, name)),
            h("p", { style: { margin: "0 0 10px" } }, tool.purpose),
            h("dl", { style: { display: "grid", gridTemplateColumns: "70px 1fr", gap: "6px 12px", margin: 0 } },
              h("dt", null, "输入"), h("dd", { style: { margin: 0 } }, tool.input),
              h("dt", null, "输出"), h("dd", { style: { margin: 0 } }, tool.output),
              h("dt", null, "执行位置"), h("dd", { style: { margin: 0 } }, tool.execution)));
        }));
    }

    function apply(ctx) {
      installLaunchSessionHint(ctx);
      var slots = ctx.get("slots");
      if (slots === undefined) return;
      if (typeof ctx.inject === "function") ctx.inject(["connection"], function (scope) {
        slots.inject("conversation.input.dock", function () {
          return slots.register({ name: "conversation.input.dock", id: "houdini-executor-picker", order: 98 },
            createExecutorPicker(scope.get("connection")));
        });
      });

      slots.inject("conversation.view", function () {
        slots.register(
          { name: "conversation.view", id: "houdinitools", order: 4, label: "Houdini 工具" },
          HoudiniTools
        );
        return slots.register(
          { name: "conversation.view", id: "houdinitrace", order: 5, label: "Houdini Trace" },
          HoudiniTrace
        );
      });

      slots.inject("conversation.composer.dock", function () {
        return slots.register(
          { name: "conversation.composer.dock", id: "houdini-workspace-status", order: 98 },
          HoudiniWorkspaceStatus
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
