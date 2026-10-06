// Handwritten factory embedded by tools/gen-trace-client.mjs.
// DSH owns history, Session lifetime and the completed-Turn slot. This module
// projects only declared execution facts; node addresses remain Host-owned.
function createNodeDelivery(React, readHoudiniCanonical) {
  var KIND = "houdini-node-delivery";
  var TARGET = "houdini-node-deliveries";
  var MARKER = "houdini/node-delivery-v1";

  function rootCall(event) {
    var data = event && event.data;
    if (!data) return null;
    if (event.type === "tool/call") return data.callId;
    if (event.type === "tool/result" && event.surfaceOp === "append") return data.message && data.message.source && data.message.source.callId;
    if (event.type === "tool/ptc-dispatch") return data.rootCallId;
    return null;
  }

  function project(state, match) {
    var event = match.event, data = event.data;
    if (event.type === "tool/call") return { callName: data.name, nodes: state.nodes };
    var nested = event.type === "tool/ptc-dispatch";
    var message = nested ? data : data.message;
    if (!message || message.isError === true) return state;
    var callId = nested ? data.subCallId : message.source && message.source.callId;
    var canonical = readHoudiniCanonical({
      callId: callId,
      call: { name: nested ? data.name : state.callName },
      meta: nested ? undefined : data.meta,
      content: nested ? data.content : []
    });
    var result = canonical && canonical.result, execution = canonical && canonical.execution;
    if (!canonical || canonical.ok !== true || !result || result.kind !== MARKER || !Array.isArray(result.nodes) || !execution ||
        Number(canonical.outcome && canonical.outcome.operations && canonical.outcome.operations.failed) > 0 ||
        Array.isArray(canonical.verbs) && canonical.verbs.some(function (verb) { return verb && verb.ok === false; })) return state;
    if (![execution.executor_id, execution.runtime_id].every(function (value) { return typeof value === "string" && /^[0-9a-f]{32}$/.test(value); }) ||
        ![execution.hip_path, execution.owner_session].every(function (value) { return typeof value === "string" && value.trim().length > 0; }) || execution.hip_is_new === true) return state;
    var nodes = [];
    result.nodes.forEach(function (node, index) {
      if (!node || typeof node.id !== "string" || !/^[0-9a-f]{32}$/.test(node.id) || typeof node.path !== "string" || node.path.charAt(0) !== "/" ||
          typeof node.label !== "string" || !node.label.trim() || typeof node.type !== "string" || !node.type.trim() ||
          ["control", "output", "node"].indexOf(node.role) < 0) return;
      nodes.push({ id: node.id, path: node.path, label: node.label, type: node.type, role: node.role,
        description: typeof node.description === "string" ? node.description : null,
        context: typeof node.context === "string" ? node.context : null,
        eventSeq: event.seq, index: index, callId: callId, execution: execution });
    });
    return nodes.length ? { callName: state.callName, nodes: state.nodes.concat(nodes) } : state;
  }

  // Native results and nested PTC dispatches share the root call's Context.
  // PTC events have no turn field; DSH supplies their actual resolved Location.
  var definition = {
    kind: KIND,
    target: TARGET,
    match: function (event) {
      var id = rootCall(event);
      return typeof id === "string" && id ? { id: id, role: "start" } : null;
    },
    start: function (_context, match) { return project({ callName: null, nodes: [] }, match); },
    update: function (context, match) { return project(context.state, match); },
    buildViewNode: function (context) {
      if (!context.state || !context.state.nodes.length || !context.start) return null;
      var location = context.start.location;
      if (location.kind !== "turn" && location.kind !== "step") return null;
      return { key: context.key, kind: KIND, id: context.id, target: TARGET,
        data: { turn: location.turn.turn, nodes: context.state.nodes } };
    }
  };

  var view = {
    target: TARGET,
    create: function () {
      var byCall = new Map(), snapshot = { calls: [] };
      function publish() {
        snapshot = { calls: Array.from(byCall.values()) };
        return snapshot;
      }
      return {
        empty: snapshot,
        replace: function (input) {
          byCall = new Map(input.nodes.map(function (node) { return [node.key, node.data]; }));
          return publish();
        },
        apply: function (input) {
          input.upserts.forEach(function (node) { byCall.set(node.key, node.data); });
          return publish();
        }
      };
    }
  };

  function forClosing(snapshot, owner) {
    var observed = [];
    (snapshot && snapshot.calls || []).forEach(function (call) {
      if (call.turn === owner.turn.turn) call.nodes.forEach(function (node) {
        if (node.eventSeq < owner.seq && node.execution.owner_session === owner.sessionId) observed.push(node);
      });
    });
    observed.sort(function (a, b) { return a.eventSeq - b.eventSeq || a.index - b.index; });
    var latest = new Map();
    observed.forEach(function (node) {
      latest.set(JSON.stringify([node.execution.executor_id, node.execution.hip_path, node.id]), node);
    });
    return Array.from(latest.values());
  }

  // These selectors own only this contribution. DSH's file cards and native
  // opening controls keep their own public slots, lifecycle and presentation.
  var fileScope = '[data-conversation-content]:has([data-houdini-workspace])';
  var cardSurface = 'box-sizing:border-box;width:100%;max-width:480px;border:1px solid transparent;border-radius:9px;background:linear-gradient(155deg,#2b2d2f,#232527) padding-box,linear-gradient(155deg,#565a5d,#383b3e 48%,#45484a) border-box;background-color:#252729;box-shadow:inset 0 1px 0 #ffffff05,0 2px 5px #00000012;color:#e9e9e6';
  var cardHover = 'background:linear-gradient(155deg,#303234,#27292b) padding-box,linear-gradient(155deg,#8b7561,#50504c 48%,#595149) border-box;background-color:#252729;box-shadow:inset 0 1px 0 #ffffff08,0 3px 8px #0000001a';
  var css =
    // rc.2 emits these semantic surfaces. Keep its file preview, native app
    // controls, status/error and grid behavior; only the appearance is shared.
    fileScope + ' [data-presented-file]{--deliverable-fill:#252729;--deliverable-hover:#2d3032;--dsw-alias-link:#e69a51;--dsw-alias-label-primary:#e9e9e6;--dsw-alias-label-secondary:#c4c7c9;--dsw-alias-label-tertiary:#a5a9ab;--dsw-alias-bg-layer-1:#252729;--dsw-alias-bg-layer-2:#303336;--dsw-alias-bg-layer-3:#35383b;--dsw-alias-border-l1:#494c4f;--dsw-alias-border-l2:#414548;min-height:56px;height:auto;padding:8px 10px;gap:10px;' + cardSurface + '}' +
    fileScope + ' [data-presented-file]:hover{' + cardHover + '}' +
    fileScope + ' [data-presented-file] [data-presented-description]:not([data-error]){color:#b0b4b7;font-size:11px;line-height:16px}' +
    '.dsh-houdini-node-card{--node-card-accent:#e69a51;position:relative;min-width:0;overflow:hidden;' + cardSurface + '}' +
    '.dsh-houdini-node-card:hover{' + cardHover + '}' +
    '.dsh-houdini-node-open{box-sizing:border-box;display:flex;align-items:center;gap:9px;width:calc(100% - 36px);min-width:0;min-height:56px;padding:9px 0 9px 11px;border:0;background:transparent;color:inherit;text-align:left;font:inherit;cursor:pointer}' +
    '.dsh-houdini-node-open:focus-visible,.dsh-houdini-node-card summary:focus-visible{outline:2px solid var(--node-card-accent);outline-offset:-3px}' +
    '.dsh-houdini-node-open:disabled{cursor:default}' +
    '.dsh-houdini-node-open:disabled .dsh-houdini-node-action{opacity:.7}' +
    '.dsh-houdini-node-icon{box-sizing:border-box;display:flex;align-items:center;justify-content:center;flex:none;width:32px;height:32px;border:1px solid #ffffff12;border-radius:6px;background:linear-gradient(145deg,#383c3f,#2d3033);box-shadow:inset 0 1px 0 #ffffff05;color:var(--node-card-accent)}' +
    '.dsh-houdini-node-copy{flex:1 1 0;min-width:0}' +
    '.dsh-houdini-node-heading{display:block;min-width:0;line-height:18px}' +
    '.dsh-houdini-node-title{display:block;font-size:13px;font-weight:600;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}' +
    '.dsh-houdini-node-description{display:block;margin-top:1px;color:#b0b4b7;font-size:11px;line-height:16px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}' +
    '.dsh-houdini-node-action{display:flex;align-items:center;gap:5px;flex:none;margin-left:4px;color:#bfc4c7;font-size:11px;line-height:18px;white-space:nowrap}' +
    '.dsh-houdini-node-open:hover .dsh-houdini-node-action{color:var(--node-card-accent)}' +
    '.dsh-houdini-node-action[data-phase="opened"]{color:#adbfaf}' +
    '.dsh-houdini-node-card details{color:#9fa6aa;font-size:11px;line-height:18px}' +
    '.dsh-houdini-node-card summary{box-sizing:border-box;position:absolute;top:14px;right:6px;display:flex;align-items:center;justify-content:center;width:28px;height:28px;border:1px solid transparent;border-radius:5px;color:#90989d;cursor:pointer;user-select:none;list-style:none}' +
    '.dsh-houdini-node-card summary::-webkit-details-marker{display:none}' +
    '.dsh-houdini-node-card summary:hover,.dsh-houdini-node-card details[open] summary{border-color:#ffffff12;background:#ffffff06;color:#d9dde0}' +
    '.dsh-houdini-node-details{display:grid;grid-template-columns:58px minmax(0,1fr);column-gap:8px;row-gap:4px;margin:0 11px 10px;padding-top:9px;border-top:1px solid #ffffff0d}' +
    '.dsh-houdini-node-details code{color:#c4c7c9;overflow-wrap:anywhere;font:11px/18px Consolas,monospace}' +
    '.dsh-houdini-node-status{margin:0 11px 10px;padding-top:8px;border-top:1px solid #ffffff0d;color:#f2a29a;font-size:12px;line-height:19px;overflow-wrap:anywhere}' +
    '@media(max-width:440px){.dsh-houdini-node-open{gap:8px;padding-left:9px}.dsh-houdini-node-action{gap:3px;margin-left:0}.dsh-houdini-node-details,.dsh-houdini-node-status{margin-left:9px;margin-right:9px}}';

  function glyph(role) {
    var h = React.createElement;
    // Familiar network-node outline and visible input/output ports; the inner
    // mark describes the delivered role without depending on external icons.
    var mark = role === "control" ? [
      h("path", { key: "rails", d: "M10 11h12M10 16h12M10 21h12" }),
      h("path", { key: "knobs", d: "M14 9v4M19 14v4M13 19v4", strokeWidth: 2.6 })
    ] : role === "output" ? [
      h("path", { key: "shape", d: "m16 9 6 3.5v7L16 23l-6-3.5v-7L16 9Zm-6 3.5 6 3.5 6-3.5M16 16v7" })
    ] : [
      h("path", { key: "edit", d: "m11 20 1-4 7-7 4 4-7 7-5 1Zm7-10 4 4M11 24h12" })
    ];
    return h("svg", { width: 24, height: 28, viewBox: "0 0 32 36", fill: "none", "aria-hidden": true },
      h("path", { d: "M7 6h18l3 4-2 17H6L4 10l3-4Z", fill: "#3a3e41", stroke: "#969d9f", strokeWidth: 1.2 }),
      h("circle", { cx: 12, cy: 3, r: 1.6, fill: "#92999c" }),
      h("circle", { cx: 20, cy: 3, r: 1.6, fill: "#92999c" }),
      h("path", { d: "M16 28v4", stroke: "#92999c", strokeWidth: 1.2 }),
      h("circle", { cx: 16, cy: 33, r: 1.7, fill: "currentColor" }),
      h("g", { stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round" }, mark));
  }

  function createTail(connection, uiConversation) {
    function NodeCard(props) {
      var node = props.node;
      var hostGeneration = React.useSyncExternalStore(connection.generation.subscribe, connection.generation.getSnapshot);
      var pair = React.useState({ phase: "idle", message: "" }), status = pair[0], setStatus = pair[1];
      var pending = React.useRef(null), revision = React.useRef(0), current = React.useRef(null);
      var address = JSON.stringify([props.sessionId, node.eventSeq, node.index, node.callId]);
      current.current = { address: address, generation: hostGeneration };
      React.useEffect(function () {
        revision.current++;
        if (pending.current) pending.current.abort();
        pending.current = null;
        setStatus({ phase: "idle", message: "" });
        return function () {
          revision.current++;
          if (pending.current) pending.current.abort();
          pending.current = null;
        };
      }, [address, hostGeneration]);
      React.useEffect(function () {
        if (status.phase !== "opened") return;
        // A completed navigation is a brief acknowledgement, not a claim
        // that this node remains selected while the user works elsewhere.
        var acknowledgement = setTimeout(function () { setStatus({ phase: "idle", message: "" }); }, 2400);
        return function () { clearTimeout(acknowledgement); };
      }, [status.phase, address, hostGeneration]);
      async function open() {
        if (pending.current || !hostGeneration || current.current.address !== address || current.current.generation !== hostGeneration) return;
        var ticket = ++revision.current, controller = new AbortController();
        pending.current = controller;
        var timeout = setTimeout(function () { controller.abort(); }, 10000);
        var active = function () {
          return revision.current === ticket && current.current.address === address && current.current.generation === hostGeneration &&
            connection.generation.getSnapshot() === hostGeneration;
        };
        setStatus({ phase: "pending", message: "正在定位…" });
        try {
          var response = await connection.rpc.call("/api", "houdiniFrontend/openNode", {
            args: { input: { sessionId: props.sessionId, eventSeq: node.eventSeq, index: node.index, callId: node.callId } }
          }, controller.signal);
          if (!active()) return;
          if (controller.signal.aborted) throw new Error("定位超时，请重试");
          if (!response.ok) throw new Error(response.error && response.error.message || "节点定位失败，请重试");
          if (response.value && response.value.ok === false) throw new Error(response.value.error || response.value.message || "节点定位失败，请重试");
          setStatus({ phase: "opened", message: node.role === "control" ? "已打开控制" : "已定位节点" });
        } catch (error) {
          if (active()) setStatus({ phase: "error", message: controller.signal.aborted ? "定位超时，请重试" : String(error.message || error) });
        } finally {
          clearTimeout(timeout);
          if (pending.current === controller) pending.current = null;
        }
      }
      var action = node.role === "control" ? "打开控制" : "定位节点";
      var roleLabel = node.role === "control" ? "控制" : node.role === "output" ? "模型输出" : "编辑入口";
      return React.createElement("article", { className: "dsh-houdini-node-card", "data-houdini-node-delivery": node.role },
        React.createElement("button", { type: "button", className: "dsh-houdini-node-open", disabled: !hostGeneration || status.phase === "pending",
          onClick: open, "aria-label": action + "：" + node.label },
          React.createElement("span", { className: "dsh-houdini-node-icon" }, glyph(node.role)),
          React.createElement("span", { className: "dsh-houdini-node-copy" },
            React.createElement("span", { className: "dsh-houdini-node-heading" },
              React.createElement("strong", { className: "dsh-houdini-node-title", title: node.label }, node.label)),
            node.description && React.createElement("span", { className: "dsh-houdini-node-description", title: node.description }, node.description)),
          React.createElement("span", { className: "dsh-houdini-node-action", "data-phase": status.phase,
            role: status.phase === "pending" || status.phase === "opened" ? "status" : undefined },
            React.createElement("span", null, status.phase === "pending" || status.phase === "opened" ? status.message : !hostGeneration ? "未连接" : node.role === "control" ? "打开" : "定位"),
            React.createElement("svg", { width: 14, height: 14, viewBox: "0 0 16 16", fill: "none", "aria-hidden": true },
              React.createElement("path", { d: status.phase === "opened" ? "m3 8 3 3 7-7" : "M3 8h9m-4-4 4 4-4 4", stroke: "currentColor", strokeWidth: 1.3, strokeLinecap: "round", strokeLinejoin: "round" })))),
        status.phase === "error" && React.createElement("div", { role: "status", className: "dsh-houdini-node-status", "data-phase": status.phase }, status.message),
        React.createElement("details", null,
          React.createElement("summary", { "aria-label": "节点详情", title: "节点详情" },
            React.createElement("svg", { width: 14, height: 14, viewBox: "0 0 16 16", fill: "currentColor", "aria-hidden": true },
              React.createElement("circle", { cx: 3, cy: 8, r: 1.2 }),
              React.createElement("circle", { cx: 8, cy: 8, r: 1.2 }),
              React.createElement("circle", { cx: 13, cy: 8, r: 1.2 }))),
          React.createElement("div", { className: "dsh-houdini-node-details" },
            React.createElement("span", null, "交付名称"), React.createElement("code", null, node.label),
            React.createElement("span", null, "节点用途"), React.createElement("span", null, roleLabel),
            node.description && React.createElement("span", null, "用途说明"),
            node.description && React.createElement("code", null, node.description),
            node.context && React.createElement("span", null, "网络上下文"),
            node.context && React.createElement("code", null, node.context),
            React.createElement("span", null, "节点类型"), React.createElement("code", null, node.type),
            React.createElement("span", null, "交付路径"), React.createElement("code", null, node.path),
            React.createElement("span", null, "所在工程"), React.createElement("code", null, node.execution.hip_path))));
    }
    function NodeDeliveryTail(props) {
      var source = uiConversation.binding(props.sessionId).target(TARGET);
      var snapshot = React.useSyncExternalStore(source.subscribe, source.getSnapshot);
      var nodes = forClosing(snapshot, props);
      if (!nodes.length) return null;
      return React.createElement("div", { "data-houdini-node-deliveries": true, "aria-label": "Houdini 节点交付",
        style: { display: "grid", gap: 6, marginTop: 6, fontFamily: "inherit" } },
        nodes.map(function (node) {
          return React.createElement(NodeCard, { key: JSON.stringify([props.sessionId, node.execution.executor_id, node.execution.hip_path, node.id]),
            sessionId: props.sessionId, node: node });
        }));
    }
    return NodeDeliveryTail;
  }

  return { definition: definition, view: view, forClosing: forClosing, createTail: createTail, css: css };
}
