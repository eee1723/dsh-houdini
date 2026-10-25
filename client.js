// dsh-houdini client half: Trace, project navigation and shared-executor selection.
// Handwritten CJS factory; generated catalogs and Trace sources are built below.
window.__ModuleLoader__.load({
  id: "dsh-houdini",
  factory: function (require) {
    var React = require("react");

    // DSH exposes stable semantic shell attributes. Scope this layout to the
    // mounted Trace, so leaving it restores the resident composer and its draft.
    var shellCss =
      '[data-conversation-content]:has(.dsh-trace) [data-chain-overlay-fallback="conversation.composer"]{display:none!important}' +
      '[data-conversation-content]:has(.dsh-trace) [data-conversation-scroll]{overflow:hidden;scrollbar-gutter:auto;margin:0}' +
      '[data-conversation-content]:has(.dsh-trace) [data-slot="conversation.session"],' +
      '[data-conversation-content]:has(.dsh-trace) [data-slot="conversation.session"]>div,' +
      '[data-conversation-content]:has(.dsh-trace) [data-slot="conversation.view"]{display:flex;flex:1 1 0;min-height:0;overflow:hidden}' +
      '.dsh-houdini-project-mark{display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;flex:none;color:var(--dsw-alias-label-secondary);vertical-align:middle}' +
      '[data-houdini-presence="online"] .dsh-houdini-project-symbol,[data-houdini-presence="online"].dsh-houdini-project-mark{color:var(--dsw-alias-state-success-primary,#3da36b)}' +
      '[data-houdini-presence="unknown"] .dsh-houdini-project-symbol,[data-houdini-presence="changed"] .dsh-houdini-project-symbol,[data-houdini-presence="unknown"].dsh-houdini-project-mark,[data-houdini-presence="changed"].dsh-houdini-project-mark{color:var(--dsw-alias-state-warn-primary,#c6974c)}' +
      '[data-houdini-presence="offline"] .dsh-houdini-project-symbol,[data-houdini-presence="offline"].dsh-houdini-project-mark{color:var(--dsw-alias-label-tertiary,#7d8590);opacity:.65}' +
      '.dsh-houdini-project-label{display:inline-flex;align-items:center;gap:6px;max-width:180px;min-width:0;height:24px;padding:0 4px;color:var(--dsw-alias-label-secondary);font-size:12px;border-radius:var(--dsw-radius-sm)}' +
      '.dsh-houdini-project-label>span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '.dsh-houdini-project-label[role="button"]{cursor:pointer}.dsh-houdini-project-label[role="button"]:hover{background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary)}.dsh-houdini-project-symbol{flex:none}' +
      '.dsh-houdini-project-label:focus-visible{outline:2px solid var(--dsw-focus-ring-color);outline-offset:2px}' +
      '.dsh-houdini-project-detail{font-size:12px;line-height:1.6;max-width:360px;overflow-wrap:anywhere;white-space:normal;color:var(--dsw-alias-label-secondary)}' +
      '.dsh-houdini-project-detail strong{color:var(--dsw-alias-label-primary);font-weight:500}' +
      '.dsh-houdini-project-chip{display:inline-flex;align-items:center;gap:7px;max-width:min(360px,100%);min-width:0;height:28px;padding:0 9px;border:1px solid var(--dsw-alias-border-l3,#42474e);border-radius:99px;background:var(--dsw-alias-bg-layer-1,transparent);color:var(--dsw-alias-label-secondary);font:inherit;font-size:12px;cursor:pointer;white-space:nowrap;transition:background .12s,border-color .12s}' +
      '.dsh-houdini-project-chip:hover{background:var(--dsw-alias-interactive-bg-hover);border-color:var(--dsw-alias-border-l2)}.dsh-houdini-project-chip:focus-visible{outline:2px solid var(--dsw-focus-ring-color);outline-offset:2px}.dsh-houdini-chip-name{min-width:0;max-width:155px;overflow:hidden;text-overflow:ellipsis;color:var(--dsw-alias-label-primary)}' +
      '.dsh-houdini-chip-status{display:inline-flex;align-items:center;gap:4px;font-size:11px;padding-left:7px;border-left:1px solid var(--dsw-alias-border-l3);color:var(--dsw-alias-label-tertiary)}.dsh-houdini-project-chip>svg{flex:none}.dsh-houdini-state-icon{flex:none}' +
      '.dsh-houdini-project-chip[data-state="ready"] .dsh-houdini-chip-status{color:var(--dsw-alias-state-success-primary,#3da36b)}.dsh-houdini-project-chip[data-state="working"] .dsh-houdini-chip-status,[data-state="working"].dsh-houdini-project-mark{color:var(--dsw-alias-state-business-primary,#649be8)}.dsh-houdini-project-chip[data-state="occupied"] .dsh-houdini-chip-status,.dsh-houdini-project-chip[data-state="changed"] .dsh-houdini-chip-status{color:var(--dsw-alias-state-warn-primary,#c6974c)}' +
      '.dsh-houdini-target-menu{width:340px;max-width:calc(100vw - 24px);padding:4px!important}.dsh-houdini-target-heading{display:grid;gap:4px;padding:10px 10px 9px}.dsh-houdini-target-heading strong{font-size:13px;font-weight:600;color:var(--dsw-alias-label-primary)}.dsh-houdini-target-heading>span,.dsh-houdini-target-meta{font-size:11px;color:var(--dsw-alias-label-tertiary);line-height:1.5}' +
      '.dsh-houdini-target-current{display:grid;gap:6px;margin:0 8px 8px;padding:9px 10px;border-radius:8px;background:var(--dsw-alias-bg-layer-1);font-size:12px}.dsh-houdini-target-current strong{font-weight:500}.dsh-houdini-target-current details{color:var(--dsw-alias-label-tertiary);font-size:11px}.dsh-houdini-target-current summary{cursor:pointer}.dsh-houdini-target-current details>span{display:block;margin-top:5px;overflow-wrap:anywhere;white-space:normal;line-height:1.5}' +
      '.dsh-houdini-target-group{padding:7px 10px 3px;color:var(--dsw-alias-label-tertiary);font-size:10px}.dsh-houdini-target-actions{padding-bottom:5px;margin-bottom:5px;border-bottom:1px solid var(--dsw-alias-border-l1)}.dsh-houdini-target-choices{height:190px;overflow:auto}.dsh-houdini-target-list{overflow:visible}.dsh-houdini-target-list [role="menuitem"]{height:auto;min-height:48px;padding-top:7px;padding-bottom:7px}.dsh-houdini-target-row{display:grid;gap:3px;min-width:0;flex:1}.dsh-houdini-target-title{display:flex;align-items:center;gap:8px;min-width:0;overflow:hidden;text-overflow:ellipsis}.dsh-houdini-target-selected{margin-left:auto;color:var(--dsw-alias-state-business-primary)}.dsh-houdini-target-message{margin:0;padding:8px 10px;color:var(--dsw-alias-label-secondary);font-size:12px;white-space:normal;line-height:1.6}' +
      '@media(max-width:540px){.dsh-houdini-project-chip{max-width:calc(100vw - 130px);gap:5px;padding:0 7px}.dsh-houdini-chip-name{max-width:105px}.dsh-houdini-chip-status{font-size:10px;padding-left:5px}}' +
      '.dsh-houdini-window-pin[aria-pressed="true"]{color:var(--dsw-alias-state-warn-primary,#e5a263);background:var(--dsw-alias-interactive-bg-hover-solid,#343940)}' +
      '.dsh-houdini-update-button{height:28px!important;gap:5px!important;padding:0 9px!important;border:1px solid var(--dsw-alias-border-l3)!important;border-radius:99px!important;color:var(--dsw-alias-state-business-primary,#649be8)!important;font-size:12px!important;white-space:nowrap;flex:none}' +
      '#dsh-houdini-navigation button{font:inherit;border:1px solid #68513c;border-radius:6px;background:#2d3136;color:#e5a263;padding:4px 10px;cursor:pointer;margin:6px 8px 0 0}' +
      '.dsh-support-modal{width:min(720px,100%);max-height:100%;gap:16px}' +
      '.dsh-support-content{min-height:0;overflow:hidden;flex:1}' +
      '.dsh-support-content>div:first-child{flex:none}' +
      '.dsh-support-content>div:last-child{min-height:0;overflow:auto;overscroll-behavior:contain;margin-top:8px}' +
      '.dsh-support-modal>div:last-child{flex:none;flex-wrap:wrap}' +
      '.dsh-support-body{font-size:14px;line-height:1.6;padding-bottom:2px}' +
      '.dsh-support-body p{margin:0 0 16px}' +
      '.dsh-support-note{color:var(--dsw-alias-label-secondary);font-size:13px}' +
      '.dsh-support-input{display:block;width:100%;box-sizing:border-box;resize:vertical;min-height:84px;max-height:160px;margin:8px 0 20px;padding:12px;border:1px solid var(--dsw-alias-border-l3);border-radius:var(--dsw-radius-md);background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);font:inherit}' +
      '.dsh-support-input:focus-visible{outline:2px solid var(--dsw-focus-ring-color,var(--dsw-alias-brand-primary));outline-offset:2px}' +
      '.dsh-support-options{display:grid;gap:16px;margin:12px 0 20px}' +
      '.dsh-support-option p{font-size:13px;color:var(--dsw-alias-label-secondary);margin:5px 0 0 22px}' +
      '.dsh-support-toolbar{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 0 12px;background:var(--dsw-alias-bg-layer-2)}' +
      '.dsh-support-file{border:1px solid var(--dsw-alias-border-l3);border-radius:var(--dsw-radius-md);margin:0 0 10px;overflow:hidden}' +
      '.dsh-support-file>button{width:100%;height:auto;min-height:56px;justify-content:space-between;text-align:left;padding:12px;gap:16px}' +
      '.dsh-support-file-heading{display:grid;gap:3px}.dsh-support-file-heading small{font-weight:400;color:var(--dsw-alias-label-secondary);font-size:12px}' +
      '.dsh-support-file-body{padding:0 12px 12px}.dsh-support-file-body pre{white-space:pre-wrap;overflow-wrap:anywhere;overflow:auto;max-height:240px;margin:8px 0 0;padding:12px;border-radius:var(--dsw-radius-sm);background:var(--dsw-alias-bg-layer-1);font:12px/1.6 Consolas,monospace}' +
      '.dsh-support-file-body small{color:var(--dsw-alias-label-tertiary);overflow-wrap:anywhere}' +
      '.dsh-support-status{margin:12px 0 0!important;overflow-wrap:anywhere}' +
      '.dsh-support-sharing{border-top:1px solid var(--dsw-alias-border-l3);padding-top:12px;margin-top:16px;font-size:13px;color:var(--dsw-alias-label-secondary)}' +
      '.dsh-support-sharing summary{cursor:pointer;padding:6px 0}.dsh-support-sharing p{margin:8px 0}.dsh-support-sharing a{color:var(--dsw-alias-label-primary);text-decoration:underline}' +
      '@media(max-width:540px){.dsh-support-modal{gap:8px}.dsh-support-options{gap:12px}.dsh-support-option p{line-height:1.5}.dsh-support-input{margin-bottom:14px}.dsh-support-file>button{gap:8px}}';
    var shellCssId = "dsh-houdini/shell.module.css";
    if (typeof document !== "undefined" &&
        document.querySelector("style[data-plugin-css=" + JSON.stringify(shellCssId) + "]") === null) {
      var shellTag = document.createElement("style");
      shellTag.dataset.plugin = "dsh-houdini";
      shellTag.dataset.pluginCss = shellCssId;
      shellTag.textContent = shellCss;
      document.head.appendChild(shellTag);
    }

    // Trace and delivery consume this same execution record.
    // Native calls carry meta; DSH PTC subcalls carry a call-bound log record.
    function readHoudiniCanonical(node) {
      var name = node && (node.call && node.call.name || node.name);
      if (typeof name !== "string" || name.indexOf("houdini_") !== 0 && name !== "job_output") return null;
      var value = node.meta && node.meta.canonical;
      for (var block of value ? [] : node.content || []) {
        if (!block || block.type !== "text") continue;
        var record;
        try { record = JSON.parse(block.text); } catch (_error) { continue; }
        if (record && record.kind === "dsh-houdini/execution-v1" &&
            record.callId === node.callId && record.tool === name) { value = record.value; break; }
      }
      return name === "job_output" ? liveJobResult(value)?.value || null : value || null;
    }

    // Style only the selected Houdini task's existing semantic delivery surfaces.
    function HoudiniDeliveryScope(props) {
      var preset = props.useSessions(function (state) {
        var row = state && state.byId && state.byId[props.sessionId];
        return row && row.projectionValues && row.projectionValues.agentPreset;
      });
      return preset === "houdini" ? React.createElement("span", {
        hidden: true, "aria-hidden": true, "data-houdini-workspace": true
      }) : null;
    }

    function useHoudiniProject(props) {
      return props.useSessions(function (state) {
        var snapshot = state && state.projectionsBySession && state.projectionsBySession[props.sessionId];
        return snapshot && snapshot.values && snapshot.values.houdiniExecutorIdentity || null;
      });
    }

    function houdiniProjectTarget(project) {
      if (!project) return null;
      if (Object.prototype.hasOwnProperty.call(project, 'target')) return project.target;
      return project.executorId ? { executor_id: project.executorId, runtime_id: project.runtimeId,
        scene_epoch: project.sceneEpoch, scene_id: project.sceneId, hip_path: project.hipPath,
        hip_is_new: project.hipIsNew, label: project.label } : null;
    }

    function houdiniProjectName(project) {
      var target = houdiniProjectTarget(project) || project || {};
      return target.hip_is_new === true || project && project.hipIsNew === true ? target.label || project && project.label || "未保存工程" :
        (target.hip_path || project && project.hipPath || "").replace(/\\/g, "/").split("/").pop() || "Houdini 现场";
    }

    function HoudiniProjectIcon() {
      return React.createElement("svg", { className: "dsh-houdini-project-symbol", viewBox: "0 0 20 20", width: 14, height: 14, fill: "none", stroke: "currentColor", strokeWidth: 1.7, "aria-hidden": true },
        React.createElement("path", { d: "M10 10c0-1.5 2.4-1.5 2.4.4 0 3.3-5.3 3.2-5.3-.6 0-5.3 8.1-5.2 8.1.7 0 7.3-11.7 7.2-11.7-.9 0-8.3 12.5-8.9 14.3-1.9", strokeLinecap: "round", strokeLinejoin: "round" }));
    }

    function HoudiniTargetStateIcon(props) {
      var paths = { ready: "M10 3a7 7 0 1 1-.01 0M10 9v2", working: "M10 3v4m0 6v4M3 10h4m6 0h4M5 5l3 3m4 4 3 3M5 15l3-3m4-4 3-3",
        occupied: "M7 6V4a3 3 0 0 1 6 0v2M5 7h10v10H5z", changed: "M10 3l8 14H2zM10 8v4m0 2v.1",
        offline: "M6 7l-3 3 3 3m8-6 3 3-3 3M3 3l14 14", unknown: "M7 7a3 3 0 1 1 4 3c-1 .4-1 1-1 2m0 3v.1",
        unbound: "M6 10h8M10 6v8" };
      return React.createElement("svg", { className: "dsh-houdini-state-icon", viewBox: "0 0 20 20", width: 12, height: 12,
        fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true },
        React.createElement("path", { d: paths[props.state] || paths.unknown }));
    }

    function houdiniPresence(project, snapshot, sessionId, nativeStatuses, useCurrentActivity) {
      var target = houdiniProjectTarget(project);
      function status(state, label, detail, presence) { return { state: state, status: presence || (state === "offline" ? "offline" : state === "changed" ? "changed" : "unknown"), label: label, detail: detail || label }; }
      if (!target) return status("unbound", "未绑定现场", "选择一个已打开的 Houdini；每段对话可以独立选择现场。");
      if (!snapshot || !snapshot.available || snapshot.visible === false || !snapshot.observedAt || Date.now() - snapshot.observedAt > 12000)
        return status("unknown", "连接待确认", "暂未取得当前连接状态。可以展开选择其他现场。");
      if (project.needsReview) return status("changed", "工程待核对", "当前场景与这段对话选择时不同，请明确选择要继续的现场。");
      var record = snapshot.records[target.executor_id];
      if (!record || !Number.isFinite(record.observedAt) || Date.now() - record.observedAt > 12000)
        return status("unknown", "连接待确认", "没有新近的现场回执；登记本身不代表在线。");
      if (record.status === "offline") return status("offline", "已断开", "这个 Houdini 已关闭或断开，可以选择其他已打开的窗口。");
      if (record.contractMismatch) return status("unknown", "版本待更新", "运行版本不一致，请重载对应 Houdini。");
      if (record.status !== "online") return status("unknown", "连接待确认", "暂时无法确认这个 Houdini 的连接状态。");
      if (!target.scene_epoch || !record.sceneEpoch || !target.runtime_id || !record.runtimeId)
        return status("unknown", "现场待确认", "现场身份信息尚未完整确认，请重新选择当前窗口。");
      if (target.scene_epoch !== record.sceneEpoch || target.runtime_id !== record.runtimeId)
        return status("changed", "场景已变化", "Houdini 已重开或切换场景，请重新选择要继续的现场。");
      var nativeCurrent = useCurrentActivity !== false && nativeStatuses && nativeStatuses.get && nativeStatuses.get(sessionId);
      var owner = record.ownerSessionId;
      var nativeOwner = owner && nativeStatuses && nativeStatuses.get && nativeStatuses.get(owner);
      var activeJobs = Number(record.activeJobs) > 0;
      var bridgeBusy = record.busy === true || Number(record.activeRequests) > 0 || activeJobs;
      if (nativeCurrent && nativeCurrent.running === true)
        return status("working", "对话工作中", "当前对话正在处理请求，Houdini 连接正常。", "online");
      if (owner && owner !== sessionId && (activeJobs || nativeOwner && nativeOwner.running === true))
        return status("occupied", "其他对话工作中", "另一个对话正在使用这个现场；可以绑定查看，修改时会等待其完成。", "online");
      if (activeJobs && owner === sessionId)
        return status("working", "对话工作中", "当前对话在 Houdini 中的后台操作尚未完成。", "online");
      if (bridgeBusy) return status("working", "现场工作中", "Houdini 有操作尚未完成，当前操作归属暂未确认。", "online");
      return status("ready", "已就绪", "目标连接正常；真正修改前仍会核对现场与写入资格。", "online");
    }

    function HoudiniProjectMark(props) {
      var project = useHoudiniProject(props), presence = props.usePresence ? props.usePresence() : null;
      var statuses = props.useNativeStatus ? props.useNativeStatus() : null;
      var status = project && houdiniPresence(project, presence, props.sessionId, statuses);
      return project && React.createElement("span", { className: "dsh-houdini-project-mark", role: "img",
        "aria-label": "关联现场：" + houdiniProjectName(project) + " · " + status.label,
        "data-state": status.state, "data-houdini-presence": status.status, "data-houdini-project-mark": true }, React.createElement(HoudiniProjectIcon));
    }

    function HoudiniProjectDetail(props) {
      var project = useHoudiniProject(props), presence = props.usePresence ? props.usePresence() : null;
      var statuses = props.useNativeStatus ? props.useNativeStatus() : null;
      if (!project) return null;
      var target = houdiniProjectTarget(project), status = houdiniPresence(project, presence, props.sessionId, statuses);
      return React.createElement("div", { className: "dsh-houdini-project-detail", "data-houdini-project-detail": true },
        React.createElement("strong", null, "关联现场 · " + houdiniProjectName(project)),
        React.createElement("div", null, status.label),
        target && target.hip_path && !target.hip_is_new && React.createElement("div", null, target.hip_path),
        React.createElement("div", null, status.detail));
    }

    function HoudiniProjectLabel(props) {
      var project = useHoudiniProject(props), presence = props.usePresence ? props.usePresence() : null;
      var statuses = props.useNativeStatus ? props.useNativeStatus() : null;
      var status = houdiniPresence(project, presence, props.sessionId, statuses), target = houdiniProjectTarget(project);
      var ui = require("@deepseek-ai/dsh-client-ui-primitives");
      return React.createElement(ui.Tooltip, { side: "bottom", align: "end", delayMs: 400, portal: true, maxWidth: 360, openOnClick: false,
        label: (target ? houdiniProjectName(project) + (target.hip_path ? "\n" + target.hip_path : "") + "\n" : "") + status.label + " · " + status.detail },
        React.createElement("button", { type: "button", className: "dsh-houdini-project-chip", onClick: props.onProjectMenuClick,
          "aria-haspopup": "menu", "aria-expanded": !!props.projectMenuOpen,
          "aria-label": "Houdini 现场：" + (target ? houdiniProjectName(project) + " · " : "") + status.label,
          "data-state": status.state, "data-houdini-presence": status.status, "data-houdini-project-label": true },
          React.createElement(HoudiniProjectIcon),
          React.createElement("span", { className: "dsh-houdini-chip-name", "data-houdini-project-name": true }, target ? houdiniProjectName(project) : "Houdini"),
          React.createElement("span", { className: "dsh-houdini-chip-status" }, React.createElement(HoudiniTargetStateIcon, { state: status.state }), status.label),
          React.createElement("svg", { width: 10, height: 10, viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: 1.3, "aria-hidden": true }, React.createElement("path", { d: "m3 4.5 3 3 3-3" }))));
    }

    function HoudiniBlankProjectLabel(props) {
      var blank = props.useSessions(function (state) { return !!(state.byId[props.sessionId] && state.byId[props.sessionId].blank); });
      return blank ? React.createElement(HoudiniProjectLabel, props) : null;
    }

    function createWorkbenchUpdates(connection) {
      var state = { available: false, version: "", opening: false }, listeners = new Set(), notice = null, serial = 0;
      var statusRequest = null, openRequest = null;
      function subscribe(listener) { listeners.add(listener); return function () { listeners.delete(listener); }; }
      function snapshot() { return state; }
      function publish(next) { state = next; listeners.forEach(function (listener) { listener(); }); }
      function useUpdate() { return React.useSyncExternalStore(subscribe, snapshot); }
      function current(controller, generation) { return !controller.signal.aborted && connection.generation.getSnapshot() === generation; }
      async function refresh() {
        if (statusRequest || !connection.generation.getSnapshot() || document.visibilityState === "hidden") return;
        var controller = new AbortController(), generation = connection.generation.getSnapshot();
        statusRequest = controller;
        try {
          var response = await connection.rpc.call("/api", "houdiniFrontend/updateStatus", { args: {} }, AbortSignal.any([controller.signal, AbortSignal.timeout(6000)]));
          if (!current(controller, generation)) return;
          if (!response.ok || !response.value) throw new Error("update status unavailable");
          publish({ available: response.value.available === true, version: typeof response.value.version === "string" ? response.value.version : "", opening: state.opening });
        } catch (_error) {
          if (current(controller, generation)) publish({ available: false, version: "", opening: state.opening });
        } finally { if (statusRequest === controller) statusRequest = null; }
      }
      async function openManager() {
        if (openRequest) return;
        var controller = new AbortController(), generation = connection.generation.getSnapshot();
        openRequest = controller; publish(Object.assign({}, state, { opening: true }));
        try {
          var response = await connection.rpc.call("/api", "houdiniFrontend/openUpdates", { args: {} }, AbortSignal.any([controller.signal, AbortSignal.timeout(6000)]));
          if (!current(controller, generation)) return;
          if (!response.ok || !response.value || response.value.opened !== true) throw new Error(response.error && response.error.message || "暂时无法打开版本与更新。");
        } catch (error) {
          if (current(controller, generation)) { notice = { id: ++serial, text: String(error.message || error) }; publish(Object.assign({}, state)); }
        } finally {
          if (openRequest === controller) { openRequest = null; publish(Object.assign({}, state, { opening: false })); }
        }
      }
      function Button() {
        var update = useUpdate();
        if (!update.available) return null;
        var ui = require("@deepseek-ai/dsh-client-ui-primitives"), label = "DSH-Houdini" + (update.version ? " " + update.version : "") + " 有更新，打开版本与更新";
        return React.createElement(ui.Tooltip, { label: label, side: "bottom", portal: true }, React.createElement(ui.Button, {
          variant: "ghost", size: "sm", className: "dsh-houdini-update-button", "aria-label": label,
          "data-houdini-update": true, "data-houdini-update-version": update.version, disabled: update.opening, onClick: openManager },
          React.createElement("svg", { width: 14, height: 14, viewBox: "0 0 20 20", fill: "none", stroke: "currentColor", strokeWidth: 1.5,
            strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true }, React.createElement("path", { d: "M10 3v9m-3-3 3 3 3-3M4 13v3a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-3" })), "有更新"));
      }
      function Lifecycle() {
        useUpdate();
        React.useEffect(function () {
          function changed() {
            if (statusRequest) statusRequest.abort(); statusRequest = null;
            if (openRequest) openRequest.abort(); openRequest = null;
            notice = null; publish({ available: false, version: "", opening: false }); refresh();
          }
          var unsubscribe = connection.generation.subscribe(changed), timer = setInterval(refresh, 60000);
          document.addEventListener("visibilitychange", changed); refresh();
          return function () {
            if (statusRequest) statusRequest.abort(); statusRequest = null;
            if (openRequest) openRequest.abort(); openRequest = null;
            clearInterval(timer); unsubscribe(); document.removeEventListener("visibilitychange", changed);
          };
        }, []);
        if (!notice) return null;
        var currentNotice = notice, ui = require("@deepseek-ai/dsh-client-ui-primitives");
        return React.createElement(ui.Toast, { key: currentNotice.id, text: currentNotice.text, onDone: function () {
          if (notice === currentNotice) { notice = null; publish(Object.assign({}, state)); }
        } });
      }
      return { Button: Button, Lifecycle: Lifecycle };
    }

    function createWorkbenchUi(connection, uiSession, sessions, uiWorkspace) {
      var state = { available: false, visible: true, records: {}, observedAt: 0 }, listeners = new Set(), notice = null, serial = 0;
      var pin = { pinned: null, busy: false }, pinRequest = null, refreshPresence = function () {};
      var nativeEmpty = new Map(), nativeSource = uiSession.sessionStatus || { getSnapshot: function () { return nativeEmpty; }, subscribe: function () { return function () {}; } };
      var openWhenSelected = false, openingTimer = null;
      function subscribe(listener) { listeners.add(listener); return function () { listeners.delete(listener); }; }
      function snapshot() { return state; }
      function publish(next) { state = next; listeners.forEach(function (listener) { listener(); }); }
      function usePresence() { return React.useSyncExternalStore(subscribe, snapshot); }
      function useNativeStatus() { return React.useSyncExternalStore(nativeSource.subscribe, nativeSource.getSnapshot); }
      function notify(text) { notice = { id: ++serial, text: text }; publish(Object.assign({}, state)); }
      async function updatePin(input, reportError) {
        if (pinRequest) return;
        var controller = new AbortController(), generation = connection.generation.getSnapshot();
        pinRequest = controller; pin = Object.assign({}, pin, { busy: true }); publish(Object.assign({}, state));
        try {
          var response = await connection.rpc.call("/api", "houdiniFrontend/windowPin", { args: { input: input } }, AbortSignal.any([controller.signal, AbortSignal.timeout(6000)]));
          if (controller.signal.aborted || connection.generation.getSnapshot() !== generation) return;
          if (!response.ok || !response.value || typeof response.value.pinned !== "boolean") throw new Error(response.error && response.error.message || "暂时无法调整窗口置顶。");
          pin = { pinned: response.value.pinned, busy: false };
        } catch (error) { if (!controller.signal.aborted && connection.generation.getSnapshot() === generation && reportError) notify(String(error.message || error)); }
        finally { if (pinRequest === controller) { pinRequest = null; pin = Object.assign({}, pin, { busy: false }); publish(Object.assign({}, state)); } }
      }
      function Pin() {
        if (!usePresence().available) return null;
        var ui = require("@deepseek-ai/dsh-client-ui-primitives"), label = pin.pinned ? "取消窗口置顶" : "窗口置顶";
        return React.createElement(ui.Tooltip, { label: label, side: "bottom", portal: true }, React.createElement(ui.Button, {
          variant: "ghost", size: "sm", className: "dsh-houdini-window-pin", style: { width: 28, height: 28, padding: 0, marginRight: 4, flex: "none" },
          "aria-label": label, "aria-pressed": pin.pinned === null ? undefined : pin.pinned, "data-houdini-window-pin": true,
          disabled: pin.busy, onClick: function () { updatePin({ pinned: pin.pinned !== true }, true); } },
          React.createElement("svg", { width: 16, height: 16, viewBox: "0 0 20 20", fill: "none", stroke: "currentColor", strokeWidth: 1.5,
            strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true }, React.createElement("path", { d: "M6 2h8l-1 5 3 3v2H4v-2l3-3zM10 12v6" }))));
      }
      async function action(kind, sessionId) {
        try {
          var response = await connection.rpc.call("/api", "houdiniFrontend/projectAction", { args: { input: sessionId ? { action: kind, sessionId: sessionId } : { action: kind } } }, AbortSignal.timeout(10000));
          if (!response.ok) throw new Error(response.error && response.error.message || "暂时无法打开工程入口。");
        } catch (error) { notify(String(error.message || error)); }
      }
      function Lifecycle() {
        usePresence();
        React.useEffect(function () {
          var stopped = false, pending = null, refreshResult = null;
          function refresh() {
            if (stopped) return Promise.resolve();
            if (refreshResult) return refreshResult;
            var result = observe(); refreshResult = result;
            result.finally(function () { if (refreshResult === result) refreshResult = null; });
            return result;
          }
          async function observe() {
            var generation = connection.generation.getSnapshot();
            if (!generation || document.visibilityState === "hidden") { publish(Object.assign({}, state, { visible: document.visibilityState !== "hidden", records: {}, observedAt: 0 })); return; }
            var controller = new AbortController(); pending = controller;
            var deadline = setTimeout(function () { controller.abort(); }, 8000);
            try {
              if (!state.available) {
                var capability = await connection.rpc.call("/api", "houdiniFrontend/capabilities", { args: {} }, controller.signal);
                if (stopped || controller.signal.aborted || connection.generation.getSnapshot() !== generation) return;
                if (!capability.ok || !capability.value || !capability.value.workbench) return;
                publish(Object.assign({}, state, { available: true, visible: true })); updatePin({}, false);
              }
              var response = await connection.rpc.call("/api", "houdiniFrontend/projectPresence", { args: {} }, controller.signal);
              if (stopped || controller.signal.aborted || connection.generation.getSnapshot() !== generation) return;
              if (!response.ok || !Array.isArray(response.value)) throw new Error("presence unavailable");
              publish({ available: true, visible: true, observedAt: Date.now(), records: Object.fromEntries(response.value.map(function (record) { return [record.executorId, record]; })) });
            } catch (_error) { if (!stopped && pending === controller && connection.generation.getSnapshot() === generation) publish(Object.assign({}, state, { observedAt: 0, records: {} })); }
            finally { clearTimeout(deadline); if (pending === controller) pending = null; }
          }
          function changed() {
            if (pending) pending.abort(); pending = null; refreshResult = null;
            if (pinRequest) pinRequest.abort(); pinRequest = null; pin = { pinned: null, busy: false };
            publish({ available: false, visible: document.visibilityState !== "hidden", observedAt: 0, records: {} }); refresh();
          }
          refreshPresence = refresh;
          var unsubscribe = connection.generation.subscribe(changed);
          document.addEventListener("visibilitychange", changed);
          var timer = setInterval(refresh, 5000); refresh();
          return function () { stopped = true; if (pending) pending.abort(); if (pinRequest) pinRequest.abort(); clearInterval(timer); unsubscribe();
            document.removeEventListener("visibilitychange", changed); refreshPresence = function () {}; if (openingTimer) clearTimeout(openingTimer); };
        }, []);
        if (!notice) return null;
        var current = notice, ui = require("@deepseek-ai/dsh-client-ui-primitives");
        return React.createElement(ui.Toast, { key: current.id, text: current.text, onDone: function () { if (notice === current) { notice = null; publish(Object.assign({}, state)); } } });
      }
      function decorate(Component) { return function (props) { return React.createElement(Component, Object.assign({}, props, { usePresence: usePresence, useNativeStatus: useNativeStatus })); }; }
      function startConversation() {
        if (!uiWorkspace || !uiWorkspace.startSession) { notify("请先打开一个 Houdini 模式的对话，再选择现场。"); return; }
        openWhenSelected = true;
        if (openingTimer) clearTimeout(openingTimer);
        openingTimer = setTimeout(function () { openWhenSelected = false; }, 10000);
        uiWorkspace.startSession(undefined, { agentPreset: "houdini" });
      }
      function Menu(props) {
        var project = useHoudiniProject(props), presence = usePresence(), nativeStatuses = useNativeStatus();
        var row = props.useSessions(function (value) { return value.byId[props.sessionId] || null; });
        var status = houdiniPresence(project, presence, props.sessionId, nativeStatuses), target = houdiniProjectTarget(project);
        var menu = React.useState({ open: false, busy: false, message: "", loaded: false }), value = menu[0], set = menu[1];
        var pending = React.useRef(null), ticket = React.useRef(0), current = React.useRef(props.sessionId); current.current = props.sessionId;
        var hostGeneration = React.useSyncExternalStore(connection.generation.subscribe, connection.generation.getSnapshot);
        React.useEffect(function () {
          ticket.current++; if (pending.current) pending.current.abort();
          set({ open: false, busy: false, message: "", loaded: false });
          return function () { ticket.current++; if (pending.current) pending.current.abort(); };
        }, [props.sessionId, hostGeneration]);
        React.useEffect(function () {
          if (openWhenSelected && props.sessionId && row && row.projectionValues && row.projectionValues.agentPreset === "houdini") {
            openWhenSelected = false; if (openingTimer) clearTimeout(openingTimer); request("list");
          }
        }, [props.sessionId, row && row.projectionValues && row.projectionValues.agentPreset]);
        async function request(method, candidate) {
          var sessionId = props.sessionId, generation = connection.generation.getSnapshot();
          if (!sessionId) { startConversation(); return; }
          if (!generation) { set(function (old) { return Object.assign({}, old, { open: true, message: "工作台连接已断开，请稍后重试。" }); }); return; }
          var attempt = ++ticket.current;
          if (pending.current) pending.current.abort();
          var controller = new AbortController(); pending.current = controller;
          var timeout = setTimeout(function () { controller.abort(); }, 10000);
          set(function (old) { return Object.assign({}, old, { open: true, busy: true, message: method === "list" ? "正在查看已打开的 Houdini…" : method === "clear" ? "正在取消绑定…" : "正在选择现场…" }); });
          var input = { sessionId: sessionId };
          if (candidate) Object.assign(input, { executorId: candidate.executor_id, registrationId: candidate.registration_id, expectedHip: candidate.hip_path,
            runtimeId: candidate.runtime_id, sceneEpoch: candidate.scene_epoch });
          try {
            if (method === "list") {
              await refreshPresence();
              if (controller.signal.aborted || current.current !== sessionId || ticket.current !== attempt || connection.generation.getSnapshot() !== generation) return;
              set({ open: true, busy: false, loaded: true, message: "" });
              return;
            }
            var response = await connection.rpc.call("/api", "houdiniTargets/" + method, { args: { input: input } }, controller.signal);
            if (controller.signal.aborted || current.current !== sessionId || ticket.current !== attempt || connection.generation.getSnapshot() !== generation) return;
            if (!response.ok) throw new Error(response.error && response.error.message || "没有完成现场选择。");
            if (sessions && sessions.refreshProjections) await sessions.refreshProjections(sessionId);
            if (controller.signal.aborted || current.current !== sessionId || ticket.current !== attempt || connection.generation.getSnapshot() !== generation) return;
            set(function (old) { return Object.assign({}, old, { busy: false, open: false, message: "" }); }); refreshPresence();
            notify(method === "clear" ? "此对话已取消现场绑定。" : "此对话已选择「" + houdiniProjectName(candidate) + "」。");
          } catch (error) {
            if (current.current === sessionId && ticket.current === attempt && connection.generation.getSnapshot() === generation)
              set(function (old) { return Object.assign({}, old, { busy: false, message: controller.signal.aborted ? "等待现场响应超时，可以重试。" : String(error.message || error) }); });
          } finally { clearTimeout(timeout); if (pending.current === controller) pending.current = null; }
        }
        var ui = require("@deepseek-ai/dsh-client-ui-primitives"), currentNative = nativeStatuses && nativeStatuses.get(props.sessionId);
        var switchingDisabled = value.busy || currentNative && currentNative.running === true;
        // The same fresh desktop observation owns both membership and status.
        // A registry hint is never another list of supposedly open windows.
        var freshPresence = presence.available && presence.visible !== false && presence.observedAt && Date.now() - presence.observedAt <= 12000;
        function workspaceKey(path) { return String(path || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase(); }
        var rows = freshPresence ? Object.values(presence.records).filter(function (observed) {
          return observed.status !== "offline" && Number.isFinite(observed.observedAt) && Date.now() - observed.observedAt <= 12000
            && observed.candidate && observed.candidate.workbench === true && observed.candidate.state === "registered";
        }).map(function (observed) { return Object.assign({}, observed.candidate, {
          same_workspace: !!(row && row.cwd && workspaceKey(row.cwd) === workspaceKey(observed.candidate.workspace_path))
        }); }).sort(function (left, right) { return Number(right.same_workspace === true) - Number(left.same_workspace === true); }) : [];
        var entries = [], lastGroup = null;
        rows.forEach(function (candidate, index) {
          var group = candidate.same_workspace ? "同一工作区" : "其他工作区";
          if (group !== lastGroup) { entries.push(React.createElement("div", { className: "dsh-houdini-target-group", key: "group-" + group, role: "presentation" }, group)); lastGroup = group; }
          var selected = target && target.executor_id === candidate.executor_id && target.runtime_id === candidate.runtime_id && target.scene_epoch === candidate.scene_epoch;
          var candidateProject = { target: candidate }, observed = houdiniPresence(candidateProject, presence, props.sessionId, nativeStatuses, !!selected);
          var label = houdiniProjectName(candidate), version = String(candidate.houdini_version || "").split(".")[0];
          var details = (candidate.hip_path || "未保存工程") + (candidate.pid ? "\n进程 " + candidate.pid : "");
          entries.push(React.createElement(ui.MenuItemButton, { key: candidate.executor_id,
            disabled: !!switchingDisabled || candidate.state === "disconnected" || observed.state === "offline" || !candidate.hip_path,
            icon: React.createElement(HoudiniTargetStateIcon, { state: observed.state }),
            onSelect: function () { request("select", candidate); } },
            React.createElement("span", { className: "dsh-houdini-target-row", title: details + "\n" + observed.detail, "data-houdini-target": candidate.executor_id, "data-state": observed.state },
              React.createElement("span", { className: "dsh-houdini-target-title" }, label, selected && React.createElement("span", { "aria-label": "当前已选现场", className: "dsh-houdini-target-selected" }, "✓")),
              React.createElement("span", { className: "dsh-houdini-target-meta" }, "窗口 " + (index + 1) + (version ? " · Houdini " + version : ""), " · ", observed.label))));
        });
        var actions = [];
        if (target) actions.push({ id: "clear", label: "取消此对话的绑定", disabled: !!switchingDisabled });
        if (project && project.hipPath && project.hipIsNew === false) actions.push({ id: "reopen", label: "打开关联工程" });
        actions.push({ id: "open", label: "打开 Houdini 工程…", disabled: !presence.available }, { id: "new", label: "新建 Houdini 工程…", disabled: !presence.available });
        var anchor = props.footer ? React.createElement(ui.Button, { variant: "ghost", size: "sm", "aria-label": "打开或新建 Houdini 工程", onClick: startConversation }, React.createElement(HoudiniProjectIcon)) :
          React.createElement(HoudiniProjectLabel, Object.assign({}, props, { usePresence: usePresence, useNativeStatus: useNativeStatus,
            projectMenuOpen: value.open, onProjectMenuClick: function () { if (value.open) { ticket.current++; if (pending.current) pending.current.abort(); set(Object.assign({}, value, { open: false, busy: false })); } else request("list"); } }));
        return React.createElement(ui.Menu, { open: value.open, portal: true, compact: true, align: "end", side: "bottom", anchor: anchor,
          listClassName: "dsh-houdini-target-menu", onClose: function () { ticket.current++; if (pending.current) pending.current.abort(); set(function (old) { return Object.assign({}, old, { open: false, busy: false }); }); },
          },
          React.createElement("div", { className: "dsh-houdini-target-heading", role: "presentation" }, React.createElement("strong", null, "Houdini 现场"),
            React.createElement("span", null, "为当前对话选择要操作的窗口")),
          React.createElement("div", { className: "dsh-houdini-target-actions", role: "presentation" }, actions.map(function (item) {
            return React.createElement(ui.MenuItemButton, { key: item.id, disabled: !!item.disabled,
              onSelect: function () {
                if (item.id === "clear") { request("clear"); return; }
                ticket.current++; if (pending.current) pending.current.abort(); pending.current = null;
                set(Object.assign({}, value, { open: false, busy: false, message: "" })); action(item.id, props.sessionId);
              } }, React.createElement("span", { "data-houdini-project-action": item.id }, item.label));
          })),
          target && React.createElement("div", { className: "dsh-houdini-target-current", role: "presentation" },
            React.createElement("strong", null, houdiniProjectName(project) + " · " + status.label),
            target.hip_path && React.createElement("details", null, React.createElement("summary", null, "工程路径"), React.createElement("span", null, target.hip_path))),
          React.createElement("div", { className: "dsh-houdini-target-choices" },
            value.message && React.createElement("p", { role: "status", className: "dsh-houdini-target-message" }, value.message),
            value.loaded && !value.busy && !value.message && !rows.length && React.createElement("p", { role: "status", className: "dsh-houdini-target-message" },
              freshPresence ? "还没有可选现场。在目标 Houdini 中选择 DSH-Houdini → Open Workspace 后，会显示在这里。" : "暂时无法确认现场列表，连接恢复后会自动更新。"),
            currentNative && currentNative.running === true && React.createElement("p", { className: "dsh-houdini-target-message" }, "当前对话工作完成后，可以切换或取消绑定。"),
            React.createElement("div", { className: "dsh-houdini-target-list", "aria-label": "已登记的 Houdini 窗口" }, entries)));
      }
      function Label(props) {
        var row = props.useSessions(function (value) { return value.byId[props.sessionId]; });
        return row && !row.blank && row.projectionValues && row.projectionValues.agentPreset === "houdini" ? React.createElement(Menu, props) : null;
      }
      function Blank(props) {
        var row = props.useSessions(function (value) { return value.byId[props.sessionId]; });
        return row && row.blank && row.projectionValues && row.projectionValues.agentPreset === "houdini" ? React.createElement(Menu, props) : null;
      }
      function Footer(props) {
        usePresence();
        var selected = React.useSyncExternalStore(uiSession.adapter.current.subscribe, uiSession.adapter.current.getSnapshot);
        return !selected || !selected.key ? React.createElement(Menu, Object.assign({}, props, { footer: true })) : null;
      }
      return { Mark: decorate(HoudiniProjectMark), Detail: decorate(HoudiniProjectDetail), Label: Label, Pin: Pin, Blank: Blank, Footer: Footer, Lifecycle: Lifecycle };
    }

    function createHoudiniTitleAction(connection) {
      var requests = new Map(), listeners = new Set(), notice = null, serial = 0, disposed = false;
      function publish(text) { notice = text ? { id: ++serial, text: text } : null; listeners.forEach(function (listener) { listener(); }); }
      function cancel() { requests.forEach(function (controller) { controller.abort(); }); requests.clear(); publish(null); }
      function subscribe(listener) { listeners.add(listener); return function () { listeners.delete(listener); }; }
      function snapshot() { return notice; }
      async function regenerate(sessionId) {
        if (disposed || requests.has(sessionId)) return;
        var generation = connection.generation.getSnapshot(), controller = new AbortController();
        requests.set(sessionId, controller); publish("正在根据对话内容整理标题…");
        var timeout = setTimeout(function () { controller.abort(); }, 45000);
        try {
          var result = await connection.rpc.call("/api", "houdiniFrontend/refreshTitle", { args: { input: { sessionId: sessionId } } }, controller.signal);
          if (disposed || requests.get(sessionId) !== controller || connection.generation.getSnapshot() !== generation) return;
          controller.signal.throwIfAborted();
          if (!result.ok) throw new Error(result.error && result.error.message || "暂时无法生成标题，请重试。");
          publish("对话标题已更新。");
        } catch (error) {
          if (!disposed && requests.get(sessionId) === controller && connection.generation.getSnapshot() === generation)
            publish(controller.signal.aborted ? "标题生成超时，可以重新尝试。" : String(error.message || error));
        } finally { clearTimeout(timeout); if (requests.get(sessionId) === controller) requests.delete(sessionId); }
      }
      function Menu(props) {
        var project = useHoudiniProject(props), menu = props.useMenuOpenState();
        React.useSyncExternalStore(subscribe, snapshot);
        if (!project) return null;
        var ui = require("@deepseek-ai/dsh-client-ui-primitives");
        return React.createElement(ui.MenuItemButton, { disabled: requests.has(props.sessionId),
          onSelect: function () { menu[1](false); return regenerate(props.sessionId); } },
          requests.has(props.sessionId) ? "正在生成标题…" : "按对话内容重新命名");
      }
      function Feedback() {
        var value = React.useSyncExternalStore(subscribe, snapshot);
        React.useEffect(function () { return connection.generation.subscribe(cancel); }, []);
        if (!value) return null;
        var ui = require("@deepseek-ai/dsh-client-ui-primitives");
        return React.createElement(ui.Toast, { key: value.id, text: value.text, onDone: function () { if (notice === value) publish(null); } });
      }
      return { Menu: Menu, Feedback: Feedback, dispose: function () { disposed = true; cancel(); } };
    }

    // >>> houdini-node-delivery (generated by tools/gen-trace-client.mjs — do not edit)
    var nodeDeliveryFactory = (// Handwritten factory embedded by tools/gen-trace-client.mjs.
// DSH owns history, Session lifetime and the completed-Turn slot. This module
// projects only declared execution facts; node addresses remain Host-owned.
function createNodeDelivery(React, readHoudiniCanonical) {
  /** Original verb receipts are the delivery source, independent of Python __result__.
 * Shared with the generated browser factory; no recursive payload discovery. */
const NODE_DELIVERY_KIND = 'houdini/node-delivery-v1';
function nodeDeliveryRows(value) {
    if (!value || value.ok !== true || Number(value.outcome?.operations?.failed) > 0
        || !Array.isArray(value.verbs) || value.verbs.some((verb) => verb?.ok === false))
        return [];
    return value.verbs.flatMap((verb) => verb?.verb === 'present_nodes' && verb.ok === true
        && verb.result?.kind === NODE_DELIVERY_KIND && Array.isArray(verb.result.nodes)
        ? verb.result.nodes : []);
}

  var KIND = "houdini-node-delivery";
  var TARGET = "houdini-node-deliveries";

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
      meta: data.meta,
      content: nested ? data.content : []
    });
    var rows = nodeDeliveryRows(canonical), execution = canonical && canonical.execution;
    if (!rows.length || !execution) return state;
    if (![execution.executor_id, execution.runtime_id].every(function (value) { return typeof value === "string" && /^[0-9a-f]{32}$/.test(value); }) ||
        ![execution.hip_path, execution.owner_session].every(function (value) { return typeof value === "string" && value.trim().length > 0; }) || execution.hip_is_new === true) return state;
    var nodes = [];
    rows.forEach(function (node, index) {
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
});
    // <<< houdini-node-delivery

    // --- 词表目录（构建期生成，勿手改） --------------------------------------
    // >>> houdini-catalog (generated by tools/gen-client-catalog.mjs — do not edit)
    function getTraceCatalog() { return [{"domain":"vocabulary 域","note":"vocabulary 域（回答「动词怎么调用」）","verbs":[{"name":"verb_help","sig":"name, detail='brief'","desc":"按需发现动词。默认brief返回准确signature、return_type、call_mode与简短用途，并明确full_help入口；detail='full'返回完整doc及已有operation_contract（input_schema/output_schema/examples/notes），说明不参与执行校验。name可为1..16项唯一名称列表，批量返回items/count；未知名列相似项，任一未知整次明确失败。Bridge签名绑定错误给真实signature与零派发事实，内部TypeError保留真实原因","returns":"dict"}]},{"domain":"类型目录","note":"类型目录（回答「能建什么」）","verbs":[{"name":"search_tab_menu","sig":"category, query","desc":"列出某 context 下匹配的节点族 + 最新版","returns":"dict"},{"name":"search_tab_entries","sig":"parent, query","desc":"按真实父网络列当前可见的 node/tool entry；排除 hidden/deprecated，Material Library 根层只暴露 Builder tool；每项标 `kind` 与 dsh 是否可安全执行","returns":"dict"},{"name":"resolve_latest_type","sig":"category, base","desc":"已注册节点族的最新版全名（内部为主）；只以 namespace 注册的族返回带前缀全名（'rigdoctor' → 'kinefx::rigdoctor'），裸别名过不了 `createNode(exact_type_name=True)`；跨 namespace 同名按排序取第一个，recipe 需跨版本一致时应显式钉命名空间；当前类别没有该族时明确失败，不回传未经验证的base","returns":"str"}]},{"domain":"node 域","note":"node 域（场景图）","verbs":[{"name":"tab_create","sig":"parent, type_name, name=, inputs=[...], parms={...}","desc":"建**单个可见节点**：最新版 + 对应 shelf 初始化；类型、输入和参数形状先预检，静态失败返回零写入事实。inputs中的直属child名称相对实际parent解析，None保留空槽。可选非空`parms`在创建/接线后走严格set_parms，任一失败会连同 partial create 清理并报告恢复结果；拒绝 hidden/deprecated 和 Material Library 根层直建 shader，setup/builder 改用 tab_apply；parent 接受 Node/path。连完 inputs 后自动落位：有输入时以输入下游均值位置为首选；无输入时以父网络现有节点右侧新列、最顶部y为首选，空网络落原点。对完整节点/Box/Note/Dot障碍做局部有界避让；无所属Box且附近候选耗尽时跳到完整障碍包络右侧，保留首选y，不移动既有内容。已有所属Box边界仍保持；间距由节点实际网络尺寸（`Node.size()`）推导","returns":"`hou.Node`"},{"name":"tab_apply","sig":"parent, tool_id","desc":"应用 allowlist 内的非交互 Tab setup recipe，返回全部新增节点/输入；GUI 恢复 Network Editor pwd/selection，同一 exec 多次调用共享用户基线；headless 同语义。首批仅 Karma Setup / Karma Material Builder。SideFX recipe 自己摆节点，tab_apply 不做自动落位","returns":"dict"},{"name":"find_nodes","sig":"pattern=\"*\", category=None, node_type=None, root=None","desc":"找**已存在**节点（扁平清单）","returns":"path 列表"},{"name":"graph","sig":"node, depth=1, direction='both'","desc":"围绕**该数据节点**查 inputs / outputs / parm_refs；检查最终 SOP 网络应对 `OUT` 向上查，不要对父 OBJ 容器调用","returns":"dict"},{"name":"describe","sig":"node","desc":"状态 + 几何摘要 + `attrib_delta`（相对 input 0 的属性增删——MMB 节点信息里「这个节点对数据干了什么」的固化）+ 帮助元数据","returns":"dict"},{"name":"node_provenance","sig":"node","desc":"报告 runtime owner、可复制的 audit tag、当前 session 是否可写；`foreign`/`owned_current_session`/`owned_other_session`/`dsh_service` 分开","returns":"dict"},{"name":"connect","sig":"src, dst, index=0, *, output=0, allow_foreign=None","desc":"index为目标输入名/索引，output为源输出名/索引；精确名称不是label。COP相同Mono/UV/RGB/RGBA图像类型直接按实际signature核对，动态undef由原生setInput判定，其余走原生兼容查询；均回读实际连线，不按节点名叠加例外，不推断隐式通道转换。output默认0，第4位置参数拒绝。mutation边界在dst；OBJ→OBJ拒绝并指向set_object_parent，跨parent拒绝，不猜端口或绕Gate。describe.ports提供有界名称/索引/类型；verified仅连接回读，不证明语义；连接后仅必要时调整落位","returns":"dict"},{"name":"node_info","sig":"parent, type_name, parm_filter='', limit=24","desc":"创建前读取实际parent最新版类型、端口、参数默认值/组件名/menu token/set_value与帮助URL；parm_filter只作字面子串筛选。按钮条另给menu_kind与赋值语义，conditionals保留参数自身的原生条件，不推断当前启用状态或父folder条件。operation_card含决策/版本，operation_parameters保留不受筛选/limit裁切的关键设置，缺字段显式报告。不建临时节点/不运行Shelf；动态菜单需list_parms，truncated明示。没有delivery准入","returns":"dict"},{"name":"modeling_dimensions","sig":"quantities, require_meter_scene=True","desc":"只读源单位换算：quantities={name:{value,unit,min?,max?,source?}}，最多64项；长度m/cm/mm/um/in/ft转米，面积/体积按平方/立方换算，rad转deg、count/ratio不按长度缩放。默认要求当前HIP=1m且不改单位；旧工程须显式False并消费scene_values。返回原始依据、canonical_values、scene_values及米制CTRL spec；不证明最终尺寸","returns":"dict"},{"name":"sop_recipe","sig":"kind, spec=None","desc":"只读普通SOP配方，catalog给schema，kind单独调用给结构模板示例；hinge/slider/repeat共享origin/axis及CTRL标量，Merge源与附件→FRAME→Copy；sweep_tube/profile_shell为单中心线/平面薄片成形；guided_slider用真实source/guide投影推导位置并拒绝越界，surface_attach在指定面组投影并取法线frame；gusset/fastener提供带厚度肋板与头杆源。返回nodes/output/required_outputs交给build_module，不创建/cook；不猜坐标、不认领输入、不保证接合。字段、适用前提和反例见SOP配方reference","returns":"dict"},{"name":"control_test_plan","sig":"controller, parameters, max_cases=16, domain=None","desc":"只读数值参数规划；1..8标量各2..8显式levels，最多4096候选，贪心覆盖levels与两两组合，最多16case。domain只预筛独立无keys标量，记录排除数与missing；返回tests的expectations为空，须由作者补独立指标/状态接口后test_controls执行，不是全域证明","returns":"dict"},{"name":"build_module","sig":"parent, nodes, output, dry_run=False, interfaces=None, *, required_outputs=None","desc":"批量新增{name,type,parms?,inputs?} SOP节点，列表非空；inputs可引用任意声明/现有直属child名，声明顺序自由，None保留空槽。先创建全部节点，再接线、设参，表达式可引用本批任意节点。独立静态错误汇总零创建拒绝；size=1/组件按标量校验，多分量tuple接受等长数值列表，与实际setter同源。dry_run只预检真实类型/参数/引用；操作知识按需读node_info，不从缺字段推断未决设计。required_outputs可显式检查必需新分支，可附实际interfaces。返回validation/interface_checks；失败清理本批新节点，不覆盖已有节点/flags","returns":"dict"},{"name":"verify_network","sig":"parent, output=None, nodes=None, limit=512, require_valid=True, *, output_index=None","desc":"SOP checkpoint：必须显式output，不跟随display。output_index=0..63另验同父网络原生Output接线；默认检查直属范围，可nodes限域，error/空输出默认拒绝。geometry给bbox_min/max/size，所有显式输出均回scene_unit_length_meters与bbox_size_sop_local_mm，须结合OBJ变换核物理尺寸。handoff_output给出名称/type/Null/leaf、显示/渲染旗标及父网络当前出口。不按输出名称追加表面或上游Sweep检查；需要时显式调用geo_piece_stats等领域工具。它不自动发布，不证明OBJ可见、部件关系或艺术质量","returns":"dict"},{"name":"set_object_parent","sig":"child, parent, keep_world=True, reason='', index=0, allow_foreign=None","desc":"显式 OBJ parenting/unparent（`parent=None`），自然参数序为 child→parent；普通父级用 input 0，Blend 等明确多输入对象可指定 index。`reason` 为可选自由用途说明，表示与方法由当前任务决定。拒绝非 OBJ、自环/层级环；mutation/ownership 边界在 child；默认恢复 child 原世界变换并回读 parent、local/world delta","returns":"dict"},{"name":"disconnect_input","sig":"dst, index=0, *, allow_foreign=None","desc":"断开普通网络 destination 输入；权限理由keyword-only非空字符串；OBJ unparent 拒绝并指向 `set_object_parent(child,None,...)`；ownership 边界在 dst，返回原 source path（若本来为空则为 null）","returns":"dict"},{"name":"rename_node","sig":"node, name, allow_foreign=None","desc":"重命名","returns":"新 path"},{"name":"delete_node","sig":"node, allow_foreign=None","desc":"删除前核对全部后代身份；原生Network Box中的Sticky Note按独立便签权限检查，删除与恢复保留成员身份，不支持的其他编辑项明确拒绝。返回外部参数引用及最多64项affected_connections（目标输入、原源输出及inputs_after），提示原生删除可能旁路重接，同名新节点不继承接线。拒绝删除owner-tagged render_view会话级基础设施。创建时同步新HDA的延迟定义后登记原生后代；不收养后来加入的foreign子节点","returns":"dict"},{"name":"cook_node","sig":"node, force=False, timeout_ms=30000","desc":"cook + error/warning，timeout_ms为1..120000的协作预算，仅原生中断检查点可响应，不保证强制停止/内存安全。Manual返回ok=False/status=not_cooked_manual，不自动切Auto；预检输入计数恒条件、平直删除语句组成的已知无界VEX循环，未知控制流不作安全认证。依赖规模本身不拒绝；verify_network的内部只读批次共享一次完整上游预检，不跨调用缓存。warning未解释不得当完成","returns":"dict"},{"name":"sop_set_output","sig":"node, render=True, allow_foreign=None, *, output_index=None","desc":"默认仅移动SOP display/render旗标。显式output_index=0..63复用/创建同父网络原生Output并接线，将旗标设到它；重复索引/循环/foreign接口写入拒绝，逐层发布不猜祖先。返回public_output接线事实，不cook/保存HDA，须另验几何、新实例与根显示；不是render_view前置条件","returns":"dict"},{"name":"sop_output_node","sig":"parent","desc":"报告 SOP 网络 display/render 输出；旗标不在链尾时提醒","returns":"dict"},{"name":"set_object_visible","sig":"node, visible=True, allow_foreign=None","desc":"设置单个 OBJ 的 viewport visibility（OBJ 没有 SOP 式 render flag）","returns":"dict"},{"name":"visible_objects","sig":"root='/obj'","desc":"列出 OBJ 层 plural visibility/effective visibility，并附每个对象的 provenance","returns":"dict"},{"name":"layout_nodes","sig":"parent, nodes=None, horizontal_spacing=-1, vertical_spacing=-1, allow_foreign=None, mode='children', *, boxes=None, profile='comfortable', dry_run=False, expected_plan=None","desc":"`children`原生layoutChildren、`flow`节点拓扑分层；已有成员Network Box时，两者无显式nodes的整网重排写前拒绝，明确的局部nodes列表仍可用。盒布局用`handoff`处理叶子框，`component`处理一层组件容器，需显式boxes；可直接应用，也可dry_run取得plan_sha256，提供expected_plan时才检查计划仍新鲜。重复应用零写入。默认只移动当前session自有项，单次allow_foreign仅用户明确授权的既有项，持久service不豁免。未选节点/Box与Sticky Note/Dot是固定障碍；量测失败零写入。返回实际节点/盒重叠、containment和净距；只证明network-editor布局，不证明接线或艺术质量","returns":"dict"},{"name":"network_boxes","sig":"parent, groups, *, remove=None, dry_run=False, expected_plan=None, allow_foreign=None","desc":"按显式groups整理Network Box：每项需要name，可选label/role/members/boxes/color；label默认name，role只提供颜色提示，未知role用中性色。members为parent直属节点，boxes可引用已有框或本批声明框，两类成员可共存，声明顺序自由，真实循环写前拒绝。可直接应用，dry_run为可选零写入预览，expected_plan仅在显式提供时核对新鲜度。已有框保留现色，显式RGB三元组才改色。移动显式成员时核对实际受影响的来源框和目标框权限；Box权限独立记录，foreign需单次授权，render服务不豁免。失败恢复成员、位置和外观；分组本身不cook、不证明布局或几何正确","returns":"dict"},{"name":"network_controls","sig":"parent, controls=None, *, remove=None, allow_foreign=None","desc":"明确声明实际控制入口：controls为node/label对象列表，remove为显式节点列表，目标须在parent范围内且遵守ownership。声明保存在节点userData，随HIP保存、改名保留；省略controls/remove只读列出parent内的已声明入口，不按名字或参数数量猜角色、不cook。节点交付卡片复用同一控制声明；不证明联动或正确性","returns":"dict"},{"name":"network_notes","sig":"parent, notes=None, *, remove=None, allow_foreign=None","desc":"读取或局部维护明确名称的Sticky Note；省略notes/remove只读返回实际text/position/size/color与归属。notes项需要name/text，可选position/size/color；默认新Note放在现有内容旁，显式remove不扫全网。Note按实际session identity独立归属，不因名称/parent认领，渲染服务永不豁免；预检及失败恢复保留事实。Note不隐式加入Box，是后续布局固定障碍；文字不证明业务正确或维护完成账本","returns":"dict"},{"name":"present_nodes","sig":"nodes, *, allow_foreign=None","desc":"明确交付节点入口，nodes为node及可选label/role/description/new_identity的1..16项列表；role为control/output/node，只表达导航用途，description为<=200字符的单行操作说明。返回context来自真实节点类别，说明和路径属于交付时观察。缺少持久标识时在目标节点userData写UUID，真实修改遵守ownership；显式new_identity只用于续新标识，旧引用失效。成功批次从present_nodes动词回执显示节点卡片，不依赖__result__包装，与DSH文件交付并列。声明后保存同一HIP，重开/改名仍可定位；不存在或复制导致重复不按历史路径猜目标，不写独立交付账本","returns":"dict"},{"name":"focus_node","sig":"reference, *, expected_hip","desc":"在Bridge主线程队列按持久id与原交付HIP进行显式界面导航，适用于节点卡片点击。定位同一实际节点并打开参数页、展开祖先框；不同HIP、缺失或重复id明确拒绝。只改变导航/框展开，不改模型参数/几何或加载保存HIP；历史runtime sessionId不作为持久节点身份","returns":"dict"}]},{"domain":"parm 域","note":"parm 域（依附 node）","verbs":[{"name":"list_parms","sig":"node","desc":"参数**目录**：名字/标签/类型/帮助/默认值及实际menu token/index/label/set_value、menu_kind、menu_setting和参数自身conditionals（不给当前值，不推断是否生效）；动态菜单以实际节点为准。toggle_strip条目为位值，0清空、组合整数精确替换；exclusive_strip为选项索引","returns":"list"},{"name":"read_parms","sig":"node, changed_only=True, *, names=None","desc":"参数**值**：默认只看非默认 + 带表达式/动画 + 被引用的（意图解读）；names可选1..32个唯一标量或tuple字段，按请求顺序返回且不受changed_only过滤，tuple给聚合value/component_names及逐分量诊断，缺失报错。无动画string含原始UTF-8源码source_sha256，展开值不同于原文时另含raw_value；表达式附referenced_parm，被引用标referenced_by；动画附time_dependent/key_count/first_frame/last_frame/curves，不默认倾倒全部keys","returns":"list"},{"name":"set_parm","sig":"node, name, value, allow_foreign=None","desc":"设参（数值字符串=表达式）。已有表达式/keys在普通赋值时清除，note说明变化。字面string可传`{expected_sha256,patch:[{old,new,count}]}`：精确版本和次数、全部锚点先验，拒绝锁定/动画/表达式/callback/固定菜单；返回patch前后hash/字符数/次数及value_omitted，不回传整份源码。最多32项，source/result各524288字符、替换文本累计131072字符、count为1..256；不执行正则/脚本。文本通过不证明cook/几何通过","returns":"dict"},{"name":"set_parms","sig":"node, values, allow_foreign=None, strict=True","desc":"默认严格批量设参：预检名称/重叠/锁定；value支持set_parm的string patch对象，本节点本批全部patch在任何设参前验证。patch只允许strict=True，set内返回变化摘要，patched列出字段；失败恢复本批值/表达式/keys。其他节点不在本批预检范围，参数回调/外部文件不属快照回滚。无patch的显式strict=False仍返回ok/set/failed；Menu string为精确token，数值string为HScript表达式，表达式对象可声明language","returns":"dict"},{"name":"set_keyframes","sig":"node, channels, replace=True, allow_foreign=None","desc":"批量写数值标量 channel keys；统一 frame 单位，有限曲线 `constant/linear/bezier`。全量预检包含锁定状态，失败恢复原值、表达式、keys和frame，并明确restored/restore_errors；提交后回读/采样并恢复用户frame。只负责channel数据，不代替路径依赖状态机或KineFX/APEX","returns":"dict"},{"name":"create_spare_parms","sig":"node, code_parm='snippet', defaults=None, spec=None, allow_foreign=None, *, update_defaults=None, layout=None, dry_run=False","desc":"缺省扫描代码参数的 `ch/chf/chi/chv/chs` 引用并创建缺失 spare parameters。`spec=[...]` 的精确条目为 folder `{type,name,label?,parms:[...]}` 或 scalar `{type:'toggle\\|int\\|float\\|string',name,label?,default?,min?,max?,min_strict?,max_strict?,help?}`；spec必须用具名参数，严格上下限字段只接受min_strict/max_strict。spec 返回 `{node,mode,created,leaf_values}`；扫描返回 `{node,code_parm,references,created,existing,defaults_applied,unsupported}`；创建仍拒绝同名覆盖。新建接口后重新赋写code_parm原始源码/keys以刷新编译依赖，保留表达式与动画；返回refreshed_code_parm（未刷新为null），锁定源码在接口写入前拒绝。显式 `update_defaults={name:literal}` 仅更新1..32个已有scalar spare的默认值，与spec/defaults/非默认code_parm互斥；保留当前值/表达式/keys，返回updated前后值及current_state_preserved。支持float/int/toggle/string，拒绝内建/tuple/menu/callback/multiparm及表达式默认值；当前值另用set_parms。layout与spec/defaults/update_defaults互斥，复用共享UI组件，默认追加并拒绝已有模板/参数名冲突；dry_run仅layout有效，预览零写入。应用保持已有通道值/keys/locks，失败恢复节点接口及通道，不修改HDA定义或绑定","returns":"dict"},{"name":"parameter_ui","sig":"node, max_depth=6, include_state=False, analyze_ui=False","desc":"任意节点参数界面只读自省：类型/可选定义文件与section、实例interface及definition.interface，含范围/默认表达式/回调/菜单生成器/条件/tags、tuple look和Ramp类型。include_state返回至多512通道raw值/keys/locks；analyze_ui返回非阻断结构建议。不执行菜单/表达式/cook，不自动修复或创建绑定","returns":"dict"},{"name":"bind_controls","sig":"controller, bindings, *, dry_run=False, expected_plan=None, replace_existing=False, allow_foreign=None","desc":"1..32项明确数值绑定：source为控制节点参数名，target为目标参数绝对路径，可选scale/offset。dry_run返回plan_sha256；应用必须expected_plan匹配identity/值/keys/锁定/帧。默认拒绝已有驱动，replace_existing显式替换；拒绝非数值/菜单/回调/multiparm、任意表达式源、批次源目标交叠及重复目标。整数目标只接受整数源与映射系数。实际HScript引用和值回读，失败恢复本批目标通道；不保证领域输出或外部副作用","returns":"dict"},{"name":"set_update_mode","sig":"mode, expected_mode","desc":"显式切换auto/manual/on_mouse_up，expected_mode防止覆盖过期用户状态；无GUI拒绝on_mouse_up（原生会降为auto）。after/changed取实际回读，未应用请求或setter失败会尝试恢复并报告结果；模式恢复不撤销触发的cook/外部副作用。切Auto可能触发全场景计算，不是取消接口","returns":"dict"}]},{"domain":"scene 域","note":"scene 域（工程/时间线）","verbs":[{"name":"scene_info","sig":"","desc":"只读 HIP/version/fps/current frame/time/frame range/playback range/UI 状态及 `unit_length_meters`（1 个场景单位对应的米数，无法读取时为 null）；明确区分 `has_named_path`、`has_unsaved_changes`、`dirty_reliable`、`clean_on_disk`，不再用路径存在冒充保存完成；hython 的 dirty 不可靠时 clean=null；不移动 playbar、不遍历整张节点图","returns":"dict"},{"name":"scene_save","sig":"expected_path=None","desc":"只保存当前已命名 HIP，不承担 Save As/open/new；可选 expected_path 作防串场断言，返回 dirty before/after/reliable、clean（headless=null）、bytes、mtime_ns","returns":"dict"},{"name":"scene_save_as","sig":"path, expected_current_path, reason, overwrite=False","desc":"用户授权的 Save As：明确绝对 HIP 路径，expected_current_path 防串场，reason 记录路径/覆盖授权；已存在目标必须 overwrite=True。拒绝插件仓库落盘，回报前后路径/dirty/file/workspace_changed。无 load/clear；文件写不可撤销，失败可能留部分新文件，跨目录后 Open Workspace 重新绑定","returns":"dict"},{"name":"set_timeline","sig":"fps=None, frame_range=None, playback_range=None, current_frame=None","desc":"设置明确的时间线字段；至少一项，所有字段的有限数值/范围写前校验，成功回读scene_info。写入失败恢复fps、两种范围和当前frame并报告restored/restore_errors；不恢复触发的cook或外部副作用","returns":"dict"},{"name":"list_bookmarks","sig":"","desc":"列出 bookmark id/name/start/end/enabled/visible/comment","returns":"list"},{"name":"create_bookmark","sig":"name, start, end, replace=False","desc":"创建整数帧 bookmark；同名默认拒绝，replace 精确替换","returns":"dict"},{"name":"delete_bookmark","sig":"name_or_id","desc":"按精确名称或 session id 删除，失败列现有项","returns":"dict"}]},{"domain":"geometry 域","note":"geometry 域（几何数据）","verbs":[{"name":"geo_attrib_stats","sig":"node, name, attrib_class='point', *, unique=False, max_elements=100000","desc":"数值min/max/mean/count；unique=True全量检查精确完整tuple（含字符串），返回unique_count/duplicate_count/all_unique及至多8个重复样本。用P查精确重叠、用id查身份；超预算/非有限拒绝，无容差焊接或自动删除。point/prim/vertex/detail","returns":"dict"},{"name":"geo_point_spacing","sig":"node, expected, tolerance, closed=False, order_attrib=None, max_points=10000","desc":"全量相邻点弦长验收：默认point number顺序，或唯一数值order_attrib；closed含末→首，SOP local单位；返回全量min/max/failure_count及最多16个最差对与sequence hash。超预算拒绝不抽样；只证明该序列约束，不证明弧长、网格接线或实际零件关系","returns":"dict"},{"name":"geo_check_interfaces","sig":"output, interfaces, max_pairs=50000","desc":"同一最终SOP内1..16实际关系。默认{id,source_group,target_group,max_distance,expected_points}测独立表面点到面距离；method=axis_gap用两个primitive组及axis/gap_range/min_overlap测投影间隙。method=solid_overlap用两个独立完整闭合朝外Polygon实体组和max_overlap_volume，在内存副本做Boolean Intersect量实体相交体积，非零有效交集返回SOP局部包围盒（多处交集仅为外包络）；实心轴穿实心铰耳fail，有孔且留间隙pass，开放/不完整/非Polygon/数值含糊为unverified。method=axis_passage用最终Polygon target_group、axis及SOP local start/end测一条跨越该组包络的轴线；碰到最终表面fail，无遮挡pass，缺组fail，非Polygon/未跨包络unverified。它不证明孔径、孔壁或其他轴；后续增材须复验。solid_overlap每组最多20000面；面包围盒扫描筛候选，共用max_pairs候选预算与2000000扫描访问预算，完整实体仍交Boolean处理包含关系；不建场景节点、不抽样。零交集不证明同轴或真实穿孔；三态分别检查，不证明连续运动、受力或公差。返回实际值/范围/几何hash","returns":"dict"},{"name":"test_controls","sig":"controller, output, tests, interfaces=None, allow_foreign=None, *, domain=None, topology=None, baseline_interfaces=None, views=None, view_bounds=None","desc":"可恢复数字控制测试，必须exec：1..16个 `{id,values:{parm:number},expectations:[{metric,axis?,group?,delta:[min,max]}],interfaces?}`，每个case最多16个expectations；同一扰动的大检查用相同values拆成多个case。metric支持bounds_size/center/min/max(axis)、point_count、primitive_count、area、point_mean(axis)、boundary_edges、piece_count、max_point_displacement/mean_point_displacement；max_transform_error另给16数row-major仿射transform，测实际点相对声明变换的最大残差。位移/变换要求稳定唯一id_attrib和相同Polygon拓扑。range验基准/扰动绝对范围，至少一项delta排除0。顶层interfaces在基准和全部case复查，baseline_interfaces只验基准，case内interfaces只验对应扰动；适合合盖接触与开盖分离等不同合同，均用geo_check_interfaces的schema和预算。control_summary区分已声明与实际执行的关系覆盖；基准失败时参数零写入且results=[]明确标not_run。domain/topology复查声明关系；恢复参数/keys/frame及完整bgeo内容（内嵌Packed临时地址转内容引用、忽略对应writer索引偏移；排除导出头date/派生group_summary，组目录按名规范排列；保留成员及组内顺序）。Polygon/Mesh/Sphere/Tube/点支持范围各指标明确，嵌入PackedGeometry在内存副本展开量测，原载荷/属性/变换按内容指纹验证恢复，其他写前unverified。拒绝callback/menu/button/multiparm/tuple列表值，foreign需单次授权；只证明声明case，非外部副作用恢复或艺术/强度认证","returns":"dict"},{"name":"geo_piece_stats","sig":"node, piece_attrib=None, sample=16, *, inspect=False, group=None, basis=None, integrity_only=False","desc":"默认统计primitive piece局部bbox/extent/面积；无piece属性用内存Connectivity SOP Verb。inspect=True按精确primitive组观察有界Polygon边界/非流形/边连通、正交basis下extent、surface_area、duplicate_boundary_faces、closed_planar_components及center_axis_surface_hits。仅近看Polygon完整性时用inspect=True, integrity_only=True：跳过昂贵的中心线/截面诊断，最多100000 prim/400000顶点引用，返回非流形、相邻面朝向冲突、闭壳有向体积符号、显式N与几何朝向相反的样本、零面积/零边及完全重复面风险；平面大面以重复点桥接孔时另报planar_repeated_point_ngons/shading_review_status，提示同角度近景复核，不把合法布线判破面。负号提示核对整壳朝向，嵌套空腔的内壳可有意反向，不能自动判错。开放边单列open_boundary_unreviewed，可能是有意接口，需按设计核对。风险/超预算在Bridge摘要与执行提醒中保留；no_detected_integrity_risk只表示本检查未发现列出的风险，不认证任意重叠、自交、接触、外形、着色或强度。普通完整inspect仍保持原预算与语义；不支持或超预算为unverified","returns":"dict"},{"name":"geo_frame_diff","sig":"node, frame_a, frame_b, attrib='P', sample=4096, tolerance=1e-6","desc":"用geometryAtFrame比较两帧point数值属性，correspondence为point_number，不能证明跨拓扑变化的稳定身份。可比较时精确返回键`mean_delta`、`max_delta`、`delta_percentiles.{p50,p90,p99}`、`component_delta.{min,max,mean}`、`unchanged_pct`（另含sampled_points/tolerance/data_type/size），不是`mean/max`。不移动playbar；只证明所声明对应与抽样范围内的数据变化，不单独证明审美/运动语义","returns":"dict"}]},{"domain":"component 域","note":"component 域（普通 SOP 组件交换）","verbs":[{"name":"component_export","sig":"node, filename, contract","desc":"候选：当前作者普通SOP subnet导出至已命名$HIP内新.dshcomponent；contract必含module_id/revision/units/outputs，可选inputs声明公共输入槽位（唯一0..63），输出索引须由sop_set_output发布。运行时verb_help提供可执行的最小示例和字段约束；检查公共输出、有限依赖与快照。同构建往返，不覆盖文件，不证明装配质量；文件写入不可Undo","returns":"dict"},{"name":"component_import","sig":"parent, filename, expected_sha256, name, trusted=False","desc":"候选：显式可信、hash固定、同构建普通subnet片段导入当前作者SOP父网络；SHA-256接受大小写十六进制并返回规范小写；新名字、不覆盖、不接管旧节点，返回待验收candidate。原生档案可执行代码，trusted不构成安全沙箱；尚非自动子作者交付通道","returns":"dict"},{"name":"component_replace","sig":"node, candidate, dry_run=True, expected_plan=None, expected_contract=None, migration=None","desc":"候选：同作者同父普通subnet的显式替换；先预览，再用未过期plan提交。输出接线总是迁移；已连接根输入、公共参数值/keys及其外部表达式消费者只在migration显式声明时迁移（inputs逐槽映射、public_parms按名），未声明即拒绝，不按位置猜。保留旧网络不删除/改名；plan失配按侧命名（old手改=保留的本地分叉/candidate被改/消费者接线变化/身份重建/迁移面漂移）。expected_contract恰含module_id+正整数revision，把候选钉在本session导入记录的合同上，拒绝迟到的旧修订与无provenance候选。带表达式的keyframe、keyframed消费者、不可识别的表达式引用形态明确拒绝；任何失败逆序恢复接线/表达式/参数值（回滚账本先登记后变更，恢复失败聚合上报RuntimeError）。提交后仍须实际装配关系/视觉复验","returns":"dict"}]},{"domain":"runtime 域","note":"runtime 域（运行时包自省）","verbs":[{"name":"tool_catalog","sig":"query='', kind=None, category=None, origin=None, offset=0, limit=64","desc":"当前Houdini实际node_type/Shelf/Panel/Viewer State/Radial注册目录，分页有界查名称/标签；category精确原生类别，origin按资源位置区分factory/external/embedded/unknown，不认证发行方。保留hidden/deprecated，GUI缺失明确unavailable，不扫描磁盘或执行工具；不是授权/安装账本","returns":"dict"},{"name":"tool_inspect","sig":"kind, name, category=None, include_code=False, max_chars=16000","desc":"精确读取当前工具来源、HDA实际/候选定义、界面和实例，按需读取有界公开脚本；node_type/viewer_state要求category，不建临时实例。Package归属只报告原生root路径关系；编译节点内部实现、独立state源码未知不猜测。发现不授权修改","returns":"dict"}]},{"domain":"cop 域","note":"cop 域（Copernicus 图层与关系）","verbs":[{"name":"cop_layer_stats","sig":"node, output=0, *, max_pixels=4194304","desc":"必须exec：直接读取当前ImageLayer，output为源输出名/索引；完整buffer统计/指纹、类型/通道、data/display window、空间、pixel scale、frame、U/V梯度。max_pixels为1..16777216，超预算拒绝不抽样，预算不限制上游GPU cook分配。拒绝Manual、失败cook、非图层和未支持storage；非有限值fail，sticky Cache新鲜度unknown；不证明视觉或外部文件最新","returns":"dict"},{"name":"cop_compare_layers","sig":"before, after, *, before_output=0, after_output=0, expected_delta=None, tolerance=1e-6, max_pixels=4194304","desc":"必须exec：测after-before，完整通道/窗口/空间对齐，不静默重采样；无expected_delta仅量测status=unverified。expected_delta={node,output?}时检验max(abs((after-before)-expected_delta))<=tolerance，返回实际操作数/公式/误差；非有限、错位拒绝，sticky Cache不认证通过；不判断作者选对了数学对象或艺术效果","returns":"dict"},{"name":"test_cop_controls","sig":"controller, output, tests, *, output_port=0, max_pixels=4194304, allow_foreign=None","desc":"必须exec：1..16个{id,values:{parm:number},expectations:[{metric,channel,delta:[min,max],range?}]}；metric为mean/min/max/mean_abs_change/max_abs_change，变化指标基准0。每case至少一项非零预期，range验基准与扰动；复用参数/keys/frame恢复并比较完整图层/元数据指纹。拒绝菜单/回调/multiparm/tuple、Manual、sticky Cache和无效基准；恢复失败抛CheckpointError，已恢复的失败仍fail。仅声明case/输出范围，不恢复外部文件/Python/solver副作用，不替代语义读图","returns":"dict"}]},{"domain":"stage / USD 域","note":"stage / USD 域（Solaris 只读自省）","verbs":[{"name":"usd_stage_summary","sig":"node, max_paths=64","desc":"概览某 LOP 输出 stage 的 geometry/material/light/camera/RenderSettings/Product/Var，材质绑定、time-sampled 属性及 cook warning；路径按组限量但计数完整","returns":"dict"},{"name":"usd_prim_info","sig":"node, prim_path, max_properties=200","desc":"检查单个 USD prim 的属性、primvar、relationship、material binding、time samples；points/topology 等大数组只报结构不整段拉取","returns":"dict"}]},{"domain":"tool package 域","note":"tool package 域（原生工具包开发与注册）","verbs":[{"name":"package_catalog","sig":"directories=None, query='', offset=0, limit=64","desc":"顶层原生JSON配置与当前Houdini加载记录合并查询；默认实际扫描目录或明确目录，区分磁盘配置/条件/加载，不读全部源码、不递归子目录。支持普通包名、多个资源位置和未加载包，未知动态条件不猜算","returns":"dict"},{"name":"package_inspect","sig":"package_file, *, files=None","desc":"精确只读原生注册配置、hash、多资源路径、当前加载及浅资源/显式文件事实；兼容hpath/path/env写法，公共脱敏投影不能当原文件写回。注册名称冲突由action预览检查；实际来源不证明授权、可用性或完整依赖，条件未知明确unresolved","returns":"dict"},{"name":"tool_package_create","sig":"resource_root, package_file, *, houdini_versions=None, enable=True","desc":"仅创建全新原生JSON，追加指向明确的既有源目录；不复制源、不加载、不创建无用途目录，不覆盖已有JSON或写$HFS。兼容版本声明可选，是加载条件而非测试证书，返回真实注册和源码位置","returns":"dict"},{"name":"tool_package_action","sig":"package_file, action, *, dry_run=True, expected_sha256=None","desc":"明确原生配置的当前进程load/activate/deactivate/unload，预览默认零写入，可核对配置hash；不改持久enable/条件/依赖，不删除注册或源，不强制清理缓存/窗口。保护当前HDA实例依赖，加载/根错位/部分失败保留真实状态；当前动作不证明下次启动状态","returns":"dict"}]},{"domain":"asset 域","note":"asset 域（HDA / 数字资产）","verbs":[{"name":"hda_create","sig":"node, name, description=None, hda_file=None, min_inputs=0, max_inputs=0, replace=False, allow_foreign=None, *, max_outputs=None","desc":"转为全新独立类型/库，默认 `$HIP/otls/<name>.hda`；已有类型/目标文件和replace=True拒绝，不破坏旧实例或多资产库。成功登记实际新库与定义的session写入来源，实例ownership不授予外部定义权限。max_outputs为1..64端口上限；spare迁移、新实例和公共输出仍须验证","returns":"dict"},{"name":"hda_fork","sig":"node, name, hda_file, description=None","desc":"只读复制实际源HDA定义到不存在的新类型/独立库，保留源定义及所有实例；不自动建实例或迁移用户内容。成功登记新库/定义，返回category/type/source_library等真实身份；官方可见可编辑HDA也可分叉，编译实现不支持","returns":"dict"},{"name":"hda_version","sig":"node, version, *, dry_run=False, allow_foreign=None","desc":"在实际来源库追加同scope/namespace/base的原生::version定义，旧版本/其他定义保持，不另存交付副本、不迁移实例；重复目标拒绝，本调用失败恢复库和新增类型。foreign库授权单次且不认领。仅复制已保存定义","returns":"dict"},{"name":"hda_switch_version","sig":"node, type_name, *, dry_run=False, allow_foreign=None","desc":"指定单个已锁定实例切换同家族精确已安装HDA版本；原生保留名字/公共参数通道/连线，使用新版内部网络。未保存内容先hda_edit处理；根/被替换后代须授权。当前session自有实例仅登记本次切换新建的内部identity，不认领已有节点或foreign实例的后代。回调外部副作用不受scene undo保证","returns":"dict"},{"name":"hda_get_section","sig":"node, section='PythonModule'","desc":"读 HDA section 内容；section 不存在时列出现有 section 名供自纠","returns":"dict"},{"name":"hda_set_section","sig":"node, section, code, allow_foreign=None","desc":"全量写section；先语法预检，核对库来源与共享实例，写后逐字回读，失败恢复本调用sections/库/根界面/通道。后续exec失败不撤销此前成功库写入，任意回调副作用不属恢复范围","returns":"dict"},{"name":"hda_patch_section","sig":"node, section, old, new, count=1, allow_foreign=None","desc":"锚点局部替换：`old` 必须恰好出现 `count` 次（0 = 锚点没找到，>count = 锚点不唯一需加长），替换后同样过语法预检；**模块改局部时用它，不要全文重发**","returns":"dict"},{"name":"hda_set_interface","sig":"node, spec=None, keep_std=True, hide_builtin_tabs=False, allow_foreign=None, *, edits=None, expected_sha256=None, dry_run=False, layout=None","desc":"spec/layout整组重建，均检查共享实例ownership；layout与spec/edits互斥，最多512条/12层。支持label/ramp、tuple、multiparm、条件及组件；SOP标准输入Label隐藏。dry_run各模式统一返回ok=true、dry_run=true、applied=false、scene_writes=0，只表示预检成功；spare冲突写前拒绝。edits成功保留旧通道，重建成功不保证旧通道；重建写后失败恢复本调用定义section、实例界面/通道及磁盘库（<=32MiB、64实例、每实例512通道），返回restored/restore_errors。定义写入独立于场景Undo，后续exec失败不撤销已成功的库写入，外部副作用不保证恢复","returns":"dict"},{"name":"hda_edit","sig":"node, action, *, dry_run=False, expected_plan=None, discard_changes=False, allow_foreign=None","desc":"受控unlock/save/lock/promote，不拆包。先dry_run取得plan_sha256，应用须expected_plan匹配库/定义/源码/实例状态；<=32MiB库、512可编辑后代、64实例、2MiB源码。锁定嵌套HDA的内部实现不计入作者工作量，明确解锁后重新计入；descendant_count仍是全部后代，editable_descendant_count是工作量，身份检查及lock丢弃授权仍覆盖全部后代。save要求解锁且无实例界面覆盖；promote显式提升源spare界面并保留已有根参数/keys/locks，拒绝其他实例覆盖与既有模板删除/变型。共享写入检查所有实例；lock丢弃内部修改须discard_changes=True且后代也获授权；unlock不授予后代ownership。save/promote写后失败恢复本调用定义/根界面/通道/磁盘，不保证外部副作用或后续exec失败恢复。返回状态/哈希不证明公共输出、回调、GUI或依赖通过","returns":"dict"}]},{"domain":"render / sim 域","note":"render / sim 域（渲染产物）","verbs":[{"name":"camera_fit","sig":"camera, target, direction='iso', coverage=0.82, width=None, height=None, frame=None, *, dry_run=False, allow_foreign=None","desc":"将正式静态OBJ cam拟合到显式SOP世界包络；保留焦距，清lookatpath，求距离/正交宽度，实际矩阵投影回验；无渲染/视口改变。尺寸默认相机值，当前frame。拒绝动画/约束/窗口偏移/自定义lens，失败恢复。ownership与单次allow_foreign适用，持久preview服务永不豁免；dry_run仍exec。Solaris需导入并按实际RenderProduct预检","returns":"dict"},{"name":"render_frame","sig":"rop, picture=None, frame=None, timeout=110, *, framing=None","desc":"渲染可执行hou.RopNode并验证新鲜产物；USD优先outputimage。可选framing={target:USD资产prim路径,coverage:.82}在renderer启动前检查实际stage所有产品的相机/有效画幅/裁切窗口；不通过或不支持时零渲染，不自动动相机。未传保持艺术裁切/通用ROP语义。临时picture/foreground/frame恢复；bytes/mtime/有界摘要确认fresh，旧文件失败；>110s走job。共享执行端模式取registry渲染单槽，被占即快速拒绝","returns":"dict"},{"name":"render_view","sig":"node, direction='iso', frame=None, width=1280, height=720, picture=None, framing='full', coverage=0.82, framing_frame=None, *, output_policy='managed', focus_group=None, isolate=False, projection='perspective', framing_bounds=None, depth_bounds=None","desc":"显式SOP→持久proxy→服务相机及对应版本后端，恢复用户状态，服务不删除。output_policy默认managed用于验证；delivery分配最终图到`$HIP/dsh-artifacts/renders/<HIPNAME>/`，两者picture省略或仅安全basename、唯一不覆盖；路径值选explicit，继续服从原$HIP/绝对路径保护。返回artifact含purpose/policy/actual/相对路径/root/run/capture/frame，旧output保留。full完整入镜；detail只缩正交宽度/透视视角，不推进相机，近远裁面错误始终零渲染失败。focus_group指定实际primitive组，可isolate；framing_bounds决定取景，depth_bounds决定全部渲染内容含上下文的深度。A/B用同framing_frame并复用返回framing.bounds/depth_bounds及方向/画幅/模式，越界不漂移。check像素事实与pixels兼容别名、framing.depth_check/crop_reasons、source指纹/stale分别报告；空/error拒绝；源/proxy有cook warning时保留诊断图片和warning，但返回ok=false，不能进入验收完成门。展示格式OCIO编码sRGB；H21缺少匹配空间时明确gamma近似，H22明确拒绝该缺口；EXR/HDR线性；output_color记录方法，不证明语义。共享执行端模式取registry渲染单槽，被占即快速拒绝","returns":"dict"},{"name":"render_check","sig":"path, ref=None","desc":"亮度/非黑/主色/content bbox；A/B 另给高精度 mean、RMSE、changed/meaningful pixel %、max diff，微小非零不再被舍入成 0","returns":"dict"}]},{"domain":"viewport 域","note":"viewport 域（视口/UI）","verbs":[{"name":"viewport_screenshot","sig":"path=None, frame=None, clean=True, frame_target=None, textures=None, backface_cull=False, *, output_policy='managed'","desc":"**用户屏幕诊断工具**：managed/delivery/explicit路径和artifact合同同render_view；delivery直接生成到`$HIP/dsh-artifacts/renders/<HIPNAME>/`，无命名HIP时两种分配拒绝。PNG/JPEG/BMP/TGA为支持截图格式。用户切空display节点时截到空是正确结果，不能用来证明agent产物；和`render_view(explicit_sop)`对照可区分viewport漂移与真实几何错误。要求独立stash的flipbook/viewport camera；绑定相机先解锁并脱离，按请求frame读取bbox，恢复frame/视图后最后还原相机关联/锁定，setter失败与回读不符保留。候选需属于请求frame、连续稳定且可解码；旧/错误frame/无效/歧义文件不算fresh。flipbook派发已尝试但未确认完成的超时/异常/轮询中断保留managed reservation并标capture_unresolved，避免晚到写入与路径复用竞争；实际输出路径复验失败不登记附件。恢复失败以CheckpointError证据拒绝假成功","returns":"dict"}]}]; }
    // <<< houdini-catalog

    // >>> houdini-trace (generated by tools/gen-trace-client.mjs — do not edit)
    var LIVE_JOB_KIND = "houdini-live";
    var LIVE_JOB_RESULT = "dsh-houdini/live-job-result-v1";
    function liveJobResult(value) {
    if (value?.job?.kind !== LIVE_JOB_KIND || typeof value.text !== 'string')
        return;
    let record;
    try {
        record = JSON.parse(value.text);
    }
    catch {
        return;
    }
    if (record?.kind !== LIVE_JOB_RESULT || record.job_id !== value.job.id
        || !record.value || typeof record.value !== 'object' || Array.isArray(record.value))
        return;
    return record;
}
    var traceView;
    function getTraceView(React) {
      if (traceView) return traceView;
      var sources = {"guidance":{"name":"dsh-houdini:guidance","order":150,"hash":"5d826db95f497a9a7c8bd5ea2590d9bfa12ee5eb8bf6d444a34bff300cd9dd1b","bytes":6301,"paragraphStarts":["Houdini tool routing:\nUse houdini_inspect for live read-only scene and API information, ho","Execution boundary and discovery:\nCompose the injected Python verbs for edits. Use the exe","Current catalog: vocabulary 域: verb_help | 类型目录: search_tab_menu, search_tab_entries, reso","Result and recovery contract:\nTool results report execution, checks, restoration and files","Domain knowledge:\nLoad the applicable skill for SOP, COP, HDA/tools, controls, rigging, So","Files and runtime:\nProject directory roles come from scene_info().project_layout, anchored"],"source":"src/index.ts"},"skills":[{"name":"houdini-trace-analysis","description":"分析 dsh-houdini 与 DeepSeek Harness 的原始会话日志，定位 Houdini 任务的完成差距、运行与工作区错位、工具合同、执行反馈、观察和性能问题。用户要求复盘指定或最新 trace、比较会话或据证据调整工具与审计技能时使用。","base":"skills/houdini-trace-analysis","files":[{"path":"agents/openai.yaml","hash":"334a2a7948a5fa607f4c2013deb13bf44398d75e1bf0bb1916707e4659a8ddb0","bytes":278},{"path":"references/audit-rubric.md","hash":"3cee7986662fe0e5f0bf8d94e20a1221ff2de10991e9be18aa63fca2714d534a","bytes":5727},{"path":"references/known-patterns.md","hash":"a435ede38dcc1ef4694cfaf70118561f44eecc10a443a53f5ba3290bbf51e879","bytes":2290},{"path":"scripts/evidence-helpers.mjs","hash":"7e6336b055398ad925d1d26dbc08b0fbe1f0228503d0fc664c61441e708e9783","bytes":71193},{"path":"scripts/extract-trace-evidence.mjs","hash":"322749fffca1d38421a41021fa55b1c63392c2e4474ce8114593feb7519ed994","bytes":26930},{"path":"SKILL.md","hash":"7695e5cf5be4f0be3820fa773d554528f9542c085725819a20c3f2b55b365fff","bytes":7085}]},{"name":"houdini-task-decomposition","description":"将复杂Houdini任务拆成可独立修改和观察的模块，按依赖逐个构建、检查并集成。用于多部件资产、多子系统模拟、跨阶段图像处理或工具开发；单参修改和纯查询直接处理。","base":"skills/houdini-task-decomposition","files":[{"path":"SKILL.md","hash":"0b591554bb806b9b980c7d922086a56d105f19727c7ac6fae2150bfb730f6b60","bytes":8832}]},{"name":"houdini-isolated-execution","description":"用houdini_isolated在一次性独立hython中构建或检查明确builder、已保存HIP副本及其依赖，取得实际输出、缓存或渲染证据。用于需要独立计算、可复现试验或团队成员自验证的工作；简单现场编辑和依赖未保存GUI状态的操作仍使用当前Houdini。","base":"skills/houdini-isolated-execution","files":[{"path":"SKILL.md","hash":"94ca43a67aaa3c4a6b4a64191fc44aa7ab14e50e81edb7583f341cfc7eb3f1eb","bytes":11036}]},{"name":"houdini-sop-workflow","description":"设计、构建、修改和交付可编辑的Houdini SOP程序化网络。用于建模、散布、曲线成形、属性、VEX和SOP动画。纯场景查询直接用工具；HDA工具、rig、COP和Solaris使用对应领域技能。","base":"skills/houdini-sop-workflow","files":[{"path":"agents/openai.yaml","hash":"8628b8dfd3d0765ba6691fcaa0d168df2bcc30d4f464ac40862d86ed70c160e0","bytes":264},{"path":"references/curves-and-routing.md","hash":"dd89fa841127790897f7564e915ee84e57b957f6cc96fe05d38b953a89ef179f","bytes":7565},{"path":"references/execution-checkpoints.md","hash":"4be3ea72d471f6cb38a809f4eee214ab4b60ab309343ac5324ecd9ab13850520","bytes":13470},{"path":"references/modeling-methods.md","hash":"ec5fa322cb8a766d3db3170e0d6a79957c7e3bd026d0e17f7ba9434e11c901bc","bytes":28785},{"path":"references/module-design-collaboration.md","hash":"be2d0c0f0ab0c0976091047fb280f678cc136ec62a743aa0c221ba1237fe921d","bytes":3891},{"path":"references/module-quality-contracts.md","hash":"49ada6560cf919f4a7b8993f2c044eca33fd55482efd659de1d77c2abd79c521","bytes":19764},{"path":"references/procedural-quality-contract.md","hash":"f2a497ab80c5a7a635aeb49fd7548a286d4dc5609b1283e4b4af08b9686785c1","bytes":10078},{"path":"references/procedural-recipes.md","hash":"58f7cebf2e151abcf08107b7818c2038d90b2c1f80e598315fbffb667623e167","bytes":7122},{"path":"references/sop-patterns.md","hash":"e6372b623a1a43ba90c8122663d021fdb41bd45471bf454caeceb1d5489b9b86","bytes":14091},{"path":"SKILL.md","hash":"4367fc3705e21e89a0f463b7b307ca8a795ee7214458912e9fd763a7d6b8fdbc","bytes":6999}]},{"name":"houdini-surface-workflow","description":"为模型与部件设计可编辑的表面外观，分析参考图中的几何与纹理分工，延续已有成果的风格与细节标准，选择细化程度、UV、COP或生成图片，并在SOP中统一预览。用于新模型外观、涂装、贴花、微表面和已有材质修改；纯几何诊断或只生成参考图片不触发。","base":"skills/houdini-surface-workflow","files":[{"path":"references/appearance-and-sources.md","hash":"f4c31c3e1d703d53f4f3ea5a65a604d1b6111c4bbd453bcedf320d3c820bedac","bytes":9929},{"path":"references/generated-textures.md","hash":"181d5566905c811d3f63cb56b69ca00fff299b7d2b174e09f8e5007d10690f7f","bytes":5083},{"path":"references/sop-preview-and-uv.md","hash":"c3345517b49fd52a1c0ed7298e6558fae9c5c50608a001ffc658e6e4a3f70f71","bytes":13175},{"path":"SKILL.md","hash":"fe275ec50eb7fea6cf10d917481743d85f5b26504976e485c7450a77ed8cf461","bytes":7516}]},{"name":"houdini-cop-workflow","description":"在 Houdini Copernicus 中制作、诊断和验证程序纹理与图像处理网络，包括建模中的涂装遮罩、标识/贴花、图像校正、微表面纹理、COP教程复现和文件导出。需要制作或修改图像数据时加载；纯几何建模、常量材质参数、只解析视频或仅消费已有贴图不触发。","base":"skills/houdini-cop-workflow","files":[{"path":"references/cache-and-delivery.md","hash":"2f828e0084649061dd4bb8e36072a394194abfa1a7cc79b7ceff785a49d90f73","bytes":7201},{"path":"references/evidence-and-validation.md","hash":"72978e6863271674b32abdcff27e9d34e3ea58e447c0c5ff409c01fbdb09f2c1","bytes":5661},{"path":"references/layers-and-ports.md","hash":"7adcd143eba07f73240284efea7ada0ade980fd7d200faff6fd36a4bca4d854a","bytes":3902},{"path":"references/pattern-design.md","hash":"a8063357f17aae9ac48d113c0cd46a5eeaa3f8052fc34b2e66e6943cfc337a0a","bytes":8745},{"path":"references/relations-and-controls.md","hash":"4941a611b7c2fd2842c20c2d993e22fd069b9b664bad43f2473e8c909c875766","bytes":6096},{"path":"SKILL.md","hash":"71a9aa094c535394c8b3c3b65805ad8a7babdd5cbf99f60e9d110c9924d9dc42","bytes":6351}]},{"name":"houdini-tool-development","description":"开发、维护和交付Houdini HDA、Shelf/Tab、Python Panel与Viewer State工具，确定工具归属、原生入口与加载范围。普通可调模型或单独保存HIP不触发；纯参数布局使用houdini-parameter-ui。","base":"skills/houdini-tool-development","files":[{"path":"assets/tool-entry-examples/dsh_artist_example_panel.py","hash":"17312b21212b100a0952717581127c4c6b5649d7fdff71ccf33ecc0ca09723b6","bytes":3890},{"path":"assets/tool-entry-examples/dsh_artist_example_state.py","hash":"5499399d79f4dec1fd19a0cf26e6feb5a9521179a5963109a2b2dc5c547ed777","bytes":2379},{"path":"references/evidence-and-validation.md","hash":"570e92ffa41f75112307cc7e17a0c48f1d25676d8e7368a28af8e4d4b61bc399","bytes":11247},{"path":"references/hda-maintenance.md","hash":"68e854e92052848b56a81b5ca88716791d6dde98f8442b26429568c762f5142b","bytes":14245},{"path":"references/hda-ui.md","hash":"856872286a1c9acec59ac7bdd7be7e08b09986b5849b0bf4a8efcd6e9c45c248","bytes":262},{"path":"references/scripts-and-packaging.md","hash":"8ec8ad6f75bbd4da4494aeccc618b2dc24dd61940dfeceb9b9bc0cff2a6f918e","bytes":12420},{"path":"references/shelf-and-hotkeys.md","hash":"dcbe33bb694cf1990c55ad9d36602df9ed88e8d31cd8b75712852a4647d44385","bytes":6280},{"path":"references/ui-components.md","hash":"25d24be85f8a46d6db870278795c0ff68c325150071411f1d2def59bced689b4","bytes":303},{"path":"scripts/build-entry-examples.py","hash":"c025445c864028ec149c148cd36dde80bc22b68a5e9185638f1853fbff246826","bytes":4124},{"path":"SKILL.md","hash":"3f562add256ed70e3190b1f2c1fe4b4d52f597fec06c349a0fefd7a830e93bff","bytes":6373}]},{"name":"houdini-parameter-ui","description":"设计、建立和维护Houdini参数面板、程序化模型控制节点与场景总控；定义控制含义、选择spare或HDA载体、组合UI组件并规划验证参数绑定。适用于从零先做控制接口、已有场景提炼总控或改善布局；普通赋值、纯模型构建和Python Panel/WebView开发不单独触发。","base":"skills/houdini-parameter-ui","files":[{"path":"assets/ui-component-gallery.json","hash":"272efe43692fc47472f6963be238c5478a92b0ceda4f9b786074ea3be15c3fde","bytes":6684},{"path":"references/artist-ui-patterns.md","hash":"883d645e62f8fb48eda7905a21dd28a379173890efb3e99ad27d78f0518f65b7","bytes":4182},{"path":"references/control-bindings.md","hash":"c247843859806791dc71d35fee3ecd9a3a44517bf417cef97c99b02d70f87255","bytes":13777},{"path":"references/hda-ui.md","hash":"f0bccc16f6a1ac488ef3c14cbca9306d7d51a3830bb2d5a7f050bdcec79b2091","bytes":6786},{"path":"references/ui-components.md","hash":"1a6df78bfc1155185ca297a688fb6770b9d7c52c556ec4682ee1ed11d9b8d454","bytes":9789},{"path":"scripts/build-ui-gallery.py","hash":"11696ee776883f7daf22c4ddd3f318a36a1df9b623435a53fb3c4f60d5ab2112","bytes":3052},{"path":"SKILL.md","hash":"eba13a14eece806e83b06b0f92c9b43fdc9af6d12866f62751a0faf0a66d5e2c","bytes":7758}]},{"name":"houdini-network-handoff","description":"让用户找到、理解并继续编辑Houdini成果：工程另存与文件交付、节点入口、Network Box和Sticky Note。准备保存交付成果、已明确模块编辑边界，或用户要求整理网络时加载；纯查询、单参修改、临时诊断不触发。","base":"skills/houdini-network-handoff","files":[{"path":"references/file-delivery.md","hash":"cb089e6fe540349c7f2d26c95899b63d73596895df9063026a725484d560cadb","bytes":8210},{"path":"references/network-layout.md","hash":"edb8fe9d7a782b6a151251390cc0e53e0075a16368af93329a7c19df33ec3af8","bytes":4611},{"path":"SKILL.md","hash":"955aa2c0dc95c2305a5cd683c9dbadc9bdce92050bc0c50a81aba542658c182b","bytes":6689}]},{"name":"houdini-solaris-karma-workflow","description":"在 Houdini Solaris/LOPs 中设计、构建、检查和交付 Karma 材质与渲染网络。用于用户要求最终渲染、Karma CPU/XPU、MaterialX、USD 材质绑定、Render Settings、AOV、USD Render ROP，或把 SOP/COP 结果接入 /stage；不用于仅需 render_view 的快速 SOP 视觉验证。","base":"skills/houdini-solaris-karma-workflow","files":[{"path":"references/karma-patterns.md","hash":"ed2154497088d0bc01b11ddda50dc6e7dc51d0be813a202df2b623af4101028c","bytes":11128},{"path":"SKILL.md","hash":"227d3da14b12791f2287c05cf2ba2c2d4e6ec70f20e2c4d55f79e92b689f14bc","bytes":5944}]},{"name":"houdini-rig-animation-workflow","description":"在 Houdini 中设计、构建、调试和交付参数动画、刚体 piece 序列、机械层级、KineFX skeleton/skin 与 animator-facing rig。用于任务涉及 keyframes、绑定、FK/IK、capture/deform、非交换多步骤或可复用控制器；不用于普通静态 SOP 建模，也不把所有“绑定”默认路由到 KineFX/APEX。","base":"skills/houdini-rig-animation-workflow","files":[{"path":"references/rig-animation-patterns.md","hash":"7337f077f52b79b64fc3572ad47c1269c8a4222af7ede576d88602d6941c0d63","bytes":15476},{"path":"SKILL.md","hash":"733ee9de44a0e4591eb619bb0f94139b89fc464b2ccb1f868cf5b6d70b6f896a","bytes":8373}]},{"name":"houdini-skill-governance","description":"创建、审查、精简和维护 dsh-houdini 的领域 skills，或依据 Houdini trace、官方资料与工程修正领域知识。用于用户要求修改或评估插件 skills；普通内容制作和单纯 trace 分析不修改生产 skill。","base":"skills/houdini-skill-governance","files":[{"path":"references/eval-cases.md","hash":"088f899b3cac25229ce514fe36197a569cac65d247e6bbc7d9ba1c315f4f0a75","bytes":4959},{"path":"references/evidence-ingestion.md","hash":"d5d9fe3c3cb450e4d7cf30305b3967abbe7db5c098d33c0f9893aec5d8b4f5ca","bytes":5934},{"path":"references/maintenance-lifecycle.md","hash":"298458af78c5a2eef5ae1eb2c50666b6c0e2ab2360a9c046b9310e7cc82ecb9d","bytes":3011},{"path":"references/quality-standard.md","hash":"3a48c5e52a89af1e83c4872e788c3db1ec5a4ec5be5790a552ba974b4dca662e","bytes":7762},{"path":"scripts/audit-houdini-skills.mjs","hash":"e584e6bcabd5b39b95a47016b335049336b823df802276c1198a9daf17f04532","bytes":7129},{"path":"SKILL.md","hash":"ca962dfa217e946c2c8d3e90513af5c0d78f7719dc8d612c7869a5d3d7692b95","bytes":3936}]},{"name":"houdini-video-tutorial","description":"解析 Houdini 视频教程，结合云端语音转录与本地画面核对，提取带时间依据的步骤、设置、冲突和复现缺口。用于用户提供视频文件或要求从视频准备教学工程；不用于图文教程、普通建模、会议转录或自动知识沉淀。","base":"skills/houdini-video-tutorial","files":[{"path":"references/reconstruction.md","hash":"ae75469dc5a97b11000a0b295d1f5d2cefd882602ce1d1e86ccf617fb3b0d42b","bytes":16440},{"path":"references/video-processing.md","hash":"33b75730feaf4bb888e5310f5ab1d60ea268c7351e376a859895e971e28d16dd","bytes":47286},{"path":"scripts/video_tutorial.py","hash":"80f1b81927463c489eb0ae9459ede216069de744b58e56b34808a5690f5aa3ed","bytes":144375},{"path":"SKILL.md","hash":"bc9c8a8d33ad24cd4fc8f378de67170173b5c892721739acda8eab7df85a6c1e","bytes":16220}]}],"presets":[{"name":"houdini","file":"presets/houdini/persona.md","presetFile":"presets/houdini/cordis.patch.yml","hash":"0d2a5224679bfcdc84ea06aaedb61ea01e80e1df5099b0a29282aaea932f7633","bytes":8443,"paragraphStarts":["You are a Houdini automation agent powered by the ","## Goal and priorities\nTurn the user's requirements, references and tutorials into high-qu","## Own the work\nCarry the authorized task through construction, observation, correction an","Use DSH's existing plan and task continuation for substantial work. Keep the current unres","Keep the user oriented before long operations and at meaningful decisions: what you observ","## Choose the next useful action\nInspect the relevant scene, reference material and availa","For multi-part assets, multi-subsystem simulation, cross-stage image processing or tool de","Use DSH teammates for useful independent work and continue existing members when their con","Use houdini-video-tutorial when reconstructing a tutorial; its demonstrated method takes p","When choosing or delegating visible surface detail, use houdini-surface-workflow to choose","Search primary sources when missing external facts would change dimensions, construction, ","For requested generated images, discover configured routes with image_models and use image","## Observe, judge and revise\nCompare the actual output with the requested shape, relations","Let local feedback guide integration: resolve source defects that would spread through rep","Judge completion against the original target and the last relevant observations. Parameter","When saving is authorized, preserve useful milestones before expensive simulation, texture","Inspect the actual Houdini interface when layout, visibility or UI state matters, preservi","## Deliver\nMake new or changed work easy to find and edit. Offer its actual node entry poi","Integrate new user-facing operations into an existing asset's editing entry points and upd","Reply in the user's language, leading with the result, what can be opened or edited, and a","After verifying affected public entries, clean this task's known disposable files and node"]}],"tools":{"houdini_inspect":{"scene":true,"label":"观察现场","purpose":"读取真实Houdini场景、节点、参数和能力资料。","input":"只读Python代码；hou与动词已导入。","output":"读取结果、诊断及本次观察的场景身份。","execution":"Houdini主线程，只读"},"houdini_exec":{"scene":true,"label":"执行操作","purpose":"批量创建、修改、检查、保存或出图。","input":"Python代码或绝对UTF-8 .py脚本；script可带expected_sha256及code调用尾段，不使用exec(open(...))加载；__result__返回结构数据。","output":"结果、真实错误、操作记录、事务状态、脚本版本、图像和文件。","execution":"Houdini主线程，串行"},"houdini_request":{"scene":true,"label":"查回执行","purpose":"回答某个未知响应的请求是否执行、是否完成；避免重复修改。","input":"原请求的request_ref；index仅列当前所选运行实例中本会话的回执。","output":"原执行状态与可取得的原始结果；不会重发代码。","execution":"Bridge请求记录，无HOM"},"houdini_resource":{"scene":false,"label":"读取资料","purpose":"按需读取原始用户资料、完整历史工具结果及已归档加载警告。","input":"kind=source/result、ref及可选分页；result可选JSON Pointer。","output":"原文或JSON分页及继续读取位置。","execution":"DSH Host，无HOM"},"houdini_capabilities":{"scene":false,"label":"观察通道","purpose":"确认当前模型能否接收图片，以及附件通道是否可用。","input":"无需参数。","output":"当前模型与附件能力事实；不会渲染或判断画面。","execution":"DSH Host，无HOM"},"houdini_isolated":{"scene":false,"label":"独立Houdini执行","purpose":"按需在新hython中执行构建脚本、已保存工程副本及加载后的准备操作，取得真实检查、错误和图片，供当前作者或团队成员自验证。","input":"operation=run/read、manifest；run可选全新output_dir，默认在当前DSH工作区execution_run角色内分配唯一目录；read传原run路径。使用已选现场登记的安装信息，离线仍可运行；可选houdini_installation显式指定HFS。manifest支持hip+script与input_root；可选background、timeout_seconds、memory_mb。","output":"独立运行报告、输入版本、构建结果、检查和原生图片；大型原始回执单份保留并返回details；后台使用DSH job_output/job_kill。","execution":"Host监管的一次性独立hython，不修改当前现场、不自动合并"},"houdini_ui_list":{"scene":true,"label":"发现界面","purpose":"列出当前Houdini中可见的原生pane及Qt窗口/面板，提供明确截图目标和实际支持状态。","input":"无需参数；不打开或切换界面。","output":"当前runtime目标引用、类型、用途线索、实际区域及支持/未支持原因。","execution":"Bridge主线程队列，只读发现"},"houdini_ui_screenshot":{"scene":true,"label":"观察界面","purpose":"截图明确的当前可见界面；目标须完整在屏内且无遮挡。","input":"target为houdini_ui_list发现所得引用；可选path/output_policy。不打开或调整界面，不传Python代码。","output":"真实PNG附件、准确目标区域、实际尺寸与状态保持事实；识图与捕获分别判断。","execution":"Bridge主线程队列分阶段观察/捕获，不改导航或窗口状态"},"houdini_job_submit":{"scene":true,"label":"提交长任务","purpose":"把渲染、模拟或长计算放入Houdini串行队列，由DSH原生jobs跟踪、通知和收集。","input":"Python代码或script、expected_sha256及可选code调用尾段；与exec相同的操作能力。","output":"DSH job_id用于job_output/job_kill，Bridge jobId和原request_ref用于真实结果及恢复；houdini_request查回原结果和图片。","execution":"DSH jobs观察；Houdini主线程串行执行"},"image_models":{"label":"发现生图模型","purpose":"读取DSH已配置的OpenAI兼容API路由和模型名称，供指定生图模型使用；不调用模型，不证明图片接口可用。","input":"可选provider和模型名称子串query，默认image。","output":"配置中的provider/model及图片接口支持尚未验证的说明；不返回凭据。","execution":"DSH Host，无HOM"},"image_generate":{"label":"生成参考或纹理图","purpose":"使用指定provider/model生成或编辑一张图片，实际上传参考像素；默认按当前HIP目录和用途分配文件，显式目的地支持离线工作。","input":"provider、model、prompt；purpose=reference/texture，output_policy=managed/explicit；可选output、references、size、quality、background。","output":"实际路径、工程锚点和目录角色、来源指纹、原图恢复/预览附件及请求事实；不自动重试或更换模型。","execution":"DSH Host HTTP与文件；managed只读查询所选Houdini现场"},"video_process":{"label":"处理教程资料","purpose":"在Host受控进程中导入/抽帧和查询/整理本地教程证据，复用原脚本的来源校验及唯一文件记录。","input":"operation与options；只接受随包离线命令，路径绝对，写入使用工作区内新output目录。","output":"原命令JSON、进度、实际退出状态、选定Houdini的Python/私有媒体工具与输出路径；不认证语义。","execution":"DSH Host普通Python子进程，无shell/密钥/云请求/HOM"},"video_models":{"label":"发现转录配置","purpose":"读取教程视频的转录用途配置、DSH服务商和凭据状态；不上传音频，不证明转录接口可用。","input":"可选provider和模型名称子串query。","output":"默认用途、API路由、模型建议和缺失配置诊断；不返回凭据。","execution":"DSH Host，无HOM"},"video_transcribe":{"label":"转录教程音频","purpose":"用DSH中选定服务商与转录模型并行处理已准备的教程音频，复用原任务的分片和请求记录。","input":"work、allow_upload；可选provider/model、chunks、max_chunks、concurrency、requests_per_second、术语词表、说话人分离及明确授权的重试预算。","output":"逐片进度、实际在途峰值与成功/失败、剩余/未知请求、原任务目录及准确模型；原始响应和时间戳在同源outcome中，密钥只交给受控子进程。","execution":"DSH Host Python子进程与HTTP，无HOM"}}};
      var css = ".dsh-trace {\n  --tr-bg: var(--dsw-alias-bg-layer-1, #24272b);\n  --tr-panel: var(--dsw-alias-bg-layer-2, #2d3136);\n  --tr-fg: var(--dsw-alias-label-primary, #e6e8eb);\n  --tr-muted: var(--dsw-alias-label-secondary, #a8afb8);\n  --tr-line: var(--dsw-alias-border-l2, #3d434b);\n  --tr-orange: #e5a263;\n  --tr-red: #f18b87;\n  --tr-raised: var(--dsw-alias-interactive-bg-hover-solid, #343940);\n  --tr-selected: #3b342e;\n  --tr-selected-border: #856346;\n  --tr-error-bg: #3d3030;\n  --tr-error-border: #6b4948;\n  color: var(--tr-fg);\n  background: var(--tr-bg);\n  font: 13px/1.65 \"Segoe UI\", \"Microsoft YaHei\", sans-serif;\n  height: 100%;\n  min-height: 0;\n  min-width: 0;\n  flex: 1;\n  display: flex;\n  flex-direction: column;\n  overflow: hidden;\n  position: relative;\n  isolation: isolate;\n}\n/* DSH owns this attribute; consume its resolved theme without changing it.\n   Static state colors also work in Houdini's Chromium 108. */\nbody:not([data-ds-dark-theme]) .dsh-trace {\n  --tr-orange: #a65f27;\n  --tr-red: #b9413c;\n  --tr-selected: #fff2e6;\n  --tr-selected-border: #cfac8b;\n  --tr-error-bg: #fceeee;\n  --tr-error-border: #dca2a0;\n}\n.dsh-trace * { box-sizing: border-box; }\n.dsh-trace button,\n.dsh-trace input,\n.dsh-trace select { font: inherit; color: inherit; }\n.dsh-trace button {\n  cursor: pointer;\n  border: 1px solid var(--tr-line);\n  background: var(--tr-panel);\n  border-radius: 8px;\n  padding: 6px 11px;\n  text-align: left;\n  /* Foreground, background and selection must change in the same paint. */\n  transition: none;\n}\n.dsh-trace button:hover { background: var(--tr-raised); }\n.dsh-trace button:focus-visible,\n.dsh-trace summary:focus-visible,\n.dsh-trace select:focus-visible,\n.dsh-trace input:focus-visible {\n  outline: 2px solid var(--tr-orange);\n  outline-offset: 2px;\n}\n.dsh-trace button[aria-pressed=\"true\"] {\n  background: var(--tr-selected);\n  border-color: var(--tr-selected-border);\n  color: var(--tr-fg);\n}\n.dsh-trace button:disabled { opacity: .4; cursor: default; }\n.dsh-trace header {\n  padding: 20px 22px 10px;\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  gap: 8px 16px;\n  flex-wrap: wrap;\n  flex: none;\n}\n.dsh-trace h2 { font-size: 18px; font-weight: 600; letter-spacing: .2px; margin: 0; }\n.dsh-trace h3 { font-size: 16px; font-weight: 600; margin: 6px 0 12px; overflow-wrap: anywhere; }\n.dsh-trace h4 { font-size: 13px; margin: 18px 0 8px; font-weight: 600; }\n.dsh-trace nav {\n  display: flex;\n  gap: 4px;\n  padding: 0 22px 12px;\n  border-bottom: 1px solid var(--tr-line);\n  flex: none;\n}\n.dsh-trace nav button { border: 1px solid transparent; background: transparent; }\n.dsh-trace .tr-status { color: var(--tr-muted); font-size: 12px; }\n.dsh-trace .tr-content { overflow: auto; min-height: 0; flex: 1; overscroll-behavior: contain; }\n.dsh-trace .tr-subnav { padding: 18px 22px 0; }\n.dsh-trace .tr-board { padding: 20px 22px; }\n.dsh-trace .tr-toolbar {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  gap: 10px;\n  flex-wrap: wrap;\n  margin-bottom: 16px;\n}\n.dsh-trace .tr-toolbar h3 { margin: 0; }\n.dsh-trace .tr-buttons { display: flex; gap: 7px; align-items: center; flex-wrap: wrap; }\n.dsh-trace .tr-buttons button { font-size: 12px; }\n.dsh-trace .tr-split {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);\n  gap: 18px;\n  align-items: start;\n}\n.dsh-trace .tr-inspector { grid-template-columns: minmax(190px, .7fr) minmax(0, 1.5fr); }\n.dsh-trace .tr-detail {\n  min-width: 0;\n  background: var(--tr-panel);\n  border: 1px solid var(--tr-line);\n  padding: 18px;\n  border-radius: 8px;\n  overflow-wrap: anywhere;\n}\n.dsh-trace .tr-list { min-width: 0; }\n.dsh-trace .tr-row {\n  display: block;\n  width: 100%;\n  padding: 14px;\n  margin: 0 0 8px;\n  border: 1px solid var(--tr-line);\n  border-radius: 8px;\n  background: var(--tr-panel);\n}\n.dsh-trace .tr-row h4 { margin-top: 0; }\n.dsh-trace .tr-meta,\n.dsh-trace .tr-muted,\n.dsh-trace small { font-size: 12px; color: var(--tr-muted); overflow-wrap: anywhere; }\n.dsh-trace .tr-meta { display: block; margin-top: 4px; }\n.dsh-trace .tr-pill {\n  display: inline-block;\n  font-size: 12px;\n  background: var(--tr-raised);\n  border-radius: 5px;\n  padding: 2px 7px;\n}\n.dsh-trace .tr-bad { color: var(--tr-red); }\n.dsh-trace .tr-warning { color: var(--tr-orange); }\n.dsh-trace .tr-attention {\n  background: var(--tr-error-bg);\n  border: 1px solid var(--tr-error-border);\n  padding: 12px 14px;\n  margin: 16px 0;\n  border-radius: 8px;\n}\n.dsh-trace .tr-attention h4 { margin-top: 0; color: var(--tr-red); }\n.dsh-trace .tr-attention-warning,\n.dsh-trace .tr-attention-unknown { background: var(--tr-panel); border-color: var(--tr-line); }\n.dsh-trace .tr-attention-warning h4 { color: var(--tr-orange); }\n.dsh-trace .tr-attention-unknown h4 { color: var(--tr-muted); }\n.dsh-trace .tr-type { color: var(--tr-muted); font-size: 12px; }\n.dsh-trace table { border-collapse: collapse; width: 100%; table-layout: fixed; font-size: 12px; }\n.dsh-trace th,\n.dsh-trace td {\n  text-align: left;\n  padding: 10px 8px;\n  vertical-align: top;\n  border-bottom: 1px solid var(--tr-line);\n  overflow-wrap: anywhere;\n}\n.dsh-trace th { font-weight: 500; color: var(--tr-muted); background: var(--tr-bg); }\n.dsh-trace code { font: 12px/1.65 Consolas, monospace; overflow-wrap: anywhere; }\n.dsh-trace pre {\n  font: 12px/1.75 Consolas, monospace;\n  white-space: pre-wrap;\n  overflow-wrap: anywhere;\n  background: var(--tr-bg);\n  padding: 12px;\n  border: 1px solid var(--tr-line);\n  border-radius: 8px;\n  margin: 10px 0;\n}\n.dsh-trace details { border-top: 1px solid var(--tr-line); padding: 11px 0; margin-top: 8px; }\n.dsh-trace summary { cursor: pointer; overflow-wrap: anywhere; font-size: 12px; color: var(--tr-muted); }\n.dsh-trace details[open] > summary { margin-bottom: 10px; color: var(--tr-fg); }\n.dsh-trace .tr-note { color: var(--tr-muted); font-size: 12px; margin: 10px 0 16px; overflow-wrap: anywhere; }\n.dsh-trace .tr-prose { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 13px; line-height: 1.8; }\n.dsh-trace .tr-prose p { margin: 8px 0; }\n.dsh-trace .tr-empty { padding: 28px 18px; color: var(--tr-muted); text-align: center; }\n.dsh-trace select,\n.dsh-trace input {\n  padding: 7px 10px;\n  background: var(--tr-bg);\n  border: 1px solid var(--tr-line);\n  border-radius: 8px;\n  max-width: 100%;\n}\n.dsh-trace input { display: block; width: 100%; margin-top: 6px; font-family: Consolas, monospace; }\n.dsh-trace .tr-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 16px 0 24px; }\n.dsh-trace .tr-metrics > div { padding: 14px; border: 1px solid var(--tr-line); border-radius: 8px; background: var(--tr-panel); }\n.dsh-trace .tr-metrics strong { display: block; font-size: 24px; font-weight: 500; margin-top: 4px; }\n.dsh-trace .tr-domains { margin-bottom: 18px; }\n.dsh-trace .tr-tree { min-width: 0; }\n.dsh-trace .tr-raw { color: var(--tr-muted); }\n.dsh-trace .tr-prompt-group { border: 1px solid var(--tr-line); border-radius: 8px; margin: 10px 0; padding: 12px 14px; background: var(--tr-panel); }\n.dsh-trace .tr-prompt-group > summary { font-weight: 600; }\n.dsh-trace .tr-prompt-section { margin-top: 12px; padding-top: 10px; }\n.dsh-trace .tr-prompt-source { display: block; margin: 5px 0 0 18px; font-weight: 400; }\n.dsh-trace .tr-prompt-raw { line-height: 1.65; font-size: 12px; }\n.dsh-trace .tr-content-timeline { overflow: hidden; }\n.dsh-trace .tr-timeline { height: 100%; min-height: 0; display: flex; flex-direction: column; }\n.dsh-trace .tr-timeline-toolbar {\n  flex: none;\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  flex-wrap: wrap;\n  gap: 10px;\n  padding: 12px 18px;\n  border-bottom: 1px solid var(--tr-line);\n}\n.dsh-trace .tr-timeline-toolbar button,\n.dsh-trace .tr-pager select { font-size: 12px; padding: 5px 9px; line-height: 1.5; }\n.dsh-trace .tr-pager { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; font-size: 12px; }\n.dsh-trace .tr-range { font-variant-numeric: tabular-nums; color: var(--tr-muted); margin-right: 6px; }\n.dsh-trace .tr-timeline-body {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);\n  flex: 1;\n  min-height: 0;\n  overflow: hidden;\n}\n.dsh-trace .tr-call-list,\n.dsh-trace .tr-call-detail {\n  min-width: 0;\n  min-height: 0;\n  overflow: auto;\n  overscroll-behavior: contain;\n  scrollbar-width: thin;\n  scrollbar-color: var(--tr-muted) transparent;\n}\n.dsh-trace .tr-call-list { background: var(--tr-bg); padding: 8px; }\n.dsh-trace .tr-call-detail { background: var(--tr-panel); border-left: 1px solid var(--tr-line); }\n.dsh-trace .tr-call-detail > .tr-detail { border: 0; border-radius: 0; padding: 20px; }\n.dsh-trace .tr-call-row {\n  display: block;\n  width: 100%;\n  border: 1px solid transparent;\n  border-radius: 8px;\n  margin-bottom: 4px;\n  padding: 11px 10px;\n  background: var(--tr-bg);\n  line-height: 1.5;\n}\n.dsh-trace .tr-call-row[aria-pressed=\"true\"] { background: var(--tr-selected); border-color: var(--tr-selected-border); color: var(--tr-fg); }\n.dsh-trace .tr-call-row:hover:not([aria-pressed=\"true\"]) { background: var(--tr-raised); }\n.dsh-trace .tr-call-head { display: grid; grid-template-columns: 30px minmax(0, 1fr) auto; gap: 7px; align-items: start; }\n.dsh-trace .tr-call-index { font: 11px/1.8 Consolas, monospace; color: var(--tr-muted); }\n.dsh-trace .tr-call-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 13px; }\n.dsh-trace .tr-call-state { font-size: 11px; color: var(--tr-muted); white-space: nowrap; }\n.dsh-trace .tr-call-state.tr-bad { color: var(--tr-red); }\n.dsh-trace .tr-call-time { font: 11px/1.5 Consolas, monospace; color: var(--tr-muted); white-space: nowrap; margin-left: auto; }\n.dsh-trace .tr-call-meta { display: flex; gap: 8px; align-items: center; margin-top: 6px; padding-left: 37px; font-size: 11px; min-width: 0; }\n.dsh-trace .tr-call-kind,\n.dsh-trace .tr-call-target { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--tr-muted); }\n.dsh-trace .tr-call-kind { max-width: 48%; flex-shrink: 0; }\n.dsh-trace .tr-call-target { flex: 1; min-width: 0; }\n.dsh-trace .tr-back-list { display: none; }\n.dsh-trace .tr-sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; }\n@media (max-width: 850px) {\n  .dsh-trace .tr-split { grid-template-columns: 1fr; }\n  .dsh-trace .tr-board { padding: 16px; }\n  .dsh-trace header { padding: 16px 16px 10px; }\n  .dsh-trace nav { padding-left: 16px; padding-right: 16px; }\n  .dsh-trace .tr-subnav { padding-left: 16px; padding-right: 16px; }\n  .dsh-trace .tr-timeline-toolbar { padding: 10px 12px; }\n  .dsh-trace .tr-timeline-body { display: block; position: relative; }\n  .dsh-trace .tr-call-list { height: 100%; }\n  .dsh-trace .tr-call-detail { display: none; height: 100%; border: 0; }\n  .dsh-trace .tr-detail-open .tr-call-list { display: none; }\n  .dsh-trace .tr-detail-open .tr-call-detail { display: block; }\n  .dsh-trace .tr-back-list {\n    display: block;\n    position: sticky;\n    top: 0;\n    z-index: 1;\n    width: 100%;\n    background: var(--tr-panel);\n    border-radius: 0;\n    border: 0;\n    border-bottom: 1px solid var(--tr-line);\n    padding: 12px 18px;\n  }\n}\n@media (max-width: 430px) {\n  .dsh-trace header { display: block; }\n  .dsh-trace .tr-status { display: block; margin-top: 4px; }\n  .dsh-trace nav { gap: 0; }\n  .dsh-trace nav button { padding: 6px 9px; }\n  .dsh-trace .tr-call-head { grid-template-columns: 26px minmax(0, 1fr); gap: 3px 7px; }\n  .dsh-trace .tr-call-state { grid-column: 2; }\n  .dsh-trace .tr-call-meta { padding-left: 33px; }\n  .dsh-trace .tr-pager { width: 100%; }\n}\n@media (pointer: coarse) {\n  .dsh-trace button,\n  .dsh-trace summary,\n  .dsh-trace select { min-height: 44px; }\n}\n";
      var classifyRawEffect = (function classifyRawEffect(step) {
  if (isStructuredHoudiniCall(step)) return null;
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
  // A transport failure has no completed ledger. It is not evidence that
  // Python itself failed or that the operation used no verbs.
  if (step.canonical?.requestReceipt?.status === 'unknown_transport') return 'unknown';
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
  return ['houdini_ui_list','houdini_ui_screenshot'].includes(step.tool)
    || step.tool==='houdini_exec' && !step.code && Boolean(step.args?.delivery || step.args?.review || step.args?.review_test)
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
    var processOutcomeFor = (function processOutcomeFor(tool, text, metadata) {
  if (tool !== 'pwsh' && tool !== 'bash') return null;
  if (metadata && Object.prototype.hasOwnProperty.call(metadata, 'shellExit')) {
    if (!metadata.shellExit || typeof metadata.shellExit !== 'object' || Array.isArray(metadata.shellExit))
      return {status:'unknown',exitCode:null,source:'structured_metadata'};
    metadata = metadata.shellExit;
  }
  if (!metadata || !['exitCode','timedOut','aborted','stopped','signal'].some(key=>Object.prototype.hasOwnProperty.call(metadata,key))) {
    const record = typeof text === 'string' ? /\n\[process-result: (\{[^\n]*\})\]\s*$/.exec(text) : null;
    if (record) metadata = tryJson(record[1]) || {exitCode:null};
  }
  let exitCode = null, source = 'not_recorded', interruption = null;
  if (metadata && ['exitCode','timedOut','aborted','stopped','signal'].some(key => Object.prototype.hasOwnProperty.call(metadata, key))) {
    exitCode = Number.isSafeInteger(metadata.exitCode) ? metadata.exitCode : null;
    source = 'structured_metadata';
    interruption = metadata.timedOut === true ? 'timed_out' : metadata.aborted === true || typeof metadata.stopped === 'string'
      ? 'stopped' : typeof metadata.signal === 'string' ? 'signal' : null;
  } else {
    const lines = typeof text === 'string' ? text.replaceAll('\r', '').trimEnd().split('\n') : [];
    for (let index = lines.length - 1; index >= 0; index--) {
      const marker = /^\[(?:exit code: (-?\d+)|timed out after (\d+)ms|stopped: ([^\]]*)|killed by signal: ([^\]]+))\]$/.exec(lines[index]);
      if (!marker) break;
      source = 'shell_result_trailer';
      if (exitCode === null && marker[1] !== undefined && Number.isSafeInteger(Number(marker[1]))) exitCode = Number(marker[1]);
      if (marker[2] !== undefined) interruption = 'timed_out';
      else if (marker[3] !== undefined && interruption !== 'timed_out') interruption = 'stopped';
      else if (marker[4] !== undefined && interruption === null) interruption = 'signal';
    }
  }
  return {status: interruption ? 'interrupted' : exitCode === null ? 'unknown' : exitCode === 0 ? 'succeeded' : 'failed',
    exitCode, source, ...(typeof metadata?.hasStderr === 'boolean' ? {hasStderr:metadata.hasStderr} : {}), ...(interruption ? {interruption} : {})};
});
      var analysis = { classifyRawEffect, isHoudiniDetailRead, isHoudiniHostCall, isStructuredHoudiniCall, collectVerbAdoption, processOutcomeFor };
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
  const checkLabels = {failed: "检查未通过", warning: "检查有警告", unverified: "检查未验证"};
  // Read producer-assigned check status, never infer it from geometry or prose.
  function checkFindings(canonical, parts) {
    const ledger = array(canonical?.verbs);
    const rows = ledger.length ? ledger : array(json(parts.checks));
    return rows.flatMap(v => {
      const status = ledger.length ? v.check_status : v.status;
      if (!own(checkLabels, status)) return [];
      const result = v.result?.validation ?? v.result;
      const facts = {...(result && typeof result === 'object' ? result : {}), ...v.summary};
      const target = facts.output || facts.path || facts.node;
      const reasons = [facts.reason, facts.error, ...array(facts.failure_reasons),
        ...array(facts.risk_reasons), ...array(facts.errors), ...array(facts.warnings),
        ...array(facts.issues).flatMap(issue => [...array(issue.errors), ...array(issue.warnings)]
          .filter(reason => typeof reason === 'string').map(reason => `${issue.path || ''} ${reason}`.trim())),
        ...array(facts.control_summary?.failures).map(failure => `测试 ${failure.id ?? '未记录'}：${failure.status ?? '未记录'}`)]
        .filter(reason => typeof reason === 'string' && reason);
      return [{status, label: checkLabels[status], verb: v.verb,
        target: typeof target === 'string' ? target : null,
        reason: [...new Set(reasons)].join('；') || null}];
    });
  }
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
    if (["houdini_inspect", "houdini_ui_list", "houdini_ui_screenshot", "houdini_request", "houdini_resource", "houdini_capabilities", "houdini_query", "houdini_job_status"].includes(name)) return "query";
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
      const canonical = info.canonical;
      const isHoudini = name.startsWith("houdini_") || name === 'job_output' && Boolean(canonical);
      const transaction = canonical?.transaction ?? json(parts.transaction);
      const req =
        c?.request ||
        requestFor(turn, step, n.seq) ||
        entriesById.get(parent)?.request ||
        null;
      const account = req?.accounting || c?.assistantUsage || null;
      const failed = !pending && (Boolean(n.isError) || info.failed);
      const processOutcome = pending ? null : info.processOutcome;
      const processFailed = processOutcome?.status === 'failed';
      const processInterrupted = processOutcome?.status === 'interrupted';
      const executionKey = canonical?.execution?.runtime_id && Number.isFinite(canonical.execution.sequence)
        ? canonical.execution.runtime_id + ':' + canonical.execution.sequence : null;
      const repeatedExecution = executionKey && seenExecutions.has(executionKey);
      if(executionKey)seenExecutions.add(executionKey);
      const verbs = canonical?.requestReceipt?.retrieved || repeatedExecution ? [] : info.verbs;
      const outcome = canonical?.outcome ?? json(parts['execution-outcome']);
      // New results consume the Bridge projection. Old records only expose
      // direct ledger facts; absent validation coverage remains unknown.
      const operationFailures = outcome?.operations?.failed ?? info.verbs.filter(v => v.ok === false).length;
      const checkCounts = outcome?.checks || null;
      const checkAttention = checkCounts ? Object.values(checkCounts).reduce((n, count) => n + count, 0) : 0;
      const checkSummary = Object.entries(checkLabels).filter(([status]) => checkCounts?.[status] > 0)
        .map(([status, label]) => `${label} ${checkCounts[status]} 项`).join(' · ');
      const findings = checkFindings(canonical, parts);
      const requestReceipt = canonical?.requestReceipt ?? json(parts['request-receipt']);
      const receiptStatus = requestReceipt?.status;
      const jobResultUnavailable = Boolean(requestReceipt?.jobId && requestReceipt.job_finished === true && requestReceipt.job_result_available === false);
      const recoveryNeeded = jobResultUnavailable || ['unknown_transport', 'unknown_runtime', 'unknown', 'result_expired', 'result_unavailable'].includes(receiptStatus);
      const receiptJobState = requestReceipt?.jobId && !canonical?.status
        ? jobResultUnavailable ? '后台任务已结束 · 结果不可用'
          : requestReceipt.job_finished === true && requestReceipt.job_result_available === true ? '后台任务已结束 · 待收集结果'
          : {queued: '后台任务排队中', running: '后台任务执行中'}[requestReceipt.job_status]
        : null;
      const receiptState = {
        queued: '请求已排队', running: '请求执行中', job_submitted: '后台任务已提交',
        not_executed: '未执行', unknown_transport: '结果未知 · 需要查回',
        unknown_runtime: '运行环境已变化 · 结果未知', unknown: '请求结果未知',
        result_expired: '已结束 · 结果已过期', result_unavailable: '已结束 · 结果不可用',
        index: '已读取请求索引',
      }[receiptStatus];
      const jobStatus = canonical?.jobId ? canonical.status : null;
      const jobState = {queued: '后台任务排队中', running: '后台任务执行中', cancelled: '后台任务已取消'}[jobStatus];
      const attention = operationFailures > 0 || checkAttention > 0 || recoveryNeeded || processFailed || processInterrupted;
      const parsedArgs = json(argsRaw);
      const args =
        parsedArgs &&
        typeof parsedArgs === "object" &&
        !Array.isArray(parsedArgs)
          ? parsedArgs
          : {};
      const analysisStep = {tool: name, isHoudini,
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
                : name === 'job_output' && isHoudini ? '现场长任务结果' : sources.tools?.[name]?.label || name;
      const rollback = transaction
        ? transaction.status === "rolled_back"
        : Boolean(info.rollback?.applied && !info.rollback.error);
      const state = pending
        ? "执行中（最后快照）"
        : jobState || receiptJobState || receiptState || (name === 'houdini_job_submit' && canonical?.jobId ? '后台任务已提交' : null)
          || (gateBlocked
          ? "Gate 拦截"
          : rollback
            ? "已回滚"
            : failed
              ? "失败"
              : processOutcome ? (processFailed ? "进程失败 · 退出 " + processOutcome.exitCode
                : processInterrupted ? "进程已终止 · " + ({timed_out:'超时',stopped:'停止',signal:'信号'}[processOutcome.interruption] || '原因未记录')
                : processOutcome.status === 'succeeded' ? "进程退出 0" : "已返回 · 进程状态未采集")
              : operationFailures
                ? "已完成 · 子操作失败"
                : checkAttention
                  ? "已完成 · " + (checkCounts.failed > 0 ? checkLabels.failed
                    : checkCounts.warning > 0 ? checkLabels.warning : checkLabels.unverified)
              : transaction?.status === "committed"
                ? "已提交"
                : "已成功");
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
        isHoudini,
        args,
        argsRaw,
        analysisStep,
        rawEffect,
        gateBlocked,
        title,
        target,
        verbs,
        failed,
        processOutcome,
        processFailed,
        processInterrupted,
        pending,
        outcome,
        operationFailures,
        checkCounts,
        checkAttention,
        checkSummary,
        checkFindings: findings,
        attentionLevel: failed || processFailed || operationFailures > 0 || checkCounts?.failed > 0 ? 'error'
          : checkCounts?.warning > 0 || recoveryNeeded || processInterrupted ? 'warning' : 'unknown',
        attention,
        requestReceipt,
        recoveryNeeded,
        jobStatus,
        repeatedExecution: Boolean(repeatedExecution || canonical?.requestReceipt?.retrieved),
        parent: parent || n.parentCallId || null,
        transaction,
        rollbackApplied: rollback,
        state,
        kind: args.request_ref || args.result_ref || args.source_ref ? "read" : name === 'job_output' && isHoudini ? 'exec' : toolKind(name),
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
        committed: !pending && !failed && !processFailed && !processInterrupted && !rollback,
        jobId: canonical?.jobId || requestReceipt?.jobId || args.jobId || result?.jobId || null,
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
    const returned = entries.filter(entry => entry.isHoudini && !entry.pending);
    const used = new Set(returned.flatMap(entry => entry.verbs.map(verb => verb.verb)));
    const known = catalog.flatMap(domain => domain.verbs.map(verb => verb.name));
    const accounts = requests.map(request => request.accounting).filter(Boolean);
    const toolUsage = new Map(), verbUsage = new Map();
    for (const entry of entries) {
      const count = toolUsage.get(entry.name) || { calls: 0, failed: 0, pending: 0, operationAttention: 0, processFailures: 0, processInterruptions: 0 };
      count.calls++;
      count.failed += Number(entry.failed);
      count.processFailures += Number(entry.processFailed);
      count.processInterruptions += Number(entry.processInterrupted);
      count.pending += Number(entry.pending);
      count.operationAttention += Number(!entry.pending && !entry.repeatedExecution && entry.operationFailures > 0);
      toolUsage.set(entry.name, count);
    }
    for (const entry of returned) for (const verb of entry.verbs) {
      const count = verbUsage.get(verb.verb) || { calls: 0, failed: 0 };
      count.calls++;
      count.failed += Number(verb.ok === false);
      verbUsage.set(verb.verb, count);
    }
    const toolNames = Object.keys(sources.tools || {});
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
      toolUsage,
      verbUsage,
      knownToolCount: toolNames.length,
      usedToolCount: toolNames.filter(name => toolUsage.has(name)).length,
      toolCalls: toolNames.reduce((count, name) => count + (toolUsage.get(name)?.calls || 0), 0),
      verbCalls: [...verbUsage.values()].reduce((count, verb) => count + verb.calls, 0),
      failedToolCalls: returned.filter(entry => entry.failed).length,
      failedProcesses: entries.filter(entry => entry.processFailed).length,
      interruptedProcesses: entries.filter(entry => entry.processInterrupted).length,
      failedVerbCalls: [...verbUsage.values()].reduce((count, verb) => count + verb.failed, 0),
      operationAttentionCalls: returned.filter(entry => !entry.repeatedExecution && entry.operationFailures > 0).length,
      checkAttentionCalls: returned.filter(entry => !entry.repeatedExecution && entry.checkAttention > 0).length,
      knownVerbCount: known.length,
      usedVerbCount: known.reduce((count, name) => count + Number(used.has(name)), 0),
      gateBlockedCalls,
      rolledBackCalls,
      rolledBackVerbCalls,
      rawEffectCounts,
      failures: entries.filter(entry => entry.failed || entry.rollbackApplied || entry.attention),
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
  const fold = (label, ...children) =>
    h("details", null, h("summary", null, label), ...children);
  const verbName = (verb) => typeof verb.verb === "string" && verb.verb.trim() ? verb.verb : null;
  const callTitle = (entry) => {
    if (entry.verbs.some(verb => !verbName(verb)))
      return [...new Set(entry.verbs.map(verb => verbName(verb)
        ? verbTitles[verb.verb] || verb.verb : "操作名称未记录"))].join(" / ");
    if (!entry.title) return "调用名称未记录";
    return entry.title === entry.name ? kindNames[entry.kind] || entry.title : entry.title;
  };
  const stateTone = e => e.failed || e.attentionLevel === 'error' ? ' tr-bad'
    : e.attentionLevel === 'warning' ? ' tr-warning' : '';
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
    if (value == null || value === "") return note("参数未记录。");
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
    const [toolPage, setToolPage] = React.useState("entry");
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
                  ? "第 " + r.turn + " 轮 · 步骤 " + r.step
                  : "压缩") +
                " · " +
                ({ complete: "已完成", running: "进行中", failed: "失败", error: "失败", aborted: "已中止" }[r.status] || r.status),
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
          { key: i, open: v.ok === false },
          h(
            "summary",
            { title: [v.argsText, v.detail].filter(value => value != null && value !== "").join(" → ") || undefined },
            i +
              1 +
              ". " +
              (verbName(v) || "操作名称未记录") +
              " · " +
              (v.ok === true
                ? e.rollbackApplied
                  ? "已执行后回滚"
                  : "动作返回成功"
                : v.ok === false ? "动作失败" : "状态未记录") +
              " · " +
              (typeof v.ms === "number" && Number.isFinite(v.ms) ? v.ms + " ms" : "耗时未记录"),
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
          verbName(v) && catalog.some(domain => domain.verbs.some(item => item.name === v.verb))
            ? button("查看动词契约 →", () => goVerb(v.verb)) : null,
        ),
      );
      return h(
        "aside",
        { className: "tr-detail" },
        h("div", { className: "tr-meta" }, "记录 #" + e.index),
        h("h3", null, callTitle(e)),
        h(
          "div",
          { className: "tr-buttons" },
          h("span", {className: "tr-pill" + stateTone(e)}, e.state),
          h("span", { className: "tr-meta" }, e.name),
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
              { className: "tr-attention" },
              h("h4", null, e.recoveryNeeded ? "结果待核对" : "失败原因"),
              prose(e.errorText || e.statusText || "工具返回错误"),
              e.rollbackApplied
                ? note("可撤销范围已回滚；外部文件等副作用不属于恢复保证。")
                : e.gateBlocked
                  ? note("Raw Gate 在执行前拒绝。")
                  : e.recoveryNeeded
                    ? note("连接失败不代表操作未执行。请查回原请求状态，不要直接重复执行。")
                    : note("场景影响按事务与操作证据判断。"),
            )
          : null,
        e.attention
          ? h("section", { className: "tr-attention tr-attention-" + e.attentionLevel },
              h("h4", null, e.checkSummary || (e.processFailed ? "命令进程退出失败" : e.processInterrupted ? "命令进程已终止" : e.operationFailures ? "子操作失败" : "结果待查回")),
              e.processFailed ? prose("工具调用已返回，命令进程以退出码 " + e.processOutcome.exitCode + " 结束；这与工具传递失败分别记录。") : null,
              e.processInterrupted ? prose("结果记录了超时、停止或信号终止；不能当作正常完成或普通命令错误。") : null,
              e.recoveryNeeded ? prose("尚不能确认这次操作的结果。请按原请求回执查回状态；结果已过期或不可用时，应检查当前场景，不要直接重复执行。") : null,
              e.operationFailures ? prose(e.operationFailures + " 个操作发生错误，详情见下方执行步骤。") : null,
              e.checkFindings.map((finding, index) => h("div", {key: index},
                h("strong", null, finding.label + " · " + (verbTitles[finding.verb] || finding.verb || "操作未记录")),
                finding.target ? h("div", {className: "tr-meta"}, finding.target) : null,
                finding.reason ? prose(finding.reason) : note("具体原因请展开操作与检查证据；本条摘要未记录。"))),
              e.checkAttention && !e.checkFindings.length ? note("回执只提供检查计数，未记录逐项原因；请查看完整返回。") : null,
              note("这是本次调用当时的结果，不是当前工程的问题清单；后续修复不会改写历史记录。"))
          : null,
        e.requestReceipt ? fold("请求回执", structured(e.requestReceipt)) : null,
        fold("请求参数", Object.keys(e.args).some((k) => k !== "code")
          ? structured(
              Object.fromEntries(
                Object.entries(e.args).filter(([k]) => k !== "code"),
              ),
            )
          : note(
              e.code
                ? "Python 执行请求 · " +
                    e.code.split("\n").length +
                    " 行；完整代码见原始记录。"
                : "未记录额外参数。",
            )),
        e.transaction
          ? fold("场景变更状态", structured(e.transaction))
          : null,
        e.evidence
          ? h("details", { open: e.attention || undefined },
              h("summary", null, "操作与检查证据"), structured(e.evidence))
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
          ? h("section", null, h("h4", null, "执行步骤 · " + e.verbs.length), verbRows)
          : null,
        e.resultValue != null
          ? fold("工具返回", structured(e.resultValue))
          : null,
        !e.isHoudini && e.text
          ? fold("工具返回", structured(json(e.text) ?? e.text))
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
        fold("关联模型请求",
          usageView(e.accounting),
          e.request
            ? button("查看提示词与上下文", () => goPrompt(e))
            : note("未记录关联的模型请求。")),
        h(
          "details",
          { className: "tr-raw" },
          h("summary", null, "原始记录"),
          h("div", { className: "tr-meta" }, "调用标识：" + e.id),
          e.parent ? note("父调用：" + e.parent) : null,
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
          (filter === "houdini" && e.isHoudini) ||
          (filter === "error" && (e.failed || e.gateBlocked || e.attention)),
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
              ["error", "需要关注"],
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
          filter === "error" ? note("包含操作失败、检查未通过/警告/未验证及待查回结果。历史记录不代表当前仍未修复，也不评定成品质量。") : null,
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
            pages > 1 ? pagerButton("上一页", safePage - 1, safePage === 0) : null,
            pages > 1 ? h(
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
            ) : null,
            pages > 1 ? pagerButton("下一页", safePage + 1, safePage === pages - 1) : null,
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
                  return h(
                    "button",
                    {
                      type: "button",
                      className: "tr-call-row",
                      key: e.id,
                      "aria-pressed": visibleEntry?.id === e.id,
                      "aria-label": `调用 #${e.index} · ${callTitle(e)} · ${e.name} · ${e.state}`,
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
                        { className: "tr-call-title", title: callTitle(e) },
                        callTitle(e),
                      ),
                      h(
                        "span",
                        {
                          className:
                            "tr-call-state" + stateTone(e),
                        },
                        shortState(e),
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
                      h("span", { className: "tr-call-time", title: "工具执行耗时" }, time),
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
          h("h3", null, "提示词与上下文"),
          requestPicker(),
        ),
        h(
          "div",
          { className: "tr-buttons" },
          [
            ["actual", "系统提示词"],
            ["sources", "来源"],
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
              h("h4", null, "请求中的系统提示词"),
              p
                ? h("div", {className:"tr-prompt-groups", key: requestKey(request)},
                    note("内容来自所选历史请求。分组来源按文本匹配，仅供定位；不代表已验证加载版本。"),
                    [...new Set(sections.map(s => s.category))].map(category => {
                      const items = sections.filter(s => s.category === category);
                      return h("details", {className:"tr-prompt-group", key:category},
                        h("summary", null, category, h("span", {className:"tr-muted"}, ` · ${items.length} 个片段 · ${items.reduce((n,s)=>n+s.text.length,0)} 字符`)),
                        items.map(s => h("details", {className:"tr-prompt-section", key:s.index},
                          h("summary", null, `#${s.index} ${s.title}`, h("small", {className:"tr-prompt-source"}, s.source)),
                          h("pre", {className:"tr-prompt-raw"}, s.text))));
                    }),
                    h("details", {className:"tr-prompt-group"},
                      h("summary", null, "完整原文 · 原始顺序"),
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
                    : note("该请求中没有可定位的片段；完整正文可在“系统提示词”查看。"),
                ),
              ),
              h("h4", null, "DSH 与其他插件"),
              note(
                "其他插件的逐段来源与注册状态未采集；完整内容见“系统提示词”。",
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
      const stats = data.statistics;
      return h(
        "div",
        { className: "tr-board" },
        h(
          "div",
          { className: "tr-toolbar" },
          h("h3", null, "工具与动词"),
          requestPicker(),
        ),
        h(
          "div",
          { className: "tr-buttons tr-domains" },
          [
            ["entry", "工具目录"],
            ["verbs", "动词目录"],
            ["visible", "请求可见工具"],
          ].map(([k, s]) => button(s, () => setToolPage(k), toolPage === k)),
        ),
        toolPage === "verbs"
          ? h(
              "section",
              null,
              note(
                "动词是工具里可组合调用的具体操作。当前目录 " +
                  total +
                  " 个动词 / " +
                  catalog.length +
                  " 个分组。选择动词查看用途和本任务记录。",
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
                          h("span", { className: "tr-meta" }, (stats.verbUsage.get(v.name)?.calls || 0) + " 次"),
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
                      h("div", { className: "tr-meta" }, "本任务执行 " + (stats.verbUsage.get(v.name)?.calls || 0) + " 次 · 失败 " + (stats.verbUsage.get(v.name)?.failed || 0) + " 次"),
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
                    ),
                  )
                : null,
            )
          : null,
        toolPage === "entry"
          ? h("section", null,
              h("div", { className: "tr-meta" }, "当前包提供 " + stats.knownToolCount + " 个工具 · 本任务已用 " + stats.usedToolCount + " 个"),
              Object.entries(sources.tools).map(([name, tool]) => {
                const count = stats.toolUsage.get(name) || { calls: 0, failed: 0, pending: 0 };
                const visible = request?.prompt ? schemas.some(t => t.name === name) ? "所选请求可见" : "未在所选请求中" : "请求可见性未采集";
                return h("article", { key: name, className: "tr-row" },
                  h("h4", null, tool.label, " · ", h("code", null, name)),
                  h("div", { className: "tr-meta" }, "本任务调用 " + count.calls + " 次" + (count.failed ? " · 失败 " + count.failed + " 次" : "") + (count.processFailures ? " · 进程失败 " + count.processFailures + " 次" : "") + (count.operationAttention ? " · 子操作失败 " + count.operationAttention + " 次" : "") + (count.pending ? " · 进行中 " + count.pending + " 次" : "")),
                  prose(tool.purpose),
                  h("details", null, h("summary", null, "输入、输出与调用记录"),
                    note(visible),
                    table(["项目", "说明"], [["输入", tool.input], ["输出", tool.output], ["执行位置", tool.execution]]),
                    h("div", { className: "tr-buttons" }, data.entries.filter(e => e.name === name).map(openCallLink)),
                    !count.calls ? note("本任务已加载记录中没有此工具调用。") : null));
              }))
          : null,
        toolPage === "visible"
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
          ...data.contexts.filter(n => n.source?.kind === "skill-invocation").map(n => n.source.name),
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
          h("h3", null, "技能"),
          requestPicker(),
        ),
        note(
          "技能提供按需加载的工作方法。复制命令，返回对话后发送即可加载。",
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
                  sources.skills.some(s => s.name === n) ? "当前包可用 · " : "历史记录 · ",
                  observed.some((s) => s.name === n)
                    ? "最近可发现"
                    : latest
                      ? "不在最近目录中"
                      : "运行目录未采集",
                ),
                h(
                  "span",
                  { className: "tr-meta" },
                  "正文返回 " + data.entries.filter(
                    (e) =>
                      e.name === "skill" &&
                      e.args.name === n &&
                      !e.failed &&
                      !e.pending,
                  ).length + " 次 · 手动加载 " + data.contexts.filter(n2 => n2.source?.kind === "skill-invocation" && n2.source.name === n).length + " 次",
                ),
              ),
            ),
          ),
          name
            ? h(
                "article",
                { className: "tr-detail" },
                h("h3", null, name),
                h("label", { className: "tr-meta" }, "选中命令，复制到对话",
                  h("input", { "aria-label": "技能加载命令", value: "/" + name, readOnly: true, onFocus: event => event.target.select() })),
                prose(
                  observed.find((s) => s.name === name)?.description ||
                    source?.description ||
                    "",
                ),
                h("h4", null, "加载记录"),
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
                  "当前上下文是否仍保留正文未采集；加载记录不代表规则已全部遵守。",
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
        ["Houdini 工具失败（已返回调用）", stats.failedToolCalls],
        ["命令进程退出失败（独立统计）", stats.failedProcesses],
        ["动词异常 / 动词调用", stats.failedVerbCalls + " / " + stats.verbCalls],
        ["含动词异常的执行", stats.operationAttentionCalls],
        ["正常返回但检查需关注的执行", stats.checkAttentionCalls],
        ["Houdini 已返回调用（排除历史回读）", adoption.houdiniCalls],
        ["Host 历史结果 / 来源回读", adoption.hostResultDetailReads],
        ...(adoption.structuredCalls ? [["结构化调用（不执行 Python）", adoption.structuredCalls],
          ["Python 调用含动词", adoption.callsWithVerbs + " / " + adoption.pythonCalls]] : []),
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
        h("h3", null, "执行统计"),
        note("统计范围为本任务已加载记录。执行完成或检查通过，不代表任务质量已经确认。"),
        h(
          "div",
          { className: "tr-metrics" },
          metrics.slice(0, 4).map(([label, value]) =>
            h(
              "div",
              { key: label },
              h("small", null, label),
              h("strong", null, String(value)),
            ),
          ),
        ),
        h("h4", null, "需要关注的记录"),
        !stats.failures.length ? note("已加载记录中没有失败、检查关注或回滚。") : null,
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
        fold("详细执行统计", table(["指标", "数值"], metrics),
          note("工具失败与操作异常分别统计；捕获异常后批次仍可完成。检查关注只统计正常返回的验证，历史回读不算新执行。")),
        fold("模型用量",
          requestUsage.reported ? table(
            ["已报告 / 已加载请求", "输入合计", "输出合计"],
            [[requestUsage.reported + " / " + requestUsage.total, format(requestUsage.input), format(requestUsage.output)]])
            : note("模型用量未采集。"),
          note("按模型请求去重；缺失用量不计为零。输入合并未缓存输入和缓存分桶。")),
        fold("低层调用的副作用证据", table(
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
        ), note(
          "历史回读不计新执行。unknown 包含动态 exec；疑似外部副作用与裸修改候选不证明实际发生，失败也不证明没有副作用。原始 Gate 回包在调用详情保留。",
        )),
      );
    }
    return h(
      "section",
      { className: "dsh-trace" },
      h("style", null, css),
      h(
        "header",
        null,
        h("h2", null, "Houdini 记录"),
        h("span", { className: "tr-status", role: "status" },
          data.pendingCount
            ? "快照中 " + data.pendingCount + " 项执行中"
            : data.partial ? "模型输出中（快照）" : "已载入 " + data.entries.length + " 条记录",
          data.recent ? " · " + stamp(data.recent) : ""),
      ),
      h(
        "nav",
        { "aria-label": "Trace 看板" },
        [
          ["timeline", "执行记录", ["timeline"]],
          ["tools", "能力资料", ["tools", "skills"]],
          ["prompt", "高级诊断", ["prompt", "analysis"]],
        ].map(([k, s, members]) => button(s, () => setTab(k), members.includes(tab))),
      ),
      h(
        "main",
        {
          className:
            "tr-content" + (tab === "timeline" ? " tr-content-timeline" : ""),
        },
        tab !== "timeline" ? h("div", { className: "tr-subnav tr-buttons", role: "group", "aria-label": "页面分类" },
          (tab === "tools" || tab === "skills"
            ? [["tools", "工具"], ["skills", "技能"]]
            : [["prompt", "提示词与上下文"], ["analysis", "执行统计"]])
            .map(([k, label]) => button(label, () => setTab(k), tab === k))) : null,
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
    var marker = /(?:^|\n\n)(stdout|stderr|__result__|rollback|transaction|request-receipt|execution-outcome|execution-observation|operation-errors|checks|operation-evidence|verb-help|result-details|control-test-summary \(not_run is not pass\)|CHECKS NEED ATTENTION \(execution success is not validation success\)|raw-usage|image-attachments|artifact-candidates \(not delivered; verify requested final files, then call present\)|hint|verbs \(\d+\)|media(?: [^\n:]*)?):\n/g;
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
    var processOutcome = analysis.processOutcomeFor(call.name, text, node.meta);
    var failed = node.isError === true || !processOutcome && (status.indexOf("Execution failed") === 0 || status.indexOf("Job failed") === 0);
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
      processOutcome: processOutcome,
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
    if (canonical && typeof canonical.ok === "boolean") {
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
        node.style.cssText = "position:fixed;right:16px;top:16px;z-index:2147483647;max-width:min(480px,calc(100vw - 32px));box-sizing:border-box;overflow-wrap:anywhere;padding:12px 16px;border:1px solid #555;border-left:3px solid #e5a263;border-radius:8px;background:#24272b;color:#eef0f2;font:13px/1.5 'Segoe UI',sans-serif;box-shadow:0 4px 20px #0005";
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
        var node = notice(), controller = null, running = false, stopped = false, detachNavigation = function () {}, detachWaitingSelection = function () {};
        function stop(reason) {
          stopped = true;
          detachNavigation();
          detachWaitingSelection();
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
          // uiWorkspace starts its initial restoration synchronously when the
          // two native lists become ready, before its asynchronous connection.
          // Wait for that baseline before claiming an explicit launch intent.
          await snapshotWhen(function (w, s) { return { workspaces: w, sessions: s }; }, attempt);
          if (!active(attempt)) return;
          detachWaitingSelection();
          var signal = layout.beginNavigation();
          var superseded = function () { stop("user-navigation"); };
          signal.addEventListener("abort", superseded, { once: true });
          detachNavigation = function () { signal.removeEventListener("abort", superseded); };
          var sessionId = target.sessionId;
          var workspace = target.workspacePath ? await workspaces.create({ path: target.workspacePath }) : null;
          if (!active(attempt)) return;
          if (refresh || sessionId) await sessions.refresh();
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
          detachWaitingSelection();
          var refresh = controller !== null, attempt = new AbortController();
          controller = attempt; running = true;
          var initialSelection = uiSession.adapter.current.getSnapshot();
          var initialKey = initialSelection && initialSelection.key;
          detachWaitingSelection = uiSession.adapter.current.subscribe(function () {
            // Native startup restoration requires both list phases ready,
            // even while a workspace baseline refresh is still loading. Only
            // earlier commits prove a separate selection while we wait,
            // including after a waiting attempt timed out.
            if (stopped || controller !== attempt) return;
            if (!matches(target)) { stop("superseded"); return; }
            var w = workspaces.list.getSnapshot(), s = sessions.list.getSnapshot();
            if (w.phase === "ready" && s.phase === "ready") return;
            var selected = uiSession.adapter.current.getSnapshot();
            if (selected && selected.key && selected.key !== initialKey) stop("user-navigation");
          });
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

    // Account presentation only. Authorization, credentials and model choices
    // remain in DSH; no token or OAuth callback is written to browser storage.
    function createChatGptSettings(connection) {
      var ui = require("@deepseek-ai/dsh-client-ui-primitives");
      var h = React.createElement;
      var css = ".dsh-chatgpt{max-width:720px;padding:8px 4px 28px;color:var(--dsw-alias-label-primary);font-size:14px;line-height:1.6}.dsh-chatgpt h2{font-size:22px;line-height:1.3;margin:0 0 8px;font-weight:600}.dsh-chatgpt h3{font-size:15px;margin:0;font-weight:600}.dsh-chatgpt p{margin:8px 0}.dsh-chatgpt .cg-muted{color:var(--dsw-alias-label-tertiary);font-size:13px}.dsh-chatgpt .cg-card{border:1px solid var(--dsw-alias-settings-card-stroke);background:var(--dsw-alias-settings-card-fill);border-radius:12px;padding:18px;margin-top:20px}.dsh-chatgpt .cg-head,.dsh-chatgpt .cg-actions{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.dsh-chatgpt .cg-actions{justify-content:flex-start;margin-top:16px}.dsh-chatgpt .cg-step{display:flex;align-items:center;gap:10px}.dsh-chatgpt .cg-step>span{display:inline-grid;place-items:center;flex:none;width:24px;height:24px;border-radius:50%;border:1px solid var(--dsw-alias-border-l2);font:12px 'Cascadia Code',Consolas,monospace}.dsh-chatgpt .cg-status{font-size:12px;white-space:nowrap}.dsh-chatgpt .cg-good{color:var(--dsw-alias-state-success-primary)}.dsh-chatgpt .cg-warn{color:var(--dsw-alias-state-warn-label)}.dsh-chatgpt .cg-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(120px,1fr);gap:12px;margin-top:16px}.dsh-chatgpt label{display:grid;gap:6px;font-size:13px}.dsh-chatgpt select,.dsh-chatgpt input{box-sizing:border-box;width:100%;min-width:0;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;padding:9px 10px;color:inherit;background:var(--dsw-alias-bg-layer-1);font:inherit}.dsh-chatgpt input:focus-visible,.dsh-chatgpt select:focus-visible,.dsh-chatgpt a:focus-visible,.dsh-chatgpt summary:focus-visible{outline:2px solid var(--dsw-alias-brand-primary,#526de8);outline-offset:3px}.dsh-chatgpt code{font:12px 'Cascadia Code',Consolas,monospace;overflow-wrap:anywhere}.dsh-chatgpt .cg-notice{padding:12px 14px;border-left:3px solid var(--dsw-alias-border-l2);margin-top:12px;background:var(--dsw-alias-bg-layer-1);overflow-wrap:anywhere}.dsh-chatgpt .cg-notice p:first-child{margin-top:0}.dsh-chatgpt details{margin-top:16px}.dsh-chatgpt summary{cursor:pointer;font-size:13px}.dsh-chatgpt a{color:inherit;text-decoration:underline;text-underline-offset:3px}.dsh-chatgpt .cg-facts{display:grid;grid-template-columns:100px minmax(0,1fr);gap:8px 12px;margin:16px 0 0;font-size:13px}.dsh-chatgpt dt{color:var(--dsw-alias-label-tertiary)}.dsh-chatgpt dd{margin:0;overflow-wrap:anywhere}.dsh-chatgpt .cg-login{background:var(--dsw-alias-label-primary);color:var(--dsw-alias-bg-base,#fff)}@media(max-width:720px){.dsh-chatgpt .cg-grid{grid-template-columns:1fr}.dsh-chatgpt .cg-card{padding:14px}.dsh-chatgpt .cg-actions>button{max-width:100%;white-space:normal}.dsh-chatgpt .cg-facts{grid-template-columns:84px minmax(0,1fr)}}";
      return function ChatGptSettings() {
        var generation = React.useSyncExternalStore(connection.generation.subscribe, connection.generation.getSnapshot);
        var factsState = React.useState(null), facts = factsState[0] && factsState[0].generation === generation ? factsState[0].value : null, setFacts = factsState[1];
        var messageState = React.useState(""), message = messageState[0], setMessage = messageState[1];
        var busyState = React.useState(""), busy = busyState[0], setBusy = busyState[1];
        var refreshingState = React.useState(false), refreshing = refreshingState[0], setRefreshing = refreshingState[1];
        var modelState = React.useState(""), model = modelState[0], setModel = modelState[1];
        var expandedState = React.useState(false), expanded = expandedState[0], setExpanded = expandedState[1];
        var effortState = React.useState(""), effort = effortState[0], setEffort = effortState[1];
        var answerState = React.useState(""), answer = answerState[0], setAnswer = answerState[1];
        var checkState = React.useState(null), check = checkState[0], setCheck = checkState[1];
        var disconnectState = React.useState(false), disconnecting = disconnectState[0], setDisconnecting = disconnectState[1];
        var active = React.useRef(null), read = React.useRef(null), epoch = React.useRef(0), popup = React.useRef(null), navigated = React.useRef("");
        var login = facts && facts.login, pending = login && login.status === "pending", prompt = pending && login.prompt;
        var connected = facts && facts.credential.stored && facts.credential.kind === "grant";
        var conflicts = facts && facts.route.conflicts || [], models = facts && facts.models || [];
        var selected = models.find(function (item) { return item.id === model; });
        var visibleModels = expanded ? models : models.slice(0, 3);
        var retainedModel = model && !visibleModels.some(function (item) { return item.id === model; });
        var validEffort = !effort || !!(selected && selected.reasoning && selected.reasoning.efforts.some(function (item) { return item.id === effort; }));
        var canUse = connected && !conflicts.length && !!selected && selected.supported !== false && validEffort;
        var defaultModel = facts && facts.defaultSelection;
        var loginUrl = pending && login.notice && login.notice.url;
        function acceptedUrl(value) {
          try { var url = new URL(value); return url.protocol === "https:" && url.hostname === "auth.openai.com" && !url.username && !url.password ? url.href : null; }
          catch (_) { return null; }
        }
        function receivedFacts(value) { setFacts({ generation: generation, value: value }); }
        async function call(method, input, signal) {
          var response = await connection.rpc.call("/api", "houdiniFrontend/" + method,
            { args: input === undefined ? {} : { input: input } }, signal);
          if (!response.ok) throw new Error(response.error && response.error.message || "暂时无法完成，请重试。");
          return response.value;
        }
        async function refresh(refreshModels) {
          if (read.current || active.current) return;
          var controller = new AbortController(), at = epoch.current; read.current = controller;
          setRefreshing(true);
          var timeout = setTimeout(function () { controller.abort(); }, 20000);
          try {
            var result = await call("chatgptStatus", refreshModels === true ? { refreshModels: true } : undefined, controller.signal);
            if (!controller.signal.aborted && at === epoch.current && generation === connection.generation.getSnapshot()) receivedFacts(result);
          } catch (_) { if (!controller.signal.aborted && at === epoch.current) setMessage("暂时无法读取连接状态。请检查工作台连接后刷新。"); }
          finally { clearTimeout(timeout); if (read.current === controller) { read.current = null; setRefreshing(false); } }
        }
        React.useEffect(function () {
          epoch.current++; setFacts(null); setCheck(null); setMessage(""); setModel(""); setExpanded(false); setEffort(""); setDisconnecting(false); setBusy(""); setRefreshing(false);
          if (generation) refresh();
          return function () { epoch.current++; if (active.current) active.current.abort(); active.current = null;
            if (read.current) read.current.abort(); read.current = null;
            if (popup.current && !navigated.current) popup.current.close(); popup.current = null; };
        }, [generation]);
        React.useEffect(function () {
          if (!pending || busy) return;
          var timer = setInterval(refresh, 1000);
          return function () { clearInterval(timer); };
        }, [pending, login && login.attemptId, busy, generation]);
        React.useEffect(function () { setAnswer(""); }, [prompt && prompt.id]);
        React.useEffect(function () {
          if (!model && (models.length || defaultModel && defaultModel.provider === "openai")) {
            var initial = defaultModel && defaultModel.provider === "openai" ? defaultModel.model : (models.find(function (item) { return item.supported !== false; }) || models[0]).id;
            setModel(initial); setEffort(defaultModel && defaultModel.provider === "openai" && defaultModel.model === initial ? defaultModel.reasoningEffort || "" : "");
          }
        }, [facts]);
        React.useEffect(function () {
          var url = acceptedUrl(loginUrl);
          if (url && popup.current && navigated.current !== url) {
            try { popup.current.location.href = url; navigated.current = url; } catch (_) { popup.current = null; }
          }
        }, [loginUrl]);
        React.useEffect(function () {
          if (login && login.status !== "pending" && popup.current && !navigated.current) { popup.current.close(); popup.current = null; }
        }, [login && login.status]);
        async function action(name, input) {
          if (active.current) return;
          var controller = new AbortController(); active.current = controller;
          var at = ++epoch.current; if (read.current) read.current.abort(); read.current = null;
          setRefreshing(false);
          if (name === "Start") setCheck(null);
          setBusy(name); setMessage("");
          var timeout = setTimeout(function () { controller.abort(); }, name === "Probe" ? 90000 : 30000);
          try {
            var result = await call("chatgpt" + name, input, controller.signal);
            if (controller.signal.aborted || at !== epoch.current || generation !== connection.generation.getSnapshot()) return;
            if (name === "Probe") setCheck(Object.assign({}, result, { selection: model + "/" + effort }));
            else receivedFacts(result);
            if (name === "Select") setMessage("已设为新对话的默认模型。已有对话可在输入框旁的模型菜单切换。");
            if (name === "Signout") { setDisconnecting(false); setCheck(null); setMessage(result.signout && result.signout.localCleared === false
              ? "操作期间账户已发生变化，当前授权仍保留。请刷新状态后确认。"
              : result.signout && result.signout.revocation !== "confirmed"
                ? "本机 ChatGPT 授权已清除；服务端撤销尚未确认，可在 ChatGPT 设置中移除应用授权。"
                : "本机 ChatGPT 授权已断开。其他模型配置保持原样。"); }
          } catch (error) {
            if (at === epoch.current) setMessage(controller.signal.aborted ? "等待已结束，请刷新确认当前状态后重试。" : String(error.message || "暂时无法完成，请重试。"));
            if (name === "Start" && popup.current && !navigated.current) { popup.current.close(); popup.current = null; }
          } finally {
            clearTimeout(timeout);
            if (active.current === controller) { active.current = null; setBusy(""); }
          }
        }
        function button(label, name, input, disabled, variant) {
          return h(ui.Button, { type: "button", variant: variant || "outline", disabled: !!busy || disabled,
            onClick: function () { return action(name, input); } }, busy === name ? "处理中…" : label);
        }
        function selection() { return { model: model, ...(effort ? { reasoningEffort: effort } : {}) }; }
        var verification = check && check.selection === model + "/" + effort ? check : null;
        var defaultText = defaultModel ? (defaultModel.provider === "openai" && connected && !conflicts.length ? "ChatGPT · " : defaultModel.provider + " · ") + defaultModel.model : "尚未选择";
        return h("section", { className: "dsh-chatgpt", "data-houdini-chatgpt-settings": true, "aria-busy": !!busy || refreshing },
          h("style", null, css),
          h("h2", null, "ChatGPT 订阅"),
          h("p", { className: "cg-muted" }, "用已有的 ChatGPT 账户驱动 Houdini 助手。符合条件的请求使用你的 ChatGPT 套餐或额度，无需填写 API Key。"),
          h("section", { className: "cg-card" },
            h("div", { className: "cg-head" },
              h("h3", { className: "cg-step" }, h("span", { "aria-hidden": true }, "1"), "连接账户"),
              h("span", { className: "cg-status" + (connected ? " cg-good" : "") }, !facts ? "正在读取…" : facts.credential.stored === null ? "状态暂不可用" : connected ? "授权已保存" : "尚未连接")),
            h("p", { className: "cg-muted" }, connected ? "由 DSH 保存和续期本机授权。授权状态不代表当前模型已经通过请求验证。" : "点击后在浏览器中登录，并允许使用 ChatGPT 套餐。完成后回到这里继续。"),
            connected && facts.account && h("p", null, facts.account.name || "ChatGPT 账户", facts.account.email ? " · " + facts.account.email : ""),
            facts && !facts.nativeFlowAvailable && h("div", { className: "cg-notice cg-warn" }, "当前运行环境尚未提供 ChatGPT 登录。请在「Version & Updates」应用配套更新，再重新打开工作台。"),
            facts && facts.credential.error && h("p", { role: "status", className: "cg-warn" }, facts.credential.error.message),
            facts && facts.credential.kind === "api-key" && h("div", { className: "cg-notice cg-warn" }, "OpenAI 当前使用 API Key。请先在「模型」设置处理现有 API 配置，再连接订阅。"),
            h("div", { className: "cg-actions" },
              !pending && h(ui.Button, { className: connected ? undefined : "cg-login", variant: connected ? "outline" : "primary", disabled: !!busy || !facts || !facts.nativeFlowAvailable || !facts.credential.writable || facts.credential.kind === "api-key" || facts.disconnecting,
                onClick: function () {
                  if (active.current) return;
                  navigated.current = ""; popup.current = window.open("", "_blank");
                  return action("Start");
                } }, busy === "Start" ? "正在开始…" : connected ? "重新登录" : "使用 ChatGPT 登录"),
              pending && button("取消登录", "Cancel", { attemptId: login.attemptId }, false),
              h(ui.Button, { variant: "ghost", disabled: !!busy || refreshing, onClick: function () { setMessage(""); setCheck(null); return refresh(true); } }, refreshing ? "刷新中…" : "刷新状态"),
              connected && h(ui.Button, { variant: "ghost", disabled: !!busy || pending, onClick: function () { setDisconnecting(!disconnecting); } }, "断开连接")),
            pending && h("div", { className: "cg-notice", role: "status" },
              h("p", null, "正在等待浏览器授权。完成后此页面会自动更新。"),
              acceptedUrl(loginUrl) && h("a", { href: acceptedUrl(loginUrl), target: "_blank", rel: "noopener noreferrer" }, "打开授权页面"),
              login.notice && login.notice.code && h("p", null, "验证码：", h("code", null, login.notice.code)),
              prompt && h("details", null, h("summary", null, "浏览器没有自动返回？"),
                h("p", { className: "cg-muted" }, "可在下面提交授权页面要求的返回信息。内容仅用于本次登录，不进入聊天。"),
                h("label", null, prompt.kind === "select" ? prompt.message : "授权返回信息",
                  prompt.kind === "select" ? h("select", { value: answer, onChange: function (event) { setAnswer(event.target.value); } },
                    h("option", { value: "" }, "请选择"), prompt.options.map(function (option) { return h("option", { key: option.id, value: option.id }, option.label); })) :
                    h("input", { value: answer, type: "password", autoComplete: "off", spellCheck: false, placeholder: prompt.placeholder || "粘贴浏览器最终的返回地址",
                      onChange: function (event) { setAnswer(event.target.value); } })),
                h("div", { className: "cg-actions" }, button("提交返回信息", "Prompt", { attemptId: login.attemptId, promptId: prompt.id, value: answer }, !answer.trim())))),
            login && login.status === "failed" && h("p", { role: "alert", className: "cg-warn" }, login.error && login.error.message || "登录未完成，请重试。"),
            login && login.status === "cancelled" && h("p", { className: "cg-muted" }, "本次登录已取消。"),
            disconnecting && h("div", { className: "cg-notice" },
              h("p", null, "断开后，使用此授权的后续请求将无法继续。可随时重新登录。需要结束正在进行的任务时，请先使用对话的停止按钮。"),
              h("div", { className: "cg-actions" }, button("确认断开本机授权", "Signout", undefined, false),
                h(ui.Button, { variant: "ghost", disabled: !!busy, onClick: function () { setDisconnecting(false); } }, "保留连接")))),
          h("section", { className: "cg-card" },
            h("h3", { className: "cg-step" }, h("span", { "aria-hidden": true }, "2"), "选择模型"),
            h("p", { className: "cg-muted" }, "按当前 ChatGPT 账户的模型清单排序。首次显示前几个选项，可按需展开；实际使用仍受套餐与额度限制。"),
            conflicts.length > 0 && h("div", { className: "cg-notice cg-warn", role: "status" },
              h("strong", null, "现有 OpenAI 配置需要先处理"), h("ul", null, conflicts.map(function (item) { return h("li", { key: item.field }, item.message); })),
              h("p", null, "请在「模型」中检查对应配置。这里不会覆盖 API 地址、密钥或自定义模型。")),
            h("div", { className: "cg-grid" },
              h("label", null, "模型", h("select", { "aria-label": "ChatGPT 模型", value: model, disabled: !!busy || !models.length,
                onChange: function (event) { setModel(event.target.value); setEffort(""); setCheck(null); setMessage(""); } },
                !models.length && !model && h("option", { value: "" }, connected ? facts.catalogError ? "模型目录暂不可用" : "此账户暂无可选模型" : "连接后读取模型"),
                retainedModel && h("optgroup", { label: "当前选择" },
                  h("option", { value: model }, selected ? selected.name : model + "（当前目录未列出）")),
                visibleModels.map(function (item) { return h("option", { key: item.id, value: item.id, disabled: item.supported === false }, item.name + (item.supported === false ? "（当前不可选）" : "")); }))),
              h("label", null, "思考程度", h("select", { "aria-label": "ChatGPT 思考程度", value: effort,
                disabled: !!busy || !selected || !selected.reasoning && !effort,
                onChange: function (event) { setEffort(event.target.value); setCheck(null); } },
                h("option", { value: "" }, "模型默认"), !validEffort && h("option", { value: effort }, effort + "（需重新选择）"),
                selected && selected.reasoning && selected.reasoning.efforts.map(function (item) { return h("option", { key: item.id, value: item.id }, item.name); })))),
            models.length > 3 && h(ui.Button, { type: "button", variant: "ghost", disabled: !!busy,
              onClick: function () { setExpanded(!expanded); } }, expanded ? "收起更多模型" : "显示全部 " + models.length + " 个模型"),
            model && !selected && connected && !facts.catalogError && h("p", { className: "cg-warn", role: "status" },
              "保留了原选择，但当前账户目录未列出此模型。请选择清单中的模型；已有对话的设置未更改。"),
            selected && selected.supported === false && h("p", { className: "cg-warn", role: "status" }, "当前账户已列出此模型，但运行环境或模型配置暂不支持。请更新运行环境，或在「模型」中检查现有配置。"),
            selected && !validEffort && h("p", { className: "cg-warn", role: "status" }, "原思考程度不在当前模型的选项中，请重新选择。"),
            selected && selected.description && h("p", { className: "cg-muted" }, selected.description),
            selected && h("p", { className: "cg-muted" },
              (selected.inputModalities && selected.inputModalities.includes("image") ? "支持接收参考图与渲染图" : "图片能力以当前模型配置为准") +
              (selected.contextWindow ? " · 上下文 " + selected.contextWindow.toLocaleString() + " tokens" : "")),
            facts && facts.catalogError && h("p", { className: "cg-warn", role: "status" }, facts.catalogError.message),
            h("div", { className: "cg-actions" }, button("设为新对话默认", "Select", selection(), !canUse, "primary"),
              button("测试模型连接", "Probe", selection(), !canUse || !facts.route.configured)),
            h("p", { className: "cg-muted" }, "测试会发送一条简短消息，消耗少量套餐额度，不附带工程或聊天内容。"),
            verification && h("div", { className: "cg-notice" + (verification.ok ? " cg-good" : " cg-warn"), role: "status" },
              h("strong", null, verification.ok ? "这次模型请求成功" : "这次模型请求未成功"), h("p", null, verification.message),
              !verification.ok && h("a", { href: "https://chatgpt.com/settings/usage", target: "_blank", rel: "noopener noreferrer" }, "查看 ChatGPT 用量与权限")),
            h("dl", { className: "cg-facts" }, h("dt", null, "新对话默认"), h("dd", null, h("code", null, defaultText)),
              h("dt", null, "已有对话"), h("dd", null, "继续使用各自选择的模型，在输入框旁可切换。"))),
          h("p", { role: "status", "aria-live": "polite" }, message),
          h("div", { className: "cg-head", style: { marginTop: 20 } }, h("h3", null, "用量与适用范围"),
            h("a", { href: "https://chatgpt.com/settings/usage", target: "_blank", rel: "noopener noreferrer" }, "管理 ChatGPT 用量 ↗")),
          h("p", { className: "cg-muted" }, "这里暂不读取剩余额度。套餐、应用用量限制和额外额度以 ChatGPT 设置为准；本插件不自动切换到 API 计费。"),
          h("details", null, h("summary", null, "订阅能用于哪些功能？"),
            h("p", { className: "cg-muted" }, "此连接用于助手对话和规划。Houdini 建模与渲染仍在你的电脑执行。图片生成、教程语音转录沿各自的服务配置，不自动复用这份订阅授权。"),
            h("p", { className: "cg-muted" }, "登录不会导入你在 ChatGPT 中的历史对话。浏览器负责账户登录，DSH 管理本机凭据。"),
            h("a", { href: "https://developers.openai.com/siwc/quickstart", target: "_blank", rel: "noopener noreferrer" }, "查看 OpenAI 官方说明")));
      };
    }

    // Tutorial preferences use DSH's shared form and credential registry.
    function createVideoSettings(connection, forms) {
      var form = forms.get("houdini-frontend");
      var inputStyle = { width: "100%", boxSizing: "border-box", border: "1px solid var(--dsw-alias-border-l2,#444b55)",
        borderRadius: 8, padding: "9px 11px", font: "inherit", color: "inherit", background: "var(--dsw-alias-bg-layer-1,#24272b)" };
      var buttonStyle = Object.assign({}, inputStyle, { width: "auto", cursor: "pointer" });
      return function VideoSettings() {
        var snapshot = React.useSyncExternalStore(function (fn) { return form.subscribe(fn); }, function () { return form.getSnapshot(); });
        var generation = React.useSyncExternalStore(connection.generation.subscribe, connection.generation.getSnapshot);
        var draftState = React.useState(null), draft = draftState[0], setDraft = draftState[1];
        var factsState = React.useState(null), facts = factsState[0], setFacts = factsState[1];
        var messageState = React.useState(""), message = messageState[0], setMessage = messageState[1];
        var busyState = React.useState(false), busy = busyState[0], setBusy = busyState[1];
        var checksState = React.useState(null), checks = checksState[0], setChecks = checksState[1];
        var customState = React.useState(false), customModel = customState[0], setCustomModel = customState[1];
        var pending = React.useRef(null);
        var value = draft || snapshot.value || { videoProvider: "", videoModel: "", videoPython: "" };
        function edit(field, next) {
          setDraft(Object.assign({}, value, { revision: draft ? draft.revision : snapshot.revision }, { [field]: next }));
          setMessage("");
        }
        async function request(method) {
          if (pending.current) pending.current.abort();
          var controller = new AbortController(); pending.current = controller;
          var timeout = setTimeout(function () { controller.abort(); }, 15000);
          try {
            var result = await connection.rpc.call("/api", "houdiniFrontend/" + method, { args: {} }, controller.signal);
            if (!result.ok) throw new Error(result.error && result.error.message || "无法读取设置");
            if (controller.signal.aborted || connection.generation.getSnapshot() !== generation) return null;
            return result.value;
          } finally { clearTimeout(timeout); }
        }
        async function refresh() {
          try { var result = await request("videoSettings"); if (result) setFacts(result); }
          catch (error) { if (!pending.current || !pending.current.signal.aborted) setMessage("读取服务配置失败：" + String(error.message || error)); }
        }
        React.useEffect(function () {
          setFacts(null); setChecks(null);
          if (generation) refresh();
          return function () { if (pending.current) pending.current.abort(); };
        }, [generation, snapshot.revision]);
        async function save() {
          setBusy(true); setMessage("");
          try {
            var ok = await form.mutate(["videoProvider", "videoModel", "videoPython"].map(function (field) {
              return { op: "set", path: [field], value: String(value[field] || "").trim() };
            }), draft ? draft.revision : snapshot.revision);
            if (!ok) { setMessage("未保存：设置已被其他页面修改或当前不可写。草稿已保留，请重新载入后再修改。"); return; }
            setDraft(null); setMessage("已保存。新转录使用此设置；已有任务绑定原服务与模型，续跑时请指定原配置。");
          } catch (error) { setMessage("保存失败：" + String(error.message || error)); }
          finally { setBusy(false); }
        }
        async function diagnose() {
          setBusy(true); setMessage("");
          try { var result = await request("videoDiagnostics"); if (result) setChecks(result); }
          catch (error) { setMessage("检查失败：" + String(error.message || error)); }
          finally { setBusy(false); }
        }
        var routes = facts && facts.routes || [], route = routes.find(function (item) { return item.provider === value.videoProvider; });
        var models = route && route.models || [];
        var otherModel = customModel || !!value.videoModel && !models.some(function (model) { return model.id === value.videoModel; });
        var ready = snapshot.status === "ready" && snapshot.writable;
        function field(label, child, note) {
          return React.createElement("label", { style: { display: "grid", gap: 7, marginTop: 20 } },
            React.createElement("strong", { style: { fontSize: 13 } }, label), child,
            note && React.createElement("span", { style: { fontSize: 12, opacity: .75 } }, note));
        }
        return React.createElement("section", { "data-houdini-video-settings": true, style: { maxWidth: 660, padding: "8px 4px 28px", fontSize: 14, lineHeight: 1.65 } },
          React.createElement("h2", { style: { fontSize: 20, margin: "0 0 8px" } }, "教程视频"),
          React.createElement("p", { style: { margin: 0, opacity: .8 } }, "把教程讲解转成可回看的文字，再结合画面复刻工程。转录供应商、账号和密钥共用「模型」设置；这里单独选择转录模型，不会改变当前聊天模型。"),
          field("转录服务供应商", React.createElement("select", { style: inputStyle, value: value.videoProvider, disabled: !ready || busy || !facts,
            onChange: function (event) {
              setCustomModel(false);
              setDraft(Object.assign({}, value, { revision: draft ? draft.revision : snapshot.revision,
                videoProvider: event.target.value, videoModel: "" })); setMessage("");
            } },
            React.createElement("option", { value: "" }, "请选择已配置的供应商"),
            value.videoProvider && !route && React.createElement("option", { value: value.videoProvider }, value.videoProvider + "（当前不可用）"),
            routes.map(function (item) { return React.createElement("option", { key: item.provider, value: item.provider }, item.display_name || item.provider); })),
            "读取「模型」中已配置的供应商。列表包含仅支持对话的服务，请确认供应商提供语音转录，并查看下方配置提示。"),
          !routes.length && facts && React.createElement("p", { role: "status" }, "尚无已配置的供应商。请先在「模型」中添加供应商、API 地址和密钥，再点击刷新。"),
          field("转录模型 ID", React.createElement("select", { style: inputStyle, value: otherModel ? "__dsh_other_transcription_model__" : value.videoModel,
            disabled: !ready || busy || !route,
            onChange: function (event) {
              var other = event.target.value === "__dsh_other_transcription_model__";
              setCustomModel(other); edit("videoModel", other ? "" : event.target.value);
            } },
            React.createElement("option", { value: "" }, "请选择供应商已配置的模型"),
            models.map(function (model) { return React.createElement("option", { key: model.id, value: model.id },
              model.name && model.name !== model.id ? model.name + "（" + model.id + "）" : model.id); }),
            React.createElement("option", { value: "__dsh_other_transcription_model__" }, "其他转录模型（填写 ID）")),
            "模型列表来自供应商的当前配置，目录中的模型不一定支持转录。仅提供语音的模型可选择「其他转录模型」填写。"),
          otherModel && field("其他转录模型 ID", React.createElement("input", { style: inputStyle, value: value.videoModel,
            disabled: !ready || busy || !route, placeholder: "例如 qwen3-asr-flash", onChange: function (event) { edit("videoModel", event.target.value); } }),
            "填写供应商公布的准确模型 ID；该设置仅用于转录，不会把语音模型加入聊天目录。"),
          route && React.createElement("p", { style: { fontSize: 12, overflowWrap: "anywhere", opacity: .8 } },
            "供应商地址：" + (route.origin || "当前配置未提供可复用的音频 API 地址") + " · 凭据：" + (route.credential && route.credential.configured ? "已配置" : "未配置")),
          route && route.diagnostics && route.diagnostics.length > 0 && React.createElement("ul", { role: "status", style: { fontSize: 12 } },
            route.diagnostics.map(function (note, index) { return React.createElement("li", { key: index }, note); })),
          React.createElement("details", { style: { marginTop: 20 } }, React.createElement("summary", { style: { cursor: "pointer" } }, "本机依赖与高级设置"),
            field("Python 程序", React.createElement("input", { style: inputStyle, value: value.videoPython, disabled: !ready || busy,
              placeholder: "自动使用 Houdini 自带 Python；可填写完整路径", onChange: function (event) { edit("videoPython", event.target.value); } }),
              "默认复用 Houdini 自带 Python；FFmpeg 和 ffprobe 使用插件的私有运行目录，不依赖全局安装。媒体处理在 Host 本机运行。"),
            React.createElement("button", { type: "button", style: Object.assign({}, buttonStyle, { marginTop: 12 }), disabled: busy || !!draft, onClick: diagnose }, "检查本机依赖"),
            draft && React.createElement("p", { style: { fontSize: 12 } }, "先保存修改，再检查实际生效的程序。"),
            checks && React.createElement("ul", null, checks.dependencies.map(function (item) { return React.createElement("li", { key: item.name, title: item.path || "" },
              item.name + "：" + (item.available ? item.version : item.error)); })),
            checks && React.createElement("p", { style: { fontSize: 12, overflowWrap: "anywhere" } }, checks.note),
            checks && checks.dependencies.some(function (item) { return !item.available; }) && checks.repair &&
              React.createElement("p", { role: "status", style: { fontSize: 12, overflowWrap: "anywhere" } },
                checks.repair.label + "：" + checks.repair.detail)),
          React.createElement("div", { style: { display: "flex", flexWrap: "wrap", gap: 10, marginTop: 24 } },
            React.createElement("button", { type: "button", style: buttonStyle, disabled: !ready || busy || !draft, onClick: save }, busy ? "处理中…" : "保存设置"),
            React.createElement("button", { type: "button", style: buttonStyle, disabled: busy, onClick: function () { setDraft(null); setCustomModel(false); setMessage(""); refresh(); } }, "刷新配置 / 放弃草稿")),
          React.createElement("p", { role: "status", style: { minHeight: 22, margin: "12px 0" } }, message || (!ready ? "正在等待可编辑的本机设置…" : "")),
          React.createElement("p", { style: { fontSize: 12, opacity: .75 } }, "支持 OpenAI 兼容的语音转录接口，以及千问 qwen3-asr-flash 和 qwen-audio-3.0-asr-flash 的音频接口。普通百炼账号可在「模型」中添加自定义 API；Token Plan 供应商的聊天额度不代表可用于转录。保存和依赖检查不会上传音频；首次处理会按你允许的服务和费用试转录短段，成功片段保留用于续跑。画面仍需单独核对。"));
      };
    }

    function createSupportReporter(connection) {
      return function SupportReporter(props) {
        var ui = require("@deepseek-ai/dsh-client-ui-primitives");
        var openState = React.useState(false), opened = openState[0], setOpened = openState[1];
        var textState = React.useState(""), description = textState[0], setDescription = textState[1];
        var logsState = React.useState(true), includeLogs = logsState[0], setLogs = logsState[1];
        var previousState = React.useState(true), includePrevious = previousState[0], setPrevious = previousState[1];
        var contentState = React.useState(false), includeContent = contentState[0], setContent = contentState[1];
        var reportState = React.useState(null), setReport = reportState[1];
        var statusState = React.useState(""), status = statusState[0], setStatus = statusState[1];
        var busyState = React.useState(""), busy = busyState[0], setBusy = busyState[1];
        var detailsState = React.useState(false), details = detailsState[0], setDetails = detailsState[1];
        var fileState = React.useState(null), expandedFile = fileState[0], setExpandedFile = fileState[1];
        var errorState = React.useState(""), errorDetail = errorState[0], setErrorDetail = errorState[1];
        var requestRef = React.useRef(null);
        var generation = React.useSyncExternalStore(connection.generation.subscribe, connection.generation.getSnapshot);
        var report = reportState[0] && reportState[0].sessionId === props.sessionId && reportState[0].generation === generation ? reportState[0].value : null;
        function invalidate() {
          if (requestRef.current) requestRef.current.abort();
          requestRef.current = null; setReport(null); setBusy(""); setStatus(""); setErrorDetail(""); setExpandedFile(null); setDetails(false);
        }
        function close() { invalidate(); setOpened(false); }
        React.useEffect(function () {
          close(); setDescription(""); setContent(false);
          return function () { if (requestRef.current) requestRef.current.abort(); };
        }, [props.sessionId, generation]);
        function download(value) {
          var bytes = Uint8Array.from(atob(value.archiveBase64), function (character) { return character.charCodeAt(0); });
          var url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
          var link = document.createElement("a"); link.href = url; link.download = value.filename;
          document.body.appendChild(link); link.click(); link.remove();
          setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
          setStatus("已开始保存。请在下载窗口确认文件位置和完成状态，之后把文件发给开发者。");
        }
        async function act(action) {
          if (requestRef.current) return;
          if (report) {
            if (action === "save") download(report);
            else { setDetails(true); setExpandedFile(null); }
            return;
          }
          setBusy(action); setStatus("正在整理报告，请稍候…"); setErrorDetail("");
          var controller = new AbortController(); requestRef.current = controller;
          var timeout = setTimeout(function () { controller.abort(); }, 45000);
          try {
            var response = await connection.rpc.call("/api", "houdiniFrontend/supportReport", { args: { input: {
              sessionId: props.sessionId, description: description, includeLogs: includeLogs,
              includePrevious: includePrevious, includeContent: includeContent
            } } }, controller.signal);
            if (controller.signal.aborted || requestRef.current !== controller) return;
            if (!response.ok) throw new Error(response.error && response.error.message || "报告收集失败");
            setReport({ sessionId: props.sessionId, generation: generation, value: response.value });
            if (action === "save") download(response.value);
            else { setDetails(true); setExpandedFile(null); setStatus(""); }
          } catch (error) {
            if (requestRef.current === controller) {
              setStatus(controller.signal.aborted ? "整理已取消或超时，可以重试。" : "暂时没能整理好报告，请重试。");
              setErrorDetail(String(error.message || error));
            }
          } finally {
            clearTimeout(timeout);
            if (requestRef.current === controller) { requestRef.current = null; setBusy(""); }
          }
        }
        function option(label, note, value, setter) {
          return React.createElement("div", { className: "dsh-support-option" },
            React.createElement(ui.Checkbox, { label: label, checked: value, onChange: function (checked) { invalidate(); setter(checked); } }),
            React.createElement("p", null, note));
        }
        var footer = React.createElement(React.Fragment, null,
          React.createElement(ui.Button, { variant: "ghost", onClick: close }, "关闭"),
          React.createElement(ui.Button, { variant: "outline", disabled: !!busy, onClick: function () {
            if (details) { setDetails(false); setExpandedFile(null); } else return act("preview");
          } }, details ? "返回填写" : busy === "preview" ? "正在整理…" : "查看报告内容"),
          React.createElement(ui.Button, { variant: "primary", disabled: !!busy, onClick: function () { return act("save"); } },
            busy === "save" ? "正在整理并保存…" : "保存报告"));
        var body = details && report ? React.createElement(React.Fragment, null,
          React.createElement("div", { className: "dsh-support-toolbar" },
            React.createElement("strong", null, "报告内容"),
            React.createElement(ui.Button, { size: "sm", disabled: expandedFile === null, onClick: function () { setExpandedFile(null); } }, "收起详情")),
          React.createElement("p", { className: "dsh-support-note" }, "这些记录供开发者排查问题。你可以按需查看，分享前确认没有私人或项目敏感内容。"),
          report.files.map(function (file, index) {
            var expanded = expandedFile === file.name, contentId = "dsh-support-file-" + index;
            return React.createElement("section", { key: file.name, className: "dsh-support-file" },
              React.createElement(ui.Button, { variant: "ghost", "aria-expanded": expanded, "aria-controls": contentId,
                onClick: function () { setExpandedFile(expanded ? null : file.name); } },
                React.createElement("span", { className: "dsh-support-file-heading" }, file.label || "补充记录",
                  React.createElement("small", null, file.description || "供开发者排查问题。")),
                React.createElement("span", null, expanded ? "收起" : "查看")),
              expanded && React.createElement("div", { id: contentId, className: "dsh-support-file-body" },
                React.createElement("small", null, file.name),
                React.createElement("pre", { tabIndex: 0, "aria-label": (file.label || "补充记录") + "详情" }, file.text)));
          })) : React.createElement(React.Fragment, null,
          React.createElement("p", { className: "dsh-support-note" }, "把问题和相关记录保存成一个文件，发给开发者帮助排查。"),
          React.createElement("label", null, "遇到了什么问题？",
            React.createElement("textarea", { "aria-label": "问题描述", "data-modal-autofocus": true, className: "dsh-support-input",
              value: description, maxLength: 4000, rows: 3, placeholder: "例如：重开 Houdini 后，之前的对话无法继续操作。也可以留空。",
              onChange: function (event) { invalidate(); setDescription(event.target.value); } })),
          React.createElement("strong", null, "附带哪些信息"),
          React.createElement("div", { className: "dsh-support-options" },
            option("当前运行情况", "插件最近的启动、连接和报错记录，用来排查卡住或操作失败。", includeLogs, setLogs),
            option("之前的运行情况", "有记录时补充之前的报错，适合重启后再来反馈。", includePrevious, setPrevious),
            option("这段对话的内容", "附上聊天和 AI 的操作细节，帮助排查理解偏差或结果不对。可能包含项目内容。", includeContent, setContent)),
          React.createElement("p", { className: "dsh-support-note" }, "默认包含软件版本和出错步骤，不会附带工程文件或图片。只保存到你的电脑，不会自动发送。"));
        return React.createElement(React.Fragment, null,
          React.createElement(ui.Button, { size: "sm", variant: "ghost", disabled: !props.sessionId, onClick: function () { setOpened(true); } }, "报告问题"),
          React.createElement(ui.Modal, { open: opened, onClose: close, title: "报告问题", closeLabel: "关闭报告窗口",
            className: "dsh-support-modal", contentClassName: "dsh-support-content", footer: footer },
            React.createElement("div", { className: "dsh-support-body" }, body,
              status && React.createElement("p", { role: "status", className: "dsh-support-status" }, status),
              errorDetail && React.createElement("details", { className: "dsh-support-sharing" },
                React.createElement("summary", null, "查看失败原因"), React.createElement("p", null, errorDetail)),
              React.createElement("details", { className: "dsh-support-sharing" },
                React.createElement("summary", null, "如何发送给开发者？"),
                React.createElement("p", null, "保存后，把文件通过你与开发者联系的渠道发过去，也可以在 GitHub 反馈页面附上文件。GitHub 的内容公开可见，涉及项目资料时请私下发送。"),
                React.createElement("p", null, "常见密钥和个人路径会自动隐藏，分享前仍请检查内容。需要完整对话和附件时，可在会话菜单选择「下载 Session 日志」。"),
                report && React.createElement("div", null,
                  React.createElement(ui.Button, { size: "sm", onClick: function () {
                    navigator.clipboard.writeText(report.summary).then(function () { setStatus("问题说明已复制。"); }, function () { setStatus("没能复制，请在报告内容中查看「问题说明」。"); });
                  } }, "复制问题说明"),
                  React.createElement("a", { href: report.issuesUrl, target: "_blank", rel: "noopener noreferrer" }, "前往反馈页面"))))));
      };
    }

    function HoudiniTrace(props) {
      return React.createElement(getTraceView(React), props);
    }

    function apply(ctx) {
      installLaunchSessionHint(ctx);
      var slots = ctx.get("slots");
      if (slots === undefined) return;
      if (typeof ctx.inject === "function") ctx.inject(["connection", "configForms"], function (scope) {
        var forms = scope.get("configForms");
        scope.effect(function () { return forms.whileServed(["houdini-frontend"], function () {
          return slots.inject("settings.section", function () {
            return slots.register({ name: "settings.section", id: "houdini-video", order: 15, label: "教程视频" },
              createVideoSettings(scope.get("connection"), forms));
          });
        }); });
      });
      if (typeof ctx.inject === "function") ctx.inject(["connection"], function (scope) {
        slots.inject("settings.section", function () {
          return slots.register({ name: "settings.section", id: "houdini-chatgpt", order: 12, label: "ChatGPT 订阅" },
            createChatGptSettings(scope.get("connection")));
        });
        var titleActions = createHoudiniTitleAction(scope.get("connection"));
        var updates = createWorkbenchUpdates(scope.get("connection"));
        scope.effect(function () { return titleActions.dispose; });
        slots.inject("conversation.session.header.controls", function () {
          return slots.register({ name: "conversation.session.header.controls", id: "houdini-update", order: 10 }, updates.Button);
        });
        slots.inject("shell.overlay", function () {
          return slots.register({ name: "shell.overlay", id: "houdini-update-feedback", order: 10 }, updates.Lifecycle);
        });
        slots.inject("sidebar.workspaces.session.menu.item", function () {
          return slots.register({ name: "sidebar.workspaces.session.menu.item", id: "houdini-title-refresh", order: 210 },
            titleActions.Menu);
        });
        slots.inject("shell.overlay", function () {
          return slots.register({ name: "shell.overlay", id: "houdini-title-feedback", order: 20 }, titleActions.Feedback);
        });
        slots.inject("conversation.session.header.utilities", function () {
          return slots.register({ name: "conversation.session.header.utilities", id: "houdini-support-report", order: 20 },
            createSupportReporter(scope.get("connection")));
        });
      });
      if (typeof ctx.inject === "function") ctx.inject(["connection", "uiSession", "sessions", "uiWorkspace"], function (scope) {
        var workbench = createWorkbenchUi(scope.get("connection"), scope.get("uiSession"), scope.get("sessions"), scope.get("uiWorkspace"));
        [["sidebar.session.row.leading", "houdini-project-mark", workbench.Mark],
          ["sidebar.session.row.hover", "houdini-project-detail", workbench.Detail],
          ["conversation.input.left", "houdini-initial-project", workbench.Blank],
          ["conversation.session.header.utilities", "houdini-project-label", workbench.Label],
          ["conversation.session.header.controls", "houdini-window-pin", workbench.Pin],
          ["sidebar.footer.action", "houdini-project-entry", workbench.Footer],
          ["shell.overlay", "houdini-project-feedback", workbench.Lifecycle]].forEach(function (entry) {
          slots.inject(entry[0], function () { return slots.register({ name: entry[0], id: entry[1], order: 5 }, entry[2]); });
        });
      });
      if (typeof ctx.inject === "function") ctx.inject(["connection", "uiConversation"], function (scope) {
        var conversation = scope.get("uiConversation"), connection = scope.get("connection");
        if (!conversation || !connection) return;
        var delivery = nodeDeliveryFactory(React, readHoudiniCanonical);
        var deliveryCssId = "dsh-houdini/node-delivery.css";
        if (typeof document !== "undefined") {
          var deliveryStyle = document.querySelector("style[data-plugin-css=" + JSON.stringify(deliveryCssId) + "]");
          if (!deliveryStyle) {
            deliveryStyle = document.createElement("style");
            deliveryStyle.dataset.plugin = "dsh-houdini";
            deliveryStyle.dataset.pluginCss = deliveryCssId;
            document.head.appendChild(deliveryStyle);
          }
          deliveryStyle.textContent = delivery.css;
        }
        scope.effect(function () { return conversation.events.register(delivery.definition); });
        scope.effect(function () { return conversation.views.register(delivery.view); });
        slots.inject("conversation.chat.turnTail", function () {
          return slots.register({ name: "conversation.chat.turnTail", id: "houdini-node-delivery", order: 10 },
            delivery.createTail(connection, conversation));
        });
      });

      slots.inject("conversation.chat.turnTail", function () {
        return slots.register({ name: "conversation.chat.turnTail", id: "houdini-delivery-scope", order: 9 },
          HoudiniDeliveryScope);
      });

      slots.inject("conversation.view", function () {
        return slots.register(
          { name: "conversation.view", id: "houdinitrace", order: 5, label: "执行记录" },
          HoudiniTrace
        );
      });


    }

    return { apply: apply };
  },
});
