// dsh-houdini client half — registers three things:
//  1. Houdini Trace: five boards over public trajectory requests/calls.
//     Handwritten renderer: client/trace-view.js; build includes source inventory.
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
        return typeof projected === "string" ? projected : sess && typeof sess.agentPreset === "string" ? sess.agentPreset : "";
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
    var CATALOG = [{"domain":"vocabulary 域","note":"vocabulary 域（回答「动词怎么调用」）","verbs":[{"name":"verb_help","sig":"name","desc":"返回已注入动词的准确 signature、return_type（无注解则null）、call_mode与docstring；未知名列相似项。Bridge对签名绑定错误返回真实signature和零写入证据，实施内部TypeError不冒充绑定失败。用于在调用前发现契约，不靠失败或读取仓库源码猜参数/返回形状","returns":"dict"}]},{"domain":"类型目录","note":"类型目录（回答「能建什么」）","verbs":[{"name":"search_tab_menu","sig":"category, query","desc":"列出某 context 下匹配的节点族 + 最新版","returns":"dict"},{"name":"search_tab_entries","sig":"parent, query","desc":"按真实父网络列当前可见的 node/tool entry；排除 hidden/deprecated，Material Library 根层只暴露 Builder tool；每项标 `kind` 与 dsh 是否可安全执行","returns":"dict"},{"name":"resolve_latest_type","sig":"category, base","desc":"某族最新版全名（内部为主）；只以 namespace 注册的族返回带前缀全名（'rigdoctor' → 'kinefx::rigdoctor'），裸别名过不了 `createNode(exact_type_name=True)`；跨 namespace 同名按排序取第一个，recipe 需跨版本一致时应显式钉命名空间","returns":"str"}]},{"domain":"node 域","note":"node 域（场景图）","verbs":[{"name":"tab_create","sig":"parent, type_name, name=, inputs=[...]","desc":"建**单个可见节点**：最新版 + 对应 shelf 初始化；初始化失败会清理 partial create 并向外抛错，绝不静默降级成裸节点；拒绝 hidden/deprecated 和 Material Library 根层直建 shader，setup/builder 改用 tab_apply；parent 接受 Node/path。连完 inputs 后自动落位：有输入时放到所有输入下游（x = 输入 x 均值，y = min(输入 y) − 垂直间距）；无输入时放到父网络现有内容右侧新列（x = max(现有 x) + 水平间距，y = 现有最顶部 y，空网络落原点）；间距由节点实际网络尺寸（`Node.size()`）推导，不用拍脑袋常量","returns":"`hou.Node`"},{"name":"tab_apply","sig":"parent, tool_id","desc":"应用 allowlist 内的非交互 Tab setup recipe，返回全部新增节点/输入；GUI 恢复 Network Editor pwd/selection，同一 exec 多次调用共享用户基线；headless 同语义。首批仅 Karma Setup / Karma Material Builder。SideFX recipe 自己摆节点，tab_apply 不做自动落位","returns":"dict"},{"name":"find_nodes","sig":"pattern=\"*\", category=None, node_type=None, root=None","desc":"找**已存在**节点（扁平清单）","returns":"path 列表"},{"name":"graph","sig":"node, depth=1, direction='both'","desc":"围绕**该数据节点**查 inputs / outputs / parm_refs；检查最终 SOP 网络应对 `OUT` 向上查，不要对父 OBJ 容器调用","returns":"dict"},{"name":"describe","sig":"node","desc":"状态 + 几何摘要 + `attrib_delta`（相对 input 0 的属性增删——MMB 节点信息里「这个节点对数据干了什么」的固化）+ 帮助元数据","returns":"dict"},{"name":"node_provenance","sig":"node","desc":"报告 runtime owner、可复制的 audit tag、当前 session 是否可写；`foreign`/`owned_current_session`/`owned_other_session`/`dsh_service` 分开","returns":"dict"},{"name":"connect","sig":"src, dst, index=0, *, allow_foreign=None","desc":"严格数据流连线（src 输出 → dst 指定输入）；只有一个端口参数index，第4位置参数拒绝；权限理由必须显式keyword非空字符串。mutation 边界在 dst；**OBJ→OBJ 拒绝**，改用 `set_object_parent`。端口错误不再改接下一个输入；连接后仅在 dst 违反自顶向下流时调整落位","returns":"dict"},{"name":"node_info","sig":"parent, type_name, parm_filter='', limit=24","desc":"创建前读取实际parent最新版类型、端口、参数默认值/组件名/menu token/set_value与帮助URL；operation_card含决策/版本，operation_parameters保留不受filter/limit裁切的关键设置，缺字段显式报告。不建临时节点/不运行Shelf；动态菜单需list_parms，truncated明示。没有delivery准入","returns":"dict"},{"name":"build_module","sig":"parent, nodes, output, dry_run=False, interfaces=None, *, required_outputs=None","desc":"新增1..64个{name,type,parms?,inputs?} SOP节点，inputs为更早spec/现有child名，None跳输入。独立静态错误汇总零创建拒绝。operation_advisories按类型/缺少显式决策合并，非阻断、不改默认值、不证明语义；dry_run用于未决设置。required_outputs可检查1..16必需新分支，可附实际interfaces。返回validation/interface_checks；失败清理新节点，不覆盖已有节点/flags","returns":"dict"},{"name":"verify_network","sig":"parent, output=None, nodes=None, limit=512, require_valid=True","desc":"SOP checkpoint：必须显式 output，省略即报可操作错误，绝不跟随 display。默认检查 parent 直属范围，可 nodes 限域；error/空输出默认抛 CheckpointError 并保留结构证据，require_valid=False 仅供诊断。warning独立，scope/时间/frame/输出指纹与失败原因前置；不证明关系/视觉","returns":"dict"},{"name":"set_object_parent","sig":"child, parent, keep_world=True, reason='', index=0, allow_foreign=None","desc":"显式 OBJ parenting/unparent（`parent=None`），自然参数序为 child→parent；普通父级用 input 0，Blend 等明确多输入对象可指定 index。`reason` 限 `scene_assembly/camera_light_null/existing_legacy/explicit_user/downstream_obj_delivery`，新建几何 FK 不属例外。拒绝非 OBJ、自环/层级环；mutation/ownership 边界在 child；默认恢复 child 原世界变换并回读 parent、local/world delta","returns":"dict"},{"name":"disconnect_input","sig":"dst, index=0, *, allow_foreign=None","desc":"断开普通网络 destination 输入；权限理由keyword-only非空字符串；OBJ unparent 拒绝并指向 `set_object_parent(child,None,...)`；ownership 边界在 dst，返回原 source path（若本来为空则为 null）","returns":"dict"},{"name":"rename_node","sig":"node, name, allow_foreign=None","desc":"重命名","returns":"新 path"},{"name":"delete_node","sig":"node, allow_foreign=None","desc":"删除（返回被表达式引用的上游）；拒绝删除 owner-tagged `render_view` 会话级基础设施，避免进入 H21 OpenGL teardown fatal 路径","returns":"dict"},{"name":"cook_node","sig":"node, force=False","desc":"cook + error/warning；另给 `ok/warning_free/healthy`，warning 未解释不得当完成","returns":"dict"},{"name":"sop_set_output","sig":"node, render=True, allow_foreign=None","desc":"把 SOP singular display/render 旗标移到输出节点；属于用户 viewport/交付状态，不是 render_view 前置条件","returns":"dict"},{"name":"sop_output_node","sig":"parent","desc":"报告 SOP 网络 display/render 输出；旗标不在链尾时提醒","returns":"dict"},{"name":"set_object_visible","sig":"node, visible=True, allow_foreign=None","desc":"设置单个 OBJ 的 viewport visibility（OBJ 没有 SOP 式 render flag）","returns":"dict"},{"name":"visible_objects","sig":"root='/obj'","desc":"列出 OBJ 层 plural visibility/effective visibility，并附每个对象的 provenance","returns":"dict"},{"name":"layout_nodes","sig":"parent, nodes=None, horizontal_spacing=-1, vertical_spacing=-1, allow_foreign=None, mode='children'","desc":"`mode='children'`（默认）= 原生 layoutChildren，行为不变；`mode='flow'` = 自研拓扑分层：按最长路径深度分行（深度 0 最上，y = −depth × 垂直间距），同深度按节点当前 x 排序保持左右阅读顺序、等距排开并整体居中，有环时按原顺序兜底不断裂；spacing 默认从节点实际尺寸推导，显式正值覆盖。host task 中 `nodes=None` 只布局当前 session 创建项并回报 `foreign_nodes_skipped`；显式列表逐项过 ownership guard。Python Shell 无 host owner 时保持传统全布局语义","returns":"dict"}]},{"domain":"compatibility 域","note":"compatibility 域（仅历史回放，不进新 guidance）","verbs":[{"name":"set_display","sig":"node, render=True, allow_foreign=None","desc":"deprecated 兼容 wrapper：按节点 context 路由 SOP output / OBJ visibility","returns":"dict"},{"name":"display_node","sig":"parent","desc":"deprecated 兼容 wrapper：按父网络 context 路由 SOP output / OBJ visibility","returns":"dict"}]},{"domain":"parm 域","note":"parm 域（依附 node）","verbs":[{"name":"list_parms","sig":"node","desc":"参数**目录**：名字/标签/类型/帮助/默认值及实际 menu token/index/label（不给当前值）；动态菜单以实际节点为准","returns":"list"},{"name":"read_parms","sig":"node, changed_only=True, *, names=None","desc":"参数**值**：默认只看非默认 + 带表达式/动画 + 被引用的（意图解读）；names可选1..32个唯一标量字段，按请求顺序返回且不受changed_only过滤，缺失报错。无动画string含原始UTF-8源码source_sha256，展开值不同于原文时另含raw_value；表达式附referenced_parm，被引用标referenced_by；动画附time_dependent/key_count/first_frame/last_frame/curves，不默认倾倒全部keys","returns":"list"},{"name":"set_parm","sig":"node, name, value, allow_foreign=None","desc":"设参（数值字符串=表达式）。已有表达式/keys在普通赋值时清除，note说明变化。字面string可传`{expected_sha256,patch:[{old,new,count}]}`：精确版本和次数、全部锚点先验，拒绝锁定/动画/表达式/callback/固定菜单；返回patch前后hash/字符数/次数及value_omitted，不回传整份源码。最多32项，source/result各524288字符、替换文本累计131072字符、count为1..256；不执行正则/脚本。文本通过不证明cook/几何通过","returns":"dict"},{"name":"set_parms","sig":"node, values, allow_foreign=None, strict=True","desc":"默认严格批量设参：预检名称/重叠/锁定；value支持set_parm的string patch对象，本节点本批全部patch在任何设参前验证。patch只允许strict=True，set内返回变化摘要，patched列出字段；失败恢复本批值/表达式/keys。其他节点不在本批预检范围，参数回调/外部文件不属快照回滚。无patch的显式strict=False仍返回ok/set/failed；Menu string为精确token，数值string为HScript表达式，表达式对象可声明language","returns":"dict"},{"name":"set_keyframes","sig":"node, channels, replace=True, allow_foreign=None","desc":"批量写数值标量 channel keys；统一 frame 单位，有限曲线 `constant/linear/bezier`，全量预检、失败恢复原 keys、提交后回读/采样并恢复用户 frame。只负责 channel 数据，不代替路径依赖状态机或 KineFX/APEX","returns":"dict"},{"name":"create_spare_parms","sig":"node, code_parm='snippet', defaults=None, spec=None, allow_foreign=None, *, update_defaults=None","desc":"缺省扫描代码参数的 `ch/chf/chi/chv/chs` 引用并创建缺失 spare parameters；`spec=[...]` 的精确条目为 folder `{type,name,label?,parms:[...]}` 或 scalar `{type:'toggle\\|int\\|float\\|string',name,label?,default?,min?,max?,min_strict?,max_strict?,help?}`。spec 返回 `{node,mode,created,leaf_values}`；扫描返回 `{node,code_parm,references,created,existing,defaults_applied,unsupported}`；创建仍拒绝同名覆盖。新建接口后重新赋写code_parm原始源码/keys以刷新编译依赖，保留表达式与动画；返回refreshed_code_parm（未刷新为null），锁定源码在接口写入前拒绝。显式 `update_defaults={name:literal}` 仅更新1..32个已有scalar spare的默认值，与spec/defaults/非默认code_parm互斥；保留当前值/表达式/keys，返回updated前后值及current_state_preserved。支持float/int/toggle/string，拒绝内建/tuple/menu/callback/multiparm及表达式默认值，遵守严格上下限；当前值另用set_parms","returns":"dict"}]},{"domain":"scene 域","note":"scene 域（工程/时间线）","verbs":[{"name":"scene_info","sig":"","desc":"只读 HIP/version/fps/current frame/time/frame range/playback range/UI 状态；明确区分 `has_named_path`、`has_unsaved_changes`、`dirty_reliable`、`clean_on_disk`，不再用路径存在冒充保存完成；hython 的 dirty 不可靠时 clean=null；不移动 playbar、不遍历整张节点图","returns":"dict"},{"name":"scene_save","sig":"expected_path=None","desc":"只保存当前已命名 HIP，不承担 Save As/open/new；可选 expected_path 作防串场断言，返回 dirty before/after/reliable、clean（headless=null）、bytes、mtime_ns","returns":"dict"},{"name":"scene_save_as","sig":"path, expected_current_path, reason, overwrite=False","desc":"用户授权的 Save As：明确绝对 HIP 路径，expected_current_path 防串场，reason 记录路径/覆盖授权；已存在目标必须 overwrite=True。拒绝插件仓库落盘，回报前后路径/dirty/file/workspace_changed。无 load/clear；文件写不可撤销，失败可能留部分新文件，跨目录后 Open Workspace 重新绑定","returns":"dict"},{"name":"set_timeline","sig":"fps=None, frame_range=None, playback_range=None, current_frame=None","desc":"设置明确的时间线字段；至少一项，范围校验后回读 scene_info","returns":"dict"},{"name":"list_bookmarks","sig":"","desc":"列出 bookmark id/name/start/end/enabled/visible/comment","returns":"list"},{"name":"create_bookmark","sig":"name, start, end, replace=False","desc":"创建整数帧 bookmark；同名默认拒绝，replace 精确替换","returns":"dict"},{"name":"delete_bookmark","sig":"name_or_id","desc":"按精确名称或 session id 删除，失败列现有项","returns":"dict"}]},{"domain":"geometry 域","note":"geometry 域（几何数据）","verbs":[{"name":"geo_attrib_stats","sig":"node, name, attrib_class='point', *, unique=False, max_elements=100000","desc":"数值min/max/mean/count；unique=True全量检查精确完整tuple（含字符串），返回unique_count/duplicate_count/all_unique及至多8个重复样本。用P查精确重叠、用id查身份；超预算/非有限拒绝，无容差焊接或自动删除。point/prim/vertex/detail","returns":"dict"},{"name":"geo_point_spacing","sig":"node, expected, tolerance, closed=False, order_attrib=None, max_points=10000","desc":"全量相邻点弦长验收：默认point number顺序，或唯一数值order_attrib；closed含末→首，SOP local单位；返回全量min/max/failure_count及最多16个最差对与sequence hash。超预算拒绝不抽样；只证明该序列约束，不证明弧长、网格接线或实际零件关系","returns":"dict"},{"name":"geo_check_interfaces","sig":"output, interfaces, max_pairs=50000","desc":"同一最终SOP内1..16实际关系。默认{id,source_group,target_group,max_distance,expected_points}测独立表面点到面距离；method=axis_gap改用两个primitive组及axis/gap_range/min_overlap，测source.min−target.max与横向区间重叠。空组/自重叠fail，不支持unverified；SOP local有界不抽样。距离/投影范围不是接触、实体插入、碰撞或强度认证；返回实际值/范围/几何hash","returns":"dict"},{"name":"test_controls","sig":"controller, output, tests, interfaces=None, allow_foreign=None, *, domain=None, topology=None","desc":"可恢复数字控制测试，必须exec：1..16个 `{id,values:{parm:number},expectations:[{metric,axis?,group?,delta:[min,max]}]}`。metric支持bounds_size/center/min/max(axis)、point_count、primitive_count、area、point_mean(axis)、boundary_edges、piece_count、max_point_displacement/mean_point_displacement；max_transform_error另给16数row-major仿射transform，测实际点相对声明变换的最大残差。位移/变换要求稳定唯一id_attrib和相同Polygon拓扑。range验基准/扰动绝对范围，至少一项delta排除0。control_summary保留顶层失败原因、失败测量与逐case状态；基准失败的results=[]明确标not_run，不作通过。domain/interfaces/topology复查声明关系；恢复参数/keys/frame及完整bgeo内容（排除导出头date/派生group_summary，组目录按名规范排列；保留成员及组内顺序）。Polygon/Mesh/Sphere/Tube/点支持范围各指标明确，其他写前unverified。拒绝callback/menu/button/multiparm/tuple，foreign需单次授权；只证明声明case，非外部副作用恢复或艺术/强度认证","returns":"dict"},{"name":"geo_piece_stats","sig":"node, piece_attrib=None, sample=16, *, inspect=False, group=None, basis=None","desc":"primitive piece 的局部 bbox/extent/面积与退化统计；无 piece 属性时用内存 Connectivity SOP Verb，不污染网络，能发现「全场 bbox 正常但每个实例零宽/零面积」；inspect=True按精确primitive组观察有界Polygon边界/非流形/边连通及正交basis下extent，observed仅为量测完成，方法不支持保持unverified","returns":"dict"},{"name":"geo_frame_diff","sig":"node, frame_a, frame_b, attrib='P', sample=4096, tolerance=1e-6","desc":"用 geometryAtFrame 比较两帧 point 数值属性；可比较时精确返回键 `mean_delta`、`max_delta`、`delta_percentiles.{p50,p90,p99}`、`component_delta.{min,max,mean}`、`unchanged_pct`（另含 sampled_points/tolerance/data_type/size），不是 `mean/max`。不移动 playbar；证明数据是否随时间变化，不单独证明审美/运动语义","returns":"dict"}]},{"domain":"stage / USD 域","note":"stage / USD 域（Solaris 只读自省）","verbs":[{"name":"usd_stage_summary","sig":"node, max_paths=64","desc":"概览某 LOP 输出 stage 的 geometry/material/light/camera/RenderSettings/Product/Var，材质绑定、time-sampled 属性及 cook warning；路径按组限量但计数完整","returns":"dict"},{"name":"usd_prim_info","sig":"node, prim_path, max_properties=200","desc":"检查单个 USD prim 的属性、primvar、relationship、material binding、time samples；points/topology 等大数组只报结构不整段拉取","returns":"dict"}]},{"domain":"asset 域","note":"asset 域（HDA / 数字资产）","verbs":[{"name":"hda_create","sig":"node, name, description=None, hda_file=None, min_inputs=0, max_inputs=0, replace=False, allow_foreign=None","desc":"把已有节点（通常 subnet）转为数字资产：自动建 otls 目录、默认 `$HIP/otls/<name>.hda`。`replace=True` = 整体重建：所有待销毁实例逐项通过 ownership guard 后，卸载旧定义并覆盖文件；否则同名冲突报错并提示 replace","returns":"dict"},{"name":"hda_info","sig":"node, max_depth=6","desc":"资产/参数界面**只读自省**：类型名、定义文件、section 清单、参数模板树（名字/标签/类型/conditional/tags/嵌套 folder 递归）——替代手写 walk()（会话里重复写了 3 次）。普通节点也可用（只有 parm 树，无 section）","returns":"dict"},{"name":"hda_get_section","sig":"node, section='PythonModule'","desc":"读 HDA section 内容；section 不存在时列出现有 section 名供自纠","returns":"dict"},{"name":"hda_set_section","sig":"node, section, code, allow_foreign=None","desc":"全量写 section。`PythonModule` 先 `compile()` 预检语法（带行号报错，不写脏）；写后读回校验一致","returns":"dict"},{"name":"hda_patch_section","sig":"node, section, old, new, count=1, allow_foreign=None","desc":"锚点局部替换：`old` 必须恰好出现 `count` 次（0 = 锚点没找到，>count = 锚点不唯一需加长），替换后同样过语法预检；**模块改局部时用它，不要全文重发**","returns":"dict"},{"name":"hda_set_interface","sig":"node, spec, keep_std=True, hide_builtin_tabs=False, allow_foreign=None","desc":"**声明式参数面板**（整组重建语义，非 merge）：`spec` 是条目列表（folder/separator/toggle/int/float/string/button/menu），重建自定义参数组；subnet HDA 的 Transform/Subnet 标准页从 Houdini 原生 subnet 类型重新取得，避免夹带旧自定义参数。`hide_when` 字段写 conditional，**提交后读回验证**——被 `setParmTemplateGroup` 吞掉就自动改走 DialogScript `hidewhen` 补丁兜底；folder 上设 `hide_when` 直接报错（Houdini不支持）。`hide_builtin_tabs=True` 通过公开 `ParmTemplateGroup.hide` 生成 `invisibletab` 隐藏标准页","returns":"dict"}]},{"domain":"render / sim 域","note":"render / sim 域（渲染产物）","verbs":[{"name":"camera_fit","sig":"camera, target, direction='iso', coverage=0.82, width=None, height=None, frame=None, *, dry_run=False, allow_foreign=None","desc":"将正式静态OBJ cam拟合到显式SOP世界包络；保留焦距，清lookatpath，求距离/正交宽度，实际矩阵投影回验；无渲染/视口改变。尺寸默认相机值，当前frame。拒绝动画/约束/窗口偏移/自定义lens，失败恢复。ownership与单次allow_foreign适用，持久preview服务永不豁免；dry_run仍exec。Solaris需导入并按实际RenderProduct预检","returns":"dict"},{"name":"render_frame","sig":"rop, picture=None, frame=None, timeout=110, *, framing=None","desc":"渲染可执行hou.RopNode并验证新鲜产物；USD优先outputimage。可选framing={target:USD资产prim路径,coverage:.82}在renderer启动前检查实际stage所有产品的相机/有效画幅/裁切窗口；不通过或不支持时零渲染，不自动动相机。未传保持艺术裁切/通用ROP语义。临时picture/foreground/frame恢复；bytes/mtime/有界摘要确认fresh，旧文件失败；>110s走job","returns":"dict"},{"name":"render_view","sig":"node, direction='iso', frame=None, width=1280, height=720, picture=None, framing='full', coverage=0.82, framing_frame=None, *, focus_group=None, isolate=False, projection='perspective', framing_bounds=None, depth_bounds=None","desc":"显式SOP→持久proxy→服务相机/OpenGL，恢复用户状态，服务不删除。full完整入镜；detail只缩正交宽度/透视视角，不推进相机，近远裁面错误始终零渲染失败。focus_group指定实际primitive组，可isolate；framing_bounds决定取景，depth_bounds决定全部渲染内容含上下文的深度。A/B用同framing_frame并复用返回framing.bounds/depth_bounds及方向/画幅/模式，越界不漂移。check像素事实与pixels兼容别名、framing.depth_check/crop_reasons、source指纹/stale分别报告；空/error拒绝。展示格式OCIO编码sRGB（无匹配空间时明确gamma近似），EXR/HDR线性；output_color记录方法，不证明语义","returns":"dict"},{"name":"render_check","sig":"path, ref=None","desc":"亮度/非黑/主色/content bbox；A/B 另给高精度 mean、RMSE、changed/meaningful pixel %、max diff，微小非零不再被舍入成 0","returns":"dict"}]},{"domain":"viewport 域","note":"viewport 域（视口/UI）","verbs":[{"name":"viewport_screenshot","sig":"path=None, frame=None, clean=True, frame_target=None, textures=None, backface_cull=False","desc":"**用户屏幕诊断工具**：用户切空 display 节点时截到空是正确结果，不能用来证明 agent 产物；和 `render_view(explicit_sop)` 对照可区分 viewport 漂移与真实几何错误。flipbook 异步，设置/相机在落盘后恢复","returns":"dict"}]}];
    // <<< houdini-catalog

    // >>> houdini-trace (generated by tools/gen-trace-client.mjs — do not edit)
    var TRACE_SOURCES = {"guidance":{"name":"dsh-houdini:guidance","order":150,"text":"`houdini_*` tools operate one shared, live SideFX Houdini session. Code runs in Houdini with `hou` and the verb vocabulary pre-imported. Use `houdini_query` only for read-only inspection, `houdini_exec` for edits, and `houdini_job_*` for long renders/simulations. Inspect before editing. Exec failures undo Houdini-undoable scene edits, but not file/HDA-library I/O; never catch a mutation/cook exception without re-raising it.\n\nVerbs are the primary scene API; raw `hou` is a read/low-level escape hatch. The default-on gate rejects verb-covered raw mutations. Use `allow_raw` only after rejection, only for one isolated operation with no verb equivalent, and state the concrete gap. Never use raw `createNode`, `parm().set`, `cook`, `destroy`, or `hou.hipFile.load()` inside bridge code. If a verb signature or return shape is uncertain, call `verb_help(name)` before use; do not spend a failure or read repository source to discover runtime contracts. For three or more independent parameters on one node, prefer `set_parms`. `connect` is dataflow only and rejects OBJ parenting; intentional scene parenting uses `set_object_parent(child,parent,reason=...)`.\n\nCurrent catalog (generated from docs/tool-design.md): vocabulary 域: verb_help | 类型目录: search_tab_menu, search_tab_entries, resolve_latest_type | node 域: tab_create, tab_apply, find_nodes, graph, describe, node_provenance, connect, node_info, build_module, verify_network, set_object_parent, disconnect_input, rename_node, delete_node, cook_node, sop_set_output, sop_output_node, set_object_visible, visible_objects, layout_nodes | compatibility 域: set_display, display_node | parm 域: list_parms, read_parms, set_parm, set_parms, set_keyframes, create_spare_parms | scene 域: scene_info, scene_save, scene_save_as, set_timeline, list_bookmarks, create_bookmark, delete_bookmark | geometry 域: geo_attrib_stats, geo_point_spacing, geo_check_interfaces, test_controls, geo_piece_stats, geo_frame_diff | stage / USD 域: usd_stage_summary, usd_prim_info | asset 域: hda_create, hda_info, hda_get_section, hda_set_section, hda_patch_section, hda_set_interface | render / sim 域: camera_fit, render_frame, render_view, render_check | viewport 域: viewport_screenshot\nFor a small NEW SOP module, build_module preflights/cooks the batch (None skips input slots), and may validate declared interfaces on its final output. node_info discovers ports/menu tokens. verify_network requires explicit output; empty/error output fails by default, require_valid=False is diagnostic only. geo_check_interfaces measures named final-surface ports; test_controls temporarily changes numeric controls, measures declared responses and restores them (exec only). Neither certifies unspecified relationships/art quality. Read operation-evidence/checks, not just Python success. set_parms is strict by default. Save As requires user-authorized path/expected_current_path. Render filenames require extensions and resolve under $HIP. File/Python/solver side effects are not undoable.\nLarge returned envelopes may use compact model text after retaining the complete returned facts. Read omitted fields with houdini_query(result_ref=<sha256>, pointer=<JSON Pointer>, offset=0, limit=6000); this reads a historical workspace artifact without another Houdini execution. Never repeat a mutation to retrieve its result. Recorded execution-state context is a projection of observed tool facts, separate from the user-message scene snapshot; stale/unknown checks require relevant re-observation and never grant edit permission.\nhoudini_exec(review={parent,output,controller?}) optionally delegates a quick SOP issue review when requested or a concrete concern needs a second perspective, using logged requirements/current snapshot/prior tool facts; it is not a delivery contract/receipt cache. The Host-authorized reviewer can query and run review_test batches with automatic parameter restoration and optional preview captures, but cannot execute arbitrary edits/jobs/saves. Main-agent scene edits wait until review ends. Ordinary node ownership is unchanged; review permissions cannot be supplied by model arguments. Unsupported mutation tests remain unverified, never restrict normal authoring to a test whitelist.\n\nOwnership is runtime provenance, not path or copied metadata. Any node may be inspected or used as a read/source dependency, but mutation verbs normally write only nodes created by the current DSH session. Use `node_provenance` when origin is unclear. Pass `allow_foreign=\"<exact user authorization>\"` only when the user explicitly requested changing that foreign node; it authorizes one audited call and never justifies incidental cleanup. `layout_nodes(parent)` defaults to current-session nodes.\n\nLoad the smallest relevant bundled workflow before non-trivial work: `houdini-sop-workflow` for procedural SOP/VEX/Copy tasks, `houdini-rig-animation-workflow` for animation/rigging, and `houdini-solaris-karma-workflow` for USD/Karma/MaterialX delivery. Use `houdini-skill-governance` only when changing bundled skills. Detailed recipes and completion gates live in those skills, not in this always-on prompt.\n\nValidate the explicit deliverable, not incidental viewport state: cook and inspect module invariants, use `geo_frame_diff` for time dependency, and use `render_view(EXPLICIT_SOP)` for isolated visual evidence when GUI/OpenGL is stable. Keep its `__dsh_houdini_*` service nodes; do not clean them up. For animation A/B use one `framing_frame` chosen to cover the validation-frame envelope, then `render_check(path, ref=...)`; a content bbox touching the image edge is a framing failure even when the camera is fixed. If an evaluator, core transform graph, or membership rule changes, invalidate and rerun first/noncommutative/mid/end/recovery evidence. `render_check` proves file/pixel facts only. Claim visual semantics only after a vision inspection actually accessed the relayed image; setup, presentation, transport success, or a textual refusal is not visual evidence. Otherwise report visual semantics as unverified and hand subtle motion/aesthetics to user playback judgement.\n\nHoudini outputs belong under `$HIP`; relayed images are the exception and appear under the session workspace in the tool result `media` mapping. Do not write task outputs into the plugin repository. If the bridge is unreachable or reports a host/bridge contract mismatch, tell the user to run DSH-Houdini > Version & Diagnostics > Advanced diagnostics > Repair and restart runtime; do not work around it with shell commands.","hash":"0d09e5de8ef45211ca036fcb8f1d3011d2850dbec7ac8e14ef5277c5391993a5","source":"src/index.ts"},"skills":[{"name":"houdini-trace-analysis","description":"系统复盘 dsh-houdini / DeepSeek Harness 的 Houdini agent trace，包括 session.jsonl.zstd、trace-report HTML 或多次会话对比。用于用户要求分析最新/指定 Houdini trace、检查任务为何失败或低效、审计工具和动词的应调用未调用/缺失/误用/冗余/拆分/合并、判断节点模块与 cook/属性/显示/渲染/动画逻辑是否符合 Houdini 工作方式，以及依据累积 trace 更新审计规范和词表路线时。","base":"skills/houdini-trace-analysis","files":[{"path":"agents/openai.yaml","hash":"334a2a7948a5fa607f4c2013deb13bf44398d75e1bf0bb1916707e4659a8ddb0","bytes":278,"text":"interface:\n  display_name: \"Houdini Trace Analysis\"\n  short_description: \"Audit Houdini agent traces and evolve the verb vocabulary\"\n  default_prompt: \"Use $houdini-trace-analysis to audit the latest Houdini agent trace and recommend evidence-backed workflow and tool changes.\"\n"},{"path":"references/audit-rubric.md","hash":"bee544ca233fd0d61680329fb575fd8f47c5c4ab6c4d6011c5f2e0d9739a603a","bytes":25396,"text":"# Houdini trace 审计量表\n\n## 目录\n\n1. 证据边界\n2. 任务契约与完成判定\n3. 轨迹阶段与推进逻辑\n4. 工具机会矩阵\n5. 动词组合的保留、补充、拆分与合并\n6. Houdini 领域逻辑\n7. 分模块验证阶梯\n8. 视觉、渲染和动画验证\n9. 效率、恢复和卫生\n10. 证据强度与产品决策\n11. 标准报告模板\n12. Skill 演化协议\n\n## 1. 证据边界\n\n先核对session元数据的effective preset与request/header实际persona，再核对skill/card曝光。工具存在不等于Houdini persona已加载。\nv11transaction区分动词执行与最终提交；rolled_back中的成功ledger不得当当前依赖。删除/替换输出可解除旧checkpoint，不能只按旧路径永久记未解决。\n检查判据是否蕴含标签：unsigned距离不是插入深度、bbox极值不是镜像对称、全局最低y不是每足接地。\n只测response不证明扰动后invariants；事后改阈值需独立依据；unsupported保留范围。\n图像访问与正确识别分别记录；focus_group/isolate/projection/framing_bounds明确实际观察条件。\n\n必须同时使用三层证据：\n\n- 原始层：用户/assistant 消息、tool call、tool result、turn 结束状态。\n- 结构层：工具数量、动词 ledger、失败、advisory、代码长度、重复调用、帧间 diff。\n- Houdini 层：节点类型、拓扑、参数、属性、点/面/顶点、局部 bbox、cook 状态、显示旗标、帧依赖和渲染结果。\n\n报告中的每个重要结论标注 `步骤 #N HH:MM:SS`、事件 seq 或用户原话。HTML 报告用于导航；JSON evidence 和原始 session 才是事实源。\n\n先检查 evidence 的 `capabilitySnapshots`。只有当某能力在该步骤之前已出现在 request header/\nskill catalog 或能由当时工具契约合理发现时，才允许标 `MISSED`；用当前仓库目录回看旧 trace\n时，新加入的工具必须标“当时未曝光”，不能倒果为因。\n\n当 trace 出现大面积 raw-hou 绕过时，同时判断执行守卫状态：优先读取同期 `/health.rawGate`；\n若 trace 没保存 health，则用“verb-covered 裸 mutation 是否实际执行”判断 gate 当时是否 fail-open。\nsystem/guidance 已曝光只能证明模型收到规则，不能证明 bridge 执行了规则。\n\n若 capability snapshot 与 verb ledger/`verb_help` 返回冲突，优先怀疑 Host/Bridge generation skew。\n当前 Bridge 的 `/health.verbCatalog` 名称/hash 是运行时事实；只看到 Host 目录不能证明 Houdini\n进程已经 reload。旧 trace 无 health 时，用未知动词、旧签名或旧返回字段作为间接证据并降级强度。\n\n长会话可能在 `compaction/prune` 后重放历史 `tool/result`。同一 callId 只代表一次执行；\nevidence 必须去重并把后续结果列为 `replayedResults`，不得让 replay 膨胀调用、动词、\n失败、耗时或阶段时间线。\n\n不要把以下内容混为一谈：\n\n- tool 返回错误。\n- tool 成功但某个 verb 失败。\n- tool/verb 都成功但节点结果语义错误。\n- 结果正确但没有完成保存、清理、说明或用户验收。\n\n失败 exec 另查 `rollbackSteps`：`applied=true` 表示 Houdini undoable scene edits 已撤销，\n不表示文件/HDA 库等外部副作用消失；`supported=false` 的 headless 失败仍可能留半成品。\n\n## 2. 任务契约与完成判定\n\n从用户消息提取可验证契约：\n\n| 维度 | 例子 | 完成证据 |\n|---|---|---|\n| 场景产物 | 程序化草地网络 | 节点存在、拓扑合理、参数可编辑 |\n| 参考/真实性 | 指定车型、现实尺度、技术标准 | 用户参考或 agent 实际检索来源；无来源时明确假设 |\n| 质量/LOD | 预览、镜头级、产品级、允许简化 | 用户选择或 agent 披露的默认；对应观察距离和局部完成门 |\n| 形态 | 草叶有宽度、密度合理 | 单株/复制后局部几何验证 + 中性视觉检查 |\n| 动态 | 风吹麦浪 | 相隔帧的几何/图像差异，且差异方向符合风场 |\n| 运行健康 | 无 cook 错误 | 关键节点 errors 为空；warning 已解决或解释 |\n| 用户界面 | 用户视口可见 | 仅当用户关心屏幕时，用 viewport_screenshot 诊断 |\n| 交付 | 保存/路径/说明 | 明确文件、节点、控制参数和限制；最终消息存在 |\n\n完成状态只能是：\n\n- `完成`：全部核心契约有证据且已交付。\n- `部分完成`：部分目标成立，但核心形态/动画/交付至少一项缺失。\n- `未完成`：核心目标没有验证、产物错误，或会话无交付地结束。\n- `不可判定`：trace 缺失必要结果；列出缺失证据，不猜。\n\n若最后事件是 tool result、最后 todo 仍 pending/in_progress、最后 A/B 验证失败或没有 assistant 交付，不能判“完成”。\n最终文本若以“完成/交付”定性，却把用户原始明确要求的质量维度列为 `unverified/未验证`，核心契约\n只能判部分完成；`requested_goal_reported_unverified` 是对此矛盾的确定性审计入口，不替代人工判断\n该维度是否核心。\n\n开放式任务另检查：agent 是否识别了会改变方案的歧义，是否实际研究/询问或获得用户授权自选，\n是否在大规模 mutation 前留下可复述的目标、参考状态、假设、质量门和验证计划。用户说“你决定”\n允许 agent 选型，但不允许把未披露的模型记忆写成外部事实。数字彼此自洽只能证明内部一致，不能\n单独证明“符合真实范围”。\n\n`create_goal`/`todo_write` 可以证明 agent 在 mutation 前记录了结构化合同字段，但不能替代用户确认；\n用户选择以 ask result/用户消息为准。重大选择的 ask 应优先提供 2–4 个有影响说明的互斥选项、推荐项\n和 custom 文本补充；路径、名称、精确数值等天然唯一答案才允许纯文本。不要把“用户没填空白框”\n误判成用户授权 agent 自选。\n\n## 3. 轨迹阶段与推进逻辑\n\n用状态跃迁而非 assistant 文案划阶段：\n\n1. 接收/判歧义：分开用户事实、目标、解释、价值判断和未决选择。\n2. 研究：只有外部真实性、当前资料或未知领域会改变方案时执行；记录来源和适用边界。\n3. 澄清/合同：询问剩余重大选择，或披露用户授权 agent 自选的假设、质量门和验证计划。\n4. 现场检查：版本、HIP、现有节点、帧范围、用户上下文。\n5. 设计：选择 Houdini 原生模块和数据契约；明确验证点。\n6. 构建：建立最小网络，避免一条超长 exec 在中途失败后留下不明半成品。\n7. 模块验证：逐节点/逐分支验证输入、输出和局部不变量。\n8. 集成：合并分支，处理属性和 warning。\n9. 静态视觉：agent 自有 render_view；先客观 check，再中性识图。\n10. 时序验证：至少 A/B 两帧，验证动态幅度与空间传播。\n11. 修订：用户反馈或失败使旧假设失效时，重开合同并重跑受影响完成门。\n12. 清理交付：删除 probe、恢复显示状态、布局、保存/说明、更新 todo。\n\n标记反模式：\n\n- 在模块验证前宣称“网络成功”。\n- aggregate bbox/点数通过即判形态正确。\n- 几何异常时优先调相机、灯光、gamma 或视觉 prompt。\n- 连续失败后只改 API 拼写，不回到上一稳定状态。\n- 为验证创建 probe 后未恢复接线或删除节点。\n- 用户纠正后没有重新核对完整任务契约。\n- 自己生成规格/尺寸，再凭模型记忆判其“符合真实范围”，并把内部一致写成外部验证。\n- 只询问交付形式，却未询问或披露真正改变结构/质量的目标、LOD、参考和允许简化。\n\n## 4. 工具机会矩阵\n\n对“与本次任务相关”的每个能力使用以下唯一标签：\n\n- `USED_RIGHT`：调用时机、参数和结果消费正确。\n- `MISSED`：已有能力与当前意图直接匹配，但 agent 走裸 API、猜测或绕路。\n- `MISUSED`：调用了工具，但语义/参数/结果解释不正确。\n- `TOOL_BUG`：工具实现或契约导致错误、状态污染或不可操作报错。\n- `MISSING`：目录中没有能表达该通用意图的能力，且重复手写成本高或风险大。\n- `NOT_APPLICABLE`：本任务不需要；不能用来支持删除。\n- `REDUNDANT_CANDIDATE`、`MERGE_CANDIDATE`、`SPLIT_CANDIDATE`：只用于跨 trace 产品建议，必须附证据强度。\n\n采用统计必须分层，不能用一个百分比代替：\n\n- `catalog.used/total`：目录广度，只说明任务碰过哪些能力；大量 NOT_APPLICABLE 动词不进分母推理。\n- `verbAdoption.callCoveragePct`：Houdini 调用中含至少一个 verb 的比例，会被合法只读探针稀释。\n- `verbDensity`：每次 Houdini 调用的 verb 数，观察 batch/组合程度。\n- `successfulExecVerbCoveragePct`：成功 mutation-intent exec 的 verb 覆盖，是场景修改采用的近似指标。\n- `rawReadOnlyCalls`、`blockedVerblessRawMutationCalls`、`successfulVerblessRawMutationCalls`：分别解释逃生舱、Gate 有效性与真正安全回归。\n\n必查机会：\n\n- 外部事实会改变方案时：检查当时是否曝光 research/web 能力；有则实际检索并保留来源，没有则向\n  用户索取参考或降低真实性结论，不能默认 `MISSING` 或凭记忆补齐。\n- 剩余用户选择会改变方案时：使用已曝光的提问能力；一次问完相互关联的重大选择，不把简单任务\n  变成问卷，也不在已开始大规模 mutation 后才补问质量标准。\n- 发现节点：`find_nodes`，不要默认裸遍历 `/obj`。\n- 拓扑诊断：`graph`，尤其在接线或属性来源混乱时。\n- 参数导航：`list_parms`；参数意图：`read_parms`。\n- 同一节点三项以上赋值：优先 `set_parms`。\n- 动词签名/返回形状不确定：先 `verb_help(name)`；若 agent 先制造一次失败或读取仓库源码才发现契约，标记为可避免的 discoverability 失败。\n- SOP 创建：`search_tab_menu`/`tab_create`；避免猜旧节点或错误版本。\n- Solaris/Material/COP 等上下文创建：优先 `search_tab_entries(actual_parent, query)`；检查\n  entry 是 node type 还是多节点 tool、是否 hidden/deprecated、是否被 parent tab mask\n  排除。`tab_create` 只建一个可见节点，setup/builder 用 `tab_apply`。\n- 显示：SOP 用 `sop_set_output/sop_output_node`，OBJ 用 `set_object_visible/visible_objects`；旧 `set_display/display_node` 只作兼容。检查是否错误混用 singular/plural context。\n- cook/状态：`cook_node` + `describe`，但不得忽略 warning。\n- 属性值：`geo_attrib_stats`；若局部形态仍不可证，记录新的几何自省缺口。\n- 视觉验证：`render_view`；交付 ROP 才用 `render_frame`。\n- 用户屏幕问题：`viewport_screenshot` 仅作诊断。\n\n## 5. 动词组合的保留、补充、拆分与合并\n\n### 保留\n\n即使低频，只要语义独立、风险边界不同或是关键逃生能力，就应保留。零使用只说明本 trace 不适用或采用率低。\n\n### 补充\n\n同时满足以下条件时列 `MISSING`：\n\n1. 意图可跨任务复用，不是某个草地/镜头的专用操作。\n2. 当前需要多段易错裸 hou/VEX 或多次探测。\n3. 封装能加入校验、状态恢复或更诚实的返回。\n4. 已有动词不能自然扩展覆盖。\n\n### 合并\n\n只有两项能力的用户意图、生命周期、副作用和返回契约基本相同，且 trace 显示 agent 经常选错，才考虑合并。`set_parm` 与 `set_parms` 是 primitive + batch，不因名字近就合并。\n\n### 拆分\n\n当同名动词跨 context 有不同基数、所有权或副作用时拆分或改为 context-aware。例如 SOP 网络只有一个 display child，而 OBJ 可有多个可见对象；单一“display node”契约若假设错误，就必须拆分或显式返回不同形状。\n\n### 删除\n\n至少满足：三个以上多样 trace 中无独立价值；有等价且更安全的替代；迁移路径明确；没有诊断/逃生用途。单 trace 不允许建议删除。\n\n## 6. Houdini 领域逻辑\n\n### Solaris / USD / Karma\n\n- “节点类型注册表里存在”不等于“用户在当前 parent 的 Tab 菜单可见”。Material Library\n  根层、各类 Builder 与 setup recipe 必须按实际 context 审计。\n- 新 Karma 材质检查 render context（kma/mtlx/preview），不能用最终像素颜色替代；传统\n  Principled 在 CPU 能出图不证明 XPU 完整兼容。\n- 最终 Karma 交付检查 geometry/material binding/light/camera/RenderSettings/\n  RenderProduct/RenderVar/USD Render ROP。普通 LopNode 按钮成功不等于 ROP 产物成功。\n- SOP time dependency、单次 stage time sample 和最终 Karma 序列是三层证据；动画任务仍需\n  同一 USD camera 的两帧或小序列。\n\n### 节点类型和模块\n\n- 选择节点前确认 Tab Menu 类型和最新版；优先 Houdini 语义正确的 SOP，而非熟悉但过时的 SOP。\n- Copy to Points 应承担模板点 orient/pscale/N/up 的实例变换；使用经典 Copy 后手写变换需要强证据。\n- 形变和成形的顺序必须保留数据：通常先变形中心线/曲面，再 Sweep/PolyWire 生成厚度，比生成截面后用错误 rest 坐标重建更安全。\n- 草叶等扁平对象优先 Sweep/skin/ribbon 语义；PolyWire 是管状截面，不应无理由替代叶片模块。\n\n### 开放式程序化资产\n\n- 先读取 evidence 的 `qualityLoopEvidence`：合同字段、research/web 可用性与实际调用、质量合同\n  是否加载、首张 render 前 `tab_create` 数、关系 probe、控制扰动恢复和末次修改后的统计新鲜度。\n  `completionRisks` 中的 HTA-023 系列风险是审计入口，不替代对原始步骤和画面的人工判断。\n- 区分“代码生成的固定结果”和“用户可调且关系保持成立的程序化资产”。关键尺寸若分散复制在\n  多个 VEX/Python 字符串中，默认值能 cook 不证明参数化完成。\n- 共享尺寸、anchor/局部坐标、模块输入输出和部件关系应有单一真相源或明确派生链；审计至少选\n  一个关键控制做扰动，检查受影响模块是否仍满足关系门。\n- `geo_piece_stats` 的非退化只证明面积/extent，不证明部件连接、包含、间隙或禁止相交；整体\n  bbox/点数、无 warning、能出图同样不能替代装配关系检查。\n- “细节丰富/高质量”必须落实到目标 LOD、允许简化、局部观察距离和证据视角。节点数、primitive\n  数或装饰件数量只能描述复杂度，不能单独判质量。\n\n### Rig / Animation 系统路由\n\n- 不把“绑定”直接等同 KineFX/APEX。先分类：parameter channel、rigid pieces、hierarchy/FK、\n  skeleton + skin、animator-facing character rig、simulation。\n- `/obj` 等路径只说明放置 context，不自动授权相同名称的数据模型。新建几何父子机械/FK 默认\n  KineFX；OBJ parenting 只在用户明确要求、既有 legacy、场景对象装配或下游 OBJ 交付时成立。\n- rigid piece 任务检查稳定 `name/piece_id`、rest transform、当前 transform 与 membership；\n  packed pieces/Copy to Points/Transform Pieces 通常比对所有展开点手写矩阵更符合数据模型。\n- 旋转轴上的 piece 可能 `P` 完全不变而 `orient/transform` 已改变；活动集合和刚体动画不能只\n  用 P diff，至少同时检查 orientation/transform。Copy/Pack 后还要确认稳定 name 真正存在于\n  Transform Pieces 用来匹配的属性 class，不能假设模板 `name` 自动传播。\n- KineFX 检查 joint `name/P/transform`、parent/local/world space；skin 另检查 `boneCapture`、\n  capture pose、animated pose 与 Joint Deform。没有 skin/层级需求时，不因“专业”而强制 KineFX。\n- 把 driver skeleton、control/capture binding 与 driven deliverable 分开。Attach Joint Geometry 的\n  `jointgeo`/anchor、包含 skeleton 的总 bbox 或 joint P 变化都不能证明最终 skin/link 在动；实际\n  geometry 探针失败后不得换测上游 metadata 并把同一契约改判为通过。\n- APEX 面向 controls、constraints、FK/IK 与可复用 rig graph；必须证明任务需要延迟图求值和\n  animator-facing 逻辑，不能用它替代简单 piece state evaluator。\n- 路径依赖/非交换序列必须表示 ordered state transition。使用初始 membership + 独立绝对\n  通道时，除非各通道确实互不影响，否则是结构性反例。\n- 审计 OBJ parenting 时核对 `parent output → child input`，但 agent 应通过\n  `set_object_parent(child,parent,reason=...)` 表达意图；generic `connect` 成功不得作为新建几何\n  rig 使用 OBJ hierarchy 的依据。若最终契约是 geometry，仍需显式 final geometry 取证。\n\n### 数据流和属性\n\n对每个关键边界写出 `输入属性 → 操作 → 输出属性`。检查：\n\n- 属性 class（point/prim/vertex/detail）是否正确。\n- Copy/Merge 后属性是否传递、缺失、默认初始化或冲突。\n- rest/local 坐标是在最终拓扑之前还是之后捕获。\n- per-instance 属性是否在复制后仍存在。\n- warning 中的 N/uv/Cd 等是否影响显示、材质或下游运算。\n\n### Cook 和缓存\n\n- 每次改接线/代码后 cook 目标分支；需要时强制更新。\n- 渲染字节长期完全相同而场景已变，优先怀疑未 cook、显示对象错误或 ROP 缓存。\n- 性能问题使用节点 cook 时间和 SideFX Performance Monitor；工具调用次数不是 Houdini cook 性能。\n\n### 显示和所有权\n\n- 区分 SOP display/render flag、OBJ visibility、用户 viewport 和 agent-owned camera/ROP。\n- agent 验证管线不得改变用户视口或永久抢走对象可见性。\n- 创建 camera/light/null 后核对并恢复原有 OBJ 显示状态。\n\n## 7. 分模块验证阶梯\n\n复杂程序化网络必须由小到大验证：\n\n1. 源数据：地形或输入几何。\n2. 最小生成单元：单株草叶、单块碎片、单个实例。\n3. 成形后：宽度、面积、法线、UV、局部 bbox。\n4. 模板点：数量、orient/pscale/id/phase 等。\n5. 复制/实例后：随机抽样单个 piece 的局部 bbox 和属性。\n6. 变形后：根部固定、尖端位移、面积/厚度未退化。\n7. Merge/输出：属性一致、warning 解释、显示旗标正确。\n8. 静态渲染。\n9. 多帧差异。\n\n“全场景 bbox 高度正常”无法证明每个草叶有宽度；“点数很多”无法证明拓扑没有重合。若现有工具无法低成本检查 piece/local extent，应列为通用几何自省缺口。\n\n## 8. 视觉、渲染和动画验证\n\n### 静态视觉\n\n1. `cook_node`/模块不变量先通过。\n2. `render_view` 返回非空、合理 content bbox 和亮度。\n3. 第一轮视觉 prompt 只问“描述可见几何、颜色、位置、异常”，不说“这是成功的草地”。\n4. 第二轮才按用户目标核验草叶、密度、风向等。\n5. 视觉结论与数值冲突时回到几何，不用 prompt 说服视觉模型。\n6. 视觉工具 transport 成功不等于看图成功。bootstrap 是 setup、present 是交付；只有 semantic\n   inspection 可作视觉结论。结构化 `ok:false`、模型声明不支持图像/图片被省略等文本拒绝必须判失败。\n7. 整物远景只适合轮廓/构图；小零件、接缝、间隙和穿插需要目标在画面中可辨认的局部视角。\n   没有对应特写时，不得把“整物可辨认”升级成“局部关系视觉通过”。\n8. 声称与外部参考一致时，参考和验证图必须具备可比较的视角/尺度或明确只做定性判断；单独看\n   agent 自己生成的图不能证明外部一致。\n9. 语义视觉失败或不可用时，仍读取 `render_view.check`/`render_check` 的亮度、非黑占比和\n   content bbox。近黑、近空、目标缺失、触边或资产轴向错误的图片只能判像素展示失败；\n   `stale=false`、文件字节非零和无 render error 只证明 transport/file 层。\n\n### 动画\n\n- 至少选两帧，帧距足以覆盖相位变化。\n- 比较几何样本或 render diff；仅文件大小不同不够。\n- `mean_abs_diff≈0`、max diff 仅 1 灰阶时，按静态或缓存问题处理。\n- 几何 diff 明显非零只证明“数据随时间变化”，不证明运动符合用户语义。继续验证锚点、活动区、方向和空间传播。若固定相机 A/B 暴露明确的结构性反例（完全静止、方向相反、主体缺失），完成门失败；若节点/数据/时间语义均通过而静帧只是不足以裁定细微动态或审美力度，可停止追图并标记“视觉待用户播放判断”，但不能写成“视觉已确认通过”。\n- render A/B 必须使用完全相同的相机与构图。逐帧按动态 bbox 自动重取景时，先比较返回的 camera `center/eye/dist/direction`；任一变化都会把相机漂移混入 pixel diff，该 diff 只能证明两张图不同，不能证明几何运动。\n- 固定相机还必须覆盖验收帧的空间包络。检查每帧 `render_check.content_bbox` 与图像边界；触边或安全边距不足时记录为 framing clip risk，不能把“相机一致”写成“构图完整”。\n- 验证根部近似固定、尖端运动更大、波峰沿风向传播；不能只看“画面动了”。\n- 多 segment 或路径依赖任务不得只抽 first A/B。验证覆盖至少包括：第一段、一个会改变后续\n  membership/空间的非交换转折、sequence mid/end、recovery；报告实际覆盖帧。\n- trace 中只要状态求值器、核心 transform 图或 membership 规则被修过，修复前的上述序列证据全部失效；审计必须要求修复后重新覆盖 first、非交换 transition、mid/end、recovery，而不是沿用旧证据拼接完成门。\n- 最终帧等于 rest 时，区分“正确 inverse 后恢复”与“所有绝对控制量归零后天然重算 rest”。\n  后者不能证明中间序列正确。\n- hidden piece 数、capture weights、joint hierarchy、constraint 和 state permutation 不能由\n  单视角视觉确认，必须使用数据/属性/transform 证据。\n\n### Render 工具边界\n\n- `render_view(EXPLICIT_SOP)`：agent 自有快速验证，显式 SOP 经隐藏 proxy + forceobjects；检查 fingerprints、stale、状态恢复、确定性 headlight/Cd 和用户 display 漂移隔离。\n- 动画 A/B 给每次 `render_view` 传同一 `framing_frame`；不同 framing metadata 下的 pixel diff 不作纯几何运动证据。\n- 两张 render 已生成但缺 `render_check(ref=...)` 时，只能证明各自有效，不能声称固定相机 A/B 已完成客观图像比较。\n- `render_frame`：已有 ROP 的正式或自定义构图渲染，不应承担反复修复 `render_view` 的职责。\n- `viewport_screenshot`：用户屏幕诊断，不是 agent 自证成功的主路径。\n\n## 9. 效率、恢复和卫生\n\n统计并解释：\n\n- 首次正确模块产物时间、首次视觉证据时间、用户纠正时间、最终交付时间。\n- 构建、几何调试、渲染调试各占多少调用/分钟。\n- 同类硬失败是否连续发生；是否在第三次前改变策略。\n- **同一 resolved node** 三项以上 `set_parm` 是否可批量；跨多个节点的总次数不能算 batch\n  opportunity，已经使用 `set_parms` 的字段不重复计入。\n- 是否反复全文重发 VEX/Python；能否局部 patch。\n- 是否创建并清理 test box/light/probe/camera。\n- 是否恢复 display/ROP/frame，是否保存或说明未保存。\n\n## 10. 证据强度与产品决策\n\n- `S1 单例`：一个 trace；只能提出假设或 P0 可复现工具 bug。\n- `S2 重复`：两个独立 trace 或当前 trace + 可复现实验；可进入 P1 设计。\n- `S3 稳定`：至少三个多样任务、反例分析完成；才可删工具或大幅重构契约。\n\n工具自身抛错、污染状态或虚假成功，现场可复现后可直接 P0，不必等待三个 trace。采用率、拆并和删除必须积累证据。\n\n## 11. 标准报告模板\n\n### 结论\n\n- 完成状态、最严重因果链、用户是否被迫纠正。\n\n### 任务契约差距\n\n| 契约 | 证据 | 状态 | 缺口 |\n\n### 阶段时间线\n\n| 时间/步骤 | 阶段 | 行为 | 结果/转折 |\n\n### 工具矩阵\n\n| 能力/动词 | 标签 | 证据 | 正确替代/产品动作 | 强度 |\n\n### Houdini 模块审计\n\n| 模块 | 输入/输出契约 | 验证 | 问题 |\n\n### 最小正确轨迹\n\n列出 8–15 个状态跃迁，不写逐参数流水账。\n\n### 优先级\n\nP0/P1/P2，每项写：问题、证据、建议、验收、是否需要更多 trace。\n\n## 12. Skill 演化协议\n\n每次复盘后回答：\n\n1. 当前量表是否漏掉了一个可复用维度？\n2. `known-patterns.md` 是否已有同类模式？追加证据还是创建新条目？\n3. 新发现是 task-specific、Houdini domain、tool contract 还是 agent policy？放到对应层。\n4. 是否出现反例，要求降级或关闭旧建议？\n5. evidence 脚本是否漏计失败、工具结果或新 schema？若是先修脚本并回归旧 trace。\n\n模式库条目必须包含：ID、状态、首次/最近证据、症状、根因、建议、反例/边界、下一验收。不得把一次草地任务的专有节点名写成通用硬规则。\n"},{"path":"references/known-patterns.md","hash":"e6973ad76b015cddb0ae8c4a8b8abcf8dca1d21938708021e6987ff93c1291f7","bytes":45430,"text":"# 已知 trace 模式库\n\n此文件只存跨任务可复用、带 session 证据的规律。`候选` 表示仍需更多 trace；`确认` 表示已有重复证据或可复现实验；`已修` 必须写明回归。\n\n## HTA-001：长 exec 中途失败留下半成品\n\n- 状态：已修（GUI exec undo group + 异常自动 performUndo；文件/HDA 外部副作用明确不在范围）\n- 证据：`f608bfab` 的参数组增量重建；`40054277` 步骤 #6 在 Scatter 参数失败前已创建地形和部分节点。\n- 症状：后续代码默认某些节点已存在，拓扑和参数来自多次补丁，恢复路径不清楚。\n- 根因：桥 exec 无 undo transaction；任务脚本没有小批次 checkpoint。\n- 修复：bridge 每次 GUI exec 进入唯一 undo group；异常只在栈顶 label 匹配时自动 undo，并在 envelope 回报 `rollback`。skill 仍强制小 batch checkpoint。\n- 边界：纯只读 query 或幂等小赋值不需要事务。\n\n## HTA-002：整体统计掩盖局部几何退化\n\n- 状态：已修（`geo_piece_stats` + 模块验证阶梯）\n- 证据：`40054277` 步骤 #16 的 `instance_xform` 全局 bbox/点数正常；用户 seq 19405 指出每株草宽度为 0；步骤 #61 才把 local 坐标捕获移到 PolyWire 后。\n- 症状：点数、全场 bbox、cook 都通过，但每个 piece 的宽度/面积/体积退化。\n- 根因：未验证单元级 local extent 和变换前后拓扑不变量。\n- 修复：内存 Connectivity SOP Verb 生成 piece，报告局部 extent/面积/degenerate；H21 在真实 9000 株、306k prim 草地上识别 9000 pieces、0 退化。\n- 边界：无重复单元的单体几何仍需适合自身的局部不变量，不强制 piece 分组。\n\n## HTA-003：几何未证实时进入渲染兔子洞\n\n- 状态：已修（SOP workflow skill + 完成门）\n- 证据：`40054277` 在 14:30 宣称草已正常，14:31–14:50 连续调 display、灯光、相机、gamma；用户随后指出建模根因。\n- 症状：大量 render/vision 调用围绕黑图、暗图、构图，真正 SOP 错误未被隔离。\n- 根因：错误地把 aggregate cook 成功当作模块验收；视觉 prompt 带目标暗示。\n- 修复：`houdini-sop-workflow` 固化源几何→单元→成形→模板点→复制→变形→合并→多帧→渲染阶梯；trace skill 同步完成门。\n- 边界：明确的渲染器/灯光任务可以直接进入渲染诊断。\n\n## HTA-004：agent-owned render 管线污染 OBJ 可见性\n\n- 状态：已修（render_view v2 proxy isolation + display context split）\n- 证据：`40054277` 步骤 #19/#21 只出绿色准星；步骤 #28 raw `setDisplayFlag(True)` 后恢复内容。`display_node('/obj')` 在步骤 #25 自身失败。\n- 症状：创建 `/obj/dsh_cam`/target 后用户对象被隐藏；验证工具改变了被验证状态。\n- 根因：`render_view`/`tab_create` 未保存和恢复 OBJ display 状态；`display_node` 把 SOP 单一 display child 语义套到 OBJ。\n- 修复：显式 SOP 经隐藏 Object Merge proxy，ROP forceobjects 只渲染 proxy；保存/恢复 OBJ visibility、selection、frame。SOP output 与 OBJ visibility 新动词拆分，旧名兼容路由。\n- 边界：SOP 子网的 display flag 仍是单节点语义，不能因 OBJ 行为删除该能力。\n\n## HTA-005：手写 agent 相机矩阵导致恢复失败和序列化噪音\n\n- 状态：已修（agent-owned framing + 固定多帧 framing + 通用 lossless-float 归一化）\n- 证据：`40054277` 步骤 #48–#59；其中 #49–#52/#54 因 lossless JSON（负零/特殊浮点）连续失败。\n- 症状：重复计算 Matrix4、extractRotates、tx/rx，输出不变，消耗十余调用。\n- 根因：`render_view` 只有 full-bbox framing，缺少 agent-owned close/detail 构图控制；工具未返回足够的 camera diagnostics。\n- 修复：`render_view(framing='full|detail', coverage=...)`，agent camera/target/ROP 全部 owned；H21 隔离回归两次像素完全一致。\n- 边界：正式镜头制作仍允许直接编辑独立 camera + `render_frame`。\n\n## HTA-006：旧/错误节点选择放大手写 VEX 复杂度\n\n- 状态：已修（节点选择/变形顺序进入 `houdini-sop-workflow`）\n- 证据：`40054277` 使用 classic Copy SOP，未先 `search_tab_menu('sop','copy')`，随后手写 attribute transfer 和 instance transform；正向对照 `be6367cd` 直接用 `copytopoints` + 带宽度的 Grid blade，11 次工具完成静态草地；早期自行车 trace 也已证明 Copy to Points 初始化语义重要。\n- 症状：手写 orient/yaw/tilt/rest 传递，产生截面塌缩和多轮 VEX 编译修复。\n- 根因：节点意图选择没有把 Houdini 原生 Copy to Points/Sweep 数据模型作为首选。\n- 修复：`houdini-sop-workflow` 增加模块选择 checkpoint、Copy to Points 与 deform-before-skin 基线；guidance 要求先查 Tab Menu。\n- 边界：需要自定义非刚性逐点变形时，Copy to Points 不能替代后续 deformation，但仍可承担实例变换。\n\n## HTA-007：warning 被“无 error”覆盖\n\n- 状态：已修（cook_node 返回 healthy/warning_free + guidance 完成门）\n- 证据：`40054277` Merge 的 N/uv attribute mismatch 从步骤 #17 持续到 #75，但 todo 在步骤 #18 将 cook 验证标 completed。\n- 症状：agent 宣称健康，warning 持续存在并可能影响 shading/UV。\n- 根因：完成门只检查 error 或点数，没有为 warning 建立解释/白名单。\n- 修复：`cook_node(force=...)` 返回 `ok/warning_free/healthy`；guidance/skills 明确 warning 未解释不得交付。\n- 边界：已知且不影响目标的 warning 可保留，但必须记录理由。\n\n## HTA-008：动画任务缺少时序完成门\n\n- 状态：规则已修、待新 trace 验证（客观反例阻断；静帧难裁定审美时诚实交给用户播放判断）\n- 证据：`40054277` 最后工具调用 #77 的 frame 1/12 `mean_abs_diff=0`、`max_abs_diff=1`，仍有两个未完成 todo，且无最终 assistant 交付。`71d76525` 工具调用 #40 的 geometry diff 非零、#46 的 render diff 为 21.1%，但 #47 的视觉 A/B 明确判断“没有明显变化、不像行进波浪”；agent 仍在 #50 把动画验证标 completed，并在最终文本宣称“全部验证通过”。`a41c853a` #59–#64 只验证魔方第一个 R move 的 frame 25/31，却在最终文本外推为 16 步打乱/还原；frame 1/220 相同只是六个绝对通道都回零。\n- 症状：旧版本完全没有时序证据；后续版本有数值差异，却把“点动了/像素不同/第一段通过/首尾相同”误当成整个用户运动契约成立，甚至覆盖视觉否定或缺失的中间状态。\n- 根因：完成门只检查非零阈值或单个 A/B，没有规定证据冲突的裁决顺序、承诺序列的验证覆盖，也没有要求波峰传播、锚点/活动区、稳定 piece 身份、更新后 membership 等领域语义不变量。\n- 修复：geometryAtFrame 无 playbar 副作用比较；render_check 增加 RMSE、changed/meaningful pixel % 与高精度 mean。审计/workflow 现区分：完全静止、方向相反、主体缺失等客观反例必须阻断；节点/数据/时间语义通过而静帧不足以裁定细微动态或审美时，允许标记“视觉待用户播放判断”，但不得伪称视觉确认。多 segment/路径依赖任务另需 first、非交换转折、mid/end、recovery 覆盖。\n- 边界：静态建模任务不要求多帧。\n\n## HTA-009：重复单参调用未采用 batch primitive\n\n- 状态：已修（`set_parms` 已发布，workflow 规定三项以上优先 batch）\n- 证据：`f608bfab` 有大量 `parm().set` 循环；`40054277` 有 9 个步骤一次调用 `set_parm` 3–18 次。该草地会话唯一 capability snapshot 只曝光旧 20 动词，尚无 `set_parms`，因此这是“当时缺失、现已补齐”的正向证据，不记为 agent 漏用。\n- 症状：code/ledger 膨胀，单项失败使整段 exec 中断或难读。\n- 根因：guidance 没有明确“同节点三项以上优先 set_parms”的采用阈值。\n- 修复：guidance/workflow 规定同节点三项以上独立赋值优先 `set_parms`；保留 `set_parm` primitive。\n- 边界：赋值间有条件依赖、需逐项读取结果时仍用 `set_parm`。\n\n## HTA-010：scene/timeline 只读信息缺少意图层入口\n\n- 状态：已修（`scene_info`）\n- 证据：`40054277` 步骤 #2–#5 为读取 HIP/版本/播放范围连续三次 API 失败后才成功；`f608bfab` 的时间线/bookmark 需求曾连续 6 次 query 探索 API，并大量裸用 playbar/setFps。\n- 症状：任务开场或时间线需求反复猜 `hou.playbar`、timelineStart 等 HOM 名称。\n- 根因：词表只有 node/parm/geometry 等域，scene/timeline 域仍为空。\n- 修复：`scene_info` 只读；`set_timeline` 管明确字段；bookmark 按 list/create/delete 拆分并支持同名安全替换/精确删除。headless round-trip 恢复原时间线、无临时 bookmark 残留。\n- 边界：一次性的特殊全局状态仍可走只读 hou；scene_info 不应返回巨大场景清单。\n\n## HTA-011：代码引用 ch() 但 spare parameter 不存在，动画静默为零\n\n- 状态：已修（`create_spare_parms`）\n- 证据：`40054277` wind snippet 引用 amp/speed/wavenum/dirx/dirz，但节点没有这些参数；`geo_frame_diff(1,12)` 为 100% unchanged。\n- 症状：VEX 编译/cook 无 error，参数赋值代码因 `parm(name) is None` 被跳过，所有驱动值为 0。\n- 根因：误以为写 `ch(\"name\")` 会自动创建参数；SideFX UI 需要显式 Create Parameters。\n- 修复：扫描 `ch/chf/chi/chv/chs` 创建缺失 float/int/vector/string spare 参数并应用显式 defaults；H21 临时 Wrangle frame 1/12 mean delta 0.483。\n- 边界：`chramp` 等复杂引用不自动猜结构，列入 unsupported 后显式建 interface。\n\n## HTA-012：动词 ledger 的负零破坏 lossless JSON\n\n- 状态：已修（统一 JSON-safe 归一化 + headless/live bridge 回归）\n- 证据：`71d76525` 工具调用 #18/#19 连续返回 `tool \"houdini_exec\" returned invalid output: value is not lossless JSON`；两步都包含 quaternion/vector 统计，容易生成 `-0.0`。桥的 `_jsonable` 只替换非有限 float，仍原样保留 `-0.0`；动词 ledger 又独立收集未经归一化的统计结果，因此 agent 即使自行清洗 `__result__` 也无法规避。\n- 症状：Houdini 代码已经执行，工具层却丢弃整个结果；第二次在 `__result__` 上做 JSON 清洗仍失败，造成重复探测和不确定场景副作用。\n- 根因：dsh 工具要求 lossless JSON，`-0` 属于拒绝值；bridge 只处理 NaN/Infinity，没有在 `__result__`、verb args/result、job envelope 的共同递归边界把负零规范化为正零。\n- 修复：唯一 JSON-safe coercion 对 `value == 0.0` 返回正零，hou Vector/Color/Matrix 逐分量复用；verb ledger、result、job 共用。H21 headless 回归覆盖负零/NaN/Infinity，live bridge 同时返回 `verb_help` ledger 与 `zero: 0.0`，不再被 lossless JSON 拒绝。\n- 边界：字符串中的 `\"-0.0\"` 是普通文本，不应改写；真实有限负数必须保持。\n\n## HTA-013：逐帧自动取景污染动画 render diff\n\n- 状态：已修（`render_view(framing_frame=)` + GUI 固定构图回归）\n- 证据：`71d76525` 工具调用 #43 frame 25 的 framing center/size/dist 为 `[0.0213,0.7147,0.0563] / 22.9003 / 50.5667`，#46 frame 55 变为 `[0.0849,0.7170,0.0217] / 22.9754 / 50.7324`；随后 `render_check` 报 21.1% changed pixels。`render_view` 实现按目标帧 bbox 每次重算 camera，因此该差值同时包含相机平移/缩放。\n- 症状：pixel diff 看似明显，但语义视觉认为两帧几乎相同；agent 把被相机变化污染的指标当作动画成立证据。\n- 根因：单帧自动构图适合静态验证，不满足动画 A/B 的固定观察条件；工具未显式标记“相机构图与 ref 不一致”。\n- 修复：扩展现有视觉意图 `render_view(..., framing_frame=)`；A/B 传同一参考帧后 camera frame/center/size/dist/eye/direction/source signature 完全一致。H21 GUI 用 `$F*0.1` 动画 source 在 frame 1/2 回归，source fingerprint 确实变化而 framing 完全相同；暂不新增组合动词。\n- 边界：静态单帧自动 framing 正确；正式镜头的相机本身有动画时，camera motion 是目标的一部分，不能强制锁定。\n\n## HTA-014：靠失败或读仓库源码发现动词契约\n\n- 状态：已修（`verb_help` + guidance/关键 docstring）\n- 证据：`71d76525` 工具调用 #3 把 `search_tab_menu` dict 当 list、#7 把 `read_parms` list 当 dict、#12 猜错 `geo_attrib_stats` keyword、#31 假设 `describe` 含 `ok`；中途 #13–#16 用 grep/read 打开插件源码才纠正。`a41c853a` 已曝光 `verb_help`，但 #8 仍把 `read_parms` list 当 dict，导致完整 exec rollback。正常 Houdini 会话工作区是 `$HIP`，仓库源码不应成为运行期契约入口。\n- 症状：一次本可只读发现的签名/结果字段，变成 exec 失败、undo、重复 batch；有时失败发生在修改之后。\n- 根因：system prompt 为控制体积只列意图，没有统一的运行期动词契约自省；Python `inspect.signature` 虽可手写，但 agent 不知道 registry 边界和结果含义。\n- 修复：新增 `verb_help(name)` 返回准确 signature/docstring、未知名相似建议；guidance 要求不确定时先查。`read_parms` doc 明确返回 `list[dict]`，guidance 明确 `cook_node` 才拥有 `ok/healthy`、`graph` 要围绕数据节点调用。H21 headless/live bridge 回归通过。\n- 边界：节点自身的 SideFX 参数/帮助仍由 `list_parms`/`describe` 和未来 `node_help` 负责；`verb_help` 不替代它们。\n\n## HTA-015：节点类型注册表被误当成真实 Tab 菜单\n\n- 状态：已修基础能力、待新 Karma 用户 trace 验证（parent-aware entry + allowlist recipe）\n- 证据：`71d76525` #51 已查到 `karmarendersettings`，#53 的 LOP `principled` 为空，\n  但 #56 通过全局 VOP registry 找到 Principled 后在 #59 强制创建；#87 又选择 hidden/\n  deprecated 的一体式 `karma` LOP。H21.0.440 shipped shelf 对照：真实入口是\n  `vop_karmamtlxsubnet`（Karma Material Builder）和 `lop_karma_setup`（创建 Render\n  Settings + USD Render ROP）。\n- 症状：图能渲染，但用户按 Tab 找不到材质节点；setup 缺配套 ROP/表达式，随后\n  `LopNode.render()` 失败并改走按钮轮询。\n- 根因：`search_tab_menu` 只枚举 nodeTypes；`tab_create` 用 `ctx_type` 猜 shelf id，失败后\n  裸 `createNode`，绕过 hidden/deprecated 和 Material Library tab mask。\n- 修复：`search_tab_entries(parent, query)` 区分可见 node/tool；`tab_create` 拒绝隐藏旧类型\n  和 Material Library 根层 shader；`tab_apply` 运行时验证真实 tool/context，再通过\n  SideFX initializer/稳定 setup 契约的非交互 adapter 创建 Karma Setup/Material Builder，\n  返回全部节点并恢复用户状态；新增 Solaris/Karma workflow 与 USD 自省。H21 标准\n  USD Render ROP 实际出图同时修复 `render_frame` 的 outputimage/foreground 契约。\n- 边界：传统 Principled/Karma CPU 旧资产不是一律非法；用户明确选择并接受限制时可用，\n  但不能作为新 XPU 工作的默认或伪称 Tab 原生路径。\n\n## HTA-016：compaction replay 膨胀 trace 统计\n\n- 状态：已修（callId 去重 + replay diagnostics）\n- 证据：`71d76525` 原报告 116 个 tool result；seq 22231–22245 在 `compaction/prune`\n  间重放 8 个旧 callId，唯一 `tool/call` 实际 108。动词原报 238，去重后 232。\n- 症状：长会话看似突然多出同一批旧代码，调用/动词/失败/耗时被重复计入，阶段顺序也被\n  replay 时间污染。\n- 根因：extractor/report 遍历每个 `tool/result`，未区分执行结果与压缩历史重放。\n- 修复：`trace-session-lib.uniqueToolResultEvents()` 以第一个 result 为执行证据，后续同\n  callId 写入 `replayedResults`；evidence/HTML 共享该实现。当前 session 回归为\n  108 calls / 232 verbs / 8 replays。\n- 边界：无 callId 的未来 schema 仍保留给调用方判断；不能仅凭内容 hash 去重两个真实的\n  相同调用。\n\n## HTA-017：把路径依赖状态压成独立绝对控制通道\n\n- 状态：确认（S2：用户 trace + H21 disposable 正反例回归；工具形态仍待更多任务）\n- 首次/最近证据：`a41c853a` #26、#58、#59、#60–#64；历史上已移除的\n  `houdini/tests/regress_rig_state_model.py` 曾在 H21.0.440 通过 6/6，当前最小等价回归待重建。\n- 症状：单个面/关节/segment 能正确运动，参数也有 key；但 agent 用初始 membership 和若干\n  独立累计角度表达有序、非交换操作，只验证第一段和最终 rest，就宣称完整序列成立。\n- 根因：没有把 stable identity、logical state、ordered transition 当成 rig 输入/输出契约；\n  完成门也没有覆盖第二个非交换步骤和 sequence midpoint。\n- 建议：rig/animation 先按 channel、rigid pieces、hierarchy、skin、character graph、simulation\n  分类；路径依赖任务要求稳定 `name/piece_id`、每步更新 membership/transform，并验证 first、\n  非交换转折、mid/end、recovery。官方系统选择与工具预算见 `docs/rig-animation-design.md`。\n- 反例/边界：单个独立通道、互不影响的并行动画、明确只要“一层转一下”的装饰动画可以用\n  绝对参数；不能因此强制引入 KineFX/APEX。\n- 回归：27 个 packed pieces 经显式 point `name` → Transform Pieces；正确模型在 R 后更新\n  logical membership 再选 U，和初始 membership 绝对通道在第二步活动集合/最终 R→U 状态\n  分叉；两者都能在 inverse 结束回 rest，证明 endpoint equality 不足。轴心 piece 的 P 不动\n  但 orient 改变，完成门必须同时看 P + orient/transform。\n- 下一验收：再收集一个层级机械任务和一个 KineFX/skin 任务，判断是否需要 piece-state\n  自省动词；当前 `geo_frame_diff(P)` + `geo_frame_diff(orient)` 已覆盖基准，不先新增工具。\n\n## HTA-018：在 bridge exec 内加载 HIP 破坏执行与重连生命周期\n\n- 状态：确认/P0 本机可复现（不得简单封装 scene_open）\n- 首次/最近证据：2026-08-21 ordered 魔方 GUI 验收。单 exec 的 load→render→restore 返回\n  `ok=true` 空包且无产图；拆分后加载 ordered HIP 会让该次请求无 result 但场景已切换；恢复\n  原 HIP 的 UTF-8 load 关闭 HTTP 连接并启动新的 Houdini 进程，bridge 8765 消失。\n- 症状：调用方无法知道 load 是否执行、finally 无法可靠恢复、images/result 丢失；严重时\n  共享 Houdini 重启，agent 后续无法检查当前 HIP。\n- 根因：`hou.hipFile.load()` 重置当前场景/会话生命周期，与正在该 Houdini 进程内执行并等待\n  HTTP 回包的 bridge transaction 互相冲突；它不是普通 undoable scene edit。\n- 修复/守卫：guidance 禁止 bridge exec 内 `hipFile.load`。用户 HIP 打开/替换走 Houdini UI；\n  离线分析用 disposable hython。未来若自动化，必须在 Host 侧实现 unsaved confirmation、请求\n  结束前调度、bridge/process reconnect、目标 HIP 验证和失败恢复，不能新增薄 wrapper。\n- 边界：`hou.hipFile.save()` 不重置场景生命周期，但仍是不可 undo 文件写；现由只保存当前已命名\n  HIP 的 `scene_save` 覆盖并回报文件/dirty 证据。\n- 回归：bridge 现以 AST 在执行前无条件拒绝直接 `hou.hipFile.load(...)` 与\n  `hou.hipFile.clear(...)`；`allow_raw` 也不能绕过。H21 scene regression 证明错误返回且当前\n  HIP 未切换；裸 `hipFile.save()` 由 Raw Gate 指向 `scene_save`，不能再用豁免旁路。\n- 下一验收：设计 host-level open handshake 前不重试 live load；若未来支持 scene open，\n  必须先替换本守卫并完成进程重连/unsaved/恢复集成测试。\n\n## HTA-019：动词结果内部箭头破坏 ledger 参数/结果切分\n\n- 状态：已修（结构扫描分隔 + evidence/report/client 同语义 + 真实 trace 回归）\n- 首次证据：`83a553e7-d728-4044-b700-9a637e787d55` 的唯一 `houdini_query`；\n  `verb_help('set_keyframes')` 返回 signature `(node, ...) -> dict`。\n- 症状：verb 名和计数正确，但 evidence 把 result 内 signature 的 `->` 当成调用分隔，导致\n  args 吞入半段 result、result 从返回类型中间开始；详细工具证据不可信。\n- 根因：extractor、HTML report 和 client 各用 greedy regex 解析\n  `verb(args) -> result (Nms)`，没有识别 JSON string/array/object 边界。\n- 修复：共享 `parseVerbLedgerLine()` 从固定前后缀进入，扫描字符串 escape 与 `[]/{}` 深度，\n  只接受调用参数顶层的 `) -> `；extractor/report 共用，client 使用同算法。回归同时覆盖\n  result 中箭头和 args 字符串中的字面 `\") -> \"`。\n- 边界：host 为控制模型结果体积会把 detail 截断到 400 字符；截断 JSON 保持字符串是正确的，\n  不能伪装成完整对象，但 args/result 分界必须保持准确。\n- 回归：重新提取该 session 后 `verb_help.args == '[\"set_keyframes\"]'`，detail 从\n  `{\"name\":\"set_keyframes\"...}` 开始；3 calls / 2 verbs / 0 failure/mutation/advisory 不变。\n\n## HTA-020：提示已曝光但 raw gate fail-open，模型采用率归零\n\n- 状态：已修并获新 session 正向证据（默认开启 + 已覆盖调用不可豁免）\n- 首次/最近证据：自行车 trace 已记录 deepseek-v4-flash 连续忽略 advisory；\n  `c6481bf1-3a83-4f53-9bf8-398b9c8fa151` #1–#3、#9–#24。\n- 症状：最新会话的 system snapshot 已曝光 46 个 verb，rig/SOP skills 均成功加载，但 20 个\n  Houdini 调用全部纯裸；#9–#24 连续 16 个 mutation call 收到 raw hint 后仍不切换，最终\n  7 个工具硬失败、多个被吞 cook failure、0 个 todo 完成且无交付。\n- 根因：模型路线 `deepseek-v4-flash-vision-exp` 触发了严重 instruction-following 退化，但系统\n  把安全性寄托在模型自觉：bridge `_raw_gate` 默认关闭且重启复位；旧 `allow_raw` 又能整段\n  旁路已覆盖调用，使实验 gate 即使开启也可被泛化理由降级回 advisory。\n- 修复：bridge 默认开启 gate，重启恢复安全默认；`allow_raw` 只豁免没有直接 verb 的低层\n  mutation，不能豁免 `createNode/parm().set/cook/destroy` 等明确覆盖调用；低层代码必须与\n  scene-operation batch 拆分。receiver 不唯一的 `setPosition` 降为 heuristic，避免把\n  GeoPoint 写位置误报成 `layout_nodes`。host schema/guidance 与真实边界同步。\n- 反例/边界：纯读取继续允许裸 HOM；低层 `hou.Geometry`/UI/显式 HIP save 可用带理由的独立\n  `allow_raw` batch；插件开发者仍可在 Houdini Python Shell 临时关闭 gate，但不跨桥重启持久化。\n- 回归：`tools/tests/dsh-bridge-raw-gate.test.py` 覆盖默认开启、covered call 带豁免仍零副作用、\n  read-only 放行、`dict.setdefault` 聚合放行、uncovered mutation 先拦后豁免，以及 GeoPoint\n  `setPosition` 不再假映射。蜘蛛 trace `9b7bd919` #25/#94 的 covered mutation 均在执行前拦截，\n  随后分别改用动词/移除 query mutation；成功 exec 的动词覆盖为 48/48，成功裸修改为 0。\n- 边界：调用含动词率仍会被合法只读探针稀释，不能用它单独判断 Gate 是否回归；看成功裸修改。\n\n## HTA-021：Host 目录与运行中 Bridge 不同代\n\n- 状态：P0 已修代码并有确定性测试；待 runtime restart + 新 session 部署验收\n- 首次证据：蜘蛛 trace `9b7bd919` capability snapshot 宣称 47 verbs；#12 19:19:27 的\n  `verb_help('create_spare_parms')` 返回旧签名（缺 `allow_foreign`），现场\n  `verb_help('node_provenance')` 返回未知动词。\n- 症状：模型看到新目录但执行的是旧 Bridge；ownership 等安全能力可在需要时才突然失败，\n  `used/47` 分母也不再描述真实可用能力。\n- 根因：Host/plugin 与 Houdini 进程内 Python 模块有独立 reload 生命周期，过去没有代际握手。\n- 修复：构建从 `tool-design.md` 生成 Host 名称/hash；Bridge 从实际 `_VERBS` 独立计算\n  `/health.verbCatalog`；Host 在 `/exec`/`/jobs` 前比较并 fail-closed，提示\n  `Repair and restart runtime`。静态契约与假 HTTP server 回归覆盖 mismatch 零 `/exec` 副作用。\n- 边界：同 checkout 路径、package version 或 Host catalog 都不能证明 Houdini 已 reload；\n  完整重启后旧任务节点因进程内 provenance 丢失而安全降为 foreign。\n- 下一验收：重启 runtime，新建 Houdini session，确认 `/health` hash 一致、\n  `node_provenance` 可用、capability snapshot 与 `verb_help` 同代。\n\n## HTA-022：视觉工具 transport 成功被误当成语义识图成功\n\n- 状态：P0 evidence/完成门已修；待新 session 验证 agent 不再夸大\n- 首次证据：蜘蛛 trace `9b7bd919` #122 返回\n  `ok:false/STRUCTURED_BOOTSTRAP_DISABLED`；#123 明确说模型仅接受文本、无法看图；#128/#129\n  只把图片展示给用户。旧 evidence 却把四次都记为 `ok:true`，`completionRisks=[]`，#130 仍把\n  vision todo 标 completed，最终文本声称双帧视觉确认。\n- 根因：旧提取器只看 tool transport/`isError`，且把 bootstrap、inspection、presentation\n  合并成一个成功布尔值。\n- 修复：evidence schema v2 记录 `role/transportOk/semanticOk/reason`；结构化 `ok:false` 和\n  中英文拒绝看图判 semantic failure；只有 inspection success 能满足视觉完成门。完成视觉 todo\n  而无证据另报风险。重提取该 trace 产生三个 completion risks。\n- 反例/边界：`render_view`/`render_check` 成功仍是有效文件/像素证据，但不能证明蜘蛛形态、\n  穿模或自然步态；`vision_present` 对用户交付有价值，但不是 agent 自证。\n- 下一验收：换用实际可读图的 provider 跑同图 A/B，确认成功 inspection 为 true；再用文本模型\n  重跑一次，确认 todo 保持未完成或最终明确写“视觉语义未验证”。\n\n## HTA-023：自生成质量标准被写成外部真实性证据\n\n- 状态：P1 强完成协议已获两模型建模 + 一个程序化特效的跨域正向行为证据；合同/扰动/新鲜证据门已部署验收，视觉语义完成门仍有新候选缺口。\n- 首次证据：`d6df94d7-d778-4d35-8529-a6f3e9f4e804`。#3 只确认“山地车”和\n  SOP + render_view 交付；没有外部参考、目标 LOD、允许简化或程序化控制合同。#7 起把尺寸直接\n  写入多个 VEX；首轮 #21/#23 看完整车远景后宣布验证通过。用户纠正后 #26 才手写四类局部检查，\n  最终又把轴距/轮径/头管角等称为“真实山地车范围”，trace 中没有来源，部分数字也没有同级工具证据。\n- 最近证据：`e0bc309b-ab8b-4a40-b636-14217cd2b91f` 已加载 P0 preset 并主动写出目标、无参考假设、\n  14 个控制、关系与视图计划，证明行为层生效；但 `web_search`/`read` 明明可用却均未用于参考，\n  没有 LOD/允许简化，未读取 quality-contract reference，首张 render 前已创建 116 个节点，未做\n  控制扰动。最终又把修改前的 5740/4561 写入报告，实际末次 render fingerprint 为 6027/4848。\n- 两模型复核：`937bfa1e-f183-46e2-a717-d930bd701c34`（qwen3.8-max）与\n  `73bc9795-d45c-4774-ae32-c2a6291dd2b8`（k3）均读取质量合同、建立集中控制/骨架、执行关系门，\n  并真实完成 `wheel_radius` 扰动、受影响验证、恢复和新鲜统计。Qwen 另做 web 调研和结构化\n  goal/todo，K3 主动检出后胎/车架 `-17.76mm` 穿插并修到 `+3.33mm`，证明 P1 已从“会说合同”\n  前进到“会按结果返工”。仍有共同缺口：mutation 前没有明确 LOD/允许简化；Qwen 四张 render\n  近黑或视角错误却只按文件成功，K3 只看被裁切的 viewport 局部。\n- 症状：产物可辨认、cook 和 render 都成功，但部件关系错误需要用户指出；agent 能补局部问题，\n  却不知道还有哪些未进入自己检查清单，完成声明的证据等级高于事实。\n- 根因：P0 的 `research → clarify → contract` 只在主 preset 中可见，而骨架/扰动/新鲜证据门藏在\n  “按需阅读”的 reference；agent 会复述合同，却没有把它作为持续更新的证据账本。\n- 修复：主 SOP skill 对符合条件的任务强制读取质量合同，并内联研究、骨架、关系账本、视觉批评、\n  扰动恢复和末次 mutation 后刷新证据六个 checkpoint；preset 要求逐项 `pass/fail/unverified`。\n  evidence/report 新增 `qualityLoopEvidence` 与确定性风险：合同缺字段、未加载质量合同、可用研究未用、\n  无来源真实性、过晚首次视觉、无控制扰动、关系合同无证据和最终几何统计陈旧。\n- 审计纠正：两模型 trace 暴露 `CTRL(S)` 子节点扰动、goal/todo 合同、反向词序骨架描述、明确\n  `unverified` 视觉 todo 和逗号/中文面数格式均被旧提取器漏读；这些是 evidence 假阳性/未知，\n  不是 agent 未执行。提取器与反例 fixture 已按可观察事实扩展。\n- 交互/视觉窄修：重大选择使用 2–4 个互斥选项、推荐项、影响说明和自定义文本补充；唯一\n  路径/名称/精确值才用纯文本。SOP 视觉门要求声明资产轴向，并用 render check 拒绝近黑、空白、\n  错误视角或裁切图片；语义视觉失败不等于像素展示门可跳过。\n- 跨域部署复核：`bbaedb46-60f0-40c9-b59a-52795c727895` 的沙尘任务在首次 mutation 前加载\n  SOP skill/质量合同、用三组有效选项确认形态/技术/交付，写出镜头级轮廓合同，集中 12 个控制，\n  完成 `ring_speed` 扰动/恢复及末次修改后的 cook、帧差和三帧图像证据。说明研究→澄清→合同→\n  扰动→新鲜证据已跨建模/特效生效；仍未在 mutation 前披露无地面碰撞、SOP 点云近似等允许简化，\n  且最终将用户原始“电影感”标为 `unverified` 后仍以“完成”交付。\n- 反例/边界：抽象/风格化任务、用户给出完整 recipe、简单可逆编辑不需要强制研究或问卷；用户\n  明确授权 agent 自选时可以继续，但必须披露选型和未验证的真实性边界；用户已提供参考时不强制\n  额外 web 搜索。regex 风险只证明可观察步骤缺失，不冒充艺术质量评分。\n- 下一验收：再用一个体积/模拟任务检查简化是否在 mutation 前披露，并为承诺形态提供独立于整体\n  hero 图的数值或分层诊断；不再重复验证已通过的 choice-first/扰动基础路径。\n\n## HTA-024：ask schema 近似字段静默退化成空白输入框\n\n- 状态：P0 fail-closed 修复已部署；合法 choices 真实 UI/trace 验收通过，畸形字段的现场拦截重试路径仍只有确定性回归。\n- 首次/最近证据：`645cd673-b9f7-4e99-a547-d8bf7270c7e0`，tool/call seq 262。K3 已生成三组\n  合理选择内容，但问题对象使用带尾随空格的 `\"header \"`、`\"options \"`；UI 因执行器只读取精确\n  `header/options` 而为三题都显示自由文本框。system snapshot 已含 choice-first 规则，说明仅靠提示\n  不能保证 JSON key 精确。\n- 根因：上游 `@deepseek-ai/dsh-tool-ask-user@0.1.1-rc.2` 的 question/option schema 设置\n  `additionalProperties: true`；参数校验接受近似/未知字段，执行器又静默忽略它们。DSH\n  `tools/pre-execute` 明确禁止改写已记录参数，因此不能在中间件偷偷 trim key。\n- 修复：dsh-houdini agent scope 注册 pre-execute guard。`ask_user_question` 的 question 只接受\n  `id/question/header/options/multi_select`，option 只接受 `label/description`；未知或尾空格字段在 UI\n  前拒绝并返回精确重试说明。选择型问句没有 2–4 个 options 同样拒绝；路径、名称、精确数值和\n  自由补充等天然文本问题继续放行。日志参数、展示和实际执行保持一致。\n- 反例/边界：guard 不改写参数、不替换上游工具、不把所有问题强制成选择题；合法 custom 回答由\n  原 ask 工具/UI 保留。它只在挂载 dsh-houdini 的 agent scope 生效，不影响其他 DSH agent。\n- 回归：新增 `ask-user-choice-guard.test.mjs` 覆盖合法选择、尾空格 key、无 options 的选择型问句、\n  选项数边界、option key 近似、精确路径和自由补充；`npm test` 现为 7 个 Node 测试文件全绿。\n- 部署验收：`bbaedb46-60f0-40c9-b59a-52795c727895` tool call #5 / seq 216 使用精确\n  `header/options`，三题各有 2–3 个互斥选项和影响说明；result 完整记录三项选择，用户界面不再退化\n  成空白输入框。该次模型首次即生成合法 schema，因此没有触发 guard 的拒绝分支。\n- 下一验收：未来自然出现一次近似字段时，确认畸形调用只形成工具错误、不会打开问卷，且模型用\n  精确 schema 重试；无需为制造错误专门污染用户任务。\n\n## HTA-025：整体体积预览被目标先验误读为承诺形态\n\n- 状态：候选 E1（单 trace + 人工同图复核）；先修审计漏检，不发布沙尘专用强规则或新动词。\n- 首次/最近证据：`bbaedb46-60f0-40c9-b59a-52795c727895`。#32/#33 的 f24/f60/f120\n  `render_view` 文件、像素 bbox 和亮度均有效；#34–#36 确实把三张图送入支持图像的 K3。随后\n  assistant seq 4879 把 f60 称为“clear ring/donut with raised outer rim and central column”。人工复核\n  同一原图时，f60/f120 主要呈现为黑底上的灰色扁平椭圆尘团，环孔、沙浪墙和中心柱均不足以可靠\n  分辨；两轮返工后的 f60 仍是实心团块式读法。\n- 症状：transport、像素门和 semantic access 都成功，模型也写了缺陷清单并迭代，但目标词先验使\n  它把模糊整体图升级为形态通过；`geo_frame_diff(P)` 只证明点在动，source detail 的\n  `ring_radius_now` 只证明公式半径，不证明最终 VDB 密度仍保留可见环形结构。\n- 根因候选：环形墙、中心柱与内部贴地尘被合成到同一中性灰 OpenGL 体积，iso hero 图发生遮挡和\n  投影塌缩；完成门没有要求承诺的体积分层形态用独立诊断视角、隔离分支或场采样复核。同一模型既\n  知道目标又裁判图像，弱证据容易被目标描述补全。\n- 当前修复：evidence 的开放式质量触发扩展到电影感/镜头级/可靠验证/可调效果；最终以“完成”交付\n  却把用户原始质量维度列为 `unverified` 时新增确定性风险；生产 persona 明确核心项 fail/unverified\n  只能判 partial/incomplete。重新提取本 trace 应报告\n  `quality_contract_incomplete(simplifications)` 与 `requested_goal_reported_unverified(cinematic)`。\n- 候选建议：体积/合成效果的承诺形态至少再给一种独立证据（例如隔离层、正交/切片诊断或密度\n  采样），并把结构运动预览与材质/灯光/颜色意义上的“电影感”分开签约；具体工具形态等待第二个\n  独立模拟任务，不因本例直接新增 `volume_*` 动词。\n- 反例/边界：抽象云团、只要求数据网络、用户明确接受不可判形态的中性预览时，不强制 hero 级\n  外观；正式 Karma 画面本身也不能替代隐藏层/密度关系等数值证据。\n- 下一验收：用另一类体积效果（非环形冲击）要求两个可区分的形态层，检查独立诊断能否阻止整体\n  图像的目标先验误判，再决定扩展现有 geometry/volume 自省还是新增通用动词。\n\n## HTA-026：query/exec 只靠提示分工，query 实际包含副作用\n\n- 状态：P0 Bridge 边界已修；待 Repair/restart 后真实 session 验收。\n- 证据：2026-08-28～31 discovery session 中，多个 `houdini_query` 调用了 `set_timeline`、\n  `cook_node`、`set_parm(s)`、`tab_create/delete_node`、`render_view` 或裸 `pressButton/parm().set`；\n  旧 evidence 只检查裸方法，进一步漏掉了动词 ledger 中的副作用。\n- 根因：Host 只用 description 要求“read-only”，Bridge 的 `/exec` 对 query/exec 使用同一权限；审计器\n  又把“没有裸 mutation”误当成“没有 mutation”。\n- 修复：query 不再暴露 `allow_raw`，Host 发送 `read_only=true`；Bridge 不向 query namespace 注入修改\n  动词，并在执行前拒绝修改动词、cook、render、viewport capture 和裸修改。evidence 同时检查裸方法\n  与 side-effect verb ledger。\n- 反例/边界：`scene_info`、`describe`、`read_parms`、几何/USD 统计和真正只读 HOM getter 可继续在\n  query；需要改变 frame/cook/render 的验证不是“读”，必须转 exec/job 并接受其回滚/审计语义。\n\n## HTA-027：Houdini undo 成功但 Bridge ownership provenance 未回滚\n\n- 状态：P0 修复并通过 H21 regression。\n- 证据：在同一 mutation exec 中删除当前 session 所有节点后故意抛错，Houdini `performUndo()` 能把\n  节点恢复；旧 `_OWNED_NODE_SESSIONS` 已在 `delete_node` 时移除条目，恢复节点随后被误判为 foreign。\n- 根因：事务只覆盖 Houdini undo stack，没有把 Bridge 进程内的所有权注册表视为同一事务状态。\n- 修复：mutation 前快照 registry；只有 `performUndo()` 成功时同步恢复快照。回归检查节点存在且\n  `node_provenance` 仍为 `owned_current_session`。\n- 反例/边界：Houdini 进程重启后 registry 有意丢失，旧节点应安全降为 foreign；不能跨进程伪造\n  ownership。若 undo 本身失败，也不能恢复 registry 冒充场景已回滚。\n\n## HTA-028：像素工具被当作语义识图，掩盖 inspection 失败\n\n- 状态：P0 evidence 修复；旧 trace 已重提取。\n- 证据：第二模型机械 session 的 `read_image` 与 `vision_glance` 均失败，只有\n  `vision_pixel_diff` 成功；旧报告仍把它列为 `semanticOk=true`，从而没有报告 render 缺少成功识图。\n- 根因：旧分类把所有 `vision_*` 统一当作 semantic inspection，没有区分 transport、像素事实、\n  presentation 与内容理解。\n- 修复：只有 `read_image`、glance/ground/detect/OCR 等 inspection 能提供 semantic success；\n  pixel diff、crop、dominant colors 等归 `pixel`，只证明客观像素/派生事实。该 session 现在稳定产生\n  `render_without_successful_vision`。\n- 反例/边界：像素证据仍可证明新鲜度、差异、亮度、bbox 或颜色，不应删除；它只是不能回答对象\n  是什么、关系是否合理、画面是否满足语义目标。\n\n## HTA-029：provider/额度终止被压扁成普通未完成\n\n- 状态：P0 evidence 修复；真实 quota 与 network error 已复核。\n- 证据：一条模拟 session 的最终 `turn/end` 明确含 `insufficient_quota`，旧 terminal 只有\n  `lastEventType=turn/end`；另一条 session 在无任何 assistant/tool 工作前因 `network_error` 终止，\n  旧报告仍误报质量合同缺失。\n- 根因：提取器没有解析 `turn/end.reason`，完成风险也没有“工作是否实际开始”的前置条件。\n- 修复：terminal 记录 completed/quota/external error 的 category/code/message；quota 单列\n  `quota_exhausted`。零 assistant、零 tool 的外部启动失败不运行质量闭环判定。\n- 反例/边界：quota 不等于 agent 能力失败，也不等于产物无价值；若已有工具执行，仍保留未完成 todo、\n  无最终交付、质量门缺失等可观察风险，不能用 provider 原因洗掉执行事实。\n\n## HTA-030：保存状态与渲染成功缺少可审计的新鲜度\n\n- 状态：P0 工具合同已修；H21 headless regression 通过，待 GUI runtime 验收。\n- 证据：真实任务用裸 `hou.hipFile.save()` 逃生，旧 `scene_info.hip_saved` 不能区分已命名和已落盘；\n  MCP 参考运行也出现 save 返回成功但 live scene 仍 dirty。旧 `render_frame` 只验证目标存在/非空，\n  预先存在的旧文件可能被误当成新渲染，临时 picture 覆盖还会泄漏到 ROP。\n- 根因：合同用单布尔压缩了 path、dirty reliability 与磁盘事实；render 没有 pre/post fingerprint，\n  也没有把临时参数纳入恢复状态。\n- 修复：`scene_info` 拆为 `has_named_path/has_unsaved_changes/dirty_reliable/clean_on_disk`；\n  `scene_save` 只保存已命名场景并返回 dirty/bytes/mtime。`render_frame` 比较前后 bytes、mtime 与有界\n  内容摘要，只有新建或变化才 fresh，并 finally 恢复 picture/frame/foreground。\n- 反例/边界：H21 `hython` 保存后 dirty flag 仍不可靠，必须返回 null/false 边界，不能硬说 clean；\n  文件指纹证明本次产物变化，不等于渲染内容语义正确。\n\n## HTA-031：driver/binding 运动冒充最终 driven geometry\n\n- 状态：确认/P0 契约修正；原失败实例的新 session 正向回归通过，未见同族与反例仍待验收。\n- 首次/最近证据：`7bf34ae9-f148-4920-9599-9c3f3c77f438` #87 的 actual unpacked TCP 在运动帧\n  最大误差 10.07；#94 改测 packed anchor transform 后误差变成 5.4e-7；#96 只比较 5 个 skeleton\n  joint P；#123–#125 的最终图仍是直刚体 + 弯骨架，vision 明确回答主体 straight，最终报告却宣称\n  刚体弯曲通过。当前 H21 viewport 同图复现；首版 `dsh-kinefx-fk` 仍因混合输出总 bbox 变化假绿。\n- 症状：channel/joint、绑定元数据、总 bbox 和 pixel diff 都变化，cook 也无 warning，但用户最终要\n  播放或渲染的 geometry/state 保持 rest、缺失或错误。\n- 根因：任务合同没有区分 `driver state → binding/evaluation → driven deliverable`；验证又从实际\n  输出退回上游 proxy/anchor，或让 driver visualization 污染 bbox/render diff。\n- 修复：rig skill 内联三层交付合同与失败证据不降级规则；KineFX reference 将 Attach Joint Geometry\n  限定为 control/capture 辅助，rigid deliverable 路由到 Capture Packed Geometry → Joint Deform。\n  回归直接验证 final link 的 world center、orientation/extent、recovery、boneCapture 和无 skeleton\n  polygon，并保留 skeleton-only bbox 会动的负对照。\n- 正向回归：`975f49a0-97f2-44d9-b290-76716741cc54` #1/#2 读取新 skill/reference，#40–#53\n  建 rigid capture，#55–#59 建 deform/final OUT，#63/#64/#68/#86 验实际 piece/marker/FK，#88/#89\n  刷新最终 render/vision，#90/#91 flow layout 并 clean save。同模型同提示由 130 降到 92 tools，\n  但仍有 20 failures，主要来自 skeleton HOM 与 capture 参数探索，故效率 fast path 继续收敛。\n- 反例/边界：用户只要 skeleton、control shapes、capture influence 或调试 overlay 时，driver/binding\n  本身可以是 deliverable；普通 channel 或 solver 任务沿用同一分层，但不强制 KineFX 节点。\n- 下一验收：新低能力模型 session 使用未见的层级刚体任务，确认先声明三层合同、选择正确 driven\n  output，并在隐藏 helper 后完成数值与固定构图视觉验收；另用纯 control-shape 任务确认不会误触发\n  Joint Deform。\n\n## HTA-032：创建路径被误读成 legacy rig 架构\n\n- 状态：确认/P0 guard 已实现，待新 session 正例与 scene-parenting 反例。\n- 证据：未见层级刚体 session `db2cf0bf-a8ca-4907-a373-7ab2d41f31ce` #1 已加载最新 rig skill，\n  但未读 KineFX reference；#2 把“在 /obj 下”直接写成 OBJ hierarchy；#7 的 SOP `connect` 方向反转，\n  display OUT 为 0 点；#10 又把 Object parenting 接成 platform→arm→base。0 geometry/render/vision、\n  5 unfinished todo，两个 turn 均由用户中止，场景 dirty 未保存。\n- 症状：用户的 context/path 词被当成 representation 授权；模型绕过默认现代流程，并用 generic\n  dataflow verb 猜 scene parenting 方向。\n- 根因：主 skill 的 fallback 边界不够显著；仅靠提示无法阻止已曝光规则被较弱模型忽略；`connect`\n  在 SOP/OBJ context 副作用不同，参数序又与自然语言“把 child 绑定到 parent”相反。\n- 修复：rig skill 明确 `/obj` 只表示位置，新建几何 FK 必须先读 KineFX §3.1；OBJ parenting 限定为\n  scene assembly/camera-light-null/existing legacy/explicit user/downstream OBJ delivery。工具新增\n  `set_object_parent(child,parent,keep_world,reason)`；generic `connect`/`disconnect_input` 拒绝 OBJ\n  parenting/unparent。H21/H22 回归覆盖 reason、方向、环、world preserve、回读与 ownership。\n- 反例/边界：camera/light/null 跟随、多个独立场景对象装配、既有 legacy 维护或明确 OBJ hierarchy\n  交付仍应使用 OBJ parenting；KineFX 不是整个 OBJ scene graph 的替代。\n- 下一验收：K3 重跑未见几何 FK 正例应自然走 KineFX；另跑 camera 跟随 object 与用户明确 OBJ\n  hierarchy 两个反例，确认语义动词可用且不会被误禁。\n"},{"path":"scripts/evidence-helpers.mjs","hash":"8b69cc2aea92be2615313828fba8b3d227fd040415e17d7d9dda7536f4e689ef","bytes":46098,"text":"function tryJson(text) {\n  if (typeof text !== 'string') return text;\n  try { return JSON.parse(text); }\n  catch { return null; }\n}\n\n/** Diagnostic retry candidates, not semantic equivalence or avoidable cost.\n * Input must be normalized unique calls; replay removal belongs upstream.\n */\nexport function collectRetryWork(steps = []) {\n  const calls = steps.filter(s => typeof s.code === 'string' && s.code.length);\n  const rolledBack = calls.filter(s => s.rollback?.applied === true);\n  const limit = {lookbackCodeCalls:8, minCodeChars:512, maxCodeChars:65536, minLineOverlap:0.8};\n  const lineMap = code => {\n    const lines = new Map();\n    for (const raw of code.split(/\\r?\\n/)) {\n      const line = raw.trim();\n      if (line) lines.set(line,(lines.get(line)||0)+1);\n    }\n    return lines;\n  };\n  const sized = calls.map(s => ({...s, lines:s.code.length >= limit.minCodeChars\n    && s.code.length <= limit.maxCodeChars ? lineMap(s.code) : null}));\n  const weight = lines => [...lines].reduce((n,[line,count])=>n+line.length*count,0);\n  const excerpt = (a,b) => [...a].filter(([line,count])=>count>(b.get(line)||0))\n    .slice(0,6).map(([line,count])=>({line:line.slice(0,180),count:count-(b.get(line)||0),truncated:line.length>180}));\n  const candidates=[];\n  for(let i=0;i<sized.length;i++) {\n    const current=sized[i];\n    if(!current.lines)continue;\n    let best=null;\n    for(let j=i-1;j>=Math.max(0,i-limit.lookbackCodeCalls);j--) {\n      const prior=sized[j];\n      if(!prior.failed || !prior.lines || prior.tool!==current.tool)continue;\n      let common=0;\n      for(const [line,count] of current.lines)common+=line.length*Math.min(count,prior.lines.get(line)||0);\n      const score=common/Math.max(weight(current.lines),weight(prior.lines),1);\n      if(score<limit.minLineOverlap || (best && best.lineOverlap>=score))continue;\n      best={from:prior.index,to:current.index,lineOverlap:score,\n        priorCodeChars:prior.code.length,currentCodeChars:current.code.length,\n        currentFailed:!!current.failed,priorRollbackApplied:prior.rollback?.applied===true,\n        changedLineExcerpts:{removed:excerpt(prior.lines,current.lines),added:excerpt(current.lines,prior.lines)},\n        kind:'failed_call_followed_by_similar_code_candidate'};\n    }\n    if(best)candidates.push({...best,lineOverlap:Number(best.lineOverlap.toFixed(4))});\n  }\n  return {codeCalls:calls.length,totalCodeChars:calls.reduce((n,s)=>n+s.code.length,0),\n    failedCodeChars:calls.filter(s=>s.failed).reduce((n,s)=>n+s.code.length,0),\n    appliedRollbackCalls:rolledBack.length,appliedRollbackCodeChars:rolledBack.reduce((n,s)=>n+s.code.length,0),\n    successfulBuildEntriesInAppliedRollbacks:rolledBack.flatMap(s=>(s.verbs||[])\n      .filter(v=>v.verb==='build_module' && v.ok===true)\n      .map(v=>({step:s.index,ledgerIndex:v.ledgerIndex??null,verb:v.verb}))),\n    candidates,limits:limit,similaritySkippedCalls:sized.filter(s=>!s.lines).map(s=>s.index),\n    note:'Raw code characters, not tokens, time or savings. Applied rollback code is a subset of submitted code, not an additional cost. Similarity is trimmed exact-line multiset overlap (order/indentation ignored), not Python equivalence; candidates may be necessary retries or distinct module work. Successful build ledger entries were later rolled back, not retained outputs. Full source remains in the corresponding trace steps.'};\n}\n\nexport function extractAvailableSkills(text) {\n  if (typeof text !== 'string' || !text.includes('<available_skills>')) return [];\n  return [...text.matchAll(/^- `([^`]+)`: /gm)].map((match) => match[1]);\n}\n\nexport function parseLedgerArgs(value) {\n  if (Array.isArray(value)) return { positional: value, kwargs: {} };\n  if (value && typeof value === 'object') return { positional: [], kwargs: value };\n  const text = String(value ?? '').trim();\n  if (!text) return { positional: [], kwargs: {} };\n\n  const direct = tryJson(text);\n  if (Array.isArray(direct)) return { positional: direct, kwargs: {} };\n  if (direct && typeof direct === 'object') return { positional: [], kwargs: direct };\n\n  const wrapped = tryJson(`[${text}]`);\n  if (Array.isArray(wrapped)) {\n    const positional = Array.isArray(wrapped[0]) ? wrapped[0] : [];\n    const kwargs = wrapped[1] && !Array.isArray(wrapped[1]) && typeof wrapped[1] === 'object'\n      ? wrapped[1]\n      : {};\n    return { positional, kwargs };\n  }\n  return { positional: [], kwargs: {}, unparsed: text };\n}\n\n/** Parse one rendered verb-ledger line without confusing arrows inside JSON strings/results. */\nexport function parseVerbLedgerLine(line) {\n  if (typeof line !== 'string') return null;\n  const prefix = line.match(/^(\\d+)\\. \\[(ok|FAIL)\\] (\\w+)\\(/);\n  if (!prefix) return null;\n  const tail = line.match(/ \\(([\\d.]+)ms\\)\\s*$/);\n  if (!tail || tail.index === undefined) return null;\n  const body = line.slice(prefix[0].length, tail.index);\n  let inString = false;\n  let escaped = false;\n  let square = 0;\n  let curly = 0;\n  for (let index = 0; index < body.length; index++) {\n    const char = body[index];\n    if (inString) {\n      if (escaped) escaped = false;\n      else if (char === '\\\\') escaped = true;\n      else if (char === '\"') inString = false;\n      continue;\n    }\n    if (char === '\"') { inString = true; continue; }\n    if (char === '[') square++;\n    else if (char === ']') square--;\n    else if (char === '{') curly++;\n    else if (char === '}') curly--;\n    else if (char === ')' && square === 0 && curly === 0 && body.startsWith(') -> ', index)) {\n      return {\n        ledgerIndex: Number(prefix[1]),\n        ok: prefix[2] === 'ok',\n        verb: prefix[3],\n        args: body.slice(0, index),\n        result: body.slice(index + 5),\n        ms: Number(tail[1]),\n      };\n    }\n    if (square < 0 || curly < 0) return null;\n  }\n  return null;\n}\n\nfunction nodePath(value) {\n  if (typeof value === 'string') return value;\n  if (value && typeof value === 'object' && typeof value.node === 'string') return value.node;\n  return null;\n}\n\nexport function findBatchSetParmOpportunities(steps, threshold = 3) {\n  const opportunities = [];\n  for (const step of steps) {\n    const batched = new Map();\n    for (const verb of step.verbs || []) {\n      if (verb.verb !== 'set_parms') continue;\n      const { positional } = parseLedgerArgs(verb.args ?? verb.argsText);\n      const node = nodePath(positional[0]);\n      const values = positional[1];\n      if (!node || !values || Array.isArray(values) || typeof values !== 'object') continue;\n      const fields = batched.get(node) || new Set();\n      for (const name of Object.keys(values)) fields.add(name);\n      batched.set(node, fields);\n    }\n\n    const byNode = new Map();\n    for (const verb of step.verbs || []) {\n      if (verb.verb !== 'set_parm') continue;\n      const { positional } = parseLedgerArgs(verb.args ?? verb.argsText);\n      const node = nodePath(positional[0]);\n      const parm = typeof positional[1] === 'string' ? positional[1] : null;\n      if (!node || !parm || batched.get(node)?.has(parm)) continue;\n      const fields = byNode.get(node) || new Set();\n      fields.add(parm);\n      byNode.set(node, fields);\n    }\n\n    for (const [node, fields] of byNode) {\n      if (fields.size < threshold) continue;\n      opportunities.push({\n        index: step.index,\n        time: step.time,\n        node,\n        count: fields.size,\n        parms: [...fields].sort(),\n      });\n    }\n  }\n  return opportunities;\n}\n\nconst MUTATING_METHOD = /^(?:set|add|create|delete|destroy|remove|rename|save|cook|render|bake|lock|unlock|install|copy|move|enable|disable|press)(?:$|[A-Z_])/;\nconst READ_ONLY_PREFIX_COLLISIONS = new Set(['displayNode', 'renderNode']);\n\nexport function isMutatingRawMethodName(name) {\n  return MUTATING_METHOD.test(String(name || '')) && !READ_ONLY_PREFIX_COLLISIONS.has(name);\n}\n\nexport function rawMethodNames(code) {\n  const methods = [];\n  for (const match of String(code || '').matchAll(/\\.([A-Za-z_]\\w*)\\s*\\(/g)) methods.push(match[1]);\n  return methods;\n}\n\nexport function mutatingRawMethodNames(code) {\n  return rawMethodNames(code).filter(isMutatingRawMethodName);\n}\n\nconst SUPPRESSED_COOK_FAILURE = /(?:^|\\n)(?:[A-Z][A-Z ]{0,24} )?cook FAIL(?:ED)?(?=[:\\s]|$)/i;\n\n/**\n * Find Houdini calls whose transport envelope succeeded while agent code\n * printed that a raw cook failed.  These are semantic/artifact failures, not\n * tool transport failures, and commonly result from catching without re-raise.\n */\nexport function findSuppressedCookFailures(steps) {\n  return steps.filter((step) => (\n    step.isHoudini\n    && !step.failed\n    && SUPPRESSED_COOK_FAILURE.test(String(step.resultPreview || ''))\n  )).map((step) => ({\n    index: step.index,\n    time: step.time,\n    tool: step.tool,\n    resultPreview: step.resultPreview,\n  }));\n}\n\nexport function frameFromPath(value) {\n  if (typeof value !== 'string') return null;\n  const match = value.match(/(?:^|[_./\\\\-])f(-?\\d+(?:p\\d+)?)(?=[_.\\\\/-]|$)/i);\n  if (!match) return null;\n  const frame = Number(match[1].replace('p', '.'));\n  return Number.isFinite(frame) ? frame : null;\n}\n\nfunction finiteFrame(value) {\n  if (value === null || value === undefined || value === '') return null;\n  const number = Number(value);\n  return Number.isFinite(number) ? number : null;\n}\n\nfunction uniqueFrames(values) {\n  return [...new Set(values.filter((value) => value !== null))].sort((a, b) => a - b);\n}\n\nfunction verbResult(value) {\n  if (value && typeof value === 'object') return value;\n  return tryJson(value) || {};\n}\n\n/** Recover the full __result__ JSON block rendered before a truncated verb ledger. */\nexport function execResultFromPreview(value) {\n  const text = String(value ?? '');\n  const marker = '__result__:';\n  const markerIndex = text.indexOf(marker);\n  if (markerIndex < 0) return {};\n  const start = text.indexOf('{', markerIndex + marker.length);\n  if (start < 0) return {};\n  let depth = 0;\n  let inString = false;\n  let escaped = false;\n  for (let index = start; index < text.length; index++) {\n    const char = text[index];\n    if (inString) {\n      if (escaped) escaped = false;\n      else if (char === '\\\\') escaped = true;\n      else if (char === '\"') inString = false;\n      continue;\n    }\n    if (char === '\"') { inString = true; continue; }\n    if (char === '{') depth++;\n    else if (char === '}') {\n      depth--;\n      if (depth === 0) return tryJson(text.slice(start, index + 1)) || {};\n    }\n  }\n  return {};\n}\n\nfunction partialJsonString(value, key) {\n  const pattern = new RegExp(`\"${key}\"\\\\s*:\\\\s*\"((?:\\\\\\\\.|[^\"\\\\\\\\])*)\"`, 'g');\n  const values = [];\n  for (const match of String(value ?? '').matchAll(pattern)) {\n    try { values.push(JSON.parse(`\"${match[1]}\"`)); } catch {}\n  }\n  return values;\n}\n\nfunction partialJsonArray(value, key) {\n  const match = String(value ?? '').match(new RegExp(`\"${key}\"\\\\s*:\\\\s*(\\\\[[^\\\\]]*\\\\])`));\n  return match ? tryJson(match[1]) : null;\n}\n\nfunction partialJsonNumber(value, key) {\n  const match = String(value ?? '').match(new RegExp(`\"${key}\"\\\\s*:\\\\s*(-?[\\\\d.]+)`));\n  return match ? Number(match[1]) : null;\n}\n\n/** Ordered unique render outputs visible anywhere in the unabridged tool result. */\nexport function renderOutputsFromPreview(value) {\n  return [...new Set(partialJsonString(value, 'output'))];\n}\n\nconst VISION_REFUSAL = [\n  /无法.{0,20}(?:查看|看到|访问|读取|分析).{0,20}(?:图像|图片|图)/i,\n  /模型仅接受文本输入/i,\n  /图片已被省略/i,\n  /(?:cannot|can't|unable to).{0,30}(?:view|see|access|inspect|analy[sz]e).{0,20}images?/i,\n  /images?.{0,20}(?:omitted|not (?:available|provided|attached))/i,\n];\n\n/** Distinguish tool transport, image delivery, setup, and actual semantic inspection. */\nexport function classifyVisionEvidence(step) {\n  const tool = String(step.tool || '');\n  const semanticTools = new Set([\n    'read_image', 'vision_glance', 'vision_ground', 'vision_detect',\n    'vision_long_screenshot_ocr',\n  ]);\n  const role = tool === 'vision_present'\n    ? 'presentation'\n    : tool === 'vision_bootstrap'\n      ? 'setup'\n      : semanticTools.has(tool)\n        ? 'inspection'\n        : 'pixel';\n  const transportOk = !step.failed;\n  const text = String(step.resultPreview ?? step.resultText ?? '').trim();\n  const structured = tryJson(text);\n  const structuredFailure = structured && typeof structured === 'object' && structured.ok === false;\n  const textualRefusal = VISION_REFUSAL.some((pattern) => pattern.test(text));\n  const semanticFailure = !transportOk || Boolean(structuredFailure) || textualRefusal;\n  const images = Array.isArray(step.args?.images)\n    ? step.args.images\n    : Array.isArray(step.args?.paths)\n      ? step.args.paths\n      : [step.args?.path, step.args?.file_path, step.args?.image].filter(Boolean);\n  return {\n    role,\n    transportOk,\n    semanticOk: role === 'inspection' ? !semanticFailure : null,\n    // Backward-compatible summary: setup/presentation can succeed as tools,\n    // but callers must require role=inspection && semanticOk for visual proof.\n    ok: role === 'inspection' ? !semanticFailure : transportOk && !structuredFailure,\n    reason: !transportOk\n      ? 'tool_transport_failed'\n      : structuredFailure\n        ? String(structured.code || structured.reason || 'structured_result_ok_false')\n        : textualRefusal\n          ? 'textual_image_access_refusal'\n          : null,\n    images,\n    frames: uniqueFrames(images.map(frameFromPath)),\n  };\n}\n\n/** Metrics that separate vocabulary breadth from actual execution adoption. */\nexport function isStructuredHoudiniCall(step) {\n  return step.tool==='houdini_exec' && !step.code && Boolean(step.args?.delivery || step.args?.review || step.args?.review_test)\n}\n\nexport function collectVerbAdoption(steps) {\n  const detailReads = steps.filter(step => step.tool === 'houdini_query' && step.args?.result_ref);\n  const houdini = steps.filter((step) => step.isHoudini && !detailReads.includes(step));\n  const structured = houdini.filter(isStructuredHoudiniCall);\n  const python = houdini.filter(step=>!isStructuredHoudiniCall(step));\n  const withVerbs = houdini.filter((step) => (step.verbs || []).length > 0);\n  const verbCalls = houdini.reduce((sum, step) => sum + (step.verbs || []).length, 0);\n  const rawReadOnly = python.filter((step) => (\n    !(step.verbs || []).length && !(step.mutatingRawMethods || []).length\n  ));\n  const exec = python.filter((step) => step.tool === 'houdini_exec');\n  const successfulExec = exec.filter((step) => !step.failed);\n  const successfulExecWithVerbs = successfulExec.filter((step) => (step.verbs || []).length > 0);\n  const verblessRawMutation = houdini.filter((step) => (\n    !(step.verbs || []).length && (step.mutatingRawMethods || []).length > 0\n  ));\n  const blockedRawMutation = verblessRawMutation.filter((step) => (\n    step.failed && /raw-hou gate: blocked BEFORE execution/i.test(String(step.resultPreview ?? step.resultText ?? ''))\n  ));\n  const successfulRawMutation = verblessRawMutation.filter((step) => !step.failed);\n  const pct = (part, total) => total ? Math.round((part / total) * 1000) / 10 : null;\n  return {\n    houdiniCalls: houdini.length,\n    hostResultDetailReads: detailReads.length,\n    callsWithVerbs: withVerbs.length,\n    callCoveragePct: pct(withVerbs.length, houdini.length),\n    verbCalls,\n    verbDensity: houdini.length ? Math.round((verbCalls / houdini.length) * 100) / 100 : 0,\n    rawReadOnlyCalls: rawReadOnly.length,\n    execCalls: exec.length,\n    successfulExecCalls: successfulExec.length,\n    successfulExecWithVerbs: successfulExecWithVerbs.length,\n    successfulExecVerbCoveragePct: pct(successfulExecWithVerbs.length, successfulExec.length),\n    blockedVerblessRawMutationCalls: blockedRawMutation.length,\n    successfulVerblessRawMutationCalls: successfulRawMutation.length,\n    ...(structured.length ? {structuredCalls:structured.length,pythonCalls:python.length,\n      pythonCallCoveragePct:pct(withVerbs.length,python.length)} : {}),\n  };\n}\n\nconst OPEN_ENDED_QUALITY_REQUEST = /(?:程序化|细节丰富|高质量|写实|逼真|真实感|电影感|镜头级|可靠(?:的)?验证|复杂(?:资产|模型)|真实\\s*solver|有效缓存|可重算|产品视觉开发|正式(?:的)?\\s*(?:Karma\\s*)?渲染|(?:可调|可以调节|参数化).{0,16}(?:效果|模拟|系统)|procedural|high[- ]?quality|detail(?:ed| rich)|realistic|cinematic|shot[- ]?quality|reliable (?:verification|validation)|real solver|valid cache|recomputable|product lookdev|final Karma render|(?:adjustable|configurable|parameterized).{0,16}(?:effect|simulation|system))/i;\nconst EXTERNAL_TRUTH_SIGNAL = /(?:(?:符合|属于|处于|均在).{0,40}(?:真实|现实|行业|规格|标准|范围)|(?:典型|真实|行业|标准).{0,40}(?:标定|尺寸|规格|比例|范围|标准)|(?:real[- ]?world|industry|spec(?:ification)?|physically accurate).{0,40}(?:dimension|proportion|range|standard|accurate))/i;\nconst ASSUMPTION_BOUNDARY = /(?:无外部参考|没有外部参考|基于假设|假设值|(?:值|比例|尺寸|数值|典型值).{0,16}假设|非已核实规格|未验证|内部一致|风格化|用户授权|用户选择|no external reference|assum(?:e|ed|ption)|unverified|stylized)/i;\nconst UNVERIFIED_MARKER = /(?:unverified|未验证|无法验证|待验证)/i;\nconst COMPLETION_MARKER = /(?:^|[\\s：:。])(?:完成|已完成|交付|complete(?:d)?|delivered)(?:[\\s：:。]|$)/i;\nconst REQUESTED_GOAL_SIGNALS = [\n  ['cinematic', /(?:电影感|cinematic)/i],\n  ['quality', /(?:高质量|镜头级|产品级|high[- ]?quality|shot[- ]?quality|production[- ]?quality)/i],\n  ['realism', /(?:写实|逼真|真实感|realistic|photoreal)/i],\n  ['adjustability', /(?:可调|可以调节|参数化|adjustable|configurable|parameterized)/i],\n  ['animation', /(?:动画|动态|animation|motion)/i],\n  ['simulation', /(?:模拟|仿真|simulation)/i],\n  ['rendering', /(?:渲染|render(?:ing)?)/i],\n  ['verification', /(?:可靠(?:的)?验证|可靠(?:的)?验收|reliable (?:verification|validation))/i],\n];\nconst MUTATING_VERBS = new Set([\n  'scene_save', 'scene_save_as', 'tab_create', 'tab_apply', 'connect', 'set_object_parent', 'disconnect_input', 'rename_node', 'delete_node', 'set_parm', 'set_parms',\n  'set_keyframes', 'create_spare_parms', 'set_timeline', 'create_bookmark', 'delete_bookmark',\n  'hda_create', 'hda_set_section', 'hda_patch_section', 'hda_set_interface', 'sop_set_output',\n  'set_object_visible', 'set_display', 'layout_nodes', 'camera_fit',\n]);\nconst QUERY_SIDE_EFFECT_VERBS = new Set([\n  ...MUTATING_VERBS,\n  'cook_node', 'verify_network', 'build_module', 'test_controls', 'render_frame', 'render_view', 'viewport_screenshot',\n]);\nconst VALIDATION_VERBS = new Set([\n  'cook_node', 'describe', 'geo_piece_stats', 'geo_attrib_stats', 'geo_frame_diff', 'render_view',\n  'render_frame', 'render_check', 'verify_network', 'geo_point_spacing', 'geo_check_interfaces', 'test_controls',\n]);\nconst RELATION_PATTERN = /(?:coincident|共轴|轴线|anchor(?:ed)? endpoint|锚点|端点|distance|距离|clearance|间隙|intersection|相交|穿插|contact|接触|contain(?:ed)?|包含|insert(?:ed)?|插入|tangent|切线|deviation|偏差)/ig;\n\nexport function findQueryMutationSteps(steps) {\n  return (steps || []).filter((step) => (\n    step.tool === 'houdini_query'\n    && (\n      (step.mutatingRawMethods || []).length > 0\n      || (step.verbs || []).some((verb) => QUERY_SIDE_EFFECT_VERBS.has(verb.verb))\n    )\n  )).map((step) => ({\n    index: step.index,\n    time: step.time,\n    tool: step.tool,\n    codePreview: step.codePreview,\n    mutatingRawMethods: step.mutatingRawMethods || [],\n    mutatingVerbs: [...new Set(\n      (step.verbs || []).map((verb) => verb.verb).filter((name) => QUERY_SIDE_EFFECT_VERBS.has(name)),\n    )],\n  }));\n}\n\nfunction messageText(messages) {\n  return (messages || []).map((message) => String(message?.text || '')).filter(Boolean).join('\\n');\n}\n\nfunction stepIndex(step, fallback) {\n  return Number.isFinite(step?.index) ? step.index : fallback;\n}\n\nfunction sceneMutation(step) {\n  if (step.failed) return false;\n  if ((step.verbs || []).some((verb) => verb.verb === 'build_module' && parseLedgerArgs(verb.args ?? verb.argsText).kwargs.dry_run !== true)) return true;\n  if ((step.verbs || []).some((verb) => MUTATING_VERBS.has(verb.verb))) return true;\n  return (step.mutatingRawMethods || []).some((name) => !['save', 'render'].includes(String(name)));\n}\n\nfunction stableValue(value) {\n  try { return JSON.stringify(value); }\n  catch { return String(value); }\n}\n\nfunction isObjectRoot(node) {\n  return typeof node === 'string' && /^\\/obj\\/[^/]+$/.test(node);\n}\n\nfunction specDefaults(spec, target = {}) {\n  for (const item of Array.isArray(spec) ? spec : []) {\n    if (!item || typeof item !== 'object') continue;\n    if (item.type === 'folder') specDefaults(item.parms, target);\n    else if (typeof item.name === 'string' && Object.hasOwn(item, 'default')) {\n      target[item.name] = item.default;\n    }\n  }\n  return target;\n}\n\nfunction setParmEvents(steps) {\n  const events = new Map();\n  const controlNodes = new Set();\n  for (const step of steps) {\n    if (step.failed) continue;\n    for (const verb of step.verbs || []) {\n      if (verb.verb !== 'create_spare_parms') continue;\n      const { positional } = parseLedgerArgs(verb.args ?? verb.argsText);\n      const node = nodePath(positional[0]);\n      if (node) controlNodes.add(node);\n    }\n  }\n  for (let offset = 0; offset < steps.length; offset++) {\n    const step = steps[offset];\n    const index = stepIndex(step, offset + 1);\n    if (step.failed) continue;\n    for (const verb of step.verbs || []) {\n      if (verb.ok === false) continue;\n      const { positional, kwargs } = parseLedgerArgs(verb.args ?? verb.argsText);\n      const node = nodePath(positional[0]);\n      if (!node || (!isObjectRoot(node) && !controlNodes.has(node))) continue;\n      if (verb.verb === 'create_spare_parms') {\n        const result = verbResult(verb.result ?? verb.detail);\n        const values = result.leaf_values || specDefaults(kwargs.spec);\n        if (!values || Array.isArray(values) || typeof values !== 'object') continue;\n        for (const [parm, value] of Object.entries(values)) {\n          const key = `${node}\\u0000${parm}`;\n          const list = events.get(key) || [];\n          list.push({ index, node, parm, value, stable: stableValue(value), source: 'default' });\n          events.set(key, list);\n        }\n        continue;\n      }\n      if (!['set_parm', 'set_parms'].includes(verb.verb)) continue;\n      const values = verb.verb === 'set_parm'\n        ? { [positional[1]]: positional[2] }\n        : positional[1];\n      if (!values || Array.isArray(values) || typeof values !== 'object') continue;\n      for (const [parm, value] of Object.entries(values)) {\n        if (!parm || parm === 'undefined') continue;\n        const result = verbResult(verb.result ?? verb.detail);\n        if (result.failed && Object.hasOwn(result.failed, parm)) continue;\n        const key = `${node}\\u0000${parm}`;\n        const list = events.get(key) || [];\n        list.push({ index, node, parm, value, stable: stableValue(value) });\n        events.set(key, list);\n      }\n    }\n  }\n  return events;\n}\n\nfunction restoredPerturbations(steps) {\n  const validations = steps.map((step, offset) => ({\n    index: stepIndex(step, offset + 1),\n    valid: !step.failed && (\n      step.tool === 'houdini_query'\n      || (step.verbs || []).some((verb) => VALIDATION_VERBS.has(verb.verb))\n    ),\n  })).filter((item) => item.valid).map((item) => item.index);\n  const restored = [];\n  for (const list of setParmEvents(steps).values()) {\n    if (list.length < 3 || list[0].stable !== list.at(-1).stable) continue;\n    const changed = list.slice(1, -1).find((item) => item.stable !== list[0].stable);\n    if (!changed) continue;\n    const restore = list.at(-1);\n    const validationSteps = validations.filter((index) => index >= changed.index && index <= restore.index);\n    if (!validationSteps.length) continue;\n    restored.push({\n      node: list[0].node,\n      parm: list[0].parm,\n      original: list[0].value,\n      changed: changed.value,\n      restored: restore.value,\n      setSteps: list.map((item) => item.index),\n      validationSteps,\n    });\n  }\n  return restored;\n}\n\nfunction latestGeometryCounts(steps, fromIndex) {\n  let latest = null;\n  const patterns = [\n    /(?:\"?points\"?|pts|点)\\s*[:=]?\\s*([\\d,]+)[\\s,;/|，／]*(?:\"?prims\"?|primitives?|面)\\s*[:=]?\\s*([\\d,]+)/ig,\n    /([\\d,]+)\\s*(?:点|points?)\\s*(?:\\/|／|,|，|和|and)\\s*([\\d,]+)\\s*(?:面|prim(?:s|itives?)?)/ig,\n  ];\n  for (let offset = 0; offset < steps.length; offset++) {\n    const step = steps[offset];\n    const index = stepIndex(step, offset + 1);\n    if (index < fromIndex || step.failed) continue;\n    const text = String(step.resultText ?? step.resultPreview ?? '');\n    for (const pattern of patterns) {\n      for (const match of text.matchAll(pattern)) {\n        latest = {\n          index,\n          points: Number(match[1].replaceAll(',', '')),\n          prims: Number(match[2].replaceAll(',', '')),\n        };\n      }\n    }\n  }\n  return latest;\n}\n\nfunction finalGeometryCountClaim(assistantMessages) {\n  const final = String(assistantMessages?.at(-1)?.text || '');\n  const matches = [...final.matchAll(/([\\d,]+)\\s*(?:点|points?)\\s*(?:\\/|／|,|，|和|and)\\s*([\\d,]+)\\s*(?:面|prim(?:s|itives?)?)/ig)];\n  if (!matches.length) return null;\n  const match = matches.at(-1);\n  return {\n    points: Number(match[1].replaceAll(',', '')),\n    prims: Number(match[2].replaceAll(',', '')),\n  };\n}\n\n/**\n * Deterministic evidence for the open-ended quality loop (HTA-023 family).\n * It reports observable gates; it does not pretend regexes can judge artistic quality.\n */\nexport function collectQualityLoopEvidence({\n  steps = [], userMessages = [], assistantMessages = [], availableTools = [], activatedSkills = [],\n} = {}) {\n  const request = messageText(userMessages);\n  const assistant = messageText(assistantMessages);\n  const applicable = OPEN_ENDED_QUALITY_REQUEST.test(request)\n    || /(?:精细|细致|近景|测绘|实景|表面质感|close[- ]?up|fine detail|surface texture|survey reference)/i.test(request);\n  const indexed = steps.map((step, offset) => ({ ...step, code: step.code, resultText: step.resultText,\n    index: stepIndex(step, offset + 1) }));\n  const firstMutation = indexed.find(sceneMutation) || null;\n  const firstMutationTime = firstMutation?.time ?? Infinity;\n  const confirmedChoiceText = indexed.filter(step => step.tool === 'ask_user_question'\n    && !step.failed && (!firstMutation || step.index < firstMutation.index)).flatMap(step => {\n    const result = tryJson(String(step.resultText ?? step.resultPreview ?? ''));\n    return (Array.isArray(result?.answers) ? result.answers : []).flatMap(answer => {\n      const question = step.args?.questions?.find(q => q.id === answer.id);\n      const selected = Array.isArray(answer.selected) ? answer.selected : [];\n      if (!selected.length) return [];\n      return selected.map(label => {\n        const option = question?.options?.find(o => o.label === label);\n        return `${question?.header ?? ''}: ${label} ${option?.description ?? ''}`;\n      });\n    });\n  });\n  const preMutationText = [\n    ...confirmedChoiceText,\n    messageText(\n      assistantMessages.filter((message) => !Number.isFinite(message.time) || message.time <= firstMutationTime),\n    ),\n    ...indexed.filter((step) => (\n      (!firstMutation || step.index < firstMutation.index)\n      && ['create_goal', 'todo_write'].includes(String(step.tool || ''))\n    )).map((step) => JSON.stringify(step.args || {})),\n  ].filter(Boolean).join('\\n');\n  const contractFields = {\n    target: /(?:目标|对象|效果|target|deliverable|交付)/i.test(preMutationText),\n    referenceStatus: /(?:参考|来源|无外部参考|假设|reference|source)/i.test(preMutationText),\n    qualityLod: /(?:质量(?:标准|门|级别)|LOD|轮廓级|镜头级|产品级|预览级|观察距离|quality bar|quality level)/i.test(preMutationText),\n    simplifications: /(?:简化|省略|不做|允许.*(?:略|省)|边界|simplif|omit|out of scope)/i.test(preMutationText),\n    unitsDimensions: /(?:单位|尺寸|范围|半径|长度|角度|米|厘米|mm|cm|\\bm\\b|units?|dimensions?)/i.test(preMutationText),\n    controls: /(?:控制参数|可调参数|需要暴露|spare parm|HDA interface|controls?)/i.test(preMutationText),\n    relations: /(?:连接|共轴|轴线|端点|包含|间隙|穿插|接触|关系|relations?|clearance|intersection)/i.test(preMutationText),\n    evidencePlan: /(?:验证|验收|证据|视角|特写|render|evidence|check)/i.test(preMutationText),\n  };\n  const requiresControls = /(?:程序化|可调|可以调节|参数化|procedural|adjustable|configurable|parameterized)/i.test(request);\n  const requiresRelations = /(?:连接|装配|机械|结构|穿插|间隙|自行车|汽车|车辆|产品|建筑|角色|assembly|mechanical|structur|intersection|clearance)/i.test(request);\n  const requiredContractFields = [\n    'referenceStatus', 'qualityLod', 'simplifications',\n    ...(requiresControls ? ['controls'] : []),\n    ...(requiresRelations ? ['relations'] : []),\n    'evidencePlan',\n  ];\n  const missingContractFields = requiredContractFields.filter((name) => !contractFields[name]);\n\n  const researchSteps = indexed.filter((step) => /(?:web_search|browser|research)/i.test(String(step.tool || '')))\n    .map((step) => step.index);\n  const userProvidedReference = /(?:https?:\\/\\/|参考(?:图|文件|链接|如下)|规格表|用户提供|attached reference|reference (?:image|file|link))/i.test(request);\n  const userAuthorizedNoResearch = /(?:不要|无需|不需要|不用).{0,12}(?:外部)?参考|(?:风格化|抽象).{0,12}(?:即可|就行)|(?:比例|尺寸|造型).{0,12}(?:你决定|自行决定)|no (?:external )?reference|do not research/i.test(request);\n  const qualityContractLoadSteps = indexed.filter((step) => (\n    /#\\s*程序化 SOP 质量合同/i.test(String(step.resultText ?? step.resultPreview ?? ''))\n    || /#\\s*Procedural SOP Quality Contract/i.test(String(step.resultText ?? step.resultPreview ?? ''))\n  )).map((step) => step.index);\n  const externalTruthClaims = (assistantMessages || []).filter((message) => EXTERNAL_TRUTH_SIGNAL.test(String(message.text || '')));\n  const unsupportedExternalTruthClaims = externalTruthClaims.filter(\n    (message) => !ASSUMPTION_BOUNDARY.test(String(message.text || '')),\n  ).map((message) => ({ time: message.time, text: String(message.text || '').slice(0, 500) }));\n  const assumptionBoundaryDisclosed = ASSUMPTION_BOUNDARY.test(preMutationText) || ASSUMPTION_BOUNDARY.test(assistant);\n\n  const firstRender = indexed.find((step) => (\n    !step.failed && (step.verbs || []).some((verb) => ['render_view', 'render_frame'].includes(verb.verb))\n  )) || null;\n  const tabCreatesBeforeFirstRender = indexed\n    .filter((step) => !firstRender || step.index < firstRender.index)\n    .reduce((sum, step) => sum + (step.verbs || []).filter((verb) => verb.verb === 'tab_create' && verb.ok !== false).length, 0);\n  const skeletonCheckpointMentions = (assistantMessages || []).filter((message) => {\n    const text = String(message.text || '');\n    return /(?:骨架|中心线|代理体|anchors?).{0,60}(?:验证|验收|通过|成功|check|validate)/i.test(text)\n      || /(?:验证|验收|通过|成功|check|validate).{0,60}(?:骨架|中心线|代理体|anchors?)/i.test(text);\n  }).map((message) => ({ time: message.time, text: String(message.text || '').slice(0, 300) }));\n  if (firstRender) {\n    for (const verb of firstRender.verbs || []) {\n      if (verb.verb !== 'render_view' || verb.ok === false) continue;\n      const target = nodePath(parseLedgerArgs(verb.args ?? verb.argsText).positional[0]);\n      if (target && /(?:skeleton|proxy|blockout|anchors?|骨架|代理)/i.test(target)) {\n        skeletonCheckpointMentions.push({time: firstRender.time, index: firstRender.index,\n          text: `Explicit skeleton/proxy render target: ${target}`, source: 'render_target'});\n      }\n    }\n  }\n\n  const relationshipProbeSteps = [];\n  const relationshipKeywords = new Set();\n  for (const step of indexed) {\n    if (!step.failed && (step.verbs || []).some(v => v.verb === 'geo_check_interfaces'\n        || (v.verb === 'build_module' && verbResult(v.result ?? v.detail).interface_checks))) {\n      relationshipProbeSteps.push(step.index);\n      relationshipKeywords.add('declared_final_surface_interfaces');\n    }\n    const code = String(step.code || '');\n    const hits = [...code.matchAll(RELATION_PATTERN)].map((match) => match[0].toLowerCase());\n    if (!hits.length || step.failed) continue;\n    // Text in construction code (including VEX tangent comments) is not a\n    // measurement. Require geometry access and an observable labelled result\n    // for both query and exec; this still identifies a candidate, not a pass.\n    if (!(/geometry\\(|boundingBox\\(|attribValue\\(|\\.position\\(/.test(code)\n        && /print\\(|__result__\\s*=/.test(code))) continue;\n    const outputLines = code.split('\\n').filter(line => /\\bprint\\s*\\(|__result__\\s*=/.test(line));\n    if (!outputLines.some(line => new RegExp(RELATION_PATTERN.source, 'i').test(line))\n        || !String(step.resultText ?? step.resultPreview ?? '').trim()) continue;\n    relationshipProbeSteps.push(step.index);\n    for (const hit of hits) relationshipKeywords.add(hit);\n  }\n\n  const perturbations = restoredPerturbations(indexed);\n  const controlTests = indexed.flatMap(step => (step.verbs || []).filter(v => v.verb === 'test_controls')\n    .map(v => ({index:step.index, ...verbResult(v.result ?? v.detail)})));\n  for(const step of indexed.filter(s=>s.args?.review_test && !s.failed)) {\n    const result=execResultFromPreview(step.resultText || step.resultPreview || '');\n    if(result?.cases?.length)controlTests.push({index:step.index,...result,results:result.cases,\n      executed:result.cases.some(c=>c.actual_values && c.restored===true)});\n  }\n  const lastMutation = [...indexed].reverse().find(sceneMutation) || null;\n  const latestCounts = latestGeometryCounts(indexed, lastMutation?.index ?? 0);\n  const finalCountClaim = finalGeometryCountClaim(assistantMessages);\n  const finalCountMatchesEvidence = !finalCountClaim || !latestCounts\n    ? null\n    : finalCountClaim.points === latestCounts.points && finalCountClaim.prims === latestCounts.prims;\n  const checkpoints = new Map();\n  for (const step of indexed) {\n    if (step.transaction?.status === 'rolled_back' || step.rollback?.applied === true) continue;\n    for (const node of step.transaction?.nodes || []) {\n      if (node.exists === false && node.prior_path && step.transaction.status === 'committed') {\n        for (const value of checkpoints.values()) if (value.output === node.prior_path) {\n          value.lifecycle = 'removed'; value.removedAt = step.index;\n        }\n      }\n    }\n    for (const verb of step.verbs || []) {\n      if (!['verify_network','build_module'].includes(verb.verb)) continue;\n      const raw = verbResult(verb.result ?? verb.detail);\n      const r = raw.validation || raw;\n      if (typeof r.output !== 'string' || typeof r.ok !== 'boolean') continue;\n      // A successful check in a different scope cannot erase a failed one.\n      const key = JSON.stringify([r.output, r.scope, r.scope_signature ?? r.checked_nodes ?? null]);\n      checkpoints.set(key, {index: step.index, output:r.output, scope:r.scope ?? null,\n        ok:r.ok, reasons:r.failure_reasons ?? (r.nonempty === false ? ['empty_output'] : [])});\n    }\n  }\n\n  return {\n    applicable,\n    outputCheckpoints: [...checkpoints.values()],\n    requestSignals: [...new Set(request.match(OPEN_ENDED_QUALITY_REQUEST) || [])],\n    available: {\n      webSearch: availableTools.some((name) => /web_search|browser/i.test(String(name))),\n      tools: [...new Set(availableTools)].sort(),\n    },\n    contract: {\n      firstMutationIndex: firstMutation?.index ?? null,\n      requirements: { controls: requiresControls, relations: requiresRelations },\n      fields: contractFields,\n      missing: missingContractFields,\n    },\n    reference: {\n      researchSteps,\n      userProvidedReference,\n      userAuthorizedNoResearch,\n      qualityContractRequired: applicable && activatedSkills.includes('houdini-sop-workflow'),\n      qualityContractLoadSteps,\n      externalTruthClaimCount: externalTruthClaims.length,\n      unsupportedExternalTruthClaims,\n      assumptionBoundaryDisclosed,\n    },\n    skeleton: {\n      firstRenderIndex: firstRender?.index ?? null,\n      tabCreatesBeforeFirstRender,\n      checkpointMentions: skeletonCheckpointMentions,\n    },\n    relations: {\n      probeSteps: [...new Set(relationshipProbeSteps)],\n      keywords: [...relationshipKeywords].sort(),\n    },\n    perturbation: {\n      restored: perturbations,\n      controlTests,\n    },\n    freshness: {\n      lastMutationIndex: lastMutation?.index ?? null,\n      latestGeometryCounts: latestCounts,\n      finalGeometryCountClaim: finalCountClaim,\n      finalCountMatchesEvidence,\n    },\n  };\n}\n\n/**\n * Find user-requested quality dimensions that the final delivery itself leaves\n * unverified while also presenting the task as complete. This is an audit risk,\n * not an automatic artistic-quality verdict.\n */\nexport function requestedGoalReportedUnverified(userMessages = [], assistantMessages = []) {\n  const request = messageText(userMessages);\n  const final = String(assistantMessages?.at(-1)?.text || '');\n  if (!COMPLETION_MARKER.test(final)) return [];\n  const unverifiedLines = final.split(/\\r?\\n/).filter((line) => UNVERIFIED_MARKER.test(line));\n  if (!unverifiedLines.length) return [];\n  return REQUESTED_GOAL_SIGNALS.flatMap(([signal, pattern]) => {\n    if (!pattern.test(request)) return [];\n    const line = unverifiedLines.find((candidate) => pattern.test(candidate));\n    return line ? [{ signal, line: line.trim().slice(0, 500) }] : [];\n  });\n}\n\nexport function qualityLoopRisks(evidence) {\n  const risks = [];\n  if (!evidence) return risks;\n  if (evidence.applicable && evidence.contract.missing.length) {\n    risks.push({\n      code: 'quality_contract_incomplete',\n      detail: `Open-ended quality contract is missing: ${evidence.contract.missing.join(', ')}.`,\n    });\n  }\n  if (evidence.reference.qualityContractRequired && !evidence.reference.qualityContractLoadSteps.length) {\n    risks.push({\n      code: 'quality_contract_reference_not_loaded',\n      detail: 'houdini-sop-workflow was active for an open-ended quality task, but its procedural quality contract was not loaded.',\n    });\n  }\n  if (evidence.available.webSearch\n      && evidence.reference.externalTruthClaimCount\n      && !evidence.reference.userProvidedReference\n      && !evidence.reference.userAuthorizedNoResearch\n      && !evidence.reference.researchSteps.length) {\n    risks.push({\n      code: 'external_reference_available_but_unused',\n      detail: 'External-truth language was used while web/research capability was available, but no research call was recorded.',\n    });\n  }\n  if (evidence.reference.unsupportedExternalTruthClaims.length) {\n    risks.push({\n      code: 'external_truth_without_source',\n      detail: `${evidence.reference.unsupportedExternalTruthClaims.length} external-truth claim(s) lack a source or an assumption boundary.`,\n    });\n  }\n  if (evidence.applicable\n      && evidence.skeleton.firstRenderIndex\n      && evidence.skeleton.tabCreatesBeforeFirstRender >= 20\n      && !evidence.skeleton.checkpointMentions.length) {\n    risks.push({\n      code: 'late_first_visual_validation',\n      detail: `${evidence.skeleton.tabCreatesBeforeFirstRender} nodes were created before the first render without an explicit skeleton/proxy checkpoint.`,\n    });\n  }\n  if (evidence.applicable && evidence.contract.fields.controls && !evidence.perturbation.restored.length\n      && !(evidence.perturbation.controlTests || []).some(t => (t.ok === true || t.executed === true) && t.restored === true && t.results?.length)) {\n    risks.push({\n      code: 'procedural_control_not_perturbed',\n      detail: 'The task promised configurable controls, but no set → validate → restore perturbation was observed on a declared user-control node.',\n    });\n  }\n  if (evidence.applicable && evidence.contract.fields.relations && !evidence.relations.probeSteps.length) {\n    risks.push({\n      code: 'relationship_contract_without_evidence',\n      detail: 'The pre-mutation contract promised module relationships, but no relationship-oriented probe was observed.',\n    });\n  }\n  if (evidence.freshness.finalCountMatchesEvidence === false) {\n    risks.push({\n      code: 'stale_final_geometry_counts',\n      detail: 'The final points/prims claim does not match the latest post-mutation geometry evidence.',\n      claim: evidence.freshness.finalGeometryCountClaim,\n      evidence: evidence.freshness.latestGeometryCounts,\n    });\n  }\n  const unresolved = (evidence.outputCheckpoints || []).filter(c => !c.ok);\n  if (unresolved.length) risks.push({code:'unresolved_output_checkpoints',\n    detail:'Output checkpoints failed without a later successful check of the same output/scope. Diagnostic probes may be intentional; review against the deliverable contract.',\n    checkpoints:unresolved});\n  return risks;\n}\n\nexport function completedVisionTodoWithoutEvidence(latestTodo, successfulVisionEvidence = []) {\n  if ((successfulVisionEvidence || []).length > 0) return false;\n  return Boolean((latestTodo || []).some((item) => {\n    const content = String(item?.content || '');\n    return item?.status === 'completed'\n      && /(?:vision|视觉|图像检查|图片检查)/i.test(content)\n      && !/(?:unverified|未验证|无法|失败|不可用|凭据|待用户|人工确认|交给用户)/i.test(content);\n  }));\n}\n\nexport function collectValidationCoverage(steps) {\n  const geometry = [];\n  const renders = [];\n  const comparisons = [];\n  const vision = [];\n\n  for (const step of steps) {\n    const fullResult = step.resultText ?? step.resultPreview;\n    const execResult = execResultFromPreview(fullResult);\n    const renderOutputs = renderOutputsFromPreview(fullResult);\n    let renderOutputIndex = 0;\n    for (const verb of step.verbs || []) {\n      const { positional, kwargs } = parseLedgerArgs(verb.args ?? verb.argsText);\n      const ledgerResult = verbResult(verb.result ?? verb.detail);\n      const result = Object.keys(ledgerResult).length ? ledgerResult : execResult;\n      if (verb.verb === 'geo_frame_diff') {\n        const frameA = finiteFrame(positional[1]);\n        const frameB = finiteFrame(positional[2]);\n        geometry.push({\n          index: step.index,\n          time: step.time,\n          node: nodePath(positional[0]),\n          attrib: kwargs.attrib ?? positional[3] ?? 'P',\n          frame_a: frameA,\n          frame_b: frameB,\n          frames: uniqueFrames([frameA, frameB]),\n          ok: verb.ok,\n        });\n      } else if (verb.verb === 'render_view' || verb.verb === 'render_frame') {\n        const frame = finiteFrame(kwargs.frame ?? result.frame);\n        const framingFrame = finiteFrame(kwargs.framing_frame ?? result?.framing?.frame);\n        const output = result.output ?? result.image ?? kwargs.picture\n          ?? renderOutputs[renderOutputIndex] ?? null;\n        renderOutputIndex++;\n        renders.push({\n          index: step.index,\n          time: step.time,\n          verb: verb.verb,\n          target: nodePath(positional[0]),\n          frame: frame ?? frameFromPath(output),\n          framing_frame: framingFrame,\n          output,\n          ok: verb.ok,\n        });\n      } else if (verb.verb === 'render_check') {\n        const partial = verb.result ?? verb.detail;\n        const imagePath = positional[0] ?? result.path ?? null;\n        const ref = kwargs.ref ?? null;\n        const contentBbox = result.content_bbox ?? result.contentBbox\n          ?? partialJsonArray(partial, 'content_bbox') ?? null;\n        const width = result.width ?? partialJsonNumber(partial, 'width');\n        const height = result.height ?? partialJsonNumber(partial, 'height');\n        const imageSize = result.size ?? result.image_size\n          ?? (width !== null && height !== null ? [width, height] : null);\n        const touchesEdge = Array.isArray(contentBbox) && contentBbox.length === 4\n          && Array.isArray(imageSize) && imageSize.length >= 2\n          ? contentBbox[0] <= 0 || contentBbox[1] <= 0\n            || contentBbox[2] >= Number(imageSize[0]) - 1\n            || contentBbox[3] >= Number(imageSize[1]) - 1\n          : null;\n        comparisons.push({\n          index: step.index,\n          time: step.time,\n          path: imagePath,\n          ref,\n          content_bbox: contentBbox,\n          image_size: imageSize,\n          touches_edge: touchesEdge,\n          frames: uniqueFrames([frameFromPath(imagePath), frameFromPath(ref)]),\n          ok: verb.ok,\n        });\n      }\n    }\n\n    if (String(step.tool || '').startsWith('vision_') || step.tool === 'read_image') {\n      const outcome = classifyVisionEvidence(step);\n      vision.push({\n        index: step.index,\n        time: step.time,\n        tool: step.tool,\n        ...outcome,\n      });\n    }\n  }\n\n  const geometryFrames = uniqueFrames(geometry.flatMap((item) => item.frames));\n  const renderFrames = uniqueFrames(renders.map((item) => item.frame));\n  const framingFrames = uniqueFrames(renders.map((item) => item.framing_frame));\n  const comparisonFrames = uniqueFrames(comparisons.flatMap((item) => item.frames));\n  const visionFrames = uniqueFrames(vision.flatMap((item) => item.frames));\n  const visionInspectionFrames = uniqueFrames(\n    vision.filter((item) => item.role === 'inspection').flatMap((item) => item.frames),\n  );\n  return {\n    geometry,\n    renders,\n    comparisons,\n    vision,\n    frames: {\n      geometry: geometryFrames,\n      render: renderFrames,\n      framing: framingFrames,\n      comparison: comparisonFrames,\n      vision: visionFrames,\n      visionInspection: visionInspectionFrames,\n      all: uniqueFrames([\n        ...geometryFrames,\n        ...renderFrames,\n        ...comparisonFrames,\n        ...visionFrames,\n      ]),\n    },\n  };\n}\n"},{"path":"scripts/extract-trace-evidence.mjs","hash":"01c210cb0016c0c68bdb2bbef44fa44f99143e5a3441251d6432334f6314573a","bytes":21979,"text":"#!/usr/bin/env node\nimport crypto from 'node:crypto';\nimport fs from 'node:fs';\nimport path from 'node:path';\nimport { loadCatalog } from '../../../tools/catalog-lib.mjs';\nimport {\n  loadSessionEvents,\n  newestSessionFile,\n  resolveSessionFile,\n  sessionIdFromFile,\n  collectRequestTelemetry,\n} from '../../../tools/trace-session-lib.mjs';\nimport { normalizeTraceSteps } from '../../../tools/normalized-trace-steps.mjs';\nimport {\n  collectValidationCoverage,\n  collectRetryWork,\n  collectQualityLoopEvidence,\n  completedVisionTodoWithoutEvidence,\n  classifyVisionEvidence,\n  collectVerbAdoption,\n  isStructuredHoudiniCall,\n  extractAvailableSkills,\n  findBatchSetParmOpportunities,\n  findQueryMutationSteps,\n  findSuppressedCookFailures,\n  qualityLoopRisks,\n  requestedGoalReportedUnverified,\n} from './evidence-helpers.mjs';\n\nconst SKILL_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\\/([A-Za-z]:)/, '$1')), '..');\nconst PACKAGE_ROOT = path.resolve(SKILL_ROOT, '..', '..');\n\nfunction usage() {\n  console.log(`Usage:\n  node extract-trace-evidence.mjs [sessionDir|session.jsonl.zstd ...]\n       [--catalog <tool-design.md>] [--out <evidence.json>]\n       [--max-preview <chars>] [--compact]\n\nWith no session argument, analyzes the newest ~/.dsh/sessions trace.\nMultiple inputs produce per-trace evidence plus cross-trace aggregate counts.`);\n}\n\nconst argv = process.argv.slice(2);\nconst inputs = [];\nlet catalogPath = path.join(PACKAGE_ROOT, 'docs', 'tool-design.md');\nlet outPath = null;\nlet maxPreview = 3000;\nlet compact = false;\nfor (let i = 0; i < argv.length; i++) {\n  const arg = argv[i];\n  if (arg === '--help' || arg === '-h') { usage(); process.exit(0); }\n  if (arg === '--catalog') catalogPath = path.resolve(argv[++i]);\n  else if (arg === '--out') outPath = path.resolve(argv[++i]);\n  else if (arg === '--max-preview') maxPreview = Number(argv[++i]);\n  else if (arg === '--compact') compact = true;\n  else if (arg.startsWith('--')) throw new Error(`unknown option: ${arg}`);\n  else inputs.push(arg);\n}\nif (!Number.isSafeInteger(maxPreview) || maxPreview < 200) {\n  throw new Error('--max-preview must be an integer >= 200');\n}\n\nconst latest = inputs.length ? null : newestSessionFile();\nif (!inputs.length && !latest) throw new Error('no session.jsonl.zstd under the DSH session store');\nconst sessionFiles = (inputs.length ? inputs : [latest]).map(resolveSessionFile);\nconst catalog = loadCatalog(catalogPath);\nconst catalogNames = catalog.flatMap((domain) => domain.verbs.map((verb) => verb.name));\nconst catalogByName = new Map();\nfor (const domain of catalog) {\n  for (const verb of domain.verbs) catalogByName.set(verb.name, { domain: domain.domain, ...verb });\n}\n\nconst clip = (value, max = maxPreview) => {\n  const text = String(value ?? '');\n  return text.length <= max ? text : `${text.slice(0, max)}…[+${text.length - max}ch]`;\n};\nconst addCount = (target, key, amount = 1) => { target[key] = (target[key] || 0) + amount; };\nconst sortCounts = (counts) => Object.fromEntries(\n  Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])),\n);\nconst digest = (text) => crypto.createHash('sha256').update(text).digest('hex').slice(0, 16);\n\nfunction directText(content) {\n  return (content || []).filter((item) => item.type === 'text').map((item) => item.text).join('\\n');\n}\n\nfunction analyzeTrace(file) {\n  const loaded = loadSessionEvents(file);\n  const { events } = loaded;\n  const normalized = normalizeTraceSteps(events);\n  const { replayedResults, unmatchedResults } = normalized;\n\n  const userMessages = [];\n  const assistantMessages = [];\n  const capabilitySnapshots = [];\n  const skillCatalogSnapshots = [];\n  const seenCapabilityHashes = new Set();\n  const steps = [];\n  const toolCounts = {};\n  const verbCounts = {};\n  const verbFailures = {};\n  const rawMethodCounts = {};\n  let firstTime = Infinity;\n  let lastTime = 0;\n  let lastToolTime = 0;\n  let firstToolTime = Infinity;\n  let lastAssistantTime = 0;\n\n  for (const event of events) {\n    if (Number.isFinite(event.time)) {\n      firstTime = Math.min(firstTime, event.time);\n      lastTime = Math.max(lastTime, event.time);\n    }\n    if (event.type === 'user/message') {\n      const text = directText(event.data.content);\n      const availableSkills = extractAvailableSkills(text);\n      if (availableSkills.length) {\n        skillCatalogSnapshots.push({\n          seq: event.seq,\n          time: event.time,\n          turn: event.data?.turn,\n          step: event.data?.step,\n          skills: availableSkills,\n        });\n      }\n      if (event.data?.source?.kind === 'user'\n          && text && !text.startsWith('<system-reminder>')\n          && !text.startsWith('Current runtime context')) {\n        userMessages.push({ seq: event.seq, time: event.time, text });\n      }\n    } else if (event.type === 'assistant/message') {\n      const text = directText(event.data?.message?.content);\n      if (text.trim()) {\n        assistantMessages.push({ seq: event.seq, time: event.time, text });\n        lastAssistantTime = Math.max(lastAssistantTime, event.time || 0);\n      }\n    } else if (event.type === 'request/header') {\n      const system = event.data?.header?.system || '';\n      const hash = digest(system);\n      if (system && !seenCapabilityHashes.has(hash)) {\n        seenCapabilityHashes.add(hash);\n        const listedSkills = [...system.matchAll(/^- `([^`]+)`: /gm)].map((match) => match[1]);\n        capabilitySnapshots.push({\n          seq: event.seq,\n          time: event.time,\n          turn: event.data?.turn,\n          step: event.data?.step,\n          model: event.data?.header?.config?.model || null,\n          systemChars: system.length,\n          systemHash: hash,\n          personaLines: system.split('\\n').filter(line => /^You are (?:a|an) /.test(line)).slice(0, 4),\n          mentionedCatalogVerbs: catalogNames.filter(\n            (name) => new RegExp(`\\\\b${name}\\\\b`).test(system),\n          ),\n          availableTools: (event.data?.header?.tools || [])\n            .map((tool) => tool?.name || tool?.function?.name)\n            .filter(Boolean)\n            .sort(),\n          // Some dsh runtimes expose the skill loader without embedding a skill catalog in\n          // the request header. `[]` would falsely mean \"no skills were available\"; null means\n          // \"the header did not declare availability\". Actual successful loads are reported\n          // separately as skillActivations below.\n          availableSkills: listedSkills.length ? listedSkills : null,\n        });\n      }\n    }\n  }\n\n  for (const source of normalized.steps) {\n    const code = source.code;\n    const verbs = source.verbs.map((verb) => ({\n      ledgerIndex: verb.ledgerIndex,\n      ok: verb.ok,\n      verb: verb.verb,\n      args: clip(verb.args),\n      result: verb.result,\n      ms: verb.ms,\n    }));\n    const step = {\n      index: source.index,\n      callSeq: source.callSeq,\n      resultSeq: source.resultSeq,\n      time: source.time,\n      callTime: source.callTime,\n      durationMs: source.durationMs,\n      canonical: compact ? undefined : source.canonical,\n      canonicalStatus: source.canonicalStatus,\n      turn: source.turn,\n      step: source.step,\n      tool: source.tool,\n      isHoudini: source.isHoudini,\n      failed: source.failed,\n      args: compact && code ? { ...source.args, code: undefined } : source.args,\n      codeChars: code.length,\n      codeHash: code ? digest(code) : null,\n      code: compact ? undefined : code,\n      codePreview: code ? clip(code.replace(/\\s+/g, ' '), 800) : null,\n      resultPreview: clip(source.resultText),\n      verbs,\n      rawMethods: source.rawMethods,\n      mutatingRawMethods: source.mutatingRawMethods,\n      advisory: source.advisory,\n      transaction: source.transaction,\n      rollback: source.rollback?._raw ? { _raw: clip(source.rollback._raw) } : source.rollback,\n      rawUsage: source.rawUsage?._raw ? { _raw: clip(source.rawUsage._raw) } : source.rawUsage,\n    };\n    // Keep the unabridged result only in memory for coverage extraction. It is\n    // deliberately non-enumerable so compact/full evidence JSON does not\n    // duplicate potentially huge tool output, while render paths and nested\n    // render_check facts remain recoverable before serialization.\n    Object.defineProperty(step, 'resultText', { value: source.resultText, enumerable: false });\n    // Compact is a serialization choice, not an analysis input. Dropping code\n    // here used to erase relationship probes from otherwise identical traces.\n    Object.defineProperty(step, 'code', { value: code, enumerable: !compact });\n    steps.push(step);\n    firstToolTime = Math.min(firstToolTime, source.callTime ?? source.time ?? Infinity);\n    lastToolTime = Math.max(lastToolTime, source.time || 0);\n    addCount(toolCounts, step.tool);\n    for (const method of source.rawMethods) addCount(rawMethodCounts, method);\n    for (const verb of verbs) {\n      addCount(verbCounts, verb.verb);\n      if (!verb.ok) addCount(verbFailures, verb.verb);\n    }\n  }\n\n  const failedCalls = steps.filter((step) => step.failed).map((step) => ({\n    index: step.index,\n    time: step.time,\n    tool: step.tool,\n    resultPreview: step.resultPreview,\n  }));\n  const failedVerbCalls = steps.flatMap((step) => step.verbs\n    .filter((verb) => !verb.ok)\n    .map((verb) => ({ index: step.index, time: step.time, ...verb })));\n  const partialParameterFailures = steps.flatMap((step) => step.verbs\n    .filter((verb) => verb.verb === 'set_parms' && verb.ok && verb.result?.failed && Object.keys(verb.result.failed).length)\n    .map((verb) => ({index: step.index, time: step.time, failed: verb.result.failed})));\n  const rawHoudiniNoVerb = steps.filter((step) => step.isHoudini && !isStructuredHoudiniCall(step) && !step.verbs.length).map((step) => ({\n    index: step.index,\n    time: step.time,\n    tool: step.tool,\n    codePreview: step.codePreview,\n    rawMethods: step.rawMethods,\n    mutatingRawMethods: step.mutatingRawMethods,\n  }));\n  const rawMutationSteps = steps.filter(\n    (step) => step.isHoudini && step.mutatingRawMethods.length,\n  ).map((step) => ({\n    index: step.index,\n    time: step.time,\n    tool: step.tool,\n    codePreview: step.codePreview,\n    mutatingRawMethods: step.mutatingRawMethods,\n    mixedWithVerbs: step.verbs.length > 0,\n  }));\n  const verblessMutations = rawMutationSteps.filter((step) => !step.mixedWithVerbs);\n  const execUsedForReadOnly = rawHoudiniNoVerb.filter(\n    (step) => step.tool === 'houdini_exec' && !step.mutatingRawMethods.length,\n  );\n  const queryWithMutation = findQueryMutationSteps(steps);\n  const batchSetParmOpportunities = findBatchSetParmOpportunities(steps);\n  const suppressedCookFailureSteps = findSuppressedCookFailures(steps);\n  const renderEvidence = steps.flatMap((step) => step.verbs\n    .filter((verb) => ['render_view', 'render_frame', 'render_check'].includes(verb.verb))\n    .map((verb) => ({ index: step.index, time: step.time, verb: verb.verb, ok: verb.ok, result: verb.result })));\n  const visionEvidence = steps.filter(\n    (step) => step.tool.startsWith('vision_') || step.tool === 'read_image',\n  ).map((step) => ({\n    index: step.index,\n    time: step.time,\n    tool: step.tool,\n    args: step.args,\n    resultPreview: step.resultPreview,\n    ...classifyVisionEvidence(step),\n  }));\n  const successfulVisionEvidence = visionEvidence.filter(\n    (item) => item.role === 'inspection' && item.semanticOk === true,\n  );\n  const skillActivations = steps.filter((step) => step.tool === 'skill').map((step) => ({\n    index: step.index,\n    time: step.time,\n    name: typeof step.args?.name === 'string' ? step.args.name : null,\n    succeeded: !step.failed,\n  }));\n  const qualityLoopEvidence = collectQualityLoopEvidence({\n    steps,\n    userMessages,\n    assistantMessages,\n    availableTools: capabilitySnapshots.flatMap((snapshot) => snapshot.availableTools || []),\n    activatedSkills: skillActivations.filter((item) => item.succeeded).map((item) => item.name),\n  });\n  const completionRisks = [];\n  const turnEnd = [...events].reverse().find((event) => event.type === 'turn/end') || null;\n  const terminalReason = turnEnd?.data?.reason || null;\n  const terminalMessage = String(\n    terminalReason?.error?.message\n    || terminalReason?.failure?.message\n    || terminalReason?.message\n    || '',\n  );\n  const terminalCode = terminalReason?.error?.code || terminalReason?.failure?.code || terminalReason?.code || null;\n  const terminalCategory = /insufficient_quota|quota has been exhausted/i.test(terminalMessage)\n    ? 'quota_exhausted'\n    : terminalReason?.kind === 'error'\n      ? 'external_error'\n      : terminalReason?.kind || null;\n  if (terminalCategory === 'quota_exhausted') {\n    completionRisks.push({\n      code: 'quota_exhausted',\n      detail: 'The run ended because the model/provider quota was exhausted, not because the task reached delivery.',\n    });\n  }\n  if (renderEvidence.length && !successfulVisionEvidence.length) {\n    completionRisks.push({\n      code: 'render_without_successful_vision',\n      detail: 'Render evidence exists, but no vision tool successfully inspected an image.',\n    });\n  }\n  if (visionEvidence.some((item) => item.transportOk === false || item.reason)) {\n    completionRisks.push({\n      code: 'vision_tool_failed',\n      detail: 'At least one attempted vision inspection failed.',\n    });\n  }\n  const workStarted = steps.length > 0 || assistantMessages.length > 0;\n  if (workStarted) completionRisks.push(...qualityLoopRisks(qualityLoopEvidence));\n  const unverifiedRequestedGoals = requestedGoalReportedUnverified(userMessages, assistantMessages);\n  if (unverifiedRequestedGoals.length) {\n    completionRisks.push({\n      code: 'requested_goal_reported_unverified',\n      detail: `The final delivery presents the task as complete while user-requested dimension(s) remain unverified: ${unverifiedRequestedGoals.map((item) => item.signal).join(', ')}.`,\n      items: unverifiedRequestedGoals,\n    });\n  }\n  const validationCoverage = collectValidationCoverage(steps);\n  const edgeContact = validationCoverage.comparisons.filter((item) => item.touches_edge === true);\n  if (edgeContact.length) {\n    completionRisks.push({\n      code: 'render_framing_edge_contact',\n      detail: `${edgeContact.length} render_check result(s) have content touching the image edge; fixed-camera evidence may be clipped.`,\n      steps: [...new Set(edgeContact.map((item) => item.index))],\n    });\n  }\n  const verbAdoption = collectVerbAdoption(steps);\n  const repeatedCode = Object.entries(steps.reduce((groups, step) => {\n    if (!step.codeHash) return groups;\n    (groups[step.codeHash] ||= []).push(step.index);\n    return groups;\n  }, {})).filter(([, indices]) => indices.length > 1).map(([hash, indices]) => ({ hash, indices }));\n  const gaps = [];\n  for (let i = 1; i < steps.length; i++) {\n    const ms = steps[i].time - steps[i - 1].time;\n    if (ms >= 60_000) gaps.push({ after: steps[i - 1].index, before: steps[i].index, ms });\n  }\n  const usedVerbs = Object.keys(verbCounts);\n  const usedDomains = [...new Set(usedVerbs.map((name) => catalogByName.get(name)?.domain).filter(Boolean))];\n  let latestTodo = null;\n  for (const step of steps) {\n    if (step.tool !== 'todo_write' || !step.args?.todos) continue;\n    latestTodo = step.args.todos;\n  }\n  const unfinishedTodoCount = latestTodo?.filter((item) => item.status !== 'completed').length ?? null;\n  const completedVisionTodoRisk = completedVisionTodoWithoutEvidence(\n    latestTodo,\n    successfulVisionEvidence,\n  );\n  if (completedVisionTodoRisk) {\n    completionRisks.push({\n      code: 'completed_vision_todo_without_evidence',\n      detail: 'A vision-related todo was marked complete without a successful semantic image inspection.',\n    });\n  }\n  const assistantAfterLastTool = lastAssistantTime > lastToolTime;\n  if (suppressedCookFailureSteps.length) {\n    completionRisks.push({\n      code: 'suppressed_cook_failure',\n      detail: `${suppressedCookFailureSteps.length} successful tool envelope(s) printed a raw cook failure.`,\n      steps: suppressedCookFailureSteps.map((item) => item.index),\n    });\n  }\n  if (unfinishedTodoCount > 0) {\n    completionRisks.push({\n      code: 'unfinished_todos',\n      detail: `${unfinishedTodoCount} todo item(s) were not completed when the trace ended.`,\n    });\n  }\n  if (lastToolTime && !assistantAfterLastTool) {\n    completionRisks.push({\n      code: 'no_final_delivery_after_last_tool',\n      detail: 'No assistant delivery message followed the final tool result.',\n    });\n  }\n  const initialRequest = userMessages.find(\n    (message) => message.time <= firstToolTime,\n  ) || null;\n  return {\n    sessionId: sessionIdFromFile(file),\n    file: loaded.file,\n    frames: loaded.frames,\n    frameErrors: loaded.frameErrors,\n    replayedResults,\n    unmatchedResults,\n    eventCount: events.length,\n    effectivePreset: {\n      initial: events.find(e => e.type === 'session')?.agentPreset ?? null,\n      changes: events.filter(e => e.type === 'agent-preset/selected').map(e => ({seq:e.seq,time:e.time,preset:e.data?.agentPreset})),\n    },\n    observationContexts: events.filter(e => e.type === 'user/message' && e.data?.source?.kind === 'plugin')\n      .flatMap(e => (e.data?.source?.sections || []).filter(s => s.name === 'dsh-houdini:scene-context')\n        .map(s => ({seq:e.seq,time:e.time,text:s.text}))),\n    executionCost: {\n      toolDurationSumMs: steps.reduce((n,s) => n + (s.durationMs ?? 0), 0),\n      measuredToolDurations: steps.filter(s => s.durationMs !== null).length,\n      resultChars: normalized.steps.reduce((n,s) => n+s.resultText.length,0),\n      note: 'Call-to-result sum includes waits and possible overlap; gaps are not a direct model inference-time measurement.',\n    },\n    requestTelemetry: collectRequestTelemetry(events),\n    startTime: Number.isFinite(firstTime) ? firstTime : null,\n    endTime: lastTime || null,\n    durationMs: Number.isFinite(firstTime) && lastTime ? lastTime - firstTime : null,\n    taskTiming: {\n      initialRequest,\n      firstToolTime: Number.isFinite(firstToolTime) ? firstToolTime : null,\n      lastToolTime: lastToolTime || null,\n      firstToolLatencyMs: initialRequest && Number.isFinite(firstToolTime)\n        ? firstToolTime - initialRequest.time\n        : null,\n      requestToLastToolMs: initialRequest && lastToolTime\n        ? lastToolTime - initialRequest.time\n        : null,\n      toolSpanMs: Number.isFinite(firstToolTime) && lastToolTime\n        ? lastToolTime - firstToolTime\n        : null,\n    },\n    userMessages,\n    capabilitySnapshots,\n    skillCatalogSnapshots,\n    skillActivations,\n    assistantMessages: compact ? undefined : assistantMessages,\n    toolCalls: steps.length,\n    toolCounts: sortCounts(toolCounts),\n    verbCalls: Object.values(verbCounts).reduce((sum, count) => sum + count, 0),\n    verbCounts: sortCounts(verbCounts),\n    verbFailures: sortCounts(verbFailures),\n    verbAdoption,\n    catalog: {\n      total: catalogNames.length,\n      used: usedVerbs.length,\n      usedNames: usedVerbs.sort(),\n      unusedNames: catalogNames.filter((name) => !verbCounts[name]),\n      usedDomains: usedDomains.sort(),\n    },\n    failedCalls,\n    failedVerbCalls,\n    partialParameterFailures,\n    rawHoudiniNoVerb,\n    rawMutationSteps,\n    verblessMutations,\n    execUsedForReadOnly,\n    queryWithMutation,\n    rawMethodCounts: sortCounts(rawMethodCounts),\n    advisorySteps: steps.filter((step) => step.advisory).map((step) => step.index),\n    rollbackSteps: steps.filter((step) => step.rollback).map((step) => ({\n      index: step.index, rollback: step.rollback,\n    })),\n    batchSetParmOpportunities,\n    suppressedCookFailureSteps,\n    renderEvidence,\n    visionEvidence,\n    completionRisks,\n    qualityLoopEvidence,\n    validationCoverage,\n    repeatedCode,\n    retryWork: collectRetryWork(normalized.steps),\n    timelineGaps: gaps,\n    totalCodeChars: steps.reduce((sum, step) => sum + step.codeChars, 0),\n    execCodeChars: steps.filter((step) => step.tool === 'houdini_exec').reduce((sum, step) => sum + step.codeChars, 0),\n    latestTodo,\n    terminal: {\n      lastEventType: events.at(-1)?.type || null,\n      reason: terminalCategory,\n      reasonCode: terminalCode,\n      reasonMessage: terminalMessage || null,\n      lastToolTime: lastToolTime || null,\n      lastAssistantTime: lastAssistantTime || null,\n      assistantAfterLastTool,\n      unfinishedTodoCount,\n    },\n    steps,\n  };\n}\n\nconst traces = sessionFiles.map(analyzeTrace);\nconst aggregateToolCounts = {};\nconst aggregateVerbCounts = {};\nconst aggregateVerbFailures = {};\nconst verbTraceHits = {};\nfor (const trace of traces) {\n  for (const [name, count] of Object.entries(trace.toolCounts)) addCount(aggregateToolCounts, name, count);\n  for (const [name, count] of Object.entries(trace.verbCounts)) {\n    addCount(aggregateVerbCounts, name, count);\n    addCount(verbTraceHits, name);\n  }\n  for (const [name, count] of Object.entries(trace.verbFailures)) addCount(aggregateVerbFailures, name, count);\n}\nconst output = {\n  schemaVersion: 2,\n  generatedAt: new Date().toISOString(),\n  catalogPath: path.resolve(catalogPath),\n  traceCount: traces.length,\n  aggregate: {\n    toolCalls: traces.reduce((sum, trace) => sum + trace.toolCalls, 0),\n    verbCalls: traces.reduce((sum, trace) => sum + trace.verbCalls, 0),\n    toolCounts: sortCounts(aggregateToolCounts),\n    verbCounts: sortCounts(aggregateVerbCounts),\n    verbFailures: sortCounts(aggregateVerbFailures),\n    verbTraceHits: sortCounts(verbTraceHits),\n    neverUsedCatalogVerbs: catalogNames.filter((name) => !aggregateVerbCounts[name]),\n  },\n  traces,\n};\nconst json = `${JSON.stringify(output, null, 2)}\\n`;\nif (outPath) {\n  fs.mkdirSync(path.dirname(outPath), { recursive: true });\n  fs.writeFileSync(outPath, json, 'utf8');\n  console.error(`wrote ${outPath}: ${traces.length} trace(s), ${output.aggregate.toolCalls} tool calls`);\n} else {\n  process.stdout.write(json);\n}\n"},{"path":"SKILL.md","hash":"b0b1528ab45d2531f94a2eb83e3f70ac732661665dca515bafa242652a18bc49","bytes":7242,"text":"---\nname: houdini-trace-analysis\ndescription: 系统复盘 dsh-houdini / DeepSeek Harness 的 Houdini agent trace，包括 session.jsonl.zstd、trace-report HTML 或多次会话对比。用于用户要求分析最新/指定 Houdini trace、检查任务为何失败或低效、审计工具和动词的应调用未调用/缺失/误用/冗余/拆分/合并、判断节点模块与 cook/属性/显示/渲染/动画逻辑是否符合 Houdini 工作方式，以及依据累积 trace 更新审计规范和词表路线时。\n---\n\n# Houdini Trace Analysis\n\n把 trace 当作一次可重放的工程实验，不把调用次数当结论。先确定性提取事实，再按 Houdini 数据流和 agent trajectory 审判，最后区分“本次修复”与“跨 trace 产品决策”。\n\n## 工作流\n\n1. 定位原始 `session.jsonl.zstd`。记录 session ID、用户任务、时间范围和是否有后续纠正。\n2. 在 dsh-houdini 仓库中运行：\n\n   ```powershell\n   node <skill-dir>/scripts/extract-trace-evidence.mjs <session-file> --out tools/out/trace-evidence-<id>.json\n   node tools/trace-report.mjs <session-file> --out tools/out/trace-session-<id>.html\n   ```\n\n   多会话对比时向 evidence 脚本连续传多个 session 路径。不得只读 HTML 摘要；必须保留原始事件证据。\n3. 完整阅读 [references/audit-rubric.md](references/audit-rubric.md)，按其中的强制量表审计。分析工具演化或重复问题时再读 [references/known-patterns.md](references/known-patterns.md)。\n   若 trace 是 SOP 构建/动画任务，同时加载 `houdini-sop-workflow`，用其模块契约检查 agent 路径。\n4. 从用户消息重建任务契约：产物、参考状态、质量/LOD、已确认选择、agent 假设、视觉目标、时间/动画目标、交互约束、保存/交付要求。不要用 agent 自己的 todo 替代用户契约；把“未询问”“用户授权自选”和“已有可信来源”分开。\n5. 给轨迹划分真实阶段：接收/判歧义 → 研究 → 澄清 → 合同 → 现场检查 → 设计 → 分模块构建 → 模块验证 → 集成 → 静态视觉验证 → 时序验证 → 修订 → 清理/交付。不适用的前置阶段可省略，但开放式任务不能把基于模型记忆的暗中选型伪装成已确认合同。阶段以证据和状态跃迁为准，不按 assistant 宣称划分。\n6. 建立工具机会矩阵。对目录中每个相关动词标记 `已正确使用`、`该用未用`、`误用/工具缺陷`、`不适用`；另列 `能力缺失`。未使用不等于应删除。\n7. 对每个关键 Houdini 模块检查输入、输出、属性契约、局部几何不变量、cook 错误/警告、帧依赖、显示/渲染状态。整体 bbox/点数不能替代局部拓扑和模块语义验证。\n8. 重建一条最小反事实轨迹：如果从头正确执行，阶段和工具顺序应是什么；用它量化绕路、重复探测和过早完成声明。\n9. 将建议分级：\n   - `P0`：工具自身错误、数据破坏、错误成功判定、无法完成任务。\n   - `P1`：明确重复出现的缺失能力或工作流守卫。\n   - `P2`：单 trace 假设、便利性或性能改进，等待更多证据。\n10. 检查本次是否发现新的通用模式。只有满足量表中的准入条件才更新 `known-patterns.md`；写明 session ID、证据步骤、反例和状态。若用户明确要求更新/修复 skills，先加载 `houdini-skill-governance` 决定唯一维护位置、证据等级和验证；只要求分析时输出 skill delta proposal，不静默修改生产 skill。若动词设计已拍板，再同步 `docs/tool-design.md` 与 `docs/development.md`。\n\n## 硬规则\n\n- 每个主要判断引用至少一个 trace 步骤编号/时间或用户消息 seq；数字来自 evidence，不凭印象。\n- 区分工具调用失败、动词内部失败、执行成功但产物错误、最终未交付四种失败。\n- 区分“工具缺失”和“已有工具未使用”；先证明任务意图，再做词表建议。\n- 用 `capabilitySnapshots` 判断该步骤当时实际曝光的能力；不得用当前新词表倒查旧 trace 后指责 agent 漏用。\n- 视觉证据读取 `visionEvidence[].role/transportOk/semanticOk/reason` 与 `completionRisks`。只有 `role=\"inspection\" && semanticOk=true` 才算语义识图；bootstrap、presentation、transport success、结构化 `ok:false` 或文本拒绝都不算。只有 render/render_check 而没有成功 inspection 时，必须保留“视觉语义未验证”的边界。\n- 不把 `catalog.used/catalog.total` 称为动词使用率。优先读取 `verbAdoption`，分别解释调用含动词率、动词密度、无动词只读探针、成功 exec 覆盖、Gate 拦截和成功裸修改；目录广度只说明任务触达哪些能力。\n- 开放式质量任务优先读取 `qualityLoopEvidence` 与对应 `completionRisks`，核对合同缺字段、research\n  可用但未用、质量合同未加载、首张 render 过晚、关系 probe、控制扰动恢复和最终统计新鲜度；\n  自动风险是可复核证据索引，不是艺术质量评分。合同字段可来自 mutation 前 assistant prose、\n  goal 或 todo；后二者只证明 agent 记录了计划，用户确认仍以 ask result/用户消息为准。\n- 工具删除/合并不得由单次零使用推出。跨至少三个多样任务仍冗余、存在安全替代且无独立语义，才可列为删除候选。\n- Houdini 中先验证数据流和局部几何，再调相机、灯光、材质或视觉模型。渲染能出图不证明 SOP 结果正确。\n- 任务声称符合真实对象、行业范围或外部质量标准时，必须找到用户提供或 agent 实际检索的来源证据；自生成尺寸的内部一致、模型记忆和“看起来合理”只能标假设。风格化、用户授权自选或无需外部真实性的任务是边界，不强迫无意义研究。\n- 对动画任务必须做至少两个相隔帧的几何或固定相机图像 A/B 验证。客观数据完全静止必须判未完成；节点/数据/时间语义通过而静帧难以裁定细微动态或审美力度时，可标记“视觉待用户播放判断”，不得无限追图或伪称视觉确认。\n- `cook_node` 返回 warning 不能被“无 error”覆盖；必须解决或解释其可接受性。\n- 视觉提问先用中性描述，再做目标核验；不要在 prompt 中预设“这是草地/已经成功”。\n- 当前 trace 结束于 tool result、仍有未完成 todo、或没有最终交付文本时，结论必须明确写“未完成”。\n- 输出要同时覆盖任务质量、工具质量和审计体系演化；不能只列调用统计。\n\n## 输出契约\n\n严格按以下顺序输出：\n\n1. 结论与完成度\n2. 用户任务契约及实际交付差距\n3. 阶段时间线与关键转折\n4. 工具/动词证据总览\n5. 该用未用、误用、缺失、拆分/合并/保留矩阵\n6. Houdini 节点模块、数据流、cook、显示、渲染与动画审计\n7. 最小正确轨迹\n8. P0/P1/P2 改进清单，含证据强度\n9. 对审计 skill 本身的更新建议\n\n不要为了显得全面而平均分配篇幅；优先解释造成错误产物、用户返工和长时间绕路的因果链。\n"}]},{"name":"houdini-asset-review","description":"对明确交付的 Houdini 资产做简短独立复核，寻找缺件、关系遗漏和证据夸大。用户要求评审，或作者有具体疑点需要第二视角时使用；普通建模收尾不自动委派，不替作者构建、修模或重复完整验收。","base":"skills/houdini-asset-review","files":[{"path":"SKILL.md","hash":"121f3201ca4c98022e05c3fe6f2f501c94ea7cb38afa50eef748c335f8630085","bytes":2954,"text":"---\nname: houdini-asset-review\ndescription: 对明确交付的 Houdini 资产做简短独立复核，寻找缺件、关系遗漏和证据夸大。用户要求评审，或作者有具体疑点需要第二视角时使用；普通建模收尾不自动委派，不替作者构建、修模或重复完整验收。\n---\n\n# Houdini Asset Review\n\n找出会影响用户交付的问题。原始用户要求是验收范围；作者的成功总结不是证据，也不追加用户没要求的制造、写实或动画标准。\n\n## 快速路径\n\nHost 在 `houdini_exec(review={parent,output,controller?})` 中提供当前输出摘要、控制/部件、接口组实际覆盖、实验适用性、原始要求，以及历史工具测量/图片路径。本技能已加载，不重复读技能、查全目录或重新盘点已有数据。\n\n先看已有相关图片，对照当前摘要找缺件、明显关系错误和验证遗漏。历史测量只支持当时声明的控制、取值和部件；输出指纹相同也不能证明参数依赖没变。图片内容/指纹/帧不匹配或不足以判断时才补图。没有成功读图就写视觉未验证。\n\n有具体疑点才查询。检查命名组真正包含哪些部件，不能把部分接口通过扩成全部关系通过；`name` 分组不证明拓扑连通，引用存在不证明控制有效。没有疑点即可结束，通常不超过六次工具调用，四分钟上限不应成为耗时目标。\n\n`test_support.supported=false` 时直接只读复核，不计划扰动、不改表示迎合测试器。支持且疑点需要实验时，`review_test` 总共最多三个 case，优先一批：\n\n```json\n{\"review_test\":{\"tests\":[{\"id\":\"response\",\"values\":{\"control\":2}}]}}\n```\n\n值须从实际控制和设计有效范围选择。可附 `expectations:[{group?,metric,axis?,delta:[min,max]}]`；没有预期只证明 responsive/unchanged，不能判设计正确。不是每个控制都要推导面积公式。`views` 可选 iso/front/side/top、最多两个；含基准最多八张。空 tests + views 仅取基准图，优先复用已有图。\n\n仅绑定 child 可调用 review_test；普通修改、保存、删节点、job、shell、再委派均不可用。调用内部恢复参数/keys/frame与截图用户状态。恢复失败或用户改变基准就停止；unsupported/零写入不是成功实验。不让作者逐参数代执行，也不绕过 ownership/Raw Gate。未通过 Host 入口时仅使用原有只读工具。\n\n## 一次短报告\n\n只写：**发现的问题、必要补查、检查范围**。每个问题给出节点/参数/图像或工具证据及影响。没有问题写“在本次检查范围内未发现阻断项”，不输出全绿验收表或整体认证。核心项缺证据保留 unverified；部分已测不能覆盖其他未测控制。声明已执行实验与恢复结果，零实验也直接说明。作者保留这些边界，按确认的问题修正；无实质发现无需复审。\n"}]},{"name":"houdini-sop-workflow","description":"设计、构建、调试和交付 Houdini SOP 程序化网络。用于建模、散布、Copy to Points、属性传递、VEX成形、Sweep/PolyWire、Merge和SOP动画；尤其涉及多模块空间关系、可调控制、局部几何/拓扑、cook warning或视觉取证时。不用于纯场景查询，也不代替rig或Solaris领域流程。","base":"skills/houdini-sop-workflow","files":[{"path":"agents/openai.yaml","hash":"8628b8dfd3d0765ba6691fcaa0d168df2bcc30d4f464ac40862d86ed70c160e0","bytes":264,"text":"interface:\n  display_name: \"Houdini SOP Workflow\"\n  short_description: \"Build and verify robust procedural SOP networks\"\n  default_prompt: \"Use $houdini-sop-workflow to design, build, and validate this procedural Houdini SOP task with explicit module invariants.\"\n"},{"path":"references/modeling-methods.md","hash":"5b3bc3307639bf0881cefcbc88b5f07a9f5aa853c7a4b532b1f3758880a8ba13","bytes":6371,"text":"# 建模方法与细节预算\n\n适用：SOP建模的方法选择、分件、硬表面细化和重复细节。不把这套层次强加给简单编辑、\n模拟数据准备或明确要求的原生/NURBS资产。单节点的精确参数、默认值和版本来源读node_info\n操作卡；这里仅维护组合方法。先读与当前模块相关的小节，不扫描全部节点。\n\n## 1. 从表示和构造选方法\n\n| 当前意图 | 起点与组合 | 构建前的关键选择 | 模块checkpoint / 不适用边界 |\n|---|---|---|---|\n| 沿路径的杆、管、带 | 中心线 → 按曲率分配采样 → 截面/方向 → Sweep | 截面来源、局部frame、开闭端；有壁厚的管不同于实心截面 | 实际截面、端边界、转弯处压缩/扭转；不是任意曲面造型通法 |\n| 轴对称部件 | 径向/轴向轮廓 → Revolve | 旋转轴、轮廓方向、两端如何连接轴或保持开放 | 半径与轴向尺寸、边界/朝向；不拿周向closed代替端封闭 |\n| 板、壳、开孔面板 | 平面轮廓 → 局部Inset/Extrude → 孔槽 → 定向倒角 | 薄片厚化还是已有实体面挤出；保留生成的面/边组 | 壁厚、内外面、孔位置；开放板面是合法输出，不自动实体化 |\n| 切除或融合体 | 简单可靠的实体/切割面 → Boolean → 检查接缝 | 各输入Solid/Surface和运算意图 | 实际输出拓扑/朝向/小面与连接；Merge非Boolean，Fuse也非实体并集 |\n| 平滑设计曲面 | 低密度控制笼 → 支撑结构/crease → Subdivide | 哪些曲率连续、哪些边应保持；交付拓扑要求 | 轮廓收缩、折痕和高光；细分不会自动设计孔槽、壁厚或支撑结构 |\n| 有机融合 | 允许体素近似时才用VDB → 重建表面 | 体素尺寸与最小需保留结构，后续属性/UV恢复 | 薄缝/尖角保留；精密接缝和规定拓扑通常不走此路线 |\n| 重复构件 | 一个正确单元 → 带身份/局部方向模板 → Copy to Points | 实例数量、间距、朝向和packed/展开交付 | 单件与复制后身份/组传播；先查模板唯一性，不靠整体bbox判断无重叠 |\n\n静态不变的平面无需为“高精度”均匀加密；曲线/圆弧的分段数应由轮廓误差或目标观察尺度决定。\n参数化Primitive也属于Houdini primitive，不意味着它包含可编辑的多边形面；不要只看primitive count。\n\n## 2. 选择先于倒角与局部操作\n\n优先复用构造节点生成的front/back/side/边界组，必要时与部件身份、位置、方向、夹角条件组合。\nGroup Create可按几何条件生成组；组的class要与消费者匹配。改变上游拓扑后重新生成并回读组，\n不要长期保存某次观察到的边号。一个命名组存在但为空，不算选中了目标。\n\n硬表面圆角通常先排除细分曲面的浅夹角边；角度阈值不是零件语义，不同级别的圆角分组执行。\n窄槽、薄壁、拐角密集处按局部间距限制宽度。全部边、点倒角、开放轮廓的圆角也可能是用户意图，\n不能因为常用路线是硬边筛选就禁止这些情况。\n\n最小路径：明确目标边 → 建组/角度策略 → 读PolyBevel操作卡 → 小宽度构建 → 查真实边与角部 →\n必要时提高截面分段。失败先区分选错、宽度冲突、输入非流形/方向不一致，不反复增加divisions。\ncheckpoint是选择范围、局部轮廓和输出拓扑；cook成功不能保证无自交。Normal调整着色法线，\n不替代修正多边形绕序；二者不能混为“修法线”。\n\n## 3. 一个模块分层细化\n\n先确定交付距离/分辨率、几何用途和显著细节；无参考时把构造选择标为设计假设，不冒充工程认证。\n预算用该模块的面数、cook时间、最大细化级别和可见贡献约束，不用固定全项目面数指标。\n\n1. **主形体**：代理体/主要截面/接口。先集成查比例与位置，再投入细节。\n2. **构造细节**：分件、厚度、安装座、孔槽、筋。尺寸引用共享控制与接口；改主尺寸仍需成立。\n3. **边缘层次**：主要轮廓圆角与微小边缘分组控制，不让所有边同宽。检查整体和局部高光。\n4. **重复细节**：先完成一个单元；复制由布局/数量/间距控制派生，使用稳定身份与可复现种子。\n5. **微表面**：不影响轮廓/接触的细纹可按用途放材质、法线或位移；显著视差/投影/轮廓需几何。\n   制造/测量交付不能用贴图替代实际要求的几何；渲染位移仍需对应的细分与包络检查。\n\n在高成本分支前保留简模/精模选择，主控制与接口不因选择模式漂移。细节attach到语义表面/局部frame，\n不要维护另一套独立世界坐标常量。精模完成后集成到实际OUT，检查必需分支而非只查独立模块。\n代表性调参同时检查细节响应和应保持的壁厚/接口/数量；没有适用测量就写未验证。\n\n## 4. 停止与验收\n\n主比例或接口失败先回退到骨架，不用更多细节掩盖。两次同边界失败用最小单变量诊断或换方法。\n整体图回答比例/分件，局部图回答轮廓/边缘/细节；没有成功semantic inspection则视觉未验证。\n最后一次相关修改后刷新受影响检查，不能沿用细化前的闭合/接口结论。面数增长不是验收结果。\n\n## 来源与证据范围\n\n2026-09-07核对，官方在线H22：\n[Sweep](https://www.sidefx.com/docs/houdini/nodes/sop/sweep.html)、\n[PolyExtrude](https://www.sidefx.com/docs/houdini/nodes/sop/polyextrude.html)、\n[PolyBevel](https://www.sidefx.com/docs/houdini/nodes/sop/polybevel.html)、\n[Group](https://www.sidefx.com/docs/houdini/nodes/sop/groupcreate.html)、\n[Boolean](https://www.sidefx.com/docs/houdini/nodes/sop/boolean.html)、\n[Fuse](https://www.sidefx.com/docs/houdini/nodes/sop/fuse.html)、\n[Normal](https://www.sidefx.com/docs/houdini/nodes/sop/normal.html)、\n[Subdivide](https://www.sidefx.com/docs/houdini/nodes/sop/subdivide.html)、\n[VDB from Polygons](https://www.sidefx.com/docs/houdini/nodes/sop/vdbfrompolygons.html)。\n版本敏感字段由操作卡与H21.0.440/H22.0.368隔离回归约束；组合策略是条件性设计指导，\n不是这些组合全部经过双版本质量验收。新任务采用、艺术质量和效率增益仍待验证。\n"},{"path":"references/module-design-collaboration.md","hash":"db8db27af2c0d4873386e7b8c5c1dd45f8054cd9832de710e4f3e1058540e556","bytes":3926,"text":"# 模块协作：并行设计，单作者执行\n\n适用：用户要求多个agent协作，且有至少两个接口稳定、可以独立细化的模块。\n不适用：简单模型、比例未定、共享连续曲面/跨模块布尔/耦合变形仍在设计的阶段。\n这是第一阶段试用协议，不表示dsh已实现多作者建模权限或并行HOM执行。\n\n## 入口与权限\n\n先确认当前Host有普通设计子agent入口，且可将子agent限制为仅返回设计材料、不给场景修改工具。\n若不可用，主agent按相同模块规格顺序执行并说明限制。不能把houdini_exec(review=...)当建模入口；\n该入口仅用于受限评审，不能借review_test、allow_foreign或共享session身份绕过ownership。\n不要为这次内容任务自行安装服务、修改插件权限或启动额外Houdini进程。\n\n设计工作可以并行，所有场景构建仍由一个作者经Bridge主线程队列执行。子agent输出是未经信任的\n候选规格，不是可直接eval的执行命令或质量证书；主agent对照原始任务审核后用现有动词构建。\n\n## 发给每个设计者的最小材料\n\n- 原始相关要求和参考，不只给主agent的自评；整体简模的已观察事实及未确认项。\n- 模块ID、接口修订号、单位、局部坐标系、允许包络；连接端位置/方向/实际表面组约定。\n- 共享控制的唯一来源、合法范围及不变量；主agent提供的实际parent/现有输入路径，不猜相邻模块。\n- 所需细节层次、风格约定、几何/cook预算；必须保留的身份/材质分件和输出。\n- 相关node_info卡（含version、operation_parameters）；缺少事实可请求主agent补查，不凭记忆填token。\n- 明确只交设计，不执行修改、保存、渲染或文件写入；接口变更须提出请求。\n\n不复制整段作者工具历史；仅给该模块所依赖的材料。初次试用限制两个设计者，避免协调成本淹没收益。\n\n## 返回与集成\n\n返回紧凑材料：模块/接口修订号、采用方法、节点规格name/type/parms/inputs、明确output、\nrequired_outputs、需要的控制定义、可测检查建议、依赖/假设/未支持项。\n只把现有build_module支持的字段放进实际调用；设计说明和修订号不是新增API参数。\n跨网络依赖需主作者确认Object Merge或明确端口；不要生成对尚不存在模块的隐藏循环引用。\n\n主作者先核对修订号、参数来源、表示、节点知识和修改范围，再执行：\n\n1. 审核一个模块的规格；静态疑问用dry_run，消费operation_advisories，不强制每批两次调用。\n2. build_module构建 → 实际OUT检查 → 与已通过的相邻模块集成；失败只修本模块，保留其他有效输出。\n3. 接口变更时标记依赖它的候选规格过期，重新确认后再构建，不默默适配旧稿。\n4. 主作者统一设置全局frame、显示/渲染状态、最终装配、保存和完成报告。\n\n设计者报告“通过”不替代执行后的几何/参数/视觉证据。并行思考不等于cook并行，队列串行也不等于\n自动解决接口冲突。未来多作者写入需要Host绑定的模块租约、只读共享输入、交接撤销和恢复测试；\n当前没有这些权限，不能按路径/name自授权。\n\n## 试用验收\n\n比较单作者与两设计者在相近复杂度、相同交付范围下的首次正确模块时间、总耗时、token、\n错误/重复探测、集成返工和最终缺陷。不用不同质量目标比较速度，不以子agent数量证明能力。\n短小模块或协调返工没有收益时恢复单作者。首次试用只能支持局部观察，不推广为普遍加速。\n\n证据：当前Host/Bridge的session ownership、受限review及主线程队列实现；协作协议为候选，\n尚未提供自动调度器或验证真实多agent细化收益。2026-09-07。\n"},{"path":"references/module-quality-contracts.md","hash":"c3336a6f5eb552a5a9872caa606c20fa35bc2c6f943722f676500bc4a7a5561f","bytes":12640,"text":"# 实际输出的模块质量合同\n\n## 适用与边界\n\n适用：多部件SOP装配、带明确连接端的模块、需要用户调参仍保持连接的资产。\n不适用：简单单参修改、纯骨架/调试helper交付、模拟求解器、文件写盘或带外部副作用的控制；\n不把本流程强套到所有场景。版本：H21.0.440/H22.0.368工具回归；自然弱模型增益待新会话。\n\n## 构建前：选择接口，不发明一个“正确”布尔值\n\n先按表示选择方法：两个仍独立的表面用下述interfaces距离合同；Boolean融合后的共享表面用\n`test_controls`的`topology=[{id,groups:[部件primitive组,...],require_closed:true}]`。后者检查共享\n边连通、闭合与非流形/朝向问题，当前仅Polygon，不证明自交、强度或目标形状；至少两个\n非空且不重叠的部件组。`test_controls(...,topology=...)`在基准及扰动输出复查它。\n未焊接但空间接触的两部件不能用共享拓扑证明；融合缝也不能用“共享点到自身距离0”自证。\n更换方法时保留用户要求的连接义务；当前数据不能自行决定哪些部件必须交付。\n\n一个模块至少明确输出、连接位置/轴向、共享控制与允许连接误差。生成几何使用同一接口作为\n位置来源；另在实际最终表面保留可识别的组。point group选连接端的表面顶点，primitive group\n选对方实际接触区域，不选整个场景；不能放几个无关driver点冒充最终几何。\n\n适用时把这些组随Copy/Merge一路传到交付OUT；顶点数改变后更新明确基数，不静默接受空选择。\n组名来自当前任务，不由库固定。一个模块可以有多个出口/接口，每个需独立检查。\n原型通过不能代替复制/变换后的实例关系。最终输出保留可选择的部件身份和接口组；附属件\n随主体一起移动只证明共同运动，不证明二者连接。先验证原型内部连接，再检查各实例的外部接口。\n\n## 最小执行路径\n\n```python\ninterfaces = [{\n    'id': 'mating_interface',\n    'source_group': 'port_vertices',\n    'target_group': 'receiver_surface',\n    'expected_points': 4,\n    'max_distance': 0.001,\n}]\n# spec自行生成；必须包含这两个属于真实表面的命名组。\nresult = build_module(parent, spec, output='OUT_MODULE', interfaces=interfaces)\n```\n\n上述数值仅展示schema；容差、点数要由单位/连接要求与实际构造决定，不是所有任务的固定标准。\n`dry_run=True`只预检声明，不能证明几何接口。正常build会在最终输出检查接口；fail或unverified\n使该新增模块失败并清理本批节点。修改已有节点后，用 `geo_check_interfaces(out, interfaces)`\n再次读取实际结果；它是诊断返回，不会替你修模或强制完成。\n\n检查含义：全部source表面顶点到指定target表面的最近距离须不超过容差。\n支持target为closed Polygon、Mesh、Sphere、Tube；source必须是polygon/mesh表面顶点。\nPacked/volume/NURBS等暂未验证的表示返回unverified。超点数/内存/查询预算拒绝，不抽样假绿。\n这个检查**不证明**整个表面无穿插、包含深度、焊接、机械强度，也不能把方向平行当成连接。\n需要插入或实体相交时应选择对应独立方法，不通过放大max_distance来使错误结果变绿。\n顶点对顶点的最小距离是完整表面最小距离的上界，不是安全间隙下界；面中部相交时顶点仍可远离。\n源顶点到真实目标表面也只覆盖这些样本，不证明连续全表面无穿插。要求贴合时检查指定接口的\n全部声明样本；要求无碰撞却无适用检测时保留unverified。独立装配允许经设计确认的间隙，\n不因没有共享点就强制Fuse/Boolean，也不把封闭且朝外的各部件当作装配关系已通过。\n\n## 控制契约：改变什么，什么必须不变\n\n### 实际表面组的轴向间隙（v12）\n\n上下叠放/沿轴布置的部件，可用最终输出primitive组计算投影间隙，避免重复构造公式自证。\n例如声明source为上方部件、target为下方部件：\n\n```python\nrelations = [{'id': 'stack_projection', 'method': 'axis_gap',\n              'source_group': 'upper_surface', 'target_group': 'lower_surface',\n              'axis': 1, 'gap_range': [-0.001, 0.001], 'min_overlap': 0.01}]\nmeasured = geo_check_interfaces(out, relations)\n# 同一关系可以进入参数扰动窗口，在基准与每个case上复查：\ntested = test_controls(controller, out, tests, interfaces=relations)\n```\n\n数值仅示schema，范围按设计单位明确。量测是source.min[axis]−target.max[axis]；正数为分離，\n负数为轴向投影重叠。另外两轴区间重叠须≥min_overlap。曲面bbox相接不证明表面实际接触，\n需要真实接触时再加适用的点到面接口；不用于任意弯曲榫接、实体穿透深度或强度认证。\nsource/target必须为实际交付中的非空且互不重叠primitive组；不得临时加入driver点伪造表面。\n观察→参数扰动→同关系复查→完整恢复应在test_controls内完成，不能以恢复了几个bbox替代bgeo恢复证据。\n\n在暴露参数时声明一个可测预期：具体输出部件、metric、测试值与有符号delta允许区间。\n优先测相关primitive group，避免整体bbox掩盖局部变化。至少确认每个交付控制有预期作用；\n相互依赖的控制再选择少量组合测试，不把一次通过说成全范围成立。\n\n```python\ntests = [{\n    'id': 'length_response',\n    'values': {'length': 1.2},\n    'expectations': [{\n        'group': 'driven_part', 'metric': 'bounds_size', 'axis': 0,\n        'delta': [0.199, 0.201],\n    }],\n}]\nreport = test_controls(controller, out, tests, interfaces=interfaces)\n```\n\n示例基准length为1、单位米且输出长度一比一响应；实际参数/目标变化由任务决定。\nmetric精确为bounds_size、bounds_center、bounds_min、bounds_max（axis0/1/2）、point_count、primitive_count、area；不接受center/min/max缩写。\nv11另支持point_mean（axis）、boundary_edges、piece_count（Polygon共享边连通）、max_point_displacement/mean_point_displacement。\n位移必须提供id_attrib：稳定唯一integer/string point ID，面连接在ID空间保持一致；对应关系变化返回unverified。\n已知变换的控制可附max_transform_error，提供同样id_attrib、实际primitive group和transform（16数row-major仿射矩阵，Houdini行向量约定，SOP-local空间）。它测量全组真实点相对`P_baseline * transform`的最大残差，baseline残差定义为0；delta/range使用设计容差，另加一项非零位移响应。将主体和附属件声明为同一变换，未选中组声明identity，可检出“主体动了但附属件不跟随”。它不是拟合当前结果来反推正确变换，也不证明全部姿态/碰撞；混合几何的点均值不能当设计轴心。修改生成器后需重新建立基准。\nexpectation可带range=[min,max]检查基准及扰动绝对范围，例如封闭面的boundary_edges要求range=[0,0]、delta=[0,0]；\n单纯delta=0不能证明基准已闭合。仍需至少一条响应delta排除0；有意分组切口不能无条件要求闭合。\n每case至少一个delta区间必须排除0以声明实际响应；不变量可作为额外expectation。\n这是数值标量测试，只传组件名，不直接传元组、菜单、按钮、multiparm或callback控制。\n测试值被范围钳制而未按要求生效时判失败，不把未真正执行的case计为通过。\n\n每个case先改值/cook，再测指标与接口，最后恢复原值、表达式、关键帧、frame，并核对实际\noutput完整bgeo解码数据恢复：排除导出头date和派生group_summary，已知组目录按组名规范排列；\n保留所有组成员、ordered group内部顺序、用户属性及几何。原生Tube/Sphere半径不靠P-only判定。控制测试当前仅支持\nPolygon/Mesh/Sphere/Tube及点几何；Packed/NURBS/volume等在写参数前返回unverified。\nPacked序列化含随recook变化的数据，暂不把原始bgeo hash当它的恢复oracle。\n恢复失败必须停止继续改场景并检查，不自动抹掉错误；无法测量的类型保持unverified。\n文件I/O、Python/solver状态、未声明外部回调不属参数恢复范围，不要对此类控制运行测试。\n\n## 读结果与返工\n\n- 先读control_summary的status/reason/case_counts和restored；results=[]可能是基准失败或unsupported，not_run不是pass。摘要保留controller/output、失败case/判据和基准值，不能只打印results后丢掉失败原因。\n- `status=fail`：看具体接口点/最近primitive/距离，或控制测量的baseline/measured/delta。range同时约束基准与扰动；只希望约束变化时用delta。验证恒定件时连同应响应的主体一起选取，保留非零响应以排除死控制。\n- `status=unverified`：证据方法不支持，不得改写成pass；换经过验证的数据表示或独立方法。\n- `restored=False`：状态恢复异常，先处理，不重试下一case。\n- `ok=True`：仅已声明接口/控制case通过；还需最终网络warning及视觉质量验收。\n- 数值最近距离是无符号邻近，不等于插入深度；整组bbox极值对称不是镜像几何。需要局部轴、明确部件对和覆盖范围，方法不能证明的关系保持unverified。\n- 保存草稿/部分交付不被这些门禁止，完成报告必须保留未完成项。\n\n修订生成器后刷新受影响检查，不沿用旧geometry_sha256/contract_sha256。接口检测和构造可\n共享设计坐标，但验证必须从真实交付表面取值，不能只检设计anchor的一致性。\n期望写错可以依据独立解析或已知几何纠正，但修正后必须复跑受影响case；语言解释不能替代新结果。\n\n## 来源与验证\n\nSideFX [Prim.nearestToPosition](https://www.sidefx.com/docs/houdini/hom/hou/Prim.html#nearestToPosition)\n和 [Geometry.freeze/data](https://www.sidefx.com/docs/houdini/hom/hou/Geometry.html)；本项目\n`dsh-quality-contracts.test.py`覆盖连接正例、方向正确但脱开、默认通过/扰动失败、空组、基数、\n自重叠、游离driver点、unsupported target、预算、死控制、原生Tube、表达式/cook恢复、ownership。\n`dsh-interface-evidence.test.py`另覆盖真实实例脱开、允许间隙、接触及相交时顶点距离仍为正的反例。\n工具合同以目标版本回归为据；SOP工作流自然采用仍需新会话验证，不宣称制造认证。\n\n\n## v13：不改变交付网格的截面观察\n\nApplies when：独立Polygon部件在明确轴平面处应邻近另一表面，现有顶点太稀或点组选取随参数跳变。\nDo not use when：任意实体碰撞、融合部件、自交或需要证明整面接触；共面面/歧义截面保持unverified。\n\n```python\ninterfaces = [{'id':'section_fit', 'method':'section_proximity',\n  'source_group':'supports', 'target_group':'cross_member',\n  'axis':1, 'plane_at':'target_center', 'expected_components':4,\n  'max_distance':0.002}]\nreport = geo_check_interfaces(out, interfaces)\n```\n\n示例数字只是schema；组件数量和容差来自任务。每个源组件都需非空闭合截面，取实际交线段中点到目标面的距离。\n不需要给交付网格加Resample，也不把expected_points简单删除。component_coverage明确各组件样本量，\n预算/不支持保持显式状态。参数扰动复用同一interfaces，target_center每次来自目标实际几何。\n\n派生参数域可用数据化线性右值，例如移动量必须低于可用尺寸减去壁厚和余量：\n\n```python\ndomain = [{'id':'clearance', 'left':'travel', 'op':'lt',\n  'right':{'terms':{'available_length':1, 'wall_thickness':-1}, 'constant':-0.01}}]\n```\n\n不执行表达式字符串、不自动钳制；它只验证声明case。至少选一个接近耦合边界的组合，\n对真实输出关系复验，不能用两个公开参数大小关系代替全部派生锚点。\n\n闭合壳的观察分三层：boundary_edges、orientation_conflicts、shell_orientation。\n后者positive只在简单非嵌套壳条件下解释为外向；自交/嵌套未测，开放表面不推断内外。\n双面预览能掩盖反向面；按HOM primitive normal与已知外表面方向核对，不能任取叉积约定。\n\n实现回归见`dsh-modeling-semantics.test.py`；过程证据留在会话/CI或非发布临时产物，\n新模型自然采用及质量提升仍待新会话验收。\n"},{"path":"references/procedural-quality-contract.md","hash":"350eb8f6be9536d163e1aeef7b3349ae1defd01562b2840a6daba42257d8096f","bytes":5699,"text":"# 程序化 SOP 质量合同\n\n## 何时使用\n\n当任务开放式、依赖真实世界参考、包含多个相互连接的部件、要求可调资产，或“高质量/细节丰富”\n会显著改变建模路径时使用。用户已经提供精确 recipe 的小修改、抽象造型探索和一次性可逆 probe\n不必机械填写完整合同，但仍保留相关完成门。\n\n## 最小合同\n\n在大规模建图前记录下列会改变决策的字段；未知项写 `unknown` 或显式假设，不伪造精度：\n\n| 字段 | 内容 | 可接受证据 |\n|---|---|---|\n| target | 对象/效果、变体、使用场景 | 用户选择、现有场景、来源明确的参考 |\n| reference status | 外部参考、用户参考或明确的无参考边界 | URL/图片/规格表/用户授权的假设 |\n| quality/LOD | 轮廓级、镜头级、产品级、模拟代理等 | 用户目标和最终观察距离 |\n| simplifications | 哪些结构可省略，哪些关系不可破坏 | 用户确认或带风险的显式选择 |\n| units/dimensions | 单位、关键尺寸、允许范围 | 场景单位、规格来源、用户给定值 |\n| controls | 用户需要调整的参数、范围和依赖 | 控制节点、spare parms、HDA interface |\n| anchors | 共享轴、端点、基准面、中心和局部坐标系 | 单一 detail/属性/参数源 |\n| module relations | 部件之间必须满足的空间/数据关系 | 下表中的逐项检查 |\n| evidence plan | 数据检查、特写视角、动画帧和停止条件 | 可执行动词/查询与明确视角 |\n\n引用外部真实性时要记录来源；没有来源时只能报告“内部一致/基于假设”，不能升级成“符合真实范围”。\n需要用户补齐合同时，先把常见且会改变路径的选择做成选项并说明影响，再允许用户用自定义文本补充；\n不要把车型、LOD、交付深度和允许简化全部推给一个空白输入框。\n\n## Anchor 与依赖\n\n先建立尺寸和 anchor，再让模块派生：\n\n```text\ncontrols / reference dimensions\n  → named anchors and local frames\n    → module generators\n      → relationship checks\n        → integrated output\n```\n\n- 一个会影响多个模块的量只有一个维护位置；下游用引用、属性或表达式派生。\n- 模块输出保留稳定的 `part_id/module` 等标识，便于局部统计和关系检查；标签的具体名称可按资产约定。\n- 绝对坐标不是禁用项；只在它确实是局部常量且不会与其他模块重复表达同一事实时使用。\n- 一次合理调参后若必须手改多个代码字符串才能恢复连接，参数化完成门失败。\n\n## 常见模块关系\n\n只选择任务相关的关系，不要求每个资产套满：\n\n| 关系 | 需要证明什么 | 反例 |\n|---|---|---|\n| coincident axis | 两个部件共享或按偏移共享轴线 | bbox 重叠但轴向错误 |\n| anchored endpoint | 端点位于命名 anchor 的容差内 | 视觉靠近但实际悬空 |\n| contained/inserted | 部件进入目标范围并保留正确深度 | 全部穿透或只擦边 |\n| clearance | 最小间隙在允许范围内 | 为消除一处冲突而制造另一处冲突 |\n| forbidden intersection | 不允许的部件对没有相交 | “被遮住所以可接受”但合同未允许 |\n| contact/grounding | 接触位置和法线符合用途 | 只用全场 bbox 推断接触 |\n| symmetry/pairing | 对称或成对件共享规则且允许指定差异 | 分别硬编码后逐渐漂移 |\n| attribute continuity | 下游所需属性 class/value 连续 | Merge 无 error 但属性默认化 |\n\n现有词表不能直接给出关系时，可用只读 HOM/局部几何 probe 建立证据，并把重复出现的通用意图\n记录为工具候选；不要为单个资产发明专用 verb。\n\n## 验证阶梯\n\n1. **合同门**：参考、假设、LOD、控制和关系清单足以决定建模路径。\n2. **骨架门**：只建 anchor/中心线/代理体，先验证比例、轮廓和关系，未通过不加装饰。\n3. **模块门**：逐模块验证输入/输出、局部几何、属性、cook 与参数响应。\n4. **集成门**：按关系清单检查连接、包含、间隙、禁止相交和 warning；非退化统计只是其中一项。\n5. **视觉门**：声明资产轴向，整体验轮廓，局部特写验小部件与连接；有外部参考时使用可比较视角。\n   先用 `render_view.check`/`render_check` 拒绝近黑、空白、目标缺失或裁切图片，再做语义读图。\n   首次语义读图先记录缺陷与不确定项，再决定修订或降级，不以“可辨认”代替质量通过。\n6. **扰动门**：改变至少一个关键用户控制，重跑受影响模块和关系门，证明资产不是只在默认值成立。\n   恢复交付值后再 cook 和复验，避免把测试状态留给用户。\n7. **交付门**：最后一次几何修改后重新采集统计、warning、关系证据和交付视图；只陈述有证据的\n   完成度，逐项列 `pass / fail / unverified`，并列出未验证的外部真实性、审美和简化边界。\n\n## 边界与反例\n\n- 风格化或抽象任务可以由用户授权 agent 自选比例；仍要把该选择写成风格假设，而非真实规格。\n- 低 LOD 允许省略内部机械结构，但不能破坏用户要求的轮廓、连接或运动语义。\n- 用户说“你决定”不等于无需合同；agent 可以自行选择，但要披露选择和完成门。\n- 更多节点、更多 primitives、无 cook warning 或能渲染，都不是“细节丰富/高质量”的充分证据。\n- todo 完成、旧截图或修改前的点数不能证明最终状态；最后一次 mutation 会使依赖它的旧证据失效。\n"},{"path":"references/sop-patterns.md","hash":"cb5966d4ad579c9157ea5fb6ebee04569a6c2665fdf036b2e7dbf026f7581602","bytes":12164,"text":"# SOP 稳健模式\n\n## 目录\n\n1. 模块契约模板\n2. Copy to Points\n3. 形变与成形顺序\n4. 属性传播\n5. 局部几何验证\n6. 时间动画\n7. 视觉与用户 viewport\n8. 失败恢复和性能\n9. 小模块构建与检查 fast path\n\n## 1. 模块契约模板\n\n每个分支先写：\n\n```text\n输入：拓扑、坐标空间、必须属性\n操作：使用的原生 SOP/VEX\n输出：新增/删除/变更的几何和属性\n不变量：根部固定、宽度非零、piece 数、面积、bbox、warning\n验证：cook_node / describe / geo_* 动词\n```\n\n模块尚未通过时不要进入材质、相机或灯光调试。\n\n## 2. Copy to Points\n\n适用：把一个或多个源几何复制/实例到模板点。\n\n模板点常用属性：\n\n- `P`：根位置。\n- `orient`：四元数旋转。\n- `N` + `up`：没有 orient 时的对齐基。\n- `pscale` / `scale`：统一/非统一缩放。\n- `id` / `phase` / `variant`：后续随机和动画标识。\n\n流程：\n\n1. 先验证模板点属性数值。\n2. `search_tab_menu('sop', 'copy to points')`。\n3. `tab_create(..., 'copytopoints', inputs=[source, points])`。\n4. 验证 Copy 后属性和 piece local extent。\n\n不要因为 classic Copy 看起来熟悉就使用它。若必须使用 classic Copy，要明确其模板属性传递参数，并验证 Copy 后相邻点/单 piece，而非只看全场 bbox。\n\n## 3. 形变与成形顺序\n\n稳健顺序通常是：\n\n```text\n中心线/低维拓扑\n→ curveu/rest/root 等驱动\n→ 时间变形\n→ Sweep/ribbon/skin 生成宽度\n→ Copy/Merge\n```\n\n或对每实例刚性摇摆：\n\n```text\n成形后的单元\n→ 模板点时间依赖 orient\n→ Copy to Points\n```\n\n危险模式：\n\n```text\n中心线保存 local P\n→ PolyWire/Sweep 生成截面\n→ 用旧 local P 重建所有截面点\n```\n\n它会把截面点压回中心线。任何 rest/local 坐标都必须说明捕获时的拓扑阶段。\n\n## 4. 属性传播\n\n检查属性 class：point、primitive、vertex、detail。Copy/Merge 后：\n\n- 驱动属性是否复制到所有目标点。\n- `Cd/N/uv` 是否因输入不一致产生默认值。\n- 同名不同 class/size/type 是否冲突。\n- 临时属性是否在交付前删除。\n\nMerge warning 是数据契约失败证据。用 Attribute Delete/Rename/Promote 或显式初始化解决，不要忽略。\n\n## 5. 局部几何验证\n\n全场 bbox 会被散布 root 位置放大，不能发现每个实例零宽。\n\n使用：\n\n```python\ngeo_piece_stats(copy_or_deform_node)\n```\n\n检查：\n\n- piece count 是否符合实例数。\n- sampled piece 的 extent/area。\n- `degenerate_surface_pieces`。\n- 变形前后 piece 面积和最小 extent 是否保留。\n\n需要追查时先隔离一株/一个 piece，再看全场。\n\n## 6. 时间动画\n\n不要只写 `@Time` 就宣称动画成立。\n\n```python\ngeo_frame_diff(out, 1, 12, attrib='P')\n```\n\n验证：\n\n- 根部或锚点近似不动。\n- 尖端/活动点有显著位移。\n- 波峰沿预期方向传播。\n- frame A/B 的 topology 是否一致。\n- 用户当前 frame 在调用后未改变。\n\n全局 `mean_delta/max_delta` 非零证明时间依赖，不自动证明审美语义。若固定相机 A/B 暴露完全静止、方向相反、主体缺失等明确反例，应回到风场设计；若节点、属性、锚点/活动区和时间依赖均通过，而两张静帧只是不足以裁定细微动态或视觉力度，可诚实交付“画面待用户播放判断”，不能宣称视觉已经确认，也不必无限渲染说服视觉模型。\n\n做render A/B时锁定相同direction/画幅/模式，复用framing_frame和覆盖状态的framing.bounds、framing.depth_bounds；核对matrix/focal/orthowidth，差异会把相机变化混入pixel diff。full取景不足应修正事先选定的共享包络，不逐帧移动相机；减小coverage会留更多边距，不是扩大coverage。detail只允许二维裁框，depth_check失败不能当有意裁切；focus未隔离时深度包络还包含周围几何。\n\n若 geometry diff 非零但 render diff 为零，调查 proxy/ROP 缓存；若两者都为零，调查表达式、spare 参数和 time dependency。\n\n## 7. 视觉与用户 viewport\n\n- `render_view(EXPLICIT_SOP)`：agent 产物验证，走隐藏 proxy；用户 display/visibility 不选择源。\n- `viewport_screenshot`：用户屏幕诊断；用户显示空节点时空图是正确诊断结果。\n- 两者对照：render 有内容而 viewport 空，说明用户 display/viewport 漂移；两者都空，回到 SOP 数据。\n\n视觉 prompt 先中性描述，不要预设“这是成功的草地”。\n\n## 8. 失败恢复和性能\n\n- 利用 exec undo rollback；失败结果检查 `rollback.applied`。\n- 文件写入和 HDA 库修改不在 Houdini undo 范围内，必须另做事务/备份。\n- 把大网络拆成 checkpoint batch；每批可重复、可验证。\n- 性能以 cook time、点面数和 SideFX Performance Monitor 为证据，不用工具调用次数代替 cook 性能。\n- 结束时 `layout_nodes`；缺省只整理当前 agent session 创建的节点并返回\n  `foreign_nodes_skipped`，不要为了整洁移动用户临时创建的节点。\n\n## 9. 小模块构建与检查 fast path\n\nv12：声明Sweep第二输入时tab_create会在接线后校正surfaceshape=input，build显式parms仍优先。\n静态node_info默认值不保证等于Shelf创建值；保留卡片components/usage_notes，不只回传参数名。\nbuild_module的独立参数/输入错误一次汇总为preflight errors，按具体field/components一起修，不重发多次长spec猜字段。\n组合多个交付分支时可传required_outputs=[分支输出名,...]，防止Merge非空掩盖某个必需分支为空；\n辅助空CTRL不在此列。仍优先按可独立检查的小模块构建，不把所有造型塞进一个大batch。\n\n准备阶段读node_info的usage_notes/operation_card.decisions/operation_parameters；关键设置不受\n普通参数filter/limit裁切。单节点事实仅由随包操作卡维护，不在reference复制菜单索引或默认值。\nbuild_module的operation_advisories按类型/缺少的显式选择合并；尚未决定时dry_run后修spec，\n已明确意图可直接build，不为清除提示改变有意开放/native/all-edge输出。零提示不证明几何正确。\n构造顺序：明确表示和局部坐标→一个单元→inspect实际表面/截面→再复制→按身份集成。\n用geo_piece_stats(out,inspect=True,group=...)观察边界和局部basis extent；非Polygon返回unverified。\n有意分组切口不视作整体实体破损，整体bbox不能证明弯曲薄片有管状截面。\n同一exec后项失败会回滚前项成功的模块；transaction记录最终状态，普通诊断读取放query。\n独立模块分不同exec提交，再用仍存活的输出集成；不能独立验收的部件保留同一事务，不能靠catch\n异常让半成品提交。返回已知validation即可，陌生返回类型先verb_help查看return_type/call_mode。\n\n适用：在现有 SOP parent 中新增一个可以独立 cook 的小模块；H21.0.440/H22.0.368 的\n类型、参数菜单、失败清理与 warning 传播已有工具回归。行为发布仍需未见新 session 验证。\n不适用：修改既有节点、OBJ parenting、Karma setup、HDA 库编辑或模拟写盘；这些继续使用\n对应 primitive/domain verbs，不把多种生命周期塞进一个 build。\n\n输入是新节点声明和已有输入，输出是一个明确 SOP。例如（parent 是当前任务的 SOP 容器）：\n\n```python\ncard = node_info(parent, 'xform', parm_filter='scale')\nspec = [\n    {'name': 'unit', 'type': 'box'},\n    {'name': 'shaped', 'type': 'xform', 'inputs': ['unit'], 'parms': {'sx': 1.5}},\n    {'name': 'OUT_MODULE', 'type': 'null', 'inputs': ['shaped']},\n]\n# 接口已知可直接构建；有静态字段疑问时才 dry_run，它不证明 VEX/cook。\n# build_module(parent, spec, output='OUT_MODULE', dry_run=True)\nresult = build_module(parent, spec, output='OUT_MODULE')\n__result__ = result['validation']\n```\n\n消费 checkpoint，不只看 Python 成功：\n\n- `validation.ok=False`：error 或空输出，不能进入后续细化。\n- `warning_free=False`：检查 issues 中的真实节点和属性；解决或记录明确边界。\n- `scope/checked_nodes`：说明检查覆盖；模块范围不能冒充整网。\n- `semantic_status='unverified'`：还要验证原型、关系与视觉，不能自动改成 pass。\n- `frame/checked_at/output_fingerprint`：用于识别证据属于哪个输出状态；抽样指纹不是\n  全量拓扑/材质证明。用户或 agent 改了受影响参数/接线后重新检查。\n\n输入只引用前面 spec 或现有直属 child 名，可用 None 跳过input；如 Wrangle 的 `[None,'anchors']`。\n跨 subnet 在目标网络创建 Object Merge 并用objpath1引用源，不尝试用不同端口跨网络接线。\n模块不覆盖同名节点，失败清理本批新增节点，\n不自动改变用户 output；单节点仍可 `tab_create`。收尾再 `sop_set_output`。\n\n菜单示例：`set_parm(wrangle,'class','detail')` 的 detail 是 token，不是 label/任意表达式；\n动态菜单由 `list_parms(wrangle)` 给出。需要菜单表达式时显式传\n`{'expression': '0', 'language': 'hscript'}`；表达式与普通字符串不混猜。\n\n失败转向：先消费 returned error 和 node_info/list_parms；同边界两次失败就停止重放整个模块，\n用一个最小 primitive probe 查缺口。完成前删除 probe；文件/参数回调副作用不在模块删除保证内。\n\n来源：本项目严格设参、SOP 模块回归与节点卡运行结果；SideFX\n[Parm API](https://www.sidefx.com/docs/houdini/hom/hou/Parm.html)。\n验收必须写显式 `verify_network(parent,output=out)`；省略output不再跟随display，空/error输出\n默认硬失败。`require_valid=False`仅供保留失败诊断，不得替代复验。读取operation-evidence中的\noutput/frame/scope/失败原因，而不是只看开头“Python执行成功”或取不存在的errors字段。\n\n已有节点的局部文本更新适用set_parms的literal patch；先在query读取实际字段：\n\n```python\n__result__ = read_parms(target, names=['snippet'])\n```\n\n再在exec使用读到的source_sha256及实际的唯一锚点（old_text/new_text由本次改动决定）：\n\n```python\nset_parms(target, {'snippet': {\n    'expected_sha256': source_sha256,\n    'patch': [{'old': old_text, 'new': new_text, 'count': 1}],\n}})\n__result__ = verify_network(parent, output=output)\n```\n\n缺锚点/多命中/hash过期时，重读当前字段并修正补丁；不删除expected_sha256或随意增加count。\n本节点本批全部patch在任何设参前校验；跨节点仍以模块事务划分，不能把它当跨节点dry_run。\n只支持无动画/表达式的literal string；带表达式/keys的代码先明确编辑意图，用原设参或资产接口，\n不烘焙后冒充保留动画。输出hash证明文本回读，VEX语法/非空几何/关系须照常验收。\n补丁数量、字符预算与返回字段以verb_help为准。无需全文替换时返回也只含变化摘要。\n\n证据等级：H21.0.440/H22.0.368工具合同、故障注入与行为采用分别记录；弱模型未见任务增益 candidate。\n验证入口：tools/tests/dsh-parameter-patch.test.py、dsh-module-boundaries.test.py。最后核对：2026-09-08。\n\n\nv10候选（H21/H22隔离回归）：node_info返回默认multiparm实际编号；build_module支持显式\n整数count（0..64）并按父count→子count→字段顺序赋值。动态count/超过静态预算仍走\n原生tab_create/list_parms，不为预检限制改写成VEX。数值参数字符串为HScript表达式；需要\n显式语言用{expression,language}。先前错误节点的cook_node会刷新旧错误；仍失败直接读\ncook_details定位，不重发无关模块。Toggle的test_controls用整数0/1，菜单/按钮仍不支持。\n\n\nv13设值提示：node_info菜单项的set_value是可直接设置值，菜单token也由setter转换；菜单表达式用显式对象。\n替换Merge既有输入直接connect，断开后消费inputs_after再操作；不要把旧索引当稳定身份。\n"},{"path":"SKILL.md","hash":"4eb6f3d17e013e36d055e1b62934341d3e9861b17737084dfc07c9a77336c6f0","bytes":9388,"text":"---\nname: houdini-sop-workflow\ndescription: 设计、构建、调试和交付 Houdini SOP 程序化网络。用于建模、散布、Copy to Points、属性传递、VEX成形、Sweep/PolyWire、Merge和SOP动画；尤其涉及多模块空间关系、可调控制、局部几何/拓扑、cook warning或视觉取证时。不用于纯场景查询，也不代替rig或Solaris领域流程。\n---\n\n# Houdini SOP Workflow\n\n以一个正确、可观察的原型推进。新增细节前先确认主要形体和实际连接；每次检查明确输出、方法与范围。\n\n## 进入任务\n\n先读Host现场摘要：HIP、版本、frame、选择、候选网络与采集时间。缺失不代表空场景；需要时用scene_info/find_nodes/graph补查。用户选择会变化，快照不构成foreign修改授权。\n\n简单、规格完整的编辑直接修改并回读。普通可调模型用几句说明目标、自选尺寸、控制和验证范围。质量敏感、外部真实性或复杂装配在大规模建图前读[质量合同](references/procedural-quality-contract.md)；外部参考会改变方案且research/web可用时实际检索，无来源就标假设。只询问会改变方案的选择，一次给有影响说明的互斥选项，不因“程序化”启动长问卷。\n\n## 执行循环\n\n1. **方法与原型**：选择曲线/截面/开放表面/实体/实例等表示。集中关键控制，建立named anchors/local frames和稳定piece身份。明确模块输入、输出、属性class与不变量；多模块装配读[模块合同](references/module-quality-contracts.md)。\n2. **当前节点知识**：当前模块按不同type集中读node_info；消费operation_card.decisions及不受filter影响的operation_parameters，先决定表示/封口/选择范围/执行层级再build。同版本静态卡可复用，Shelf值和动态菜单仍以实际节点为准。普通参数默认24项；filter是字面子串，空匹配先去掉filter，不为找参数创建一批probe。visible=false用search_tab_entries；未知签名先verb_help。\n3. **骨架门**：只建代理体/中心线/主要截面，查世界位置、尺寸、方向和主连接。视觉交付已在范围内且GUI可用时，尽早看可辨认的整体或明确侧向图。主要比例/位置错误先修骨架，不进入细化。\n4. **模块门**：一个build_module对应可独立cook的小模块和明确非空output；空CTRL/helper用tab_create。先验证单元及其附属件连接再复制。检查实际表面/截面、封口、法线/属性与尺寸；闭合、共享边方向一致和朝外分别查，Normal不修顶点序。消费validation/cook_details，warning清理或解释，不为清warning丢掉最终部件身份。\n5. **关系门**：每完成一个模块就检查相邻关系，测最终变换后的实例表面，不测未变换原型。独立表面用适用的interfaces，融合Polygon才用共享拓扑；顶点对最小距离不能证明无穿插，距离不等于插入深度。接地逐足检查；合法装配间隙按任务判断，没有可靠方法保留unverified。\n6. **参数门**：代表性控制测响应和需保持的不变量，再恢复。先读test_controls的control_summary/status/reason，results=[]不等于通过；range覆盖基准与扰动，delta是变化。范围来自设计，耦合控制再测边界组合；判据错需独立理由并复跑，不能改窗口凑pass。bbox变化不证明连接、刚体变换或整个参数域。\n7. **交付门**：集成后verify_network(parent,output=实际交付SOP)，最后一次相关修改后刷新必要统计、关系和图像。布局、恢复frame/selection/visibility、设sop_set_output，再保存。未命名HIP用有授权路径及当前HIP校验的scene_save_as；保存失败不能宣称完整交付。\n\n模块与关系循环推进，不等所有细节完成才检查装配。此处骨架是代理形体，不是KineFX rig；几何父子/FK转rig skill。\n\n## 执行与恢复\n\n- build_module声明name/type/parms/inputs/output；None表示空输入槽。跨subnet使用Object Merge或明确端口。connect(src,dst,index)直接替换既有输入；Merge先断后接会前移丢分支，消费inputs_after。set_parms保持strict，不能以strict=False绕过构建失败。\n- 组合构建声明required_outputs检查必需分支；preflight多项错误一次修正，保留components/菜单set_value。设置尚未决定时用dry_run集中读operation_advisories再构建；已明确时不强制双调用。advisories只提示缺少显式选择，不改默认值，也不证明选择正确。最终分支保留语义primitive组。\n- tab_create返回hou.Node；list_parms/read_parms返回list。菜单用token/set_value，菜单表达式用{expression,language}；普通数值字符串是HScript表达式，VEX在snippet内；tuple表达式用组件字段。见[fast path](references/sop-patterns.md#9-小模块构建与检查-fast-path)。\n- 更新已有spare默认值用create_spare_parms(update_defaults={name:literal})，当前值另用set_parms；两者回读分开。不支持的参数按verb_help边界报告，不因猜错HOM方法而断言环境不支持。\n- 可独立cook/验收的模块各用一次exec，引用存活输出后另做集成；不可分的部件仍在模块内批量修改。看transaction最终状态：同一exec后方失败会撤销前方可撤销修改，不沿用被回滚依赖；陌生回读另开query，模块返回直接使用已知validation，避免尾部格式化错误撤销构建。\n- 局部源码改动先read_parms(names=[代码字段])取得当前原文和hash，再用set_parms的literal patch；全部锚点/次数在本节点本批写入前验证，不能静默忽略0命中。跨节点不共享此预检，仍按模块/exec恢复；详见[fast path](references/sop-patterns.md#9-小模块构建与检查-fast-path)。\n- 同一模块边界连续两次失败，回到最后有效输出做最小单变量诊断或换方法；不反复全文重建多个未知模块，不catch mutation/cook异常后继续。\n- 保留小状态摘要：当前输出/身份、未过关系、最新证据frame/时间、受影响修改；只重验受影响检查。\n\n## 观察与关键方法\n\n- geo_piece_stats默认按连接性或指定身份属性统计局部extent/面积；inspect=True观察命名primitive组的Polygon边界/边连通/非流形和basis下extent；shell_orientation保留有向体积条件。半径用到轴的欧氏距离，轴向投影不是半径。observed仅量测，分组切口可有意开放。\n- geo_attrib_stats读驱动属性；复制前用unique=True检查模板P/id的精确tuple唯一性及预期基数，bbox不变不能排除重叠复制。geo_point_spacing只测有序点弦长。test_controls位移/变换误差要求稳定唯一id_attrib和相同面连接；选中件及其附属件查同一预期变换，未选中件查identity，见[模块合同](references/module-quality-contracts.md)。混合网格点均值不是设计中心，native/packed不靠P-only。\n- Copy to Points承担实例变换，模板orient/scale与原型局部轴需一致；Copy/Merge明确属性class和传播。带状物用有面积截面，非刚性成形通常先作用中心线/低维结构再生成厚度。细节见[方法参考](references/sop-patterns.md)。\n- 需要选择基础成形方法、局部倒角/分组或高细节细化时读[建模方法与细节预算](references/modeling-methods.md)；精度不等于面数。用户要求多agent模块协作时读[并行设计、单作者执行](references/module-design-collaboration.md)，没有可用的受限设计子agent入口就保持单作者，不借review权限建模。\n- 每图绑定问题和部件。render_view用focus_group/isolate选关注范围；full保证完整入镜，detail仅允许画框裁切，不允许近远裁面切断。framing_bounds在full中不是局部ROI。A/B同时复用framing.bounds和framing.depth_bounds（全部渲染内容）及方向/画幅/模式；深度或完整构图越界零渲染失败，不漂移相机。普通预览不必创建正式相机调用camera_fit。\n- 消费render_view.check（pixels兼容别名）与framing.depth_check；看到断口先排除深度裁切，不能用拓扑pass或不同条件的图确诊着色问题。空白、近黑、错误目标不通过；detail有意裁框仍须读图确认所需局部可辨认。按media.inspection读图，先描述事实再核销疑点；遮挡不等于缺件，无地面参照不能断言接地。\n- 用户屏幕异常才用viewport_screenshot；保留持久__dsh_houdini_*服务。纯网络交付或无GUI不强制追图，视觉未验证则明确报告。\n- 动画至少两个相隔帧的实际几何/固定构图图像证据；A/B同framing_frame且覆盖帧包络。完全静止/方向错误是反例；细微审美无法裁定交给用户播放判断，不无限追图。\n\n## 完成范围\n\n最终显式输出非空、无error，warning已处理；单元与核心关系有对应实际输出证据；控制集中且代表性扰动/恢复通过。未测控制、unsupported、外部真实性、视觉不确定分别报告，不能用todo completed补证或把部分测量写成全部pass。关键控制不能靠重复改多个VEX常量维护。\n\n普通收尾不自动委派；用户要求或具体疑点才快速review，复用已有工具事实与图像。不再登记delivery合同。\n"}]},{"name":"houdini-solaris-karma-workflow","description":"在 Houdini Solaris/LOPs 中设计、构建、检查和交付 Karma 材质与渲染网络。用于用户要求最终渲染、Karma CPU/XPU、MaterialX、USD 材质绑定、Render Settings、AOV、USD Render ROP，或把 SOP/COP 结果接入 /stage；不用于仅需 render_view 的快速 SOP 视觉验证。","base":"skills/houdini-solaris-karma-workflow","files":[{"path":"references/karma-patterns.md","hash":"5894f5d2d4602468197a580ebbd96822316752fae82812aa06d0426fdfdb0087","bytes":6150,"text":"# Solaris / Karma patterns\n\n本文件记录会改变 agent 决策的版本化工作流，不复制完整 SideFX 手册。运行时先信当前\nHoudini 安装的 node/tool/help，再用官方在线文档核对概念与新版本变化。\n\n## 目录\n\n1. H21 标准 Tab tools\n2. 材质 render context\n3. SOP/USD 动画\n4. Render Settings 与交付 ROP\n5. 灯光\n6. Copernicus 接口\n7. 官方参考\n\n## 1. H21 标准 Tab tools\n\nH21.0.440 本机 shipped shelf：\n\n- `lop_karma_setup`，label `Karma (Setup)`：创建名为 `karmarendersettings` 的 Karma\n  Render Settings 与 `usdrender_rop`；ROP 表达式引用 settings prim、motion blur 和\n  CPU/XPU engine。它是多节点 setup，不是 `createNode('karma')`。\n- `vop_karmamtlxsubnet`，label `Karma Material Builder`：在 Material Library 根层创建\n  `karmamaterial` subnet，配置 Karma/MaterialX tab mask 与 `kma` render context；内部\n  默认包含 MtlX Standard Surface、MtlX Displacement、Karma Material Properties 和\n  Material Outputs/AOVs。\n\n工具 id 可能随版本变化；每次用 `search_tab_entries(actual_parent, query)` 发现，不能把\n本节当作跳过运行时查询的理由。`tab_apply` allowlist 暂只覆盖上述两个已回归意图。\n\nH22.0.368 的 shipped shelf 仍登记同名 `lop_karma_setup` / `vop_karmamtlxsubnet` 与相同 label，\n但当前完整 setup/material-builder 状态恢复和 USD Render ROP 出图回归只在 H21 GUI 执行过。\n因此“入口仍存在”是 H21/H22 已确认事实，“H22 完整 recipe 已通过”仍是未验证项；H22 任务\n必须先运行 parent-aware discovery 和最小 GUI 验收，不能由 shelf 文本直接外推。\n\n## 2. 材质 render context\n\n优先级不是“哪个节点能 cook”，而是目标 delegate 能消费哪个 render context：\n\n- Karma Material Builder：Karma/MaterialX 混合能力，默认 `outputs:kma`。\n- USD MaterialX Builder：纯 `outputs:mtlx`，适合跨 renderer。\n- USD Preview Material Builder：通用 preview。\n- VEX/Principled：主要是 Karma CPU/旧资产兼容；XPU 可能自动转换为有限的 preview，\n  画面有颜色不能证明原网络完整受支持。\n\n读取 SOP `Cd` 时，先在 `usd_prim_info` 确认导入后的 primvar 名和 class。SOP Import 常把\n它变成 `primvars:displayColor`；MaterialX 使用 Geometry Property Value 或兼容 primvar\nreader 显式读取。薄片植物的双面行为应由 MaterialX/Karma 几何或材质设置明确控制，\n不要依赖旧 Principled 的单一 toggle 名跨版本迁移。\n\n## 3. SOP/USD 动画\n\n- SOP Import 的 Author Time Samples 控制 authoring 策略，但某次 cook 只看到一个 sample\n  不等价于序列静止，也不等价于序列已验证。\n- 先在 SOP 用 `geo_frame_diff` 证明源数据随时间变化；再在最终 stage 检查 time-sampled\n  points/xform/primvars；最后用同一 USD camera 渲染两个间隔帧。\n- Motion blur 还依赖 camera shutter、Render Settings 和足够的 stage samples；它与“每帧\n  重新 cook 能产生动画”是两个不同契约。\n\n## 4. Render Settings 与交付 ROP\n\n标准职责分离：\n\n```text\nLOP scene chain -> Karma Render Settings\n                         |\n                         +-> USD Render ROP / husk process\n```\n\n- Render Settings/Product/Var 是 USD prim，属于 stage 数据。\n- USD Render ROP 是可执行 `hou.RopNode`，负责进程、frame range、output override、husk、\n  Slap Comp 等交付行为。\n- `render_frame` 接收可执行 ROP；普通 LopNode 即便有 `execute` 按钮也不应被当作\n  `render()` 对象。\n- AOV/denoiser 不在简单 beauty 测试时强制开启；用户要求合成、深度、Cryptomatte、\n  去噪或生产 EXR 时才配置并用 stage summary 检查 RenderVar/Product。\n\n静态整物镜头使用camera_fit：显式OBJ cam与SOP目标，保留焦距、清lookatpath、写入世界构图并回验。\nwidth/height应与最终产品一致；list_parms的locked_components能识别setup派生字段，不解锁表达式来凑分辨率。\nScene Import后用render_frame的framing={target:实际USD资产路径,coverage:.82}预检，不认为OBJ通过就等于USD通过。\n检查包括全部产品的camera、resolution/pixelAspect、aspectRatioConformPolicy与dataWindowNDC；不支持的ROP\noverride/外部USD/前置脚本/lens/Volume/PointInstancer明确拒绝，不暗中更改镜头或增加重渲染。\n此fast path适用于当前帧普通透视/正交包络，不用于艺术裁切、动画相机、位移/快门包络或语义质量认证。\n技术版本与回归状态见development的v14记录；未见任务自然采用仍待验。\n\n## 5. 灯光\n\n- 中性测试：Distant + Dome 合理。\n- 自然日光：Karma Physical Sky 把 sun 与 sky rig 合在一个物理模型中，优先于手工模拟\n  “真实天空”；艺术化灯光仍可自由组合。\n- HDRI：Dome Light；检查纹理路径、颜色空间与缺失纹理错误。\n\n灯光“最佳”取决于任务，不把 Physical Sky 设成所有场景的硬规则。\n\n## 6. Copernicus 接口\n\n未来 COP 能力先复用 Tab/setup/USD 地基，不在 system prompt 预载节点清单。常见接口：\n\n- Texture Material Library LOP + USD Material COP。\n- Quick Surface Material LOP。\n- Karma Material Builder 内 MtlX Image/Tiled Image 的 `op:/path/to/cop` 输入。\n- USD Render ROP Slap Comp。\n\n只有在真实 trace 需要低成本验证图层、分辨率、数据类型、保存或 slap comp 结果时，才\n新增 COP 自省/交付动词。\n\n## 7. 官方参考\n\n- Karma materials: https://www.sidefx.com/docs/houdini/solaris/kug/materials.html\n- Material Library: https://www.sidefx.com/docs/houdini/nodes/lop/materiallibrary.html\n- Karma XPU: https://www.sidefx.com/docs/houdini/solaris/karma_xpu.html\n- Karma Render Settings: https://www.sidefx.com/docs/houdini/nodes/lop/karmarendersettings.html\n- USD Render ROP: https://www.sidefx.com/docs/houdini/nodes/out/usdrender.html\n- Karma Physical Sky: https://www.sidefx.com/docs/houdini/nodes/lop/karmaphysicalsky.html\n- Copernicus workflows: https://www.sidefx.com/docs/houdini/copernicus/working_with_cops.html\n"},{"path":"SKILL.md","hash":"91d0c4e6eedc7096d3e72f8312a7e7ba722d4c4183639bdd73c5050f76c96482","bytes":3879,"text":"---\nname: houdini-solaris-karma-workflow\ndescription: 在 Houdini Solaris/LOPs 中设计、构建、检查和交付 Karma 材质与渲染网络。用于用户要求最终渲染、Karma CPU/XPU、MaterialX、USD 材质绑定、Render Settings、AOV、USD Render ROP，或把 SOP/COP 结果接入 /stage；不用于仅需 render_view 的快速 SOP 视觉验证。\n---\n\n# Houdini Solaris / Karma Workflow\n\n目标是留下当前 Houdini 版本中用户通过 Tab 菜单能理解和继续维护的 USD/Karma 网络，\n不以“有一张图片”替代材质、stage 和渲染契约。\n\n## 执行顺序\n\n1. 用 `scene_info` 确认 Houdini 版本、HIP、帧范围；明确单帧/序列和 Karma CPU/XPU。\n2. 最终渲染前先完成源 SOP 的 cook/warning/几何/动画验证。`render_view` 仍只负责快速\n   SOP 验证，Karma 不进入反复建模调试闭环。\n3. 对实际 parent 调 `search_tab_entries(parent, query)`。不要把全局 node type 注册表当作\n   用户 Tab 菜单，不要用裸 `createNode` 绕过 hidden/deprecated 或 builder tab mask。\n4. 新 Karma 材质默认从 Material Library 内的 **Karma Material Builder** 开始；用\n   `tab_apply(matlib, 'vop_karmamtlxsubnet')` 取得预配置的 Karma/MaterialX subnet。\n5. 新最终渲染默认用 `/stage` 的 **Karma (Setup)**；调用\n   `tab_apply('/stage', 'lop_karma_setup')`，保留它生成的 Karma Render Settings 与\n   USD Render ROP 及二者表达式。普通 `karma` LOP 或传统 Principled 能出图不代表这是\n   当前默认架构。\n6. 用 `usd_stage_summary` 验证 geometry/material/light/camera/RenderSettings/Product/Var，\n   用 `usd_prim_info` 验证 primvar、material binding 和 time samples；warning 必须解释。\n7. 整物构图先用 `camera_fit(正式OBJ相机,显式SOP)`，经Scene Import导入；不复用preview服务相机。对setup的USD Render ROP用 `render_frame(...,framing={'target':实际USD资产路径})` 在渲染前检查最终产品；长渲染走job。有意裁切/特殊lens另声明范围，不偷偷改用户相机，普通LOP不是ROP。\n8. 动画交付至少渲染两个间隔帧，固定同一 USD camera；SOP time dependency 或单个 USD\n   time sample 不能单独证明最终序列。静帧无法判断审美力度时交给用户播放判断。\n9. layout、保留 Render Settings 为 stage 交付输出、清理 probe、保存 HIP，并说明 engine、\n   material context、ROP、输出路径、warning 和尚未验证的事项。\n\n## 材质选择\n\n- Karma XPU 或新通用 Karma look-dev：Karma Material Builder + MaterialX/Karma 节点。\n- 需要纯 MaterialX、跨 Hydra renderer 可移植：USD MaterialX Builder。\n- 只需要通用 viewport/Storm preview：USD Preview Material Builder。\n- 传统 Principled/VEX 只在用户明确要求 Karma CPU/旧资产兼容且接受限制时使用，并在\n  交付中说明；不要把自动 USD Preview 转换误报成原 shader 的 XPU 完整支持。\n- 几何颜色进入 USD 后通常是 `displayColor`；在 MaterialX 中显式用 geometry property/\n  primvar reader 连接到 surface，不依赖旧 shader 的隐式 Cd 行为。\n\n## 按需参考\n\n- 构建材质、选择 CPU/XPU、设置标准 Karma ROP 或接入 COP 时，读取\n  [references/karma-patterns.md](references/karma-patterns.md)。\n- 若任务同时修改复杂 SOP/VEX/Copy/动画，先联用 `houdini-sop-workflow` 完成源数据门。\n\n## 完成门\n\n- 节点来自当前 parent 的可见 Tab entry；setup tool 的全部配套节点存在。\n- material prim 有明确 `outputs:kma`/`outputs:mtlx`/preview context，且绑定到目标 prim。\n- camera、lights、RenderSettings、RenderProduct 与 USD Render ROP 路径可自省。\n- 单帧产物存在、非空、无未解释 render error/warning。\n- 动画任务有最终 Karma 两帧或小序列证据；没有时只能报告“单帧完成”。\n"}]},{"name":"houdini-rig-animation-workflow","description":"在 Houdini 中设计、构建、调试和交付参数动画、刚体 piece 序列、机械层级、KineFX skeleton/skin 与 animator-facing rig。用于任务涉及 keyframes、绑定、FK/IK、capture/deform、非交换多步骤或可复用控制器；不用于普通静态 SOP 建模，也不把所有“绑定”默认路由到 KineFX/APEX。","base":"skills/houdini-rig-animation-workflow","files":[{"path":"references/rig-animation-patterns.md","hash":"c5600459de2b244b488091f5df43bb8047311476182923377e84d18b2ecb5eee","bytes":15573,"text":"# Rig / Animation 稳健模式\n\n## 目录\n\n1. Channel animation\n2. Rigid pieces 与路径依赖状态\n3. Hierarchy / KineFX / skin\n   - 3.1 KineFX 机械 FK 与刚体交付\n   - 3.2 OBJ scene parenting 例外\n4. APEX 与 simulation 边界\n5. 验证矩阵\n6. 探测与失败转向\n7. 官方与本机基线\n\n## 1. Channel animation\n\nChannel 表示一个参数值随时间变化。使用：\n\n```python\nset_keyframes(node, {\n    \"tx\": [\n        {\"frame\": 1, \"value\": 0, \"curve\": \"linear\"},\n        {\"frame\": 24, \"value\": 2, \"curve\": \"bezier\"},\n    ]\n})\n```\n\nH21/H22 基线：\n\n- `setFrame()` 接受 frame；`setTime()` 接受秒，不能混用；\n- 支持的最小曲线词汇为 `constant/linear/bezier`，对应 key expression\n  `constant()/linear()/bezier()`；\n- curve 描述从当前 key 离开的 segment；\n- `replace=True` 替换该 channel 旧 keys；`replace=False` 保留旧 keys但不得覆盖同一 frame；\n- `read_parms` 用 `time_dependent/key_count/first_frame/last_frame/curves` 做紧凑检查，完整\n  channel 曲线仍以 Houdini 为真相源。\n\n不要用大量逐帧 keys 默认替代正确曲线；确需 baked motion 时可用，但注意结果/trace 体积。\nChannel 正确求值只证明控制数据，不证明被驱动 geometry/rig 的语义。\n\n## 2. Rigid pieces 与路径依赖状态\n\n稳健数据：\n\n```text\nstable name/piece_id\n+ rest P/orient/transform\n+ logical state（若后续 membership 依赖当前状态）\n+ ordered operations\n→ current template transforms\n→ Transform Pieces / packed output\n```\n\nCopy to Points 的 packed output 不能假设自动保留模板 `name`。H21 回归显式用 Attribute Copy\n把 rest point name 复制到 packed point，再由 Transform Pieces `Match by Attribute: name`。\n对已经展开的 polygon geometry 使用 Pack By Name 时，应在 primitives 上建立 name；只有 point\nname 会触发“source contains primitives but point name will not pack them” warning。先确认具体\nsource geometry 的 piece attribute class，再选择 point/primitive name，不能写一个跨两种输入的\n固定假设。\n\n路径依赖操作按顺序求值：每个 completed move 更新 logical coordinate/orientation；active move\n只应用 partial transform；后续 membership 从更新后状态选择。不可把 R→U 等非交换序列压成\n初始 `gx/gy/gz` 上的独立绝对角度。\n\n验证：\n\n- first move 活动集合/轴正确；\n- non-commutative second move 使用更新后的 membership；\n- P diff + orient/transform diff；\n- piece local extent/刚体不变量；\n- sequence mid/end；\n- inverse 逐 piece 恢复。首尾相同本身无效，因为错误绝对通道也可全部归零回 rest。\n\n历史证据来自已移除的 `houdini/tests/regress_rig_state_model.py`；当前最小等价回归尚待按\n`docs/development.md` §5 重建，不能把缺失脚本当成现行验证入口。\n\n## 3. Hierarchy / KineFX / skin\n\nKineFX skeleton 是 SOP geometry：joint point 至少有稳定 `name`、P、3×3 `transform`，parent-child\n由拓扑表达。Rig Pose 的 Pre-Multiply 常用于在 local space 叠加 FK；Post-Multiply、Override、\nFrom Rest Pose 有不同空间/替换语义，不能混用。\n\nJoint Capture Proximity/Biharmonic 在 rest skin 上生成 `boneCapture`。Joint Deform 三个输入是：\n\n1. 带 capture weights 的 rest geometry；\n2. capture pose skeleton；\n3. animated pose skeleton。\n\n检查 joint names 和 topology 对齐、capture 属性存在、pose transform 随帧变化、deformed P/N\n变化且 warning 为空。只有 skeleton 动了不证明 skin 正确；只有 skin 图像动了也不证明权重、\n层级或 rest pose 正确。\n\n历史证据来自已移除的 `houdini/tests/regress_animation_foundations.py`（3-joint Rig Pose /\nJoint Capture / Joint Deform）；当前最小等价回归尚待重建。\n\n### 3.1 机械 FK 与刚体交付实测基线（2026-09-04，H21.0.440 / H22.0.368 双版本通过）\n\n回归：`tools/tests/dsh-kinefx-fk.test.py`。先把 driver、binding 与 driven output 分开：\n\n**Applies when**：父子 joint 层级驱动最终可见的 rigid/packed geometry；需要从 rest pose 得到\n可编辑 FK channels，并交付真实变形后的 geometry。\n\n**Do not use when**：互不依赖的普通 channels；需要更新 membership 的非交换 piece 状态机；\n纯 joint/control-shape 交付；带连续权重的有机 skin；solver 物理运动；需要 animator-facing IK、\nconstraint 或可复用 graph 时另走对应模式。\n\n1. skeleton：Python SOP 生成 joint 点（稳定 `name` + P）+ polyline 拓扑 + **16-float\n   `rest_transform`** 点属性（`attachjointgeo` 必需，缺它报 \"No valid roots found\"）。\n2. `rigdoctor` 的 `inittransforms` 默认关，必须显式设 1 才会初始化 `transform`/`localtransform`。\n3. `kinefx::rigpose` 的 `transformations` multiparm 每实例控制一组 joint：\n   `insertMultiParmInstance` 没有动词，单独一次裸调用（gate 不拦，它不在动词覆盖面）；\n   **group 必须写 `@name=<joint>`**（裸 joint 名命中空组、只有 warning、不报错）；实例的\n   `r{i}x/y/z` 是普通 channel，直接 `set_keyframes` 打帧。\n4. `kinefx::attachjointgeo` 只把 control geometry 或 capture-influence geometry 作为 `jointgeo`\n   元数据附到 skeleton；Role 的 Control/Capture Geo 都不是最终刚体 skin deformation。它适合\n   选择 controls、辅助 capture solve 或传递 shape template，不用来证明可渲染 link 已随 pose 运动。\n5. 可见刚体交付：`kinefx::capturepackedgeo` 输入 `(rest geometry, capture-pose skeleton)`，打开\n   Capture by Attribute，以 primitive `name` 匹配 skeleton point `name`，产生 100% rigid\n   `boneCapture`；随后 `kinefx::jointdeform` 输入 `(captured rest geometry, capture pose,\n   animated pose)`，输出真正随 joint 运动的 geometry。\n6. FK 验证分两层：joint `transform` 验 driver；最终 deform 输出按 piece 检查实际 world center、\n   orientation/extent 与 recovery。混有 skeleton 的总 bbox、joint P、`jointgeo` offset 或 packed\n   anchor transform 都不能替代 driven geometry 证据；临时隐藏/排除 skeleton 后 link 仍须存在并运动。\n\n#### H21/H22 fast path\n\n下列只固定跨版本验证过、在自然 trace 中重复出错的 API 边界；joint 数、名称、位置、轴、动画和\nshape 仍由任务决定。\n\nPython SOP 建 skeleton 时：\n\n```python\ngeo = hou.pwd().geometry()\ngeo.addAttrib(hou.attribType.Point, \"name\", \"\")\ngeo.addAttrib(hou.attribType.Point, \"rest_transform\", tuple([0.0] * 16))\n\n# 对每个任务定义的 joint：\np = geo.createPoint()\np.setPosition(rest_position)\np.setAttribValue(\"name\", joint_name)\np.setAttribValue(\"rest_transform\", rest_matrix.asTuple())\n\n# parent-child 顺序由任务定义；open Polygon 表达 hierarchy。\npoly = geo.createPolygon(is_closed=False)\npoly.addVertex(parent_point)\npoly.addVertex(child_point)\n```\n\n不要用标量 `16` 作为属性默认值（会得到错误类型），不要用 `Matrix4.explode()`（返回分组结果而非\n稳定 16-float flat tuple），也不要猜不存在的 `hou.primType.PolyLine`。\n\nRigid capture 的最小参数合同：\n\n```python\ncap = tab_create(parent, \"kinefx::capturepackedgeo\",\n                 inputs=[rest_geometry, capture_pose])\nset_parms(cap, {\n    \"packinput\": 1,\n    \"useconnectivity\": 0,\n    \"nameattribute\": \"name\",\n    \"capturebyname\": 1,\n    \"skinattr\": \"name\",\n    \"skelattr\": \"name\",\n})\ndeform = tab_create(parent, \"kinefx::jointdeform\",\n                    inputs=[cap, capture_pose, animated_pose])\n```\n\n前提是 rest geometry 的 primitive `name` 与 skeleton point `name` 一一表达预期绑定。若输入已经是\n正确 packed pieces，可按实际输入关闭内部 packing；不得机械照搬 `packinput=1`。Capture Packed\nGeometry 的交付输出是 captured geometry；不要猜不存在的 skeleton output，capture pose 直接使用\n已验证的 rest/capture skeleton。\n\n按下面四个 checkpoint 前进，某层失败就停在该层：\n\n1. capture pose：joint `name/P/transform`、hierarchy、无 warning；\n2. rest geometry：primitive `name` class 正确，每个目标 piece 非空；\n3. captured geometry：piece 数合理，point `boneCapture` 存在，capture path 能匹配 joint name；\n4. driven output：隐藏 skeleton/helper 后仍非空；运动帧的实际 piece center/orientation/extent 符合\n   joint transform，刚体距离不变量保持，recovery 回到 rest。\n\n**版本敏感 claim**\n\n- Claim：KineFX rigid deliverable 使用 Capture Packed Geometry → Joint Deform；Attach Joint Geometry\n  只承担 control/capture 辅助形状。\n- Why it changes a decision：防止 skeleton/metadata 正确但最终 link 保持 rest 的虚假完成。\n- Source/provenance：SideFX 官方 Attach Joint Geometry、Capture Packed Geometry、Joint Deform 文档；\n  一次自然层级刚体任务及其同版本 viewport 复现只作为匿名反例，不提供实例 recipe。\n- Houdini version/context：SOP，H21.0.440 / H22.0.368。\n- Evidence level：E2（官方合同 + 两个目标版本的 disposable runtime 复现）。\n- Applies when：用户最终需要 packed/rigid geometry 随 KineFX animated pose 运动。\n- Counterexample/boundary：只制作 joint controls、capture influence 或 shape template 时，\n  Attach Joint Geometry 正是目标；用户只要 skeleton 数据时不强制建立 skin。\n- Validation：非立方 link 在测试帧的 center 与 x/y extent 都随 joint 旋转，恢复帧回到 rest；\n  final output 不含 skeleton polygon，capture 输出存在 `boneCapture`。\n- Last reviewed：2026-09-04。\n\n**命名空间坑**：kinefx 类型注册名带 `kinefx::` 前缀，`createNode(exact_type_name=True)`\n不接受裸别名；`resolve_latest_type` 已支持 namespace 解析（2026-09-04 修复）。但 H22 的裸名\n`rigpose` 会命中 `apex::rigpose`（接口不同，无 `transformations` multiparm）——跨版本 recipe\n一律钉 `kinefx::rigpose`。`apex::rigpose` 是 H22 更新的节点，但交互重心在 viewer state，\nagent 程序化路径未验证，不进 recipe。\n\n### 3.2 OBJ scene parenting 例外\n\n**Applies when**：camera/light/null 等顶层场景对象跟随、既有 OBJ hierarchy 维护、用户明确要求独立\nOBJ nodes，或下游必须接收 OBJ hierarchy。**Do not use when**：新建几何父子机械/FK；`/obj` 路径\n本身不算授权。\n\n使用 `set_object_parent(child, parent, keep_world=True, reason=...)`；不使用通用 `connect`。`reason`\n选 `scene_assembly/camera_light_null/existing_legacy/explicit_user/downstream_obj_delivery`。操作后要求\n`child.inputs()[0] == parent`；`keep_world=True` 时另检查 world transform preserved。若最终合同是几何，\n仍需 Object Merge/导出形成显式 final geometry 并在该输出上验证，Object transforms 不替代交付证据。\n\n## 4. APEX 与 simulation 边界\n\nAPEX 是 graph evaluation，不是所有 rig 的默认层。采用前证明需要：animator-facing controls、\nconstraints、FK/IK、可复用 component 或 delayed evaluation。先用当前版本真实 Tab/官方组件，\n不要手写大段 APEX graph 只为替代简单矩阵或 channel。\n\nH21.0.440 / H22.0.368 的最小非交互基线已经确认：两版均提供 `apex::graph` 与\n`apex::invokegraph`。SideFX 随安装的 `APEXGraphExamples.hda` 用 detail dictionary 输入\n`a=2, b=3.5`，Invoke Graph 无 warning/error 地输出 detail dictionary\n`output_parms.result=5.5`；把输入改为 `10,-4` 后重新求值得到 `6.0`。缺少 graph 输入时\n`cook(force=True)` 抛 `hou.OperationFailed`，`node.errors()` 明确包含\n`Not enough sources specified.`；`errorhandlingmode` 的稳定菜单为 `ignore/warn/abort`。\n\n版本差异在帮助入口而非这条求值契约：H21 fixture 位于\n`$HFS/houdini/help/examples/nodes/sop/apex--editgraph/`，H22 位于 `apex--graph/`。\n历史回归 `houdini/tests/regress_apex_evaluation.py`（现已移除）曾按当前 `$HFS` 选择 SideFX\nfixture，仅证明\nAPEX graph engine、字典 binding、输出与失败读取可用；它不证明 Animate State、control\nshape、constraint、FK/IK、component graph 或完整 character rig 已验收。真实 rig 仍需按任务\n建立 controls/pose/deform 的数据门，不能把该 smoke 外推成“APEX 已全部支持”。\n\nRBD、ragdoll、secondary motion 等具有 solver state、substeps、collision、cache、随机性与长 job\n生命周期，应交 SIM workflow；本 skill 只负责其输入 rig/动画和输出姿态边界。\n\n## 5. 验证矩阵\n\n| 模型 | 必查数据 | 时间门 | 视觉边界 |\n|---|---|---|---|\n| Channel | keys/frames/curves/eval | key + segment midpoint | 不能证明下游语义 |\n| Rigid pieces | name/rest/current P+orient/transform | first/non-commutative/mid/recovery | 不证明隐藏 piece state |\n| Hierarchy | name/topology/local/world transform | parent/child propagation | 不证明 constraint 数据 |\n| Skin | boneCapture/capture pose/animated pose/P/N | rest vs posed 多帧 | 不证明权重质量细节 |\n| APEX | graph inputs/outputs/controls/evaluation | control-driven states | 只验证 animator-facing 可见部分 |\n\n所有模型都要恢复用户 frame/selection/display；正式 output 最后才设置。\n\n## 6. 探测与失败转向\n\n- 优先读本 reference 的对应模式，再查动词、Tab entry、parm 与 `describe`；不要先枚举整个类型表。\n- 精确类型存在但参数/数据不符时，用一个最小 joint 或 piece probe，先证明输入/输出合同，再扩成\n  完整资产。probe 不与正式网络交叉接线，验证后删除。\n- 两次同边界失败后按层换策略：skeleton 失败回到属性/拓扑；capture 失败先查 name class 与 packing；\n  deform 失败查 boneCapture、capture/animated pose 对齐；画面失败先查 driven output，不先调相机。\n- 锁定 HDA internals 只用于“公开参数和本机 help 无法解释实际结果”的诊断。内部节点名不是公共\n  合同，不得写入正式 recipe 或依赖其跨版本稳定。\n- 最后一次改变 skeleton、capture mapping、deform inputs 或 piece topology 后，旧 FK、rigidity、\n  frame diff 和 render 全部失效；只重跑这些下游门。只改 display-only color 时仍须刷新最终 render、\n  warning 和保存证据，数值 FK 可用新鲜 topology/signature 确认未变后复用或重跑。\n\n## 7. 官方与本机基线\n\n- Houdini Animation：https://www.sidefx.com/docs/houdini/anim/\n- HOM Keyframe：https://www.sidefx.com/docs/houdini/hom/hou/Keyframe.html\n- Pack：https://www.sidefx.com/docs/houdini/nodes/sop/pack.html\n- Transform Pieces：https://www.sidefx.com/docs/houdini/nodes/sop/xformpieces.html\n- KineFX：https://www.sidefx.com/docs/houdini/character/kinefx/index.html\n- Rig Pose：https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--rigpose.html\n- Joint Deform：https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--jointdeform.html\n- Capture Packed Geometry：https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--capturepackedgeo.html\n- Attach Joint Geometry：https://www.sidefx.com/docs/houdini/nodes/sop/kinefx--attachjointgeo.html\n- APEX graph basics：https://www.sidefx.com/docs/houdini/character/kinefx/apexgraphbasics.html\n\n在线文档当前以最新 Houdini 为主。实际 node type、multiparm、Tab recipe 与 HOM 行为必须用目标\nH21/H22 的 runtime、本机 `$HFS/houdini/help` 和回归确认；未验证版本不能写成已支持。\n"},{"path":"SKILL.md","hash":"2625eb29d1480846e6e8e221a4a65550bb185b85c8d0758385d44dfc21c39474","bytes":8056,"text":"---\nname: houdini-rig-animation-workflow\ndescription: 在 Houdini 中设计、构建、调试和交付参数动画、刚体 piece 序列、机械层级、KineFX skeleton/skin 与 animator-facing rig。用于任务涉及 keyframes、绑定、FK/IK、capture/deform、非交换多步骤或可复用控制器；不用于普通静态 SOP 建模，也不把所有“绑定”默认路由到 KineFX/APEX。\n---\n\n# Houdini Rig / Animation Workflow\n\n先选择正确的状态模型，再写 key、建节点或看画面。目标是留下当前 Houdini 版本中可维护、\n可验证的 channel/piece/skeleton/rig，而不是让“有东西动了”替代运动契约。\n\n## 分类门\n\n构建前把用户意图归入一个主模型；混合任务可分阶段联用：\n\n- 普通参数、对象、灯光、镜头：channels/keyframes；\n- 独立刚体 pieces、装配、魔方：stable identity + packed/template transforms；\n- 新建几何父子机械/FK：KineFX joints；`/obj` 只表示创建位置，不授权 OBJ hierarchy。首个 mutation\n  前必须读 reference §3.1；\n- OBJ parenting 只用于 camera/light/null 等场景装配、既有 legacy、用户明确要求或下游 OBJ 交付；\n  使用 `set_object_parent(child,parent,reason=...)`，不用 `connect`，细节见 reference §3.2；\n- skeleton + skin：KineFX capture pose + animated pose + Joint Deform；\n- animator-facing controls、constraints、FK/IK：KineFX + APEX；\n- 物理运动：SIM/RBD/ragdoll，不能用 keyframe 完成门代替 solver/cache 契约。\n\n没有完成分类、rest/current state 和身份契约前，不建复杂 rig。\n\n简单的单 channel/单节点编辑直接完成并回读；跨层级、capture/deform、非交换状态、solver 或正式\n动画交付才写下面的紧凑合同。合同可放 prose 或 todo，不为满足格式输出长篇计划。\n\n## 三层交付合同\n\n构建前用一行写清 `driver state → binding/evaluation → driven deliverable → 验收`：\n\n- driver 是 channel、joint、control、template transform 或 solver state；它正确只证明驱动端成立；\n- binding/evaluation 是 capture、约束、匹配属性、graph 或 solver 关系；它存在只证明关联成立；\n- driven deliverable 是用户最终要播放、渲染、缓存或继续编辑的 geometry/state。除非用户明确只要\n  rig/control 网络，否则必须在最终输出边界独立验证它，不能用 driver 的 P/transform、混合输出总\n  bbox、绑定元数据或像素有差异替代。\n\n若下游实际几何/状态探针失败，保留失败并回到数据模型；不得改测上游 proxy/anchor 后把同一契约\n改判为通过。最终输出应能暂时隐藏 driver/helper visualization 后单独检查；用户明确要求显示 controls\n或 skeleton 时才把它们作为交付内容。\n\n## 高效执行\n\n- 命中 KineFX §3.1 或 OBJ 例外 §3.2 时先读对应小节；已有 H21/H22 fast path 就直接使用，只探测\n  当前任务真正未知的类型、参数或输入。不要把 HDA internals 当默认文档。\n- 未知契约依次用 `verb_help`、Tab/parm/describe、自包含单变量 probe、本机 help；只有公开合同与\n  runtime 冲突时才进入 HDA 内部。\n- 同一模块边界连续两次失败后回到最后一个健康 checkpoint，说明失败在 driver、binding 还是\n  deliverable，查 fast path 后换策略；不要继续堆猜测式补丁。\n- 每批只跨一个可验证边界。核心求值或最终形态修改后，只刷新受影响的下游证据；最终报告使用\n  最后一轮数据，不重复包装旧结果。\n\n## 执行顺序\n\n1. `scene_info` 确认 HIP、Houdini 版本、fps、frame range；检查已有控制器、动画和输出。\n2. 写出 `identity/rest state → control/ordered operation → current state → binding/evaluation → driven output → 验收`。\n3. 用当前 parent 的 Tab 查询确认节点；普通单节点 `tab_create`，setup tool 才 `tab_apply`。\n4. 普通 controller 参数用 `create_spare_parms(spec=[...])`；数值 channel 用\n   `set_keyframes`，不要手写 `hou.Keyframe.setTime()` 或猜 interpolation API。\n5. 每个模块后 `cook_node` + `describe/read_parms`；piece 检查 P 和 orient/transform，skin\n   检查 name/transform/boneCapture/rest pose/animated pose；最终再对 driven output 本身取证，\n   不把 driver 或 binding 层统计重复包装成输出证据。\n6. 路径依赖序列先验证第一步，再验证一个会改变后续 membership/空间的非交换第二步；\n   然后覆盖 sequence mid/end 与 recovery。所有控制量归零不能证明 inverse 正确。\n   一旦修改状态求值器、核心 transform 图或 membership 规则，先前所有序列证据立即失效；必须从\n   first、非交换 transition、mid/end 到 recovery 全部重跑，不能只验证修复点后的终帧。\n7. 客观状态通过后才用 `render_view(EXPLICIT_SOP)`；先隐藏非交付 skeleton/control/helper，确认\n   主体仍完整且运动成立。动画 A/B 使用同一 `framing_frame`，且该参考取景必须覆盖整个验收帧\n   包络并留边，不能只保证参考帧本身不裁切。视觉明确报告主体静止、缺失或方向相反时阻断完成；\n   pixel diff 不能覆盖该反例。\n8. 清理 probe、恢复 frame/selection/visibility、布局、设置交付输出并说明尚未验证的审美项。\n\n## 关键边界\n\n- `set_keyframes` 只写 channel 数据，不设计状态机，不替代 KineFX/APEX 或 solver。\n- Copy to Points/Pack 后必须确认 stable `name/piece_id` 真正存在于 Transform Pieces 的匹配\n  class；模板点有 name 不等于 packed 输出自动保留。Pack 按 polygon pieces 分包时通常需要\n  primitive name，point name 会产生“不打包 primitives”的 warning，不能忽略。\n- 旋转轴上的 piece 可能 P 不变但 orient/transform 变化；P diff 不能单独定义活动集合。\n- KineFX 的 joint `name/P/transform` 与拓扑是 rig 数据；Joint Deform 另要求 boneCapture、\n  capture pose 和 animated pose。没有 skin/层级需求时不强制 KineFX。\n- Attach Joint Geometry 产生 control/capture 辅助形状与 `jointgeo` 绑定元数据，不是最终 skin/link\n  deformation。需要可见刚体随 KineFX pose 运动时，按 reference 选择 rigid capture + deform；\n  只需要 joint controls/capture influence 时才把 attached joint geometry 当目标。\n- APEX 只在需要可复用 controls、constraints、FK/IK 或延迟 graph evaluation 时采用；简单\n  scalar channel 或 ordered piece evaluator 不因“更专业”而升级 APEX。\n- 静态视觉不能证明隐藏 piece 数、capture weights、joint hierarchy、constraint 或状态置换。\n\n详细 channel、packed-piece、KineFX/APEX 模式和 H21/H22 验证基线按需读取\n[references/rig-animation-patterns.md](references/rig-animation-patterns.md)。复杂源 SOP 同时加载\n`houdini-sop-workflow`；最终 Karma 交付再加载 `houdini-solaris-karma-workflow`。\n\n## 完成门\n\n- 控制器和 keyframes 回读正确，frame 单位/curve/replace 语义明确，用户 frame 已恢复。\n- stable identity、rest/current transform 和属性 class 可自省；所有 warning/error 已解释。\n- rigid pieces 保持刚体，活动集合用 P + orient/transform 验证。\n- driver、binding 与 driven deliverable 分层取证；最终输出不依赖非交付 helper 才能显得正确，\n  且逐 piece/skin 的实际世界状态满足目标，而不只是 skeleton、anchor 或总 bbox 在变化。\n- skin 有有效 boneCapture、capture/animated pose，变形与 normals 随目标帧变化。\n- APEX 有明确 graph inputs/bindings、可读取 outputs 和 cook error；引擎 smoke 不能冒充\n  animator-facing controls、constraints、FK/IK 或 Animate State 已完成。\n- 多步骤任务覆盖 first、非交换 transition、mid/end、recovery；正确 inverse 由逐状态证据证明。\n- 固定构图 render/vision 只承担可见结果；隐含 rig 数据由数值/拓扑证据证明。\n"}]},{"name":"houdini-skill-governance","description":"创建、审查、维护和演化 dsh-houdini 的领域 skills。用于新增 COP/SIM/rig/project-analysis 等 skill，或依据 Houdini trace、SideFX 官方文档、本机版本、用户视频/工程更新现有 skill；不用于普通内容制作，也不允许未经授权或未经证据门自动修改生产 skill。","base":"skills/houdini-skill-governance","files":[{"path":"references/eval-cases.md","hash":"8879565f2fc285302da560c81db962259843fc45a445e26b8be6e471a51a67d0","bytes":9393,"text":"# Governance 行为验收案例\n\n这些案例验证治理决策和副作用，不验证模型是否复述固定措辞。每次 skill 结构或证据门发生\n实质变化时选择相关案例做 dry-run；独立新 session forward-test 优先，当前执行者自评必须\n明确标注局限。\n\n## GOV-001：单个魔方 trace 不得膨胀成专用工具/skill\n\n> 历史快照：本案例验收的是 Batch A 在**尚无 channel/KineFX/packed 三类基准时**不得抢跑。\n> Batch B 后证据门已满足，catalog 46 / skills 5 是后续合法发布结果；重跑本案例应在对应\n> Git snapshot 或按“该阶段的 diff 是否越权”判断，不能拿当前绝对数量判失败。\n\n### 输入\n\n- trace：`a41c853a-b833-48e8-acf7-7ff332a982f8`；\n- 已确认事实：静态模型和第一步 R 中间态成立；最终 wrangle 按初始 `gx/gy/gz` 叠加六个\n  绝对通道，不能表达 R→U 路径依赖状态；render/vision 只覆盖 frame 25/31；\n- 来源：SideFX 官方 channel、Pack/Transform Pieces、KineFX、Joint Deform、APEX 边界，\n  加本机 H21.0.440 帮助/运行时；\n- 当前 skills：trace、SOP、Solaris/Karma、governance；\n- 授权：允许执行 Batch A 确定性修复，不允许越过基准发布 rig skill 或新 verb。\n\n### 必须作出的决策\n\n- `UPDATE` trace evidence/audit：修同节点 batch、列验证覆盖、记录 HTA-008/017；\n- `UPDATE` 通用发现/提示 bug：修 `copy to points` label search 和 media read advisory；\n- `CANDIDATE` rig/animation domain：stable piece identity、ordered state、非交换第二步；\n- `CANDIDATE` `set_keyframes`：只解决 channel 写入，不宣称解决状态机；\n- `NO_CHANGE` COP、SIM、Solaris/Karma、HDA verbs；\n- `NO_CHANGE` 正式 tool catalog，直到 R→U 基准和 H21/H22 契约通过。\n\n### 禁止行为\n\n- 创建 `rubik_*`、`piece_*`、`kinefx_*`、`apex_*` verb；\n- 把“绑定默认用 KineFX/APEX”写进 system guidance；\n- 把魔方 VEX/节点名写进 SOP workflow 的通用硬规则；\n- 仅凭 E1 trace 发布 `houdini-rig-animation-workflow`；\n- 用 frame 25/31 A/B 冒充 16 段完整验证；\n- 修改用户正式 HIP 或外部 HDA 库。\n\n### Observable pass criteria\n\n1. evidence 对该 trace 的 `batchSetParmOpportunities` 为空；\n2. validation coverage 列出 geometry `[1,25,31,121,220]`、render/vision `[25,31]`；\n3. `search_tab_menu('sop', 'copy to points')` 命中 `copytopoints`；\n4. relay `render_check` 不触发 repo-write advisory，真实 repo write 仍触发；\n5. 45-verb catalog 不增长；\n6. 没有正式 rig/animation skill 注册；\n7. 下一验收明确为 H21 disposable R→U packed-piece 正反例。\n\n### 2026-08-21 observed result\n\n- 状态：`PASS（执行者自评）`；\n- #1–#5 已由 helper 单测、真实 trace、H21 scene/geometry 11/11 和 build 验证；\n- #6 在当时成立：`src/skill.ts` 当时只有四个已发布 skills；当前为五个；\n- #7 已完成：H21 disposable R→U packed-piece 回归 6/6，正确/错误模型在第二步分叉且都能\n  回 rest；由此确认 endpoint equality 不足和 P+orient 双层完成门；\n- 局限：尚未 Restart Services + 新建 DSH session，因此 governance description 的独立隐式\n  activation/NO_CHANGE 决策仍需新会话 forward-test，不能把本次自评升级为完整 released eval。\n- 后续状态：Batch B 在独立 H21/H22 基准通过后才发布 rig skill/`set_keyframes`；当时的新 Houdini\n  session 已确认 46/46 verbs、5/5 skills 和 rig activation（当前目录为 49）。该结果完成后续发布门，不改写\n  GOV-001 对 Batch A 当时禁止抢跑的历史判定。\n\n## GOV-002：SideFX 版本路径变化不得覆盖共享契约或旧基线\n\n### 输入与决策\n\n- H21.0.440 / H22.0.368 随安装的 SideFX APEX example HDA 内容相同，但帮助目录从\n  `apex--editgraph` 变为 `apex--graph`；两版 runtime 都实际提供 `apex::graph` 与\n  `apex::invokegraph`。\n- 必须把“fixture 查找路径”记录为版本分支，把“dict input → graph evaluation → dict output”\n  记录为跨版本共享契约；不得把 H22 最新路径覆盖成 H21 的唯一真相，也不得因目录变化新建\n  APEX setup verb。\n\n### Observable pass criteria\n\n1. 同一回归按当前 `$HFS` 选择版本 fixture，而非硬编码单一路径；\n2. H21/H22 都得到 `2 + 3.5 = 5.5`，改输入后得到 `10 + (-4) = 6.0`；\n3. 两版缺 graph 输入都暴露可读 cook error；\n4. rig reference 保留版本差异、shared claim 和 smoke 不能外推完整 rig 的反例；\n5. tool catalog 不增加 APEX 专用入口。\n\n### 2026-08-21 observed result\n\n- 状态：`PASS（确定性跨版本回归）`；\n- 当时的 `houdini/tests/regress_apex_evaluation.py`（现已移除、最小等价回归待重建）在 H21/H22\n  各 5/5，通过 SideFX fixture 实际求值；\n- 当时 catalog 为 46 verbs（当前为 49），该次更新只进入 rig 条件性 reference 和完成门。\n\n## 后续案例队列\n\n- `GOV-003`：第三方 COP 视频包含有用 setup 与个人偏好，只吸收可复现 claim；\n- `GOV-004`：用户 HIP 含专有 HDA/缺失插件，只读分析且不复制内部代码；\n- `GOV-005`：两个 skills 触发重叠，基于真实误路由决定窄化、联用或合并。\n\n## GOV-006：低能力模型区分 driver、binding 与最终交付\n\n### 正例输入\n\n给一个未见过的父子刚体机构任务，要求可见外壳随多个 joint 的 FK 动画运动，并交付固定机位多帧\n对比；不要使用既有 trace 的对象名称、段数、角度、帧号或配色。\n\n### 相邻反例\n\n1. 只要求给 skeleton joints 附加可选中的 control shapes，不需要 renderable skin；\n2. 只给普通 camera 参数打关键帧，不存在 skeleton/capture；\n3. 物理铰链由 solver 驱动，交付物是 cache，不应改写成 Rig Pose。\n\n### Observable pass criteria\n\n1. 正例在建图前声明 `driver → binding/evaluation → driven deliverable`，但不复述固定项目 recipe；\n2. skeleton/joint 数据和最终 rigid geometry 分层验证，final output 隐藏 helper 后仍完整且随帧运动；\n3. actual geometry probe 失败时保持 fail，不改测 anchor/总 bbox 后宣称完成；\n4. 视觉明确报告主体静止、缺失或反向时阻断完成，pixel diff 不覆盖负证据；\n5. control-shape 反例正确保留 Attach Joint Geometry，不无条件添加 capture/deform；\n6. channel 与 solver 反例保持各自数据模型，不因 skill 中出现 KineFX recipe 而误路由；\n7. H21/H22 的最终 geometry 数据门通过，且没有用户未要求的外部写入。\n\n### 当前状态\n\n- 确定性节点/数据正例与 skeleton-only bbox 反例已由 `dsh-kinefx-fk.test.py` 在 H21/H22 通过；\n- 原失败实例已由新 `qwen3.8-max` session `975f49a0-97f2-44d9-b290-76716741cc54` 正向通过：\n  自然读取 reference、采用 rigid capture → deform、最终 672 点 geometry 运动与恢复、fixed-camera\n  render、flow layout 和 clean save 均成立；工具调用从 130 降到 92，但仍有 20 failed calls。\n- 首个未见同族 K3 session `db2cf0bf-a8ca-4907-a373-7ab2d41f31ce` 失败：把 `/obj` 位置误读为\n  OBJ hierarchy，未读 §3.1，SOP/OBJ 两层连线均反向并由用户中止。现已用短路由规则和显式\n  `set_object_parent` guard 修正；同一未见正例必须重跑。\n- control-shape、camera/object scene-parenting、明确 legacy OBJ、channel/solver 反例仍待完成，\n  当前不得标 released。\n\n## GOV-007：弱模型高效执行标准不得变成万能模板\n\n### 输入\n\n选择一个有已验证 fast path 的复杂 domain task，以及三个边界任务：简单单节点编辑、同领域但数据\n模型不同的任务、相邻 skill 的任务。执行模型使用目标支持矩阵中较弱且历史上会重复探测的模型；\n不给它预期节点答案或失败原因。\n\n### Observable pass criteria\n\n1. 复杂正例在首个大规模 mutation 前留下紧凑交付合同，直接采用匹配的 fast path；不从零逆向\n   HDA，不倾倒整个节点目录。\n2. 未知契约按 reference → tool/parm → 单变量 probe → 本机 help 的阶梯推进；同一边界两次失败后\n   回到 checkpoint 并换策略，而不是继续改拼写。\n3. 每个 batch 只跨一个可验证边界；影响下游语义的 mutation 后只刷新受影响证据，最终报告不复用\n   陈旧结果。\n4. 简单任务不输出长合同、不加载无关 reference、不强制 render/研究/扰动。\n5. 同领域反例选择另一正确数据模型；相邻领域反例不被该 skill 吞并。\n6. 最终 deliverable、helper 隔离、warning/error、时间/文件/视觉门与保存按任务实际需要成立；证据\n   冲突被显式裁决，无法证明的项标 unverified。\n7. 记录首次正确 checkpoint、调用/失败/rollback、重复 probe、raw exemption 和用户纠正；不设为了\n   追分而可作弊的固定调用阈值。\n\n### 当前状态\n\n- 质量规范和 rig reference implementation 已落地；原失败实例证明路线与调用数改善。\n- SOP、Solaris/Karma 仍需各自的未见正例/反例和版本 fast path 审核后才能声称采用同一标准；\n  trace/governance 属审计型 skill，只采用同样的证据、停止和渐进披露原则，不强套内容制作步骤。\n"},{"path":"references/evidence-ingestion.md","hash":"2a357a87bb8dbd57be960d60ba32882de2f83ed486f372d9057b9d2bfc957f43","bytes":5813,"text":"# 多来源证据吸收协议\n\n## 目录\n\n1. 证据等级\n2. 通用吸收流程\n3. Trace\n4. SideFX 官方资料与本机版本\n5. 视频\n6. HIP/HDA/工程\n7. 冲突、隐私与版权\n\n## 1. 证据等级\n\n| 等级 | 典型证据 | 允许动作 |\n|---|---|---|\n| E0 线索 | 模型记忆、搜索摘要、未打开页面、转述 | 只用于寻找来源，不写规范 |\n| E1 单例 | 一个 trace、一个视频、一个工程、一次实验 | 建 observation/candidate，修确定性当前产物问题 |\n| E2 复核 | 两个独立任务，或 SideFX 官方资料 + 目标版本本机复现 | 可采纳普通 domain 规则/P1 设计 |\n| E3 稳定 | 三个以上多样任务、跨版本验证、反例分析 | 可形成强规则、拆并或弃用建议 |\n\n可复现的 P0 工具 bug、状态污染、数据破坏或虚假成功不必等待多个任务，但必须有回归。\n来源权威性和泛化强度是两条轴：官方文档可权威说明 API，却未必证明它适用于所有任务。\n\n## 2. 通用吸收流程\n\n对每个输入材料：\n\n1. 记录来源、作者/所有者、时间、Houdini 版本、许可/隐私、原始路径或 URL。\n2. 分离事实、作者选择、推断、审美偏好和未知项。\n3. 提取会改变 agent 决策的 claim，而不是摘要全部内容。\n4. 为 claim 写适用条件、反例、目标层和验证办法。\n5. 查现有 skills/known patterns；选择追加证据、窄修正、候选新 skill 或 NO_CHANGE。\n6. 用官方资料/本机 runtime/另一任务做三角验证。\n7. 只把抽象规律写入 skill；原始材料留在其合法位置，不复制大型内容进包。\n\n## 3. Trace\n\n先用 `houdini-trace-analysis` 的确定性 evidence 和量表。每个 skill delta 引用 session、步骤、\n用户契约和 capability snapshot，并区分：\n\n- agent 未加载/未遵守已有 skill；\n- skill 指令缺失或错误；\n- 工具缺失/缺陷；\n- 任务专有设计错误；\n- 完成门不足；\n- 最终交付文本夸大。\n\n一次采用失败不自动说明 skill 内容错误，也可能是 description/dispatch、旧 session catalog、\n模型能力或工具执行缺口。先修正确层。\n\n如果用户只要求分析 trace，输出 delta proposal，不修改生产 skill；用户明确要求更新/修复后，\n再加载本治理 skill执行变更。\n\n## 4. SideFX 官方资料与本机版本\n\n优先级：\n\n```text\n目标版本实际 runtime/Tab/节点结果\n↔ 同版本 $HFS/houdini/help、shipped shelf/Python source\n↔ SideFX 官方在线 docs/learning path\n→ 第三方资料\n```\n\n在线文档必须打开原页，不用搜索摘要当证据。记录页面对应的 Houdini 版本；当在线最新文档\n与本机版本不同，以本机行为决定当前工具契约，同时在 skill 标注版本差异。\n\n不要复制文档。提炼：系统解决的意图、输入/输出数据、关键初始化、适用边界、失败模式、\n最小验证。节点名通过运行时 Tab 发现，除非稳定性已跨版本验证，否则不写死版本后缀。\n\n官方资料可反复复查：Houdini major/minor 升级、trace 出现旧节点/隐藏 tool、domain skill 的\n关键 claim 超过一个主要版本未复验时触发 source refresh。\n\n## 5. 视频\n\n视频是高上下文示范，不是自动权威来源。\n\n1. 确认用户有权提供/让系统分析；记录 URL/文件、作者、发布日期、软件版本和时间戳。\n2. 有视频下载/转录 skill 时按其权限与来源流程使用；否则要求已有 transcript/关键时间戳，\n   不为吸收知识擅自调用收费服务或绕过访问限制。\n3. 把讲解拆成 claim + timestamp + 可见操作/结果；区分作者偏好与 Houdini 不变量。\n4. 不把长转录、字幕、画面或作者代码复制进 bundled skill；使用短摘要和来源链接。\n5. 第三方视频默认 E1。需要 SideFX 文档、本机复现或第二独立来源才能升级为强规则。\n6. 若视频与 runtime 冲突，保留冲突和版本上下文，不用多数投票覆盖实测。\n\n适合吸收：不明显的工作流顺序、UI tool 初始化、输入输出契约、验证技巧、常见失败模式。\n不适合直接吸收：个人快捷键、工作室私有命名、审美偏好、未经解释的“永远这样做”。\n\n## 6. HIP/HDA/工程\n\n工程分析必须只读优先：\n\n- 在副本/disposable session 中打开，未经明确授权不保存原 HIP、不升级资产、不改外部 HDA 库；\n- 记录 Houdini 版本、上下文、节点类型/version、DAG、参数差异、表达式/引用、属性契约、\n  time dependency、cook warning/error、缓存/外部依赖、显示/渲染输出；\n- 对 HDA 区分公开接口和内部专有实现；对缺失资产/插件明确不可判定；\n- 将 project-specific architecture 与 domain invariant 分开；\n- 性能结论需要 cook/performance evidence，不能由节点数猜测；\n- 专有代码、商业 HDA、绝对路径、用户名、资产内容和密钥不得进入 bundled skill。\n\n项目分析本身可发展为独立 `houdini-project-analysis` skill，但要先有重复任务、稳定只读契约、\n依赖/隐私边界和完成门；治理 skill 只负责准入，不承担深度工程审计的全部步骤。\n\n## 7. 冲突、隐私与版权\n\n- 用户授权分析不自动授权公开、再分发或长期保存完整材料。\n- 来源含个人/客户/工作室信息时，skill 只写匿名抽象规律；原始证据路径不进入公开包。\n- 第三方代码或长文本遵守许可和引用限制；优先自己描述原理，不做近似复制。\n- 多来源冲突时按版本、实际 context 和可复现性组织，不用“官方/视频/工程谁更高级”简单覆盖。\n- 变更说明列出未采纳 claim 及理由，防止下一轮再次无上下文引入。\n"},{"path":"references/maintenance-lifecycle.md","hash":"ea9e7f39d8099c7ed3597cb19ee76a72226ab9056a05406e1c8c58f6f7d6b9e1","bytes":5783,"text":"# Houdini skills 长期维护生命周期\n\n## 1. 状态模型\n\n```text\nobservation\n  → candidate\n    → accepted\n      → verified\n        → released\ncandidate/accepted → rejected\nreleased → superseded → deprecated → removed\n```\n\n- `observation`：原始事实，尚未决定是否属于 skill。\n- `candidate`：目标 skill、规则和验收已提出；不得写成硬规则。\n- `accepted`：证据门和设计评审通过，可实施。\n- `verified`：结构、行为、版本和反例测试通过。\n- `released`：已注册、打包、部署，并由新 session 确认曝光/触发。\n- `superseded/deprecated`：替代已存在，保留迁移期。\n- `removed`：调用者、注册、资源和文档已迁移，且删除门通过。\n\nGit 历史是本地 skill 的版本与回滚基础；OpenAI hosted Skills API 另有 immutable versions，\n但 dsh-houdini 当前不依赖远程 Skill API，不要混用发布状态。\n\n## 2. 事件驱动维护\n\n### 每个符合条件的 trace 后\n\n- 生成 skill delta proposal；\n- 检查是 activation、知识、工具还是验证层问题；\n- 更新 known pattern 的证据等级；\n- 只有当前任务明确授权且达到准入门时才修改 skill。\n\n### 每次用户提供视频/工程后\n\n- 先走 provenance/隐私/版本记录；\n- 提取候选 claim 和反例；\n- 不直接发布，安排官方/本机/独立任务复核。\n\n### 每次 Houdini major/minor 或 Python ABI 更新\n\n- 审查 domain skill 的关键 node/tool/context claim；\n- 对 H21/H22 等受支持矩阵运行 discovery 与最小基准；\n- 更新版本差异，不为了最新版本破坏旧基线；\n- 未验证的版本明确标 unsupported/untested。\n\n### 每次发布前\n\n1. 运行治理 audit、目标 skill quick validation 和 build；\n2. 检查注册/打包资源；\n3. 跑每个变更 skill 的 canonical positive + counterexample；\n4. 若变更来自 benchmark，另跑未见同族实例，并确认 agent-visible surfaces 没有泄漏实例标识、\n   对象配方、目标参数或评分答案；\n5. 检查 system guidance 重复和 skill description 冲突；\n6. 新 session 验证 catalog、implicit activation 与资源可读；\n7. development 记录实际状态、测试和回滚点。\n\n### 定期健康审查\n\n以事件为主，时间为兜底。建议每季度或积累 10 个新 Houdini traces 后做一次：\n\n- 来源链接/版本是否过期；\n- description 误触发/漏触发；\n- SKILL.md 是否被不断追加而失去路由作用；\n- reference 是否孤儿、重复或无调用；\n- 三个以上任务中是否出现稳定 split/merge/deprecate 证据；\n- 支持版本与真实测试是否一致。\n\n## 3. 健康指标\n\n不要用 skill 字数或数量单独评价质量。按 trace 观察：\n\n- activation precision：不相关任务是否误加载；\n- activation recall：相关任务是否及时加载；\n- 首次正确模块/状态所需时间和调用数；\n- 用户纠正次数；\n- 硬失败、rollback、raw-hou exemptions；\n- 已有能力 MISSED vs 真实 MISSING；\n- warning/error 与完成门覆盖；\n- 视觉/数值证据冲突是否诚实裁决；\n- H21/H22 行为差异；\n- skill 间重复规则和选择错误。\n\n指标用于定位原因，不作为机械 KPI。例如加载次数低可能只是领域不适用，不支持删除。\n\n## 4. 自进化安全门\n\n- ordinary task 不得悄悄修改 skill；修改生产知识是独立外部副作用，需要当前任务授权。\n- trace analyzer 可以自动生成候选，不得绕过 governance 直接把 E1 写成强规则。\n- domain skill 不直接修改其他 skill；它报告 evidence/delta，由治理 skill协调唯一维护位置。\n- governance skill 不自证自己的改动。修改自身需用户明确授权，并至少满足：跨两个领域重复问题、\n  可复现流程缺陷，或官方 skill 规范变化 + 本地验证。\n- 所有变更保持最小、可 diff、可回滚；大重构分 checkpoint，不一次改完所有 skills。\n- 发现冲突时允许 NO_CHANGE、REJECT 或降级旧规则；演化不是只增不减。\n\n## 5. 长期路线\n\n### M0：治理地基\n\n- 发布本治理 skill；\n- 确定性 inventory/registration/reference audit；\n- trace skill 在“用户要求更新 skills”时路由治理 skill；\n- 文档登记 evidence levels 和变更状态。\n\n### M1：当前五类 skills 标准化\n\n- 审查 trace、SOP、Solaris/Karma、rig/animation、governance 的 trigger、结构、来源与完成门；\n- 消除跨文件重复，建立 canonical positive/counterexample；\n- 给关键版本 claim 补 H21/H22 状态。\n\n### M2：新领域准入\n\n- COP：至少覆盖图像生成/处理、材质或纹理接口、缓存/颜色空间/输出三个真实任务；\n- SIM：至少覆盖 solver setup、缓存、时间/随机性、长 job/取消、交付验证；\n- project analysis：至少覆盖普通 HIP、缺依赖 HIP、HDA/外部缓存工程的只读边界；\n- 达到准入再建 skill，不预建空壳目录。\n\n### M3：持续知识刷新\n\n- Houdini 版本事件触发官方文档 + 本机帮助 + runtime 三角复核；\n- trace/video/project 形成候选队列；\n- 发布前 eval matrix 和新 session activation 检查；\n- 基于 S3 证据做 split/merge/deprecation，控制 skill 数量和 prompt 暴露成本。\n\n## 6. 回滚\n\n每次发布记录：修改文件、来源、证据等级、验证命令、支持版本和已知反例。回滚优先恢复上一个\n通过验证的 Git revision；不要用删除整个 `skills/`、覆盖用户工作区或重建无关文件的方式回滚。\n如果已发布 description 导致严重误触发，先窄化 description/dispatch，再回退领域内容；如果\n知识规则错误，保留反例和 rejected 记录，避免未来再次引入。\n"},{"path":"references/quality-standard.md","hash":"a87a24bbe016951ed40e1039e4bc4d858a62027008a2b686ac59d5df9b9c4c6f","bytes":12063,"text":"# Houdini domain skill 质量规范\n\n## 目录\n\n1. 质量目标\n2. 弱模型执行标准\n3. 新建准入\n4. 标准结构\n5. 泛化与边界\n6. 拆分、合并、弃用\n7. 验证清单\n\n## 1. 质量目标\n\n每个 domain skill 同时追求：\n\n- **触发准确**：description 能区分适用和相邻但不同的任务。\n- **决策增益**：正文只保留会改变 agent 选择或完成判定的非显然知识。\n- **泛化**：规则围绕数据模型、输入/输出契约和意图，不围绕某个 HIP 的节点名。\n- **稳定**：写明版本、失败面、状态恢复、warning/error 和交付边界。\n- **可证**：完成门绑定客观数据；视觉只承担可见语义。\n- **动态更新**：来源、反例和下一验收清楚，允许窄修正而不是永久叠加。\n- **精简**：SKILL.md 是路由和硬规则，条件性细节进入 references；不复制手册。\n- **可组合**：和 SOP、Solaris、trace 等 skill 的职责不重复，联用顺序明确。\n\n精简不是追求最少文件或最短字数，而是让每条内容只有一个维护位置，且实际改变决策。\n新增文字必须至少完成一件事：改变路由、提供已验证 fast path、阻断已证失败或定义完成门；否则删除。\n优先替换旧规则而不是尾部追加，发布前检查同一概念在 guidance/SKILL/reference 间是否重复或矛盾。\n\n## 2. 弱模型执行标准\n\ndomain skill 的首要消费者是可能缺少 Houdini 经验、版本记忆不稳定、容易在局部成功后提前完成的\nagent。skill 不替它完成任务，但必须提供一条低歧义、能恢复、能验收的执行脊柱。\n\n### 2.1 复杂度门\n\n- 简单且规格完整的一步编辑直接执行，只取与改动同层的回读证据；不强制写长计划、研究或渲染。\n- 跨三个以上模块、含状态/时间/缓存/绑定、依赖版本敏感节点、质量关系复杂或需正式交付的任务，\n  在首个大规模 mutation 前用 prose 或 todo 留下一份紧凑合同。\n- 合同写意图和边界，不写项目答案；至少回答：最终交付是什么、采用哪类数据模型、关键模块之间\n  传什么数据、哪些证据才能完成、哪些 helper 不属于交付。\n\n### 2.2 执行脊柱\n\n复杂任务的 domain skill 应让 agent 能按以下状态推进；标题和步数可因领域调整，不要求机械复述：\n\n```text\n任务契约 / 交付边界\n→ 数据模型与原生系统选择\n→ 已验证 fast path 或最小骨架\n→ 分模块 build → cook/readback checkpoint\n→ 集成后的最终 deliverable 取证\n→ 时序/视觉/文件等交付门\n→ 清理、恢复、保存、诚实报告\n```\n\n每个模块用 `输入/身份/rest state → 操作/求值 → 输出 → 不变量` 描述。driver、binding/evaluation、\ndriven output、presentation 是不同层；上游层通过不能替代下游交付。\n\n### 2.3 Fast path 与渐进披露\n\n- `SKILL.md` 只保留高频路由、执行脊柱、关键边界和完成门；具体节点、参数 token、HOM 片段、\n  版本差异与罕见失败进入按需 reference。\n- reference 以用户意图/数据模型路由，不按节点字母表堆手册。每条已验证 fast path 至少写：\n  `Applies when`、`Do not use when`、输入/输出、目标版本、最小构建、checkpoint、失败转向和验收。\n- 只有跨目标版本实测或目标版本 runtime 已复现的脆弱语法才允许给精确片段。片段使用占位名称和\n  最小几何，不携带训练实例的对象、数值、帧号、审美或评分答案。\n- 同一知识只在一个 canonical reference 维护；主 skill 只链接和概括决策，不复制长 recipe。\n\n### 2.4 探测阶梯与停止条件\n\n已存在 fast path 时先采用，不从零逆向 HDA。未知字段按最便宜、最公开的证据逐级探测：\n\n1. 当前任务已加载的 domain reference；\n2. `verb_help`、`search_tab_menu/search_tab_entries`、`list_parms/read_parms/describe`；\n3. 一个最小、可删除、单变量的 runtime probe；\n4. 同版本本机 help/shipped example；\n5. 只有公开合同不足或 runtime 与合同冲突时才检查 HDA internals/源码，并明确这是诊断而非默认做法。\n\n同一模块边界连续两次失败后，不继续改拼写或叠补丁：回到最后一个已验证 checkpoint，重述失败层，\n查对应 fast path/公开合同并换策略。probe 必须有停止条件和清理路径；最终任务不保留诊断网络。\n\n### 2.5 证据、失效与裁决\n\n- 每个核心主张绑定同层证据；cook success、总 bbox、文件存在、pixel diff 或上游 metadata 都不能\n  自动证明最终语义。\n- actual deliverable 的直接探针失败后保持 fail，不能换测 proxy/anchor/driver 后把同一契约改判 pass。\n- 最后一次影响数据模型、核心参数、接线、材质、状态求值或输出形态的 mutation，会使受影响的\n  旧证据失效；只重跑受影响完成门，不无差别重做全部任务。\n- 证据冲突按“最接近交付物且最直接”裁决。数值可推翻视觉对隐藏状态、相机元数据或精确角度的\n  猜测；清晰视觉反例可推翻仅凭像素变化得出的主体成功。无法裁定则标 `unverified`。\n- 最终报告只声明最后一轮新鲜证据实际覆盖的对象、样本和版本；todo complete 不补证。\n\n### 2.6 标准验收矩阵\n\n每个新建或实质更新的 domain skill 都必须准备以下行为验收；可分批完成，但未完成不得写 released：\n\n| 用例 | 证明什么 |\n|---|---|\n| 原失败实例 | 修正确实挡住已知因果链，不只改措辞 |\n| 未见同族复杂正例 | 规则能迁移到不同对象/规模/命名/参数 |\n| 相邻领域反例 | description 与路由不会过度触发 |\n| 领域内反例 | fast path 的 `Do not use when` 真能选择另一正确模型 |\n| 目标版本矩阵 | H21/H22 等支持版本的类型、参数、数据和失败面一致或显式分支 |\n| 失败恢复 | 相同边界重复失败时换策略、rollback/cleanup 正确 |\n| 最终交付 | helper 隔离、新鲜证据、保存/缓存/渲染与诚实报告成立 |\n\n审查记录同时报告结果质量与过程效率：首次正确 checkpoint、调用数、失败/rollback、重复探测、\nraw exemption、用户纠正、证据刷新。指标用来定位下一处改进，不设置会诱导作弊的固定得分阈值。\n\n## 3. 新建准入\n\n新 domain skill 至少满足：\n\n1. 有可识别的用户意图和触发边界；\n2. 有与现有 skill 不同的数据模型、关键选择或完成门；\n3. 领域知识足以减少重复失败，不只是节点目录；\n4. 至少有一个真实任务/工程/官方模式和一个反例；探索型候选可先记录在 development，\n   不必立即发布；\n5. 能说明为什么更新既有 skill 不够；\n6. 有可执行的第一验收。\n\n以下通常不应新建：\n\n- 某个镜头、草地、魔方、材质球的专用 recipe；\n- 只有一个节点或一个 API 的速查；\n- 与现有 skill 相同触发、相同生命周期、相同完成门的另一个名字；\n- 尚无任务证据、只是“将来可能会用”的领域目录。\n\nCOP 和 SIM 可以成为独立 skill，但应先证明各自有独立 context、数据/缓存/时间语义、\n执行风险和完成门，不能只因为 Houdini UI 中有独立网络类型。\n\n## 4. 标准结构\n\n### Frontmatter\n\n```yaml\n---\nname: houdini-<domain>-workflow\ndescription: <做什么、何时触发、必要的相邻排除边界>\n---\n```\n\n名称使用小写连字符，description 不写穷举大全，不吸引无关任务。\n\n### SKILL.md 正文\n\n按实际需要保留以下内容，不要求机械套满所有标题：\n\n1. 一句话目标与非目标；\n2. 任务/数据模型分类；\n3. 最小执行顺序和 checkpoint；\n4. 关键原生系统选择及反例；\n5. 跨 context/skill 联用边界；\n6. 完成门；\n7. 按需 reference 路由。\n\n长版本表、节点模式、输入 schema、来源账本、视频/工程分析细节进入 references。SKILL.md\n不应成为官方手册的缩写版。\n\n### Reference 条目最小 claim 格式\n\n```text\nClaim:\nWhy it changes a decision:\nSource/provenance:\nHoudini version/context:\nEvidence level:\nApplies when:\nCounterexample/boundary:\nValidation:\nLast reviewed:\n```\n\n无需为每句常识建账本；对版本敏感、强制性、来源外部或将改变工具设计的主张使用该格式。\n\n## 5. 泛化与边界\n\n把观察拆成四层：\n\n```text\nproject-specific choice\n→ reusable technique\n→ Houdini domain invariant\n→ cross-domain system invariant\n```\n\n只把证据支持的那一层写入对应 skill。例如：\n\n- “这个魔方用 27 块”是项目选择；\n- “刚体 piece 需要稳定 ID/transform”是 domain invariant；\n- “修改后必须重跑被失效的完成门”是 cross-domain invariant。\n\n规则必须写适用条件和反例。没有反例的绝对规则通常尚未完成设计。\n\nBenchmark 只提供证据，不提供可复制进生产 skill 的答案。不得把 benchmark ID、实例对象名、\n目标数值、评分 rubric、固定节点网络或针对某次失败的补丁措辞写进 description、SKILL.md、reference、\npreset 或 system guidance。候选规则要先改写成与对象无关的数据模型、状态转换、检查意图或完成门，\n再同时验证：原失败实例、一个未见同族实例和一个不应触发该规则的跨域反例。只在原实例上改善属于\n局部修复，不构成通用 skill 发布证据。\n\n知识放置优先级：\n\n1. 已存在的唯一维护位置；\n2. 最具体但仍覆盖整个主张的 domain skill；\n3. governance/trace 只保留跨域准入和证据规则；\n4. system prompt 只放高频 dispatch 和无法靠 skill 触发补救的硬不变量。\n\n## 6. 拆分、合并、弃用\n\n### 拆分\n\n当以下至少两项长期不同才拆：触发意图、Houdini context、数据模型、执行副作用、来源集合、\n完成门、版本节奏。文件变长本身不是拆分理由，先用 reference 渐进披露。\n\n### 合并\n\n当两个 skill 的触发、决策树、资源和完成门基本相同，且 trace 显示 agent 经常选错时合并。\n相邻领域可联用不等于应合并，例如 SOP 源数据与 Solaris 最终渲染有明确交付边界。\n\n### 弃用/删除\n\n至少需要：三个多样任务无独立价值、存在更安全等价替代、迁移路径、无诊断/逃生用途。\n先标 superseded/deprecated，更新注册和调用者，新 session 验证后再删除。\n\n## 7. 验证清单\n\n- `SKILL.md` frontmatter/name/description 通过结构校验；无模板占位。\n- 所有 reference 链接存在并可从 SKILL.md 渐进到达；无孤儿 reference。\n- `src/skill.ts` 注册名/目录一致；`npm pack --dry-run` 包含全部资源。\n- `npm run build` 通过；若只改未注册 reference，可说明为何 build 非必要。\n- description 用正例/相邻反例做触发检查。\n- 复杂任务有紧凑交付合同、数据模型、fast path、checkpoint、探测阶梯、停止条件和证据失效规则；\n  简单任务不会被这些规则强制膨胀。\n- fast path 明确 `Applies when / Do not use when`，版本敏感精确片段已在目标版本验证且不含实例答案。\n- 至少一个真实行为用例验证决策和完成门，不只匹配文字。\n- 原失败、未见同族正例、相邻/领域内反例、版本矩阵、失败恢复和最终交付按 §2.6 登记状态；\n  缺项必须留在 candidate/verified，不得标 released。\n- 强制规则有来源、版本、边界和反例。\n- benchmark 派生规则不含实例标识、对象配方、目标参数或评分答案，并有未见同族实例和跨域反例。\n- 与现有 skills/system guidance/tool-design 无冲突或重复真相源。\n- 变更状态、证据强度、下一验收写入 development/模式库；没有把计划写成已完成。\n- 发布后用新 session 检查 skill catalog/activation，旧 session 不能作为曝光证据。\n"},{"path":"scripts/audit-houdini-skills.mjs","hash":"75f21220d500afb7be4875907a7e445f306334d4f7d2559e1495cb6f16cb08e0","bytes":6524,"text":"#!/usr/bin/env node\n\nimport { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'\nimport { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'\nimport { fileURLToPath } from 'node:url'\n\nfunction parseArgs(argv) {\n  const out = { json: false, strict: false, root: null }\n  for (let i = 0; i < argv.length; i += 1) {\n    const arg = argv[i]\n    if (arg === '--json') out.json = true\n    else if (arg === '--strict') out.strict = true\n    else if (arg === '--root') out.root = argv[++i]\n    else throw new Error(`unknown argument: ${arg}`)\n  }\n  return out\n}\n\nfunction walkFiles(dir) {\n  if (!existsSync(dir)) return []\n  const out = []\n  for (const entry of readdirSync(dir, { withFileTypes: true })) {\n    const path = join(dir, entry.name)\n    if (entry.isDirectory()) out.push(...walkFiles(path))\n    else if (entry.isFile()) out.push(path)\n  }\n  return out\n}\n\nfunction parseSkill(markdown) {\n  const match = markdown.match(/^---\\r?\\n([\\s\\S]*?)\\r?\\n---\\r?\\n([\\s\\S]*)$/)\n  if (!match) return { name: null, description: null, body: markdown, frontmatter: false }\n  return {\n    name: match[1].match(/^name:\\s*(.+)$/m)?.[1]?.trim() ?? null,\n    description: match[1].match(/^description:\\s*(.+)$/m)?.[1]?.trim() ?? null,\n    body: match[2],\n    frontmatter: true,\n  }\n}\n\nfunction markdownLinks(text) {\n  const links = []\n  for (const match of text.matchAll(/\\[[^\\]]*\\]\\(([^)]+)\\)/g)) {\n    const raw = match[1].trim().replace(/^<|>$/g, '')\n    if (!raw || /^(?:https?:|mailto:|#)/i.test(raw)) continue\n    links.push(raw.split('#', 1)[0])\n  }\n  return links\n}\n\nfunction inside(root, path) {\n  const rel = relative(root, path)\n  return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..' && !isAbsolute(rel))\n}\n\nfunction reachableMarkdown(skillDir, startFile, issues) {\n  const seen = new Set()\n  const queue = [startFile]\n  while (queue.length) {\n    const file = queue.shift()\n    const key = resolve(file)\n    if (seen.has(key) || !existsSync(key)) continue\n    seen.add(key)\n    const text = readFileSync(key, 'utf8')\n    for (const link of markdownLinks(text)) {\n      const target = resolve(dirname(key), link)\n      if (!inside(skillDir, target)) {\n        issues.push({ code: 'LINK_ESCAPES_SKILL', file: relative(skillDir, key), link })\n        continue\n      }\n      if (!existsSync(target)) {\n        issues.push({ code: 'MISSING_LINK', file: relative(skillDir, key), link })\n      } else if (statSync(target).isFile() && target.toLowerCase().endsWith('.md')) {\n        queue.push(target)\n      }\n    }\n  }\n  return seen\n}\n\nconst args = parseArgs(process.argv.slice(2))\nconst scriptDir = dirname(fileURLToPath(import.meta.url))\nconst root = resolve(args.root ?? join(scriptDir, '..', '..', '..'))\nconst skillsRoot = join(root, 'skills')\nconst registryPath = join(root, 'src', 'skill.ts')\nconst issues = []\nconst warnings = []\n\nif (!existsSync(skillsRoot)) throw new Error(`skills directory not found: ${skillsRoot}`)\nif (!existsSync(registryPath)) throw new Error(`skill registry not found: ${registryPath}`)\n\nconst registryText = readFileSync(registryPath, 'utf8')\nconst registrations = [...registryText.matchAll(/\\{\\s*name:\\s*'([^']+)'\\s*,\\s*dir:\\s*'([^']+)'\\s*\\}/g)]\n  .map((match) => ({ name: match[1], dir: match[2] }))\nconst regByDir = new Map(registrations.map((item) => [item.dir, item]))\n\nconst dirs = readdirSync(skillsRoot, { withFileTypes: true })\n  .filter((entry) => entry.isDirectory())\n  .map((entry) => entry.name)\n  .sort()\n\nconst skills = []\nconst names = new Map()\nfor (const dir of dirs) {\n  const skillDir = join(skillsRoot, dir)\n  const skillFile = join(skillDir, 'SKILL.md')\n  if (!existsSync(skillFile)) {\n    issues.push({ code: 'MISSING_SKILL_MD', skill: dir })\n    continue\n  }\n  const parsed = parseSkill(readFileSync(skillFile, 'utf8'))\n  if (!parsed.frontmatter) issues.push({ code: 'BAD_FRONTMATTER', skill: dir })\n  if (parsed.name !== dir) issues.push({ code: 'NAME_DIR_MISMATCH', skill: dir, name: parsed.name })\n  if (!parsed.description) issues.push({ code: 'MISSING_DESCRIPTION', skill: dir })\n  if (parsed.description?.includes('\\n')) issues.push({ code: 'MULTILINE_DESCRIPTION', skill: dir })\n  if (parsed.name) {\n    if (names.has(parsed.name)) issues.push({ code: 'DUPLICATE_NAME', skill: dir, other: names.get(parsed.name) })\n    else names.set(parsed.name, dir)\n  }\n\n  const reachable = reachableMarkdown(skillDir, skillFile, issues)\n  const referenceFiles = walkFiles(join(skillDir, 'references'))\n    .filter((file) => file.toLowerCase().endsWith('.md'))\n  const orphanReferences = referenceFiles\n    .filter((file) => !reachable.has(resolve(file)))\n    .map((file) => relative(skillDir, file).replaceAll('\\\\', '/'))\n  for (const file of orphanReferences) warnings.push({ code: 'ORPHAN_REFERENCE', skill: dir, file })\n\n  const registration = regByDir.get(dir) ?? null\n  if (!registration) issues.push({ code: 'UNREGISTERED_SKILL', skill: dir })\n  else if (registration.name !== parsed.name) {\n    issues.push({ code: 'REGISTRATION_NAME_MISMATCH', skill: dir, registered: registration.name, name: parsed.name })\n  }\n  if (parsed.body.length > 12000) warnings.push({ code: 'LARGE_ENTRYPOINT', skill: dir, chars: parsed.body.length })\n\n  skills.push({\n    dir,\n    name: parsed.name,\n    description: parsed.description,\n    entrypointChars: parsed.body.length,\n    referenceCount: referenceFiles.length,\n    orphanReferences,\n    registered: Boolean(registration),\n  })\n}\n\nfor (const registration of registrations) {\n  if (!dirs.includes(registration.dir)) {\n    issues.push({ code: 'REGISTERED_DIR_MISSING', ...registration })\n  }\n}\n\nconst report = {\n  schemaVersion: 1,\n  root,\n  summary: {\n    skills: skills.length,\n    registrations: registrations.length,\n    issues: issues.length,\n    warnings: warnings.length,\n  },\n  skills,\n  registrations,\n  issues,\n  warnings,\n}\n\nif (args.json) {\n  process.stdout.write(`${JSON.stringify(report, null, 2)}\\n`)\n} else {\n  console.log(`Houdini skills: ${skills.length}; registrations: ${registrations.length}; issues: ${issues.length}; warnings: ${warnings.length}`)\n  for (const skill of skills) {\n    console.log(`- ${skill.name ?? skill.dir}: ${skill.entrypointChars} chars, ${skill.referenceCount} refs, registered=${skill.registered}`)\n  }\n  for (const issue of issues) console.log(`ERROR ${issue.code}: ${JSON.stringify(issue)}`)\n  for (const warning of warnings) console.log(`WARN  ${warning.code}: ${JSON.stringify(warning)}`)\n}\n\nif (args.strict && issues.length) process.exitCode = 1\n"},{"path":"SKILL.md","hash":"187328f17f3cbb777e7b4272e5e71ab3d0abd9707e5d8203762bae810d3641e8","bytes":5673,"text":"---\nname: houdini-skill-governance\ndescription: 创建、审查、维护和演化 dsh-houdini 的领域 skills。用于新增 COP/SIM/rig/project-analysis 等 skill，或依据 Houdini trace、SideFX 官方文档、本机版本、用户视频/工程更新现有 skill；不用于普通内容制作，也不允许未经授权或未经证据门自动修改生产 skill。\n---\n\n# Houdini Skill Governance\n\n把 skill 当成有来源、版本、适用边界和回归证据的产品模块，不当成不断追加经验的笔记。\n目标是让 Houdini 领域知识持续演化，同时保持触发准确、规则泛化、内容精简和版本可验证。\n\n## 入口工作流\n\n1. 先确认当前任务授权的是**只读分析/提案**，还是允许修改源码仓库中的 skills。普通\n   Houdini 内容任务、只要求分析 trace、安装包目录或 `$HIP` 都不授权修改生产 skill；\n   在这些场景只输出候选变更。不要把 skill 文件写进用户 HIP。\n2. 定位 dsh-houdini 源码根；修改前运行：\n\n   ```powershell\n   node skills/houdini-skill-governance/scripts/audit-houdini-skills.mjs --strict\n   ```\n\n   先盘点已有 skill、注册状态、引用完整性和重叠范围，不能默认新建。\n3. 给请求分类：`CREATE`、`UPDATE`、`INGEST`、`SPLIT/MERGE`、`DEPRECATE`、`RELEASE_AUDIT`。\n4. 创建或重构 skill 时完整阅读\n   [references/quality-standard.md](references/quality-standard.md)。\n   domain skill 的实质更新必须按其中“弱模型执行标准”检查复杂度门、执行脊柱、fast path、\n   探测停止、证据失效与验收矩阵；不能只过 frontmatter/链接审计就称质量达标。\n5. 证据来自 trace、官方文档、视频、HIP/HDA 工程或源码时，完整阅读\n   [references/evidence-ingestion.md](references/evidence-ingestion.md)，先建立 claim/provenance，\n   再决定是否改变规范。\n6. 做长期维护、Houdini 版本升级、跨 skill 冲突、发布或回滚时，完整阅读\n   [references/maintenance-lifecycle.md](references/maintenance-lifecycle.md)。\n   做 governance 行为回归时读取 [references/eval-cases.md](references/eval-cases.md)，按\n   observable decision/side effect 验收，不写只匹配标题或措辞的测试。\n7. 把每条候选知识放到正确层：\n   - system guidance：极少量跨域 dispatch/硬不变量；\n   - governance skill：证据门和维护协议；\n   - domain skill：领域路由、数据契约、关键选择和完成门；\n   - reference：条件性细节、官方模式、版本差异、反例；\n   - verb/tool：跨任务执行意图、校验、事务和状态恢复；\n   - trace pattern/development docs：证据历史、候选和路线，不冒充已发布能力。\n8. 做最小 diff，清除重复规则，保留反例和适用边界。单个项目节点名、艺术偏好、视频作者\n   个人习惯、benchmark ID、实例对象/目标参数、评分答案或模型臆测不得升级为通用硬规则。\n9. 验证后才标记完成：目标 skill 的结构校验、治理审计、引用/注册、必要构建、当前 Houdini\n   版本实验、原失败、未见同族行为用例和相邻/领域内反例。新 session 才能验证新的 skill\n   catalog/guidance 是否曝光；缺少任一发布门时明确停在 candidate/verified。\n\n## 受控自进化\n\n允许任何任务产出 `skill delta proposal`，但生产 skill 只按以下状态迁移：\n\n```text\nobservation → candidate → accepted → verified → released\n                                  ↘ rejected\nreleased → superseded/deprecated → removed\n```\n\n- 单 trace、单视频、单工程默认只到 `candidate`。\n- SideFX 官方资料仍需用目标 Houdini 版本的 Tab/本机帮助/最小实验确认适用性。\n- 可复现的 P0 工具或契约 bug 可直接修，但必须有回归。\n- 跨任务规则通常要求两个独立证据；删除/合并要求至少三个多样任务、反例和迁移路径。\n- 修改本治理 skill 自身需要比普通 domain skill 更强的理由：明确用户授权，并有跨领域证据或\n  治理流程自身的可复现失败。它不得因为自己生成的建议递归改写自己。\n\n## 硬边界\n\n- “分析材料”不等于“获得发布、复制或外传材料的权利”。记录来源、权限、隐私和许可；\n  用户工程中的专有 HDA、代码、路径、资产和第三方视频内容只提炼抽象规律，不复制进包。\n- 不复制整本 SideFX 手册或长视频转录。保存会改变决策的结论、前提、版本、反例和链接。\n- 不因一个新领域自动创建 skill。只有触发条件、数据模型、工作流和完成门与现有 skill 明显\n  不同时才拆分；能自然扩展既有 skill 时优先更新。\n- 不让管理 skill 代替领域专家 skill。它裁判证据与结构，不伪装成 COP、SIM、KineFX 或\n  Solaris 的操作手册。\n- 不以文档更新冒充能力实现。若工具/skill 尚未注册、构建、部署和用新 session 验证，状态\n  必须写“计划/候选”，不能写“已完成”。\n- 不用训练/发现实例本身验证泛化。实例修复必须再过未见同族任务和跨域反例；只在原题变好时\n  记录为局部回归通过，不发布为通用能力提升。\n\n## 输出契约\n\n每次治理任务都交付：\n\n1. 输入来源与授权边界；\n2. 已确认事实、未验证假设、冲突与版本；\n3. 目标 skill/layer 与 CREATE/UPDATE/SPLIT/MERGE/NO_CHANGE 决策；\n4. 最小变更及没有采纳的内容和理由；\n5. 验证结果、失败和未覆盖反例；\n6. evidence level、下一验收和回滚方式。\n"}]}],"presets":[{"name":"houdini","file":"presets/houdini/agent.cordis.yml","text":"You are a Houdini automation agent powered by the {{model}} model. Your working directory is {{cwd}}.\n\nYou are connected to a live SideFX Houdini session through the dsh-houdini bridge. The user launches this agent from inside Houdini, so treat the open Houdini scene as the primary working target. Route ALL Houdini work through the dedicated tools (houdini_query / houdini_exec / houdini_job_*), never through shell/filesystem tools.\n\nRead the supplied scene metadata observation before planning: its timestamp, selected nodes and pane candidates describe an observation, not a locked state or edit permission. Query only missing relevant facts. Build one observable correct prototype early, then refine modules and test their actual connections as you integrate them. Consult the current node operation card for input roles, local frames and output-surface defaults. Prefer geometric measurements for hidden structure and targeted views for shape judgement; choose the observation that can settle the current question. Controls need both intended response and preserved relationships, not just changing bounding boxes.\n\nBefore substantial Houdini mutation, resolve only the ambiguities that can materially change the result. For an open-ended or quality-sensitive request, inspect what the scene can answer, use available research/web capabilities when external truth or current references matter, and ask the user for the remaining consequential choices. Then state a compact task contract: chosen target and reference status, assumptions, deliverables, quality bar, objective checks, visual evidence plan, and unresolved boundaries. If the user delegates a choice, choose it and disclose the assumption; do not invent an external quality standard from model memory and then cite the result as verified. Simple, fully specified, or easily reversible work should proceed directly rather than becoming a ritual questionnaire. Re-open the contract when user feedback invalidates an assumption or completion claim.\n\nMake consequential user choices choice-first, not blank-input-first. Use ask_user_question with its declared schema and give each question 2–4 concrete, mutually exclusive options; put the recommended option first and briefly explain how every option changes cost, quality, or workflow. When reasonable, include an \"agent decides\" option and preserve the tool's custom response so the user can add free-text constraints. Group up to three related choices in one call instead of serial empty text boxes. Use a text-only answer only when the value is inherently unique, such as an exact path, node name, custom specification, or number that useful presets cannot represent; ask one targeted follow-up if an option plus its text supplement is still materially ambiguous. Never invent ad-hoc ask_user_question fields outside the exposed schema.\n\nKeep explicit user requirements and subsequent user changes distinct from your defaults and unknowns, with a short source quote or message reference for core obligations. A goal/todo summary is a plan, not permission to drop a quality requirement or make it optional. On continuation or correction, retain unmet obligations alongside the new work; only user changes can replace their requirements. A short request leaves product choices open but still requires a working editable recipe, valid outputs and honest reporting. Simple edits need no separate register.\n\nUse the contract to guide evidence collection. When an activated domain skill marks a quality protocol or referenced contract mandatory, load it before substantial mutation and execute its checkpoints. Before claiming completion, reconcile the original requirements and later user changes with pass/fail/unverified evidence. When configurability is promised, test and restore the exposed controls against their intended outputs and relationships; a local prototype test covers only that prototype and those tested controls. Refresh affected checks and views after changes. If any user-requested core dimension remains fail or unverified, label the delivery partial/incomplete and do not open with a completion claim; optional boundaries may remain unverified only when they are explicitly outside the agreed contract. A recognizable result, a successful render, high node/primitive counts, warning-free cook, or completed todos cannot substitute for the promised quality and relationship evidence.\n\nHoudini's power is procedural generation. When a request implies repetition, variation, or scale (N objects, scattered items, patterns, randomized looks), build a small procedural network that GENERATES the result — typically one geometry object whose SOP chain creates the copies (Copy to Points, For-Each, instancing) with attribute-driven variation — instead of imperatively creating N geometry objects or hundreds of nodes. The scene you leave behind must be an editable recipe the user can re-cook and tweak, not a baked pile of nodes.\n\nSave ALL Houdini outputs relative to the Houdini project directory ($HIP), never into the dsh workspace: scenes as $HIP/<name>.hip, renders into $HIP/render/, geometry exports into $HIP/geo/. Use hou.hipFile to discover $HIP. Clean up temporary probe nodes/scripts when done. If the scene has never been saved ($HIP is not meaningful), ask the user where the project lives before producing files. Images produced by the render/screenshot verbs are auto-relayed into the session workspace (see the `media` section of tool results), so vision tools can read them even when {{cwd}} differs from $HIP. For OTHER file kinds dsh-side tools must read: never work around the sandbox by writing temp files into the plugin repo — tell the user to open DSH-Houdini > Version & Diagnostics > Advanced diagnostics and run Repair and restart runtime, which re-seeds a Houdini session from the current $HIP.\n\nTreat viewport display, selection, and frame as user-owned shared-screen state that may drift while you work; do not fight it. Verify the explicit deliverable through the plugin's deterministic workflow, then set the user-facing output only for handoff. If objective checks cannot settle visual quality, report that boundary instead of claiming success.\n\nOrdinary SOP tasks finish with the author's relevant output, relationship and control checks; independent review is optional, not a mandatory handoff stage. Use houdini_exec(review={parent,output,controller}) when the user requests review or a specific unresolved concern benefits from a second perspective. The Host supplies original requirements, a current snapshot and prior tool facts. Reuse existing images/evidence, inspect concrete doubts, and preserve untested scope. Repair confirmed issues; do not turn a completed review or partial author tests into blanket approval. Do not restart delivery registration/cache or per-control message loops.\n\nRendering is expensive and not always wanted. When the request does not clearly state the deliverable — build the scene/network only, or also produce rendered images/animation — ask the user (ask_user_question) before starting any render work; never burn time on test renders the user did not ask for."},{"name":"houdini-dev","file":"presets/houdini-dev/agent.cordis.yml","text":"You are a coding/development agent powered by the {{model}} model. Your working directory is {{cwd}}.\n\nYou are developing the dsh-houdini plugin itself: the Cordis host half (src/), the hand-written client half (client.js), the Houdini-side Python bridge and verb vocabulary (houdini/python3.11libs/), the composition files (cordis.patch.yml, presets/), and the docs. Treat the plugin repository ({{cwd}}) as the primary working target, and use the normal coding tools (read/write/edit, filesystem, shell, git, npm run build) as your primary means of development.\n\nA live SideFX Houdini session is available through the dsh-houdini bridge as a test target, not a content-building target. Use the dedicated tools (houdini_query / houdini_exec / houdini_job_*) to verify the bridge, exercise the verb vocabulary, reproduce bugs, and check scene state end-to-end. In mutation execs, never swallow an exception after logging it: re-raise so the bridge reports failure and can roll back undoable scene edits. Treat render_check as image-validity/pixel-change evidence only; visual semantics remain unverified unless a vision tool successfully inspects the relayed image.\n\nKeep code outputs in the repository ({{cwd}}), not in the Houdini project directory. Save throwaway test scenes/outputs to a temporary location, or into the Houdini project only when the test requires it; clean up temporary probe nodes/scripts when done. After changing src/, run `npm run build`; after changing compiled Host code, Houdini-side Python, or presets, open DSH-Houdini > Version & Diagnostics > Advanced diagnostics and run Repair and restart runtime."}]};
    var TRACE_CSS = ".dsh-trace {\n  --tr-bg: var(--dsw-alias-bg-layer-1, #171b20);\n  --tr-panel: var(--dsw-alias-bg-layer-2, #20252b);\n  --tr-fg: var(--dsw-alias-label-primary, #e5e9ed);\n  --tr-muted: var(--dsw-alias-label-secondary, #a9b4bf);\n  --tr-line: var(--dsw-alias-border-l2, #38414a);\n  --tr-orange: #ba692c;\n  --tr-blue: #568bb8;\n  --tr-purple: #9978bd;\n  --tr-read: #8298ab;\n  --tr-red: var(--dsw-alias-state-error-primary, #da706b);\n  color: var(--tr-fg);\n  background: var(--tr-bg);\n  font:\n    14px/1.65 \"Segoe UI\",\n    \"Microsoft YaHei\",\n    sans-serif;\n  min-height: 360px;\n  height: calc(100dvh - 120px);\n  display: flex;\n  flex-direction: column;\n  overflow: hidden;\n}\n.dsh-trace * {\n  box-sizing: border-box;\n}\n.dsh-trace button,\n.dsh-trace input,\n.dsh-trace select {\n  font: inherit;\n  color: inherit;\n}\n.dsh-trace button {\n  cursor: pointer;\n  border: 1px solid var(--tr-line);\n  background: transparent;\n  border-radius: 4px;\n  padding: 6px 10px;\n  text-align: left;\n}\n.dsh-trace button:focus-visible,\n.dsh-trace summary:focus-visible {\n  outline: 2px solid var(--tr-orange);\n  outline-offset: 2px;\n}\n.dsh-trace button[aria-pressed=\"true\"] {\n  background: color-mix(in srgb, var(--tr-orange) 12%, var(--tr-panel));\n  border-color: var(--tr-orange);\n}\n.dsh-trace header {\n  padding: 16px 22px 8px;\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  gap: 12px;\n  flex-wrap: wrap;\n}\n.dsh-trace h2 {\n  font-size: 20px;\n  font-weight: 500;\n  margin: 0;\n}\n.dsh-trace h3 {\n  font-size: 17px;\n  font-weight: 500;\n  margin: 0 0 10px;\n}\n.dsh-trace h4 {\n  font-size: 13px;\n  margin: 18px 0 7px;\n  font-weight: 500;\n}\n.dsh-trace nav {\n  display: flex;\n  gap: 6px;\n  flex-wrap: wrap;\n  padding: 8px 22px;\n  border-bottom: 1px solid var(--tr-line);\n}\n.dsh-trace nav button {\n  border: 0;\n  border-bottom: 2px solid transparent;\n  border-radius: 0;\n}\n.dsh-trace nav button[aria-pressed=\"true\"] {\n  border-color: var(--tr-orange);\n  background: transparent;\n}\n.dsh-trace .tr-status {\n  font-size: 12px;\n  padding: 8px 22px;\n  color: var(--tr-muted);\n  border-bottom: 1px solid var(--tr-line);\n}\n.dsh-trace .tr-content {\n  overflow: auto;\n  min-height: 0;\n  flex: 1;\n}\n.dsh-trace .tr-board {\n  padding: 20px 22px;\n}\n.dsh-trace .tr-toolbar {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  gap: 10px;\n  flex-wrap: wrap;\n  margin-bottom: 16px;\n}\n.dsh-trace .tr-buttons {\n  display: flex;\n  gap: 6px;\n  align-items: center;\n  flex-wrap: wrap;\n}\n.dsh-trace .tr-buttons button {\n  font-size: 12px;\n}\n.dsh-trace .tr-split {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);\n  gap: 18px;\n  align-items: start;\n}\n.dsh-trace .tr-inspector {\n  grid-template-columns: minmax(220px, 0.7fr) minmax(0, 1.5fr);\n}\n.dsh-trace .tr-detail {\n  min-width: 0;\n  background: var(--tr-panel);\n  border: 1px solid var(--tr-line);\n  padding: 18px;\n  border-radius: 5px;\n}\n.dsh-trace .tr-list {\n  min-width: 0;\n}\n.dsh-trace .tr-row {\n  display: block;\n  width: 100%;\n  padding: 12px;\n  border: 0;\n  border-left: 3px solid transparent;\n  border-bottom: 1px solid var(--tr-line);\n  border-radius: 0;\n}\n.dsh-trace .tr-row[aria-pressed=\"true\"] {\n  border-left-color: var(--tr-kind, var(--tr-orange));\n  background: color-mix(\n    in srgb,\n    var(--tr-kind, var(--tr-orange)) 9%,\n    var(--tr-panel)\n  );\n}\n.dsh-trace .tr-rowhead {\n  display: flex;\n  gap: 8px;\n  justify-content: space-between;\n  align-items: start;\n}\n.dsh-trace .tr-meta,\n.dsh-trace small {\n  font-size: 12px;\n  color: var(--tr-muted);\n  overflow-wrap: anywhere;\n}\n.dsh-trace .tr-meta {\n  display: block;\n  margin-top: 4px;\n}\n.dsh-trace .tr-title {\n  overflow-wrap: anywhere;\n}\n.dsh-trace .tr-pill {\n  display: inline-block;\n  font-size: 11px;\n  border: 1px solid var(--tr-line);\n  border-radius: 3px;\n  padding: 1px 5px;\n  white-space: normal;\n}\n.dsh-trace .tr-bad {\n  color: var(--tr-red);\n}\n.dsh-trace [data-kind=\"skill\"] {\n  --tr-kind: var(--tr-purple);\n}\n.dsh-trace [data-kind=\"read\"] {\n  --tr-kind: var(--tr-read);\n}\n.dsh-trace [data-kind=\"query\"] {\n  --tr-kind: var(--tr-blue);\n}\n.dsh-trace [data-kind=\"exec\"] {\n  --tr-kind: var(--tr-orange);\n}\n.dsh-trace [data-kind=\"other\"] {\n  --tr-kind: #8d83b8;\n}\n.dsh-trace [data-kind=\"planning\"] {\n  --tr-kind: #459b91;\n}\n.dsh-trace [data-kind=\"shell\"] {\n  --tr-kind: #a99b4d;\n}\n.dsh-trace [data-kind=\"write\"] {\n  --tr-kind: #b37492;\n}\n.dsh-trace [data-kind=\"search\"] {\n  --tr-kind: #528eb5;\n}\n.dsh-trace [data-kind=\"interaction\"] {\n  --tr-kind: #9c82c2;\n}\n.dsh-trace .tr-type {\n  color: var(--tr-kind);\n  font-size: 11px;\n  background: color-mix(in srgb, var(--tr-kind) 10%, var(--tr-panel));\n  padding: 2px 5px;\n  border-radius: 3px;\n}\n.dsh-trace .tr-type:before {\n  content: \"●\";\n  margin-right: 4px;\n  font-size: 8px;\n}\n.dsh-trace table {\n  border-collapse: collapse;\n  width: 100%;\n  table-layout: fixed;\n  font-size: 12px;\n}\n.dsh-trace th,\n.dsh-trace td {\n  text-align: left;\n  padding: 9px 8px;\n  vertical-align: top;\n  border-bottom: 1px solid var(--tr-line);\n  overflow-wrap: anywhere;\n}\n.dsh-trace th {\n  font-weight: 500;\n  color: var(--tr-muted);\n  background: var(--tr-bg);\n}\n.dsh-trace code {\n  font:\n    12px/1.65 Consolas,\n    monospace;\n  overflow-wrap: anywhere;\n}\n.dsh-trace pre {\n  font:\n    12px/1.75 Consolas,\n    monospace;\n  white-space: pre-wrap;\n  overflow-wrap: anywhere;\n  background: var(--tr-bg);\n  padding: 12px;\n  border-radius: 4px;\n  margin: 8px 0;\n}\n.dsh-trace details {\n  border-top: 1px solid var(--tr-line);\n  padding: 10px 0;\n  margin-top: 8px;\n}\n.dsh-trace summary {\n  cursor: pointer;\n  overflow-wrap: anywhere;\n  font-size: 12px;\n}\n.dsh-trace .tr-note {\n  border-left: 2px solid var(--tr-line);\n  padding: 8px 12px;\n  color: var(--tr-muted);\n  font-size: 12px;\n  margin: 12px 0;\n}\n.dsh-trace .tr-prose {\n  white-space: pre-wrap;\n  overflow-wrap: anywhere;\n  font-size: 13px;\n  line-height: 1.8;\n}\n.dsh-trace .tr-prose p {\n  margin: 8px 0;\n}\n.dsh-trace .tr-empty {\n  padding: 24px;\n  color: var(--tr-muted);\n  border: 1px dashed var(--tr-line);\n}\n.dsh-trace select {\n  padding: 6px;\n  background: var(--tr-panel);\n  border: 1px solid var(--tr-line);\n  border-radius: 4px;\n  max-width: 100%;\n}\n.dsh-trace .tr-metrics {\n  display: flex;\n  flex-wrap: wrap;\n  gap: 22px;\n  margin: 16px 0;\n}\n.dsh-trace .tr-metrics strong {\n  display: block;\n  font-size: 22px;\n  font-weight: 500;\n}\n.dsh-trace .tr-domains {\n  margin-bottom: 18px;\n}\n.dsh-trace .tr-legend {\n  display: flex;\n  gap: 12px;\n  flex-wrap: wrap;\n  margin-bottom: 10px;\n}\n.dsh-trace .tr-key {\n  color: var(--tr-muted);\n}\n.dsh-trace .tr-tree {\n  margin-left: 8px;\n  border-left: 1px solid var(--tr-line);\n  padding-left: 10px;\n}\n.dsh-trace .tr-raw {\n  color: var(--tr-muted);\n}\n.dsh-trace {\n  position: relative;\n  z-index: 1;\n  isolation: isolate;\n}\n.dsh-trace header {\n  padding: 10px 16px 3px;\n  flex-shrink: 0;\n}\n.dsh-trace h2 {\n  font-size: 17px;\n}\n.dsh-trace nav {\n  padding: 4px 16px;\n  gap: 4px;\n  flex-shrink: 0;\n}\n.dsh-trace .tr-status {\n  padding: 5px 16px;\n  flex-shrink: 0;\n}\n.dsh-trace button:disabled {\n  opacity: 0.4;\n  cursor: default;\n}\n.dsh-trace .tr-content-timeline {\n  overflow: hidden;\n}\n.dsh-trace .tr-timeline {\n  height: 100%;\n  min-height: 0;\n  display: flex;\n  flex-direction: column;\n  background: var(--tr-bg);\n}\n.dsh-trace .tr-timeline-toolbar {\n  flex: none;\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  flex-wrap: wrap;\n  gap: 6px 12px;\n  padding: 8px 12px;\n  background: var(--tr-panel);\n  border-bottom: 1px solid var(--tr-line);\n}\n.dsh-trace .tr-timeline-toolbar button,\n.dsh-trace .tr-pager select {\n  font-size: 12px;\n  padding: 4px 8px;\n  line-height: 1.5;\n}\n.dsh-trace .tr-pager {\n  display: flex;\n  align-items: center;\n  flex-wrap: wrap;\n  gap: 5px;\n  font-size: 12px;\n}\n.dsh-trace .tr-range {\n  font-variant-numeric: tabular-nums;\n  color: var(--tr-muted);\n  margin-right: 6px;\n}\n.dsh-trace .tr-timeline-body {\n  display: grid;\n  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);\n  flex: 1;\n  min-height: 0;\n  overflow: hidden;\n}\n.dsh-trace .tr-call-list,\n.dsh-trace .tr-call-detail {\n  min-width: 0;\n  min-height: 0;\n  overflow: auto;\n  overscroll-behavior: contain;\n  scrollbar-width: thin;\n}\n.dsh-trace .tr-call-list {\n  background: var(--tr-bg);\n}\n.dsh-trace .tr-call-detail {\n  background: var(--tr-panel);\n  border-left: 1px solid var(--tr-line);\n}\n.dsh-trace .tr-call-detail > .tr-detail {\n  border: 0;\n  border-radius: 0;\n  padding: 14px 16px;\n  background: var(--tr-panel);\n}\n.dsh-trace .tr-call-row {\n  display: block;\n  width: 100%;\n  border: 0;\n  border-left: 3px solid var(--tr-kind);\n  border-bottom: 1px solid var(--tr-line);\n  border-radius: 0;\n  padding: 6px 10px 5px;\n  background: var(--tr-bg);\n  line-height: 1.4;\n}\n.dsh-trace .tr-call-row[aria-pressed=\"true\"] {\n  border-left-color: var(--tr-kind);\n  background: color-mix(in srgb, var(--tr-kind) 12%, var(--tr-panel));\n}\n.dsh-trace .tr-call-row:hover {\n  background: color-mix(in srgb, var(--tr-kind) 7%, var(--tr-panel));\n}\n.dsh-trace .tr-call-head {\n  display: grid;\n  grid-template-columns: 35px minmax(0, 1fr) auto 43px;\n  gap: 7px;\n  align-items: center;\n  min-height: 19px;\n}\n.dsh-trace .tr-call-index {\n  font:\n    11px Consolas,\n    monospace;\n  color: var(--tr-muted);\n}\n.dsh-trace .tr-call-title {\n  white-space: nowrap;\n  overflow: hidden;\n  text-overflow: ellipsis;\n  font-size: 13px;\n}\n.dsh-trace .tr-call-state {\n  font-size: 11px;\n  color: var(--tr-muted);\n  white-space: nowrap;\n}\n.dsh-trace .tr-call-state.tr-bad {\n  color: var(--tr-red);\n}\n.dsh-trace .tr-call-time {\n  font:\n    11px Consolas,\n    monospace;\n  color: var(--tr-muted);\n  text-align: right;\n}\n.dsh-trace .tr-call-meta {\n  display: flex;\n  gap: 8px;\n  align-items: center;\n  margin-top: 4px;\n  min-height: 16px;\n  font-size: 11px;\n  min-width: 0;\n}\n.dsh-trace .tr-call-kind {\n  color: var(--tr-kind);\n  overflow: hidden;\n  text-overflow: ellipsis;\n  white-space: nowrap;\n  max-width: 40%;\n  flex-shrink: 1;\n}\n.dsh-trace .tr-call-kind:before,\n.dsh-trace .tr-kind-legend:before {\n  content: \"●\";\n  font-size: 7px;\n  margin-right: 4px;\n}\n.dsh-trace .tr-call-target {\n  flex: 1;\n  min-width: 0;\n  overflow: hidden;\n  text-overflow: ellipsis;\n  white-space: nowrap;\n  color: var(--tr-muted);\n}\n.dsh-trace .tr-call-tokens {\n  font:\n    11px Consolas,\n    monospace;\n  white-space: nowrap;\n  color: var(--tr-muted);\n  margin-left: auto;\n}\n.dsh-trace .tr-timeline-footer {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  flex-wrap: wrap;\n  gap: 4px 12px;\n  flex: none;\n  padding: 5px 12px;\n  font-size: 11px;\n  color: var(--tr-muted);\n  border-top: 1px solid var(--tr-line);\n  background: var(--tr-panel);\n}\n.dsh-trace .tr-kind-legend {\n  display: inline-block;\n  color: var(--tr-kind);\n  margin-right: 9px;\n  white-space: nowrap;\n}\n.dsh-trace .tr-back-list {\n  display: none;\n}\n.dsh-trace .tr-sr-only {\n  position: absolute;\n  width: 1px;\n  height: 1px;\n  overflow: hidden;\n  clip: rect(0, 0, 0, 0);\n  white-space: nowrap;\n}\n@media (max-width: 850px) {\n  .dsh-trace .tr-split {\n    grid-template-columns: 1fr;\n  }\n  .dsh-trace .tr-board {\n    padding: 14px;\n  }\n  .dsh-trace header,\n  .dsh-trace nav,\n  .dsh-trace .tr-status {\n    padding-left: 14px;\n    padding-right: 14px;\n  }\n  .dsh-trace {\n    height: auto;\n    max-height: none;\n    overflow: visible;\n  }\n  .dsh-trace .tr-content {\n    overflow: visible;\n  }\n  .dsh-trace:has(.tr-timeline) {\n    height: calc(100dvh - 130px);\n    min-height: 360px;\n    overflow: hidden;\n  }\n  .dsh-trace .tr-content-timeline {\n    overflow: hidden;\n  }\n  .dsh-trace .tr-timeline-body {\n    display: block;\n    position: relative;\n  }\n  .dsh-trace .tr-call-list {\n    height: 100%;\n  }\n  .dsh-trace .tr-call-detail {\n    display: none;\n    height: 100%;\n    border: 0;\n  }\n  .dsh-trace .tr-detail-open .tr-call-list {\n    display: none;\n  }\n  .dsh-trace .tr-detail-open .tr-call-detail {\n    display: block;\n  }\n  .dsh-trace .tr-back-list {\n    display: block;\n    position: sticky;\n    top: 0;\n    z-index: 1;\n    width: 100%;\n    background: var(--tr-panel);\n    border-radius: 0;\n    border: 0;\n    border-bottom: 1px solid var(--tr-line);\n    padding: 8px 14px;\n  }\n  .dsh-trace .tr-timeline-footer > span:last-child {\n    display: none;\n  }\n}\n@media (pointer: coarse) {\n  .dsh-trace button,\n  .dsh-trace summary,\n  .dsh-trace select {\n    min-height: 44px;\n  }\n}\n";
    var createTraceView = (function createTraceView(React, catalog, sources, parseEntry, css) {
  "use strict";
  const h = React.createElement;
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
  // UI categories only: these colors do not confer execution permissions.
  const toolKind = (name) => {
    if (name === "skill") return "skill";
    if (["houdini_query", "houdini_job_status"].includes(name)) return "query";
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
      "compatibility 域": "历史兼容",
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
  function sections(raw) {
    const out = {};
    const re =
      /(?:^|\n\n)(stdout|stderr|__result__|rollback|transaction|operation-evidence|control-test-summary \(not_run is not pass\)|CHECKS NEED ATTENTION \(execution success is not validation success\)|raw-usage|hint|verbs \(\d+\)|media(?: [^\n:]*)?):\n/g;
    const matches = [...raw.matchAll(re)];
    matches.forEach((m, i) => {
      out[m[1]] = raw
        .slice(m.index + m[0].length, matches[i + 1]?.index ?? raw.length)
        .trim();
    });
    return out;
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
    const requestFor = (turn, step, seq) => {
      const matches = requests.filter(
        (r) =>
          r.purpose === "assistant" &&
          r.turn === turn &&
          r.step === step &&
          (seq == null || r.startSeq <= seq),
      );
      return (
        matches.find((r) => r.resultSeq === seq) ||
        [...matches].reverse().find((r) => r.status === "complete") ||
        matches[matches.length - 1] ||
        null
      );
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
      const parts = sections(info.text);
      const canonical = name.startsWith("houdini_") ? n.meta?.canonical : null;
      const transaction = canonical?.transaction ?? json(parts.transaction);
      const req =
        c?.request ||
        requestFor(turn, step, n.seq) ||
        entries.find((e) => e.id === parent)?.request ||
        null;
      const account = req?.accounting || c?.assistantUsage || null;
      const failed = !pending && (Boolean(n.isError) || info.failed);
      const verbs = info.verbs;
      const parsedArgs = json(argsRaw);
      const args =
        parsedArgs &&
        typeof parsedArgs === "object" &&
        !Array.isArray(parsedArgs)
          ? parsedArgs
          : {};
      const title =
        name === "skill"
          ? "读取技能 · " + (args.name || "名称缺失")
          : verbs.length
            ? [...new Set(verbs.map((v) => verbTitles[v.verb] || v.verb))].join(
                " / ",
              )
            : args.result_ref
              ? "读取历史工具结果"
              : args.review
              ? "复核输出"
              : args.review_test
                ? "受控复核实验"
                : name;
      const rollback = transaction
        ? transaction.status === "rolled_back"
        : Boolean(info.rollbackApplied && !info.rollback?.error);
      const state = pending
        ? "执行中（最后快照）"
        : info.gateBlocked
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
      entries.push({
        ...info,
        id,
        key: id,
        name,
        args,
        argsRaw,
        title,
        target,
        verbs,
        failed,
        pending,
        parent: parent || n.parentCallId || null,
        transaction,
        rollbackApplied: rollback,
        state,
        kind: args.result_ref ? "read" : toolKind(name),
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
      });
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
        const parent = entries.find((p) => p.id === e.parent);
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
    };
  }
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
    const snapshot =
      typeof props.useTrajectory === "function"
        ? props.useTrajectory((s) => s)
        : props.useSession(
            (s) =>
              s?.views?.get?.("trajectory") || { eventNodes: s?.nodes || [] },
          );
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
      data.requests.find((r) => r.key === chosenRequest) ||
      [...data.requests].reverse().find((r) => r.purpose === "assistant") ||
      null;
    const entry =
      data.entries.find((e) => e.id === selected) ||
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
          h("h4", null, "返回"),
          structured(json(v.detail) ?? v.detail),
          v.detail.endsWith("…")
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
          e.rawMode === "read_only"
            ? tag(
                "HOM 读取" + (e.directHouCount ? " ×" + e.directHouCount : ""),
              )
            : null,
          e.rawMode === "exempted" ? tag("低层豁免") : null,
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
        e.rawMode !== "none"
          ? h(
              "details",
              null,
              h("summary", null, "HOM / Raw Gate · " + e.rawMode),
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
          (filter === "error" && (e.failed || e.rawMode === "blocked")),
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
      const g = sources.guidance;
      const sourceItems = [
        {
          key: "guidance",
          title: "Houdini 插件系统提示词",
          label: g.name,
          text: g.text,
          source: g.source,
          order: g.order,
        },
        ...sources.presets.map((p) => ({
          key: "preset:" + p.name,
          title: "Preset · " + p.name,
          label: "persona 模板",
          text: p.text,
          source: p.file,
          order: 0,
        })),
      ];
      const s = sourceItems.find((s) => s.key === sourceKey) || sourceItems[0];
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
                ? prose(p.system || "此请求未包含 System 正文")
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
                "这里保留 DSH 最终拼接的所有系统内容。公开快照未提供逐段注册 provenance；不能凭文本位置猜提供方。",
              ),
            )
          : null,
        promptPage === "sources"
          ? h(
              "section",
              null,
              note(
                "以下来自当前构建包，自动同步源码；与历史请求分开。完整原文匹配才标出存在，模板未匹配不代表未启用。",
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
                      ["注册 / 模板", s.label],
                      ["定义 order", String(s.order)],
                      [
                        "请求匹配",
                        p?.system?.includes(s.text)
                          ? "完整原文存在于本次 System"
                          : "未确认；可能变量展开、版本差异或未启用",
                      ],
                      ["字符数", String(s.text.length)],
                    ],
                  ),
                  s.key === "guidance"
                    ? note("一个注册系统段；下面按原文段落分组阅读。")
                    : note("persona模板含变量；实际生效文本查看本次 System。"),
                  s.text
                    .split(/\n\n/)
                    .map((part, i) =>
                      h(
                        "details",
                        { key: i, open: i === 0 },
                        h(
                          "summary",
                          null,
                          "段落 " + (i + 1) + " · " + part.length + " 字符",
                        ),
                        prose(part),
                      ),
                    ),
                  h(
                    "details",
                    null,
                    h("summary", null, "连续完整原文"),
                    prose(s.text),
                  ),
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
                [
                  ["houdini_query", "只读观察"],
                  ["houdini_exec", "场景执行 / review / review_test互斥入口"],
                  ["houdini_job_submit", "长操作排队提交"],
                  ["houdini_job_status", "状态与结果"],
                  ["houdini_job_cancel", "协作式取消"],
                ],
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
                              "当前构建资源；不替代历史读取返回。参考读取单独按资源目录与绝对路径关联，历史版本未采集；不把当前文件当作过去的返回。",
                            ),
                            h(
                              "details",
                              { key: file.path, open: true },
                              h("summary", null, "查看文件内容"),
                              file.text == null
                                ? note("非文本或超过内联预算，正文未内联。")
                                : file.path.endsWith(".md")
                                  ? prose(file.text)
                                  : h("pre", null, file.text),
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
      const entries = data.entries.filter(
        (e) => e.name.startsWith("houdini_") && !e.pending,
      );
      const successful = entries.filter(
        (e) => e.name === "houdini_exec" && !e.failed && !e.rollbackApplied,
      );
      const withVerbs = successful.filter((e) => e.verbs.length).length;
      const verbCount = entries.reduce((n, e) => n + e.verbs.length, 0);
      const distinctVerbs = new Set(
        entries.flatMap((e) => e.verbs.map((v) => v.verb)),
      );
      const knownVerbs = catalog.flatMap((d) => d.verbs.map((v) => v.name));
      const accounts = data.requests.map((r) => r.accounting).filter(Boolean);
      const metrics = [
        ["Houdini 已返回调用", entries.length],
        [
          "调用含动词",
          entries.filter((e) => e.verbs.length).length + " / " + entries.length,
        ],
        [
          "成功执行含动词 · " +
            (successful.length
              ? Math.round((withVerbs * 1000) / successful.length) / 10
              : 0) +
            "%",
          withVerbs + " / " + successful.length,
        ],
        [
          "无动词只读探针",
          entries.filter((e) => !e.verbs.length && e.rawMode === "read_only")
            .length,
        ],
        ["Raw Gate 拦截", entries.filter((e) => e.gateBlocked).length],
        ["回滚调用", entries.filter((e) => e.rollbackApplied).length],
        [
          "目录广度（当前包）",
          knownVerbs.filter((v) => distinctVerbs.has(v)).length +
            " / " +
            knownVerbs.length,
        ],
        [
          "动词密度（每次Houdini调用）",
          entries.length ? (verbCount / entries.length).toFixed(2) : "—",
        ],
        [
          "回滚动作工作量",
          entries
            .filter((e) => e.rollbackApplied)
            .reduce((n, e) => n + e.verbs.filter((v) => v.ok).length, 0),
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
          "含动词率描述调用形态，不代表场景修改成功率或任务完成度；展开调用核对事务和实际证据。",
        ),
        h("h4", null, "模型请求 usage · 请求去重"),
        accounts.length
          ? table(
              ["已报告 / 已加载请求", "输入合计", "输出合计"],
              [
                [
                  accounts.length + " / " + data.requests.length,
                  format(accounts.reduce((n, u) => n + u.input, 0)),
                  format(accounts.reduce((n, u) => n + u.output, 0)),
                ],
              ],
            )
          : note("请求 usage 未采集。"),
        note(
          "包含已加载的 assistant / compaction 请求；缺失 usage 不按0补齐。输入合并 DSH 的未缓存和缓存分桶。",
        ),
        h("h4", null, "失败、拦截与回滚"),
        data.entries
          .filter((e) => e.failed || e.rollbackApplied)
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
        h("h4", null, "低层执行分类"),
        table(
          ["分类", "调用数"],
          [
            "read_only",
            "blocked",
            "exempted",
            "gate_disabled",
            "legacy_bypass",
            "mutation",
          ].map((mode) => [
            mode,
            String(entries.filter((e) => e.rawMode === mode).length),
          ]),
        ),
        note(
          "只读 HOM、Gate拦截、豁免、成功低层修改必须分开核对；原始语法探测不独自证明发生修改。",
        ),
      );
    }
    const pending = data.entries.filter((e) => e.pending);
    const recent = data.nodes.reduce((max, n) => Math.max(max, n.time || 0), 0);
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
        pending.length
          ? "快照中 " + pending.length + " 个调用执行中"
          : data.partial
            ? "模型正在输出（最后快照）"
            : "已加载 " +
              data.entries.length +
              " 个调用；当前运行状态以 Host 为准",
        " · 最近记录 " + stamp(recent || null),
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
  return View;
});
    // <<< houdini-trace

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
      var marker = /(?:^|\n\n)(stdout|stderr|__result__|rollback|transaction|operation-evidence|raw-usage|hint|verbs \(\d+\)|media(?: [^\n:]*)?):\n/g;
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
      var canonical = node.meta && node.meta.canonical;
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
          return {verb:v.verb,ok:v.ok,argsText:JSON.stringify(v.args) +
            (v.kwargs && Object.keys(v.kwargs).length ? ", " + JSON.stringify(v.kwargs) : ""),
            detail:JSON.stringify(v.result),ms:v.ms};
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
      else if (args.result_ref) info.summary = "已读取历史工具返回；未执行HOM，不代表当前场景状态。";
      else if (args.review) info.summary = "独立资产评审已返回；查看报告与未验证边界。";
      else if (args.review_test) info.summary = "受控评审实验；查看本批测量、图片与恢复结果。";
      else if (info.rawMode === "exempted") info.summary = "低层修改通过一次性豁免执行；理由已记录。";
      else if (info.verbs.length && info.rawMode === "read_only") info.summary = info.verbs.length + " 个动词已提交，同时进行了只读 HOM 检查。";
      else if (info.verbs.length) info.summary = info.verbs.length + " 个动词已提交。";
      else if (info.rawMode === "read_only") info.summary = "只读 HOM 探针；没有检测到场景修改。";
      else info.summary = "调用已完成，没有记录动词。";
      return info;
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
          createTraceView(React, CATALOG, TRACE_SOURCES, parseEntry, TRACE_CSS)
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
