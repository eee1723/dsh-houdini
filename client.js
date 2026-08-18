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
    var CATALOG = [{"domain":"类型目录","note":"类型目录（回答「能建什么」）","verbs":[{"name":"search_tab_menu","sig":"category, query","desc":"列出某 context 下匹配的节点族 + 最新版"},{"name":"resolve_latest_type","sig":"category, base","desc":"某族最新版全名（内部为主）"}]},{"domain":"node 域","note":"node 域（场景图）","verbs":[{"name":"tab_create","sig":"parent, type_name, name=, inputs=[...]","desc":"建节点：最新版 + shelf 初始化"},{"name":"find_nodes","sig":"pattern=\"*\", category=None, node_type=None, root=None","desc":"找**已存在**节点（扁平清单）"},{"name":"graph","sig":"node, depth=1, direction='both'","desc":"拓扑：inputs / outputs / parm_refs"},{"name":"describe","sig":"node","desc":"状态 + 几何摘要 + 帮助元数据"},{"name":"connect","sig":"src, dst, index=0","desc":"连线（src 输出 → dst 输入）；落口与请求不一致时返回里带 `note`"},{"name":"rename_node","sig":"node, name","desc":"重命名"},{"name":"delete_node","sig":"node","desc":"删除（返回被表达式引用的上游）"},{"name":"cook_node","sig":"node","desc":"cook + 采集 error/warning"},{"name":"set_display","sig":"node, render=True","desc":"把 display（默认连同 render）旗标移到指定节点——视口/渲染只认旗标节点"},{"name":"display_node","sig":"parent","desc":"报告旗标当前挂在哪个节点；旗标不在链尾时带 `note` 提醒"}]},{"domain":"parm 域","note":"parm 域（依附 node）","verbs":[{"name":"list_parms","sig":"node","desc":"参数**目录**：名字/标签/类型/帮助（导航用，不给值）"},{"name":"read_parms","sig":"node, changed_only=True","desc":"参数**值**：默认只看非默认 + 带表达式 + 被引用的（意图解读）；表达式参数附 `referenced_parm`，被引用参数标 `referenced_by`"},{"name":"set_parm","sig":"node, name, value","desc":"设参（数值参数收到字符串 = 设表达式；失败列相似名，自纠）"}]},{"domain":"geometry 域","note":"geometry 域（几何数据）","verbs":[{"name":"geo_attrib_stats","sig":"node, name, attrib_class='point'","desc":"属性**值**统计：min/max/mean/count（`describe` 只给属性名清单）；point/prim/vertex/detail，多分量按分量给"}]},{"domain":"render / sim 域","note":"render / sim 域（渲染产物）","verbs":[{"name":"render_frame","sig":"rop, picture=None, frame=None, timeout=110","desc":"渲染单帧并**验证产物**：输出参数按常见名自动解析（picture/vm_picture/sopoutput…），等文件落盘非空，采集 ROP 错误；`render()` 不报错 ≠ 产物存在。>110s 的渲染走 job 通道"},{"name":"render_check","sig":"path, ref=None","desc":"渲染产物**客观验证**（无视觉模型的盲验）：亮度统计/非黑像素占比/主色/内容 bbox；传 ref 算两图 diff（循环帧一致性、A/B 对比）。QImage 解码，hython 退回纯 Python PNG"}]},{"domain":"viewport 域","note":"viewport 域（视口/UI）","verbs":[{"name":"viewport_screenshot","sig":"path=None, frame=None, clean=True, frame_target=None, textures=None, backface_cull=False","desc":"抓当前场景视口截图（所见即所得，走 SceneViewer flipbook 单帧通道，**异步**——还原设置必须等产物落盘后）；GUI 限定，headless 抛错指向 `render_frame`。`clean` 隐藏视口装饰（地面参考网格走 `SceneViewer.referencePlane().setIsVisible(False)`——它**不是** viewportGuide 枚举；外加坐标指示器/手柄/标签/遮幅/HUD，见 `_CLEAN_GUIDES`）；`frame_target` 取景到节点显示几何 bbox，**也接受 `True`** = 「/obj 下当前挂 display 旗标的对象」（agent 直觉写法，2026-08-18 trace 实测）；`textures=False` 临时关纹理（UV 贴图不入镜）；`backface_cull=True` 临时背面剔除。收尾自动还原被最小化的内嵌 web UI 窗口（`_restore_webview_window`，仅 isMinimized 时才动）。截图前先用 `display_node` 核对旗标"}]}];
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
