// dsh-houdini client half — registers two things:
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
    var CATALOG = [{"domain":"vocabulary 域","note":"vocabulary 域（回答「动词怎么调用」）","verbs":[{"name":"verb_help","sig":"name","desc":"返回已注入动词的准确 signature 与 docstring；未知名列相似项。用于在调用前发现契约，不靠失败或读取仓库源码猜参数/返回形状"}]},{"domain":"类型目录","note":"类型目录（回答「能建什么」）","verbs":[{"name":"search_tab_menu","sig":"category, query","desc":"列出某 context 下匹配的节点族 + 最新版"},{"name":"resolve_latest_type","sig":"category, base","desc":"某族最新版全名（内部为主）"}]},{"domain":"node 域","note":"node 域（场景图）","verbs":[{"name":"tab_create","sig":"parent, type_name, name=, inputs=[...]","desc":"建节点：最新版 + shelf 初始化；parent 接受 `hou.Node` 或 path 字符串"},{"name":"find_nodes","sig":"pattern=\"*\", category=None, node_type=None, root=None","desc":"找**已存在**节点（扁平清单）"},{"name":"graph","sig":"node, depth=1, direction='both'","desc":"围绕**该数据节点**查 inputs / outputs / parm_refs；检查最终 SOP 网络应对 `OUT` 向上查，不要对父 OBJ 容器调用"},{"name":"describe","sig":"node","desc":"状态 + 几何摘要 + `attrib_delta`（相对 input 0 的属性增删——MMB 节点信息里「这个节点对数据干了什么」的固化）+ 帮助元数据"},{"name":"connect","sig":"src, dst, index=0","desc":"连线（src 输出 → dst 输入）；落口与请求不一致时返回里带 `note`"},{"name":"rename_node","sig":"node, name","desc":"重命名"},{"name":"delete_node","sig":"node","desc":"删除（返回被表达式引用的上游）"},{"name":"cook_node","sig":"node, force=False","desc":"cook + error/warning；另给 `ok/warning_free/healthy`，warning 未解释不得当完成"},{"name":"sop_set_output","sig":"node, render=True","desc":"把 SOP singular display/render 旗标移到输出节点；属于用户 viewport/交付状态，不是 render_view 前置条件"},{"name":"sop_output_node","sig":"parent","desc":"报告 SOP 网络 display/render 输出；旗标不在链尾时提醒"},{"name":"set_object_visible","sig":"node, visible=True","desc":"设置单个 OBJ 的 viewport visibility（OBJ 没有 SOP 式 render flag）"},{"name":"visible_objects","sig":"root='/obj'","desc":"列出 OBJ 层 plural visibility/effective visibility"},{"name":"layout_nodes","sig":"parent, nodes=None, horizontal_spacing=-1, vertical_spacing=-1","desc":"用 Houdini 原生 layoutChildren 布局全部或指定网络项"}]},{"domain":"compatibility 域","note":"compatibility 域（仅历史回放，不进新 guidance）","verbs":[{"name":"set_display","sig":"node, render=True","desc":"deprecated 兼容 wrapper：按节点 context 路由 SOP output / OBJ visibility"},{"name":"display_node","sig":"parent","desc":"deprecated 兼容 wrapper：按父网络 context 路由 SOP output / OBJ visibility"}]},{"domain":"parm 域","note":"parm 域（依附 node）","verbs":[{"name":"list_parms","sig":"node","desc":"参数**目录**：名字/标签/类型/帮助（导航用，不给值）"},{"name":"read_parms","sig":"node, changed_only=True","desc":"参数**值**：默认只看非默认 + 带表达式 + 被引用的（意图解读）；表达式参数附 `referenced_parm`，被引用参数标 `referenced_by`"},{"name":"set_parm","sig":"node, name, value","desc":"设参（数值参数收到字符串 = 设表达式；失败列相似名，自纠）。参数上有表达式/关键帧时**自动清除再设值**，返回带 `note` 说明清掉了什么（2026-08-20 起，OTL 会话 seq 28944：`$FEND` 表达式把 set 静默架空）；想保留动画就请显式用字符串表达式"},{"name":"set_parms","sig":"node, values","desc":"批量设参：`{name: value}` 字典逐项走 `set_parm` 同一套语义，**逐项容错**——单项失败不中断，返回分 `set`/`failed` 两组（消灭循环裸 `parm().set` 的 advisory 噪音）"},{"name":"create_spare_parms","sig":"node, code_parm='snippet', defaults=None","desc":"扫描代码参数的 `ch/chf/chi/chv/chs` 引用，声明式创建缺失 spare parameters 并应用显式默认值；复杂 `chramp` 等列 unsupported。修复「Wrangle 引用了 amp/speed 但参数不存在，ch() 全为 0、动画静止」"}]},{"domain":"scene 域","note":"scene 域（工程/时间线）","verbs":[{"name":"scene_info","sig":"","desc":"只读 HIP/version/fps/current frame/time/frame range/playback range/UI 状态；不移动 playbar、不遍历整张节点图"},{"name":"set_timeline","sig":"fps=None, frame_range=None, playback_range=None, current_frame=None","desc":"设置明确的时间线字段；至少一项，范围校验后回读 scene_info"},{"name":"list_bookmarks","sig":"","desc":"列出 bookmark id/name/start/end/enabled/visible/comment"},{"name":"create_bookmark","sig":"name, start, end, replace=False","desc":"创建整数帧 bookmark；同名默认拒绝，replace 精确替换"},{"name":"delete_bookmark","sig":"name_or_id","desc":"按精确名称或 session id 删除，失败列现有项"}]},{"domain":"geometry 域","note":"geometry 域（几何数据）","verbs":[{"name":"geo_attrib_stats","sig":"node, name, attrib_class='point'","desc":"属性**值**统计：min/max/mean/count（`describe` 只给属性名清单）；point/prim/vertex/detail，多分量按分量给"},{"name":"geo_piece_stats","sig":"node, piece_attrib=None, sample=16","desc":"primitive piece 的局部 bbox/extent/面积与退化统计；无 piece 属性时用内存 Connectivity SOP Verb，不污染网络，能发现「全场 bbox 正常但每个实例零宽/零面积」"},{"name":"geo_frame_diff","sig":"node, frame_a, frame_b, attrib='P', sample=4096, tolerance=1e-6","desc":"用 geometryAtFrame 比较两帧 point 数值属性，返回 mean/max、p50/p90/p99、逐分量位移与 unchanged%；不移动用户 playbar。证明数据是否随时间变化，不单独证明审美/运动语义"}]},{"domain":"asset 域","note":"asset 域（HDA / 数字资产，2026-08-20 落地）","verbs":[{"name":"hda_create","sig":"node, name, description=None, hda_file=None, min_inputs=0, max_inputs=0, replace=False","desc":"把已有节点（通常 subnet）转为数字资产：自动建 otls 目录、默认 `$HIP/otls/<name>.hda`。`replace=True` = 整体重建：销毁该类型的全部现有实例 + 卸载旧定义 + 覆盖文件（返回里列出被销毁的实例路径）；否则同名冲突报错并提示 replace"},{"name":"hda_info","sig":"node, max_depth=6","desc":"资产/参数界面**只读自省**：类型名、定义文件、section 清单、参数模板树（名字/标签/类型/conditional/tags/嵌套 folder 递归）——替代手写 walk()（会话里重复写了 3 次）。普通节点也可用（只有 parm 树，无 section）"},{"name":"hda_get_section","sig":"node, section='PythonModule'","desc":"读 HDA section 内容；section 不存在时列出现有 section 名供自纠"},{"name":"hda_set_section","sig":"node, section, code","desc":"全量写 section。`PythonModule` 先 `compile()` 预检语法（带行号报错，不写脏）；写后读回校验一致"},{"name":"hda_patch_section","sig":"node, section, old, new, count=1","desc":"锚点局部替换：`old` 必须恰好出现 `count` 次（0 = 锚点没找到，>count = 锚点不唯一需加长），替换后同样过语法预检；**模块改局部时用它，不要全文重发**"},{"name":"hda_set_interface","sig":"node, spec, keep_std=True, hide_builtin_tabs=False","desc":"**声明式参数面板**（已拍板：整组重建语义，非 merge）：`spec` 是条目列表（folder/separator/toggle/int/float/string/button/menu），重建自定义参数组；subnet HDA 的 Transform/Subnet 标准页从 Houdini 原生 subnet 类型重新取得，避免夹带旧自定义参数。`hide_when` 字段写 conditional，**提交后读回验证**——被 `setParmTemplateGroup` 吞掉就自动改走 DialogScript `hidewhen` 补丁兜底（seq 124609 的教训）；folder 上设 `hide_when` 直接报错（Houdini 不支持，seq 98973 实测）。`hide_builtin_tabs=True` 通过公开 `ParmTemplateGroup.hide` 生成 `invisibletab` 隐藏标准页"}]},{"domain":"render / sim 域","note":"render / sim 域（渲染产物）","verbs":[{"name":"render_frame","sig":"rop, picture=None, frame=None, timeout=110","desc":"渲染单帧并验证产物；调用期间切到目标帧、结束/失败后恢复用户原 frame。>110s 走 job"},{"name":"render_view","sig":"node, direction='iso', frame=None, width=1280, height=720, picture=None, framing='full', coverage=0.82, framing_frame=None","desc":"**视觉验证主干 v2**：显式 SOP → agent-owned Object Merge proxy → agent camera/OpenGL ROP `forceobjects` 只渲染 proxy；不依赖/不改变用户 SOP output、OBJ visibility、selection、viewport 或 frame。传 OBJ 时只在调用开始解析一次 SOP并提醒。preflight 拒绝空/error 几何；返回 source fingerprint 前后、`stale`、eye/direction、ROP 设置和 render_check。动画 A/B 给所有调用传相同 `framing_frame`，用同一 bbox 锁定相机；空闲 proxy 清空真实引用但保留 last-target/frame/output userData 与解释 comment"},{"name":"render_check","sig":"path, ref=None","desc":"亮度/非黑/主色/content bbox；A/B 另给高精度 mean、RMSE、changed/meaningful pixel %、max diff，微小非零不再被舍入成 0"}]},{"domain":"viewport 域","note":"viewport 域（视口/UI）","verbs":[{"name":"viewport_screenshot","sig":"path=None, frame=None, clean=True, frame_target=None, textures=None, backface_cull=False","desc":"**用户屏幕诊断工具**：用户切空 display 节点时截到空是正确结果，不能用来证明 agent 产物；和 `render_view(explicit_sop)` 对照可区分 viewport 漂移与真实几何错误。flipbook 异步，设置/相机在落盘后恢复"}]}];
    // <<< houdini-catalog

    // --- houdinitrace 视图样式与解析 ------------------------------------------
    var monoFont = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
    var dimColor = "var(--dsw-alias-label-secondary, #999)";
    var borderColor = "var(--dsw-alias-border-l2, #333)";
    var rootStyle = {
      display: "flex", flexDirection: "column", gap: "10px",
      padding: "14px 16px", height: "100%", boxSizing: "border-box",
      overflow: "hidden", color: "var(--dsw-alias-label-primary, #e8e8e8)",
    };
    var statsStyle = {
      border: "1px solid " + borderColor, borderRadius: "8px", padding: "8px 12px",
      background: "var(--dsw-alias-bg-layer-2, #1b1b1b)", fontSize: "12px",
      fontWeight: "600", flexShrink: "0",
    };
    var bodyStyle = { display: "flex", gap: "12px", flex: "1", minHeight: "0" };
    var catalogColStyle = {
      width: "272px", flexShrink: "0", overflowY: "auto",
      border: "1px solid " + borderColor, borderRadius: "8px",
      background: "var(--dsw-alias-bg-layer-2, #1b1b1b)", padding: "8px 10px",
    };
    var timelineColStyle = {
      flex: "1", minWidth: "0", overflowY: "auto",
      display: "flex", flexDirection: "column", gap: "8px", paddingRight: "2px",
    };
    var domainStyle = { marginBottom: "10px" };
    var domainNameStyle = {
      fontWeight: "700", fontSize: "12px",
      color: "var(--dsw-alias-label-brand, #5b9dff)", marginBottom: "4px",
    };
    var catVerbStyle = {
      display: "flex", alignItems: "baseline", gap: "6px",
      padding: "3px 2px", borderTop: "1px dashed " + borderColor, fontSize: "12px",
    };
    var catVerbNameStyle = { fontFamily: monoFont, fontWeight: "600" };
    var catSigStyle = {
      fontFamily: monoFont, fontSize: "10px", color: dimColor,
      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: "1",
    };
    var badgeBase = { flexShrink: "0", fontSize: "10px", borderRadius: "4px", padding: "0 5px", border: "1px solid" };
    var badgeUsed = { color: "#7fd68f", borderColor: "#7fd68f" };
    var badgeUnused = { color: dimColor, borderColor: borderColor };
    var entryStyle = {
      border: "1px solid " + borderColor, borderRadius: "8px", padding: "8px 12px",
      background: "var(--dsw-alias-bg-layer-2, #1b1b1b)", flexShrink: "0",
    };
    var entryFailedStyle = Object.assign({}, entryStyle, { borderColor: "#e06c75" });
    var entryHeadStyle = { display: "flex", alignItems: "center", flexWrap: "wrap", gap: "6px", fontSize: "12px" };
    var timeStyle = { fontFamily: monoFont, fontWeight: "700", color: "var(--dsw-alias-label-brand, #5b9dff)" };
    var seqStyle = { color: dimColor, fontSize: "11px" };
    var toolChipStyle = {
      fontFamily: monoFont, fontSize: "11px", background: "#2c3a2e",
      color: "#a6d189", borderRadius: "4px", padding: "1px 7px",
    };
    var chipBase = { fontSize: "10px", borderRadius: "4px", padding: "0 6px", border: "1px solid" };
    var chipOk = { color: "#7fd68f", borderColor: "#7fd68f" };
    var chipWarn = { color: "#e0a458", borderColor: "#e0a458" };
    var chipBad = { color: "#e06c75", borderColor: "#e06c75" };
    var verbChipStyle = {
      fontFamily: monoFont, fontSize: "11px", background: "#2b3049",
      color: "#c6d0f5", borderRadius: "4px", padding: "1px 7px",
    };
    var verbChipFailStyle = {
      fontFamily: monoFont, fontSize: "11px", background: "#4a2b2b",
      color: "#f0a8a8", borderRadius: "4px", padding: "1px 7px",
    };
    var msStyle = { color: dimColor };
    var summaryStyle = { cursor: "pointer", color: dimColor, fontSize: "11px" };
    var preStyle = {
      margin: "6px 0 0", fontFamily: monoFont, fontSize: "11px", lineHeight: 1.5,
      whiteSpace: "pre-wrap", wordBreak: "break-word",
      background: "var(--dsw-alias-bg-layer-1, #17181b)",
      border: "1px solid " + borderColor, borderRadius: "6px", padding: "6px 8px",
      maxHeight: "300px", overflow: "auto",
    };
    var hintPreStyle = Object.assign({}, preStyle, { color: "#e0a458" });
    var emptyStyle = { color: dimColor, padding: "24px", textAlign: "center" };

    // `verbs (N):` 块里的一行（host renderVerbs 的渲染格式）：
    // `i. [ok|FAIL] verb(args, kwargs) -> detail (Xms)`
    var VERB_LINE = /^(\d+)\. \[(ok|FAIL)\] (\w+)\((.*)\) -> (.*) \(([\d.]+)ms\)\s*$/;

    // 把一个 tool-result 节点拆成视图要的全部字段。
    function parseEntry(node) {
      var call = node.call || {};
      var args = {};
      try { args = JSON.parse(call.argsRaw || "{}"); } catch (e) { /* 非 JSON */ }
      var text = "";
      var blocks = node.content || [];
      for (var j = 0; j < blocks.length; j++) {
        var b = blocks[j];
        if (b && b.type === "text" && typeof b.text === "string") text += b.text + "\n";
      }
      text = text.replace(/\n+$/, "");
      var info = {
        key: String(node.seq),
        time: node.time || node.callTime || null,
        name: typeof call.name === "string" ? call.name : "?",
        code: typeof args.code === "string" ? args.code : null,
        houCalls: 0,
        verbs: [],
        hint: null,
        failed: text.indexOf("Execution failed") === 0,
        text: text,
      };
      if (info.code) info.houCalls = (info.code.match(/\bhou\.\w+\(/g) || []).length;
      var sections = text.split("\n\n");
      for (var i = 0; i < sections.length; i++) {
        var s = sections[i];
        if (s.indexOf("verbs (") === 0) {
          var lines = s.split("\n");
          for (var k = 1; k < lines.length; k++) {
            var m = VERB_LINE.exec(lines[k]);
            if (m) {
              info.verbs.push({ verb: m[3], ok: m[2] === "ok", argsText: m[4], detail: m[5], ms: m[6] });
            }
          }
        } else if (s.indexOf("hint:") === 0) {
          info.hint = s.slice("hint:".length).trim();
        }
      }
      return info;
    }

    function pad2(n) { return (n < 10 ? "0" : "") + n; }
    function fmtTime(ms) {
      if (!ms) return "--:--:--";
      var d = new Date(ms);
      return pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" + pad2(d.getSeconds());
    }

    function apply(ctx) {
      var slots = ctx.get("slots");
      if (slots === undefined) return;

      slots.inject("conversation.view", function () {
        return slots.register(
          { name: "conversation.view", id: "houdinitrace", order: 5, label: "Houdini Trace" },
          function HoudiniTraceView(props) {
            var nodes = props.useSession(function (s) { return s.nodes; });
            var list = nodes || [];
            var entries = [];
            var usedMap = {};
            var totalVerbCalls = 0;
            var withHint = 0;
            var failedCount = 0;
            var rawCount = 0;
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
              if (info.hint) withHint++;
              if (info.failed) failedCount++;
              if (info.houCalls > 0 && info.verbs.length === 0) rawCount++;
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
                        React.createElement("span", { style: catVerbNameStyle }, verb.name),
                        React.createElement("span", { style: catSigStyle }, verb.sig),
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
                if (e.failed) badges.push(React.createElement("span", { key: "f", style: Object.assign({}, chipBase, chipBad) }, "失败"));
                if (e.houCalls > 0) badges.push(React.createElement("span", { key: "h", style: Object.assign({}, chipBase, e.verbs.length ? chipWarn : chipBad) }, "裸 hou ×" + e.houCalls));
                if (e.hint) badges.push(React.createElement("span", { key: "a", style: Object.assign({}, chipBase, chipWarn) }, "advisory"));
                if (e.verbs.length) badges.push(React.createElement("span", { key: "v", style: Object.assign({}, chipBase, chipOk) }, "动词 ×" + e.verbs.length));
                var chips = [];
                for (var c = 0; c < e.verbs.length; c++) {
                  (function (vb, ci) {
                    chips.push(
                      React.createElement(
                        "span",
                        { key: "c" + ci, style: vb.ok ? verbChipStyle : verbChipFailStyle, title: vb.argsText + " -> " + vb.detail },
                        vb.verb + " ",
                        React.createElement("span", { style: msStyle }, vb.ms + "ms")
                      )
                    );
                  })(e.verbs[c], c);
                }
                var detailChildren = [];
                if (e.code) detailChildren.push(React.createElement("pre", { key: "code", style: preStyle }, e.code));
                if (e.hint) detailChildren.push(React.createElement("pre", { key: "hint", style: hintPreStyle }, "hint:\n" + e.hint));
                detailChildren.push(React.createElement("pre", { key: "res", style: preStyle }, e.text || "(no output)"));
                timelineChildren.push(
                  React.createElement(
                    "div",
                    { key: e.key, style: e.failed ? entryFailedStyle : entryStyle },
                    React.createElement(
                      "div",
                      { style: entryHeadStyle },
                      React.createElement("span", { style: timeStyle }, fmtTime(e.time)),
                      React.createElement("span", { style: seqStyle }, "#" + idx),
                      React.createElement("span", { style: toolChipStyle }, e.name),
                      badges,
                      chips
                    ),
                    React.createElement(
                      "details",
                      { style: { marginTop: "4px" } },
                      React.createElement("summary", { style: summaryStyle }, "详情"),
                      detailChildren
                    )
                  )
                );
              })(entries[k], k + 1);
            }

            var statsText =
              entries.length + " houdini 调用 · " + totalVerbCalls + " 动词调用 · 命中 " +
              distinctUsed + "/" + catalogTotal + " · 纯裸 hou " + rawCount +
              " · 失败 " + failedCount + " · advisory " + withHint;

            return React.createElement(
              "div",
              { style: rootStyle },
              React.createElement("div", { style: statsStyle }, statsText),
              React.createElement(
                "div",
                { style: bodyStyle },
                React.createElement("div", { style: catalogColStyle }, catalogChildren),
                React.createElement("div", { style: timelineColStyle }, timelineChildren)
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
