// dsh-houdini client half: Trace, project navigation and shared-executor selection.
// Handwritten CJS factory; generated catalogs and Trace sources are built below.
window.__ModuleLoader__.load({
  id: "dsh-houdini",
  factory: function (require) {
    var React = require("react");

    function Button(props) {
      var options = Object.assign({ type: "button" }, props);
      options.className = "dsh-houdini-button" + (props.className ? " " + props.className : "");
      delete options.variant; delete options.size; delete options.icon;
      options["data-variant"] = props.variant || "outline";
      options["data-size"] = props.size || "md";
      return React.createElement("button", options, props.children);
    }

    function Checkbox(props) {
      return React.createElement("label", { className: "dsh-houdini-checkbox" },
        React.createElement("input", { type: "checkbox", checked: !!props.checked,
          onChange: function (event) { props.onChange(event.target.checked); } }),
        React.createElement("span", null, props.label));
    }

    function Tooltip(props) {
      return React.createElement("span", { className: "dsh-houdini-tooltip", title: props.label }, props.children);
    }

    function Toast(props) {
      return React.createElement("div", { className: "dsh-houdini-toast", role: props.role || "status" },
        React.createElement("span", null, props.text), props.children,
        React.createElement(Button, { variant: "ghost", size: "sm", onClick: props.onDone }, "关闭"));
    }

    function MenuItemButton(props) {
      function select(event) { if (!props.disabled && props.onSelect) props.onSelect(event); }
      return React.createElement("button", { type: "button", role: "menuitem",
        className: "dsh-houdini-menuitem", disabled: !!props.disabled,
        onClick: select, onPointerDown: props.onPointerDown,
        onKeyDown: function (event) {
          if (event.key === "Enter") { event.preventDefault(); select(event); }
          else if (event.key === " ") event.preventDefault();
        },
        onKeyUp: function (event) {
          if (event.key === " ") { event.preventDefault(); select(event); }
        } },
        props.icon, props.children);
    }

    function Menu(props) {
      var root = React.useRef(null), panel = React.useRef(null);
      var placement = React.useState({}), position = placement[0], setPosition = placement[1];
      React.useEffect(function () {
        if (!props.open) return;
        function place() {
          var anchor = root.current && root.current.getBoundingClientRect();
          var rect = anchor || { left: 0, right: 0, top: 0, bottom: 0 };
          var viewportWidth = typeof window !== "undefined" && window.innerWidth || 1024;
          var viewportHeight = typeof window !== "undefined" && window.innerHeight || 768;
          var width = panel.current && panel.current.offsetWidth || 340;
          var left = Math.max(12, Math.min(viewportWidth - width - 12, rect.right - width));
          var below = viewportHeight - rect.bottom - 12;
          var above = rect.top - 12, useBelow = below >= Math.min(320, above);
          var height = panel.current && panel.current.scrollHeight || 320;
          // Pin the top while observations refresh. A user disclosure/resize
          // may place again; incoming windows never move a pending click.
          var top = useBelow ? rect.bottom + 4 : Math.max(12, rect.top - Math.min(height, above) - 4);
          var next = { left: left, top: top, maxHeight: Math.max(80, viewportHeight - top - 12), visibility: "visible" };
          setPosition(next);
        }
        function outside(event) {
          if (root.current && !root.current.contains(event.target)) props.onClose();
        }
        function keydown(event) {
          if (event.key === "Escape") { event.preventDefault(); props.onClose(); var anchor = root.current && root.current.querySelector('[aria-haspopup="menu"]'); if (anchor) anchor.focus(); return; }
          if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
          var items = panel.current ? Array.from(panel.current.querySelectorAll("[role='menuitem']:not(:disabled),summary")).filter(function (item) {
            var folded = item.closest("details:not([open])");
            return (!folded || folded.firstElementChild === item) && item.getClientRects().length > 0;
          }) : [];
          if (!items.length) return;
          event.preventDefault();
          var current = items.indexOf(document.activeElement), index = current;
          if (event.key === "Home") index = 0;
          else if (event.key === "End") index = items.length - 1;
          else if (event.key === "ArrowDown") index = (current + 1) % items.length;
          else index = current <= 0 ? items.length - 1 : current - 1;
          items[index].focus();
        }
        place();
        var surface = panel.current;
        if (surface) surface.addEventListener("toggle", place, true);
        document.addEventListener("mousedown", outside);
        document.addEventListener("keydown", keydown);
        if (typeof window !== "undefined") {
          window.addEventListener("resize", place);
          window.addEventListener("scroll", place, true);
        }
        return function () {
          document.removeEventListener("mousedown", outside);
          document.removeEventListener("keydown", keydown);
          if (surface) surface.removeEventListener("toggle", place, true);
          if (typeof window !== "undefined") {
            window.removeEventListener("resize", place);
            window.removeEventListener("scroll", place, true);
          }
        };
      }, [props.open]);
      return React.createElement("span", { className: "dsh-houdini-menu-root", ref: root }, props.anchor,
        props.open && React.createElement("div", { className: "dsh-houdini-menu-surface " + (props.listClassName || ""),
          role: "menu", ref: panel, style: position }, props.children));
    }

    function Modal(props) {
      var dialog = React.useRef(null);
      React.useEffect(function () {
        if (!props.open) return;
        var previous = document.activeElement;
        var root = dialog.current;
        function focusable() {
          return root ? Array.from(root.querySelectorAll("button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])")) : [];
        }
        var initial = root && (root.querySelector("[data-modal-autofocus]") || focusable()[0] || root);
        if (initial && initial.focus) initial.focus();
        function keydown(event) {
          if (event.key === "Escape") { event.preventDefault(); props.onClose(); return; }
          if (event.key !== "Tab" || !root) return;
          var items = focusable();
          if (!items.length) { event.preventDefault(); return; }
          var first = items[0], last = items[items.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
        document.addEventListener("keydown", keydown);
        return function () {
          document.removeEventListener("keydown", keydown);
          if (previous && previous.focus) previous.focus();
        };
      }, [props.open]);
      if (!props.open) return null;
      return React.createElement("div", { className: "dsh-houdini-modal-backdrop",
        onMouseDown: function (event) { if (event.target === event.currentTarget) props.onClose(); } },
        React.createElement("section", { className: "dsh-houdini-modal " + (props.className || ""), ref: dialog,
          role: "dialog", "aria-modal": true, "aria-label": props.title, tabIndex: -1 },
          React.createElement("div", { className: "dsh-houdini-modal-header" },
            React.createElement("strong", null, props.title),
            React.createElement(Button, { variant: "ghost", size: "sm", "aria-label": props.closeLabel, onClick: props.onClose }, "关闭")),
          React.createElement("div", { className: "dsh-houdini-modal-body " + (props.contentClassName || "") }, props.children),
          props.footer && React.createElement("div", { className: "dsh-houdini-modal-footer" }, props.footer)));
    }

    var ui = { Button: Button, Checkbox: Checkbox, Tooltip: Tooltip, Toast: Toast,
      Menu: Menu, MenuItemButton: MenuItemButton, Modal: Modal };

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
      '.dsh-houdini-target-menu{width:320px;max-width:calc(100vw - 24px);padding:4px!important}.dsh-houdini-target-heading{display:grid;gap:4px;padding:10px 10px 9px}.dsh-houdini-target-heading strong{font-size:13px;font-weight:600;color:var(--dsw-alias-label-primary)}.dsh-houdini-target-heading>span,.dsh-houdini-target-meta{font-size:11px;color:var(--dsw-alias-label-tertiary);line-height:1.5}' +
      '.dsh-houdini-target-current{margin:0 0 4px}.dsh-houdini-target-current [role="menuitem"],.dsh-houdini-target-unavailable{min-height:48px}.dsh-houdini-target-unavailable{display:flex;align-items:center;gap:8px;padding:7px 10px;box-sizing:border-box}.dsh-houdini-target-section{border-top:1px solid var(--dsw-alias-border-l1)}.dsh-houdini-target-section>summary{display:flex;align-items:center;justify-content:space-between;box-sizing:border-box;min-height:36px;padding:7px 10px;list-style:none;border-radius:var(--dsw-radius-sm);color:var(--dsw-alias-label-secondary);font-size:12px;cursor:pointer}.dsh-houdini-target-section>summary::-webkit-details-marker{display:none}.dsh-houdini-target-section>summary::after{content:"›";font-size:16px;line-height:12px}.dsh-houdini-target-section[open]>summary::after{transform:rotate(90deg)}.dsh-houdini-target-section>summary:hover{background:var(--dsw-alias-interactive-bg-hover)}.dsh-houdini-target-section>summary:focus-visible{outline:2px solid var(--dsw-focus-ring-color);outline-offset:-2px}.dsh-houdini-target-info{display:grid;gap:3px;margin:2px 10px 8px;font-size:11px;line-height:1.5}.dsh-houdini-target-info dt{color:var(--dsw-alias-label-tertiary)}.dsh-houdini-target-info dd{margin:0 0 5px;color:var(--dsw-alias-label-secondary);overflow-wrap:anywhere}' +
      '.dsh-houdini-target-group{padding:8px 10px 3px;color:var(--dsw-alias-label-tertiary);font-size:10px}.dsh-houdini-target-choices{max-height:min(240px,40vh);overflow:auto}.dsh-houdini-target-list{overflow:visible}.dsh-houdini-target-list [role="menuitem"]{height:auto;min-height:48px;padding-top:7px;padding-bottom:7px}.dsh-houdini-target-row{display:grid;gap:3px;min-width:0;flex:1}.dsh-houdini-target-title{display:flex;align-items:center;gap:8px;min-width:0;overflow:hidden;text-overflow:ellipsis}.dsh-houdini-target-selected{margin-left:auto;color:var(--dsw-alias-state-business-primary)}.dsh-houdini-target-error{margin:0 10px 8px;color:var(--dsw-alias-label-secondary);font-size:11px}.dsh-houdini-target-error summary{cursor:pointer}.dsh-houdini-target-error pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:180px;overflow:auto;font:11px/1.5 Consolas,monospace}.dsh-houdini-target-message{margin:0;padding:8px 10px;color:var(--dsw-alias-label-secondary);font-size:12px;white-space:normal;line-height:1.6}@media(pointer:coarse){.dsh-houdini-target-menu [role="menuitem"],.dsh-houdini-target-section>summary{min-height:44px}}' +
      '@media(max-width:540px){.dsh-houdini-project-chip{max-width:calc(100vw - 130px);gap:5px;padding:0 7px}.dsh-houdini-chip-name{max-width:105px}.dsh-houdini-chip-status{font-size:10px;padding-left:5px}}' +
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
      '.dsh-houdini-tooltip{display:inline-flex}.dsh-houdini-button{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:32px;padding:5px 12px;border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-md);background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);font:inherit;font-size:12px;cursor:pointer}.dsh-houdini-button[data-size="sm"]{min-height:26px;padding:3px 9px;font-size:11px}.dsh-houdini-button[data-variant="primary"]{border-color:var(--dsw-alias-button-primary-fill);background:var(--dsw-alias-button-primary-fill);color:var(--dsw-alias-label-primary-foreground)}.dsh-houdini-button[data-variant="ghost"]{border-color:transparent;background:transparent;color:var(--dsw-alias-label-secondary)}.dsh-houdini-button:hover:not(:disabled){background:var(--dsw-alias-interactive-bg-hover)}.dsh-houdini-button[data-variant="primary"]:hover:not(:disabled){background:var(--dsw-alias-button-primary-hover)}.dsh-houdini-button:focus-visible,.dsh-houdini-menuitem:focus-visible{outline:2px solid var(--dsw-focus-ring-color);outline-offset:1px}.dsh-houdini-button:disabled{opacity:.5;cursor:default}.dsh-houdini-checkbox{display:flex;align-items:center;gap:8px;color:var(--dsw-alias-label-primary);font-size:13px}.dsh-houdini-checkbox input{width:16px;height:16px;margin:0}' +
      '.dsh-houdini-button.dsh-houdini-window-pin{border-radius:7px;box-shadow:none}.dsh-houdini-window-pin svg{display:block;flex:none}' +
      '.dsh-houdini-menu-root{display:inline-flex;position:relative}.dsh-houdini-menu-surface{position:fixed;z-index:1000;box-sizing:border-box;overflow:auto;border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-lg);background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary);box-shadow:var(--dsw-elevation-prominent)}.dsh-houdini-menuitem{display:flex;align-items:center;gap:8px;width:100%;box-sizing:border-box;min-height:34px;padding:7px 10px;border:0;border-radius:var(--dsw-radius-sm);background:transparent;color:var(--dsw-alias-label-primary);font:inherit;font-size:12px;text-align:left;cursor:pointer}.dsh-houdini-menuitem:hover:not(:disabled){background:var(--dsw-alias-interactive-bg-hover)}.dsh-houdini-menuitem:disabled{opacity:.5;cursor:default}' +
      '.dsh-houdini-modal-backdrop{position:fixed;inset:0;z-index:1100;display:flex;align-items:center;justify-content:center;box-sizing:border-box;padding:24px;background:var(--dsw-alias-overlay-backdrop,#0008)}.dsh-houdini-modal{display:flex;flex-direction:column;width:min(520px,100%);max-height:calc(100vh - 48px);box-sizing:border-box;border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-lg);background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary);box-shadow:var(--dsw-elevation-prominent);outline:none}.dsh-houdini-modal-header,.dsh-houdini-modal-footer{display:flex;align-items:center;gap:8px;padding:12px 16px}.dsh-houdini-modal-header{justify-content:space-between;border-bottom:1px solid var(--dsw-alias-border-l1)}.dsh-houdini-modal-header>strong{font-size:15px}.dsh-houdini-modal-footer{justify-content:flex-end;flex-wrap:wrap;border-top:1px solid var(--dsw-alias-border-l1)}.dsh-houdini-modal-body{min-height:0;overflow:auto;padding:14px 16px}' +
      '.dsh-houdini-toast{position:fixed;top:16px;right:16px;z-index:1200;display:flex;align-items:center;gap:10px;max-width:min(440px,calc(100vw - 32px));box-sizing:border-box;padding:12px 14px;border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-md);background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary);box-shadow:var(--dsw-elevation-prominent);font-size:12px;line-height:1.6}.dsh-houdini-toast>span{min-width:0;overflow-wrap:anywhere}' +
      '@media(max-width:540px){.dsh-support-modal{gap:8px}.dsh-support-options{gap:12px}.dsh-support-option p{line-height:1.5}.dsh-support-input{margin-bottom:14px}.dsh-support-file>button{gap:8px}.dsh-houdini-modal-backdrop{padding:12px}.dsh-houdini-modal{max-height:calc(100vh - 24px)}}';
    var shellCssId = "dsh-houdini/shell.module.css";

    // Node delivery consumes this execution record.
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
      var isNew = typeof target.hip_is_new === "boolean" ? target.hip_is_new : project && project.hipIsNew;
      return isNew === true ? target.label || project && project.label || "未保存工程" :
        (target.hip_path || project && project.hipPath || "").replace(/\\/g, "/").split("/").pop() || "Houdini 工程";
    }

    function houdiniSameTarget(target, candidate) {
      return !!(target && candidate && target.executor_id && target.runtime_id && target.scene_epoch && target.scene_id &&
        target.executor_id === candidate.executor_id && target.runtime_id === candidate.runtime_id &&
        target.scene_epoch === candidate.scene_epoch && target.scene_id === candidate.scene_id);
    }

    // Save As changes the file, not the selected scene. Fresh matching presence
    // supplies presentation only; it never rewrites the native selection.
    function houdiniDisplayProject(project, snapshot) {
      var target = houdiniProjectTarget(project);
      if (!target || project.needsReview || !snapshot || !snapshot.available || snapshot.visible === false ||
        !snapshot.observedAt || Date.now() - snapshot.observedAt > 12000) return project;
      var record = snapshot.records && snapshot.records[target.executor_id], candidate = record && record.candidate;
      if (!record || record.status !== "online" || record.contractMismatch || !Number.isFinite(record.observedAt) ||
        Date.now() - record.observedAt > 12000 || record.executorId !== target.executor_id ||
        record.runtimeId !== target.runtime_id || record.sceneEpoch !== target.scene_epoch ||
        typeof record.sceneId === "string" && record.sceneId.length > 0 && record.sceneId !== target.scene_id ||
        !houdiniSameTarget(target, candidate) || typeof candidate.hip_path !== "string" || !candidate.hip_path ||
        typeof candidate.hip_is_new !== "boolean") return project;
      return Object.assign({}, project, { hipPath: candidate.hip_path, hipIsNew: candidate.hip_is_new,
        target: Object.assign({}, target, { hip_path: candidate.hip_path, hip_is_new: candidate.hip_is_new, label: candidate.label }) });
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
      if (!target) return status("unbound", "未绑定工程", "选择一个已打开的 Houdini；每段对话可以独立选择工程。");
      if (!snapshot || !snapshot.available || snapshot.visible === false || !snapshot.observedAt || Date.now() - snapshot.observedAt > 12000)
        return status("unknown", "连接待确认", "暂时无法确认连接。可以展开查看其他 Houdini 窗口。");
      if (project.needsReview) return status("changed", "工程待核对", "当前场景与这段对话选择时不同，请明确选择要继续的工程。");
      var record = snapshot.records[target.executor_id];
      if (!record || !Number.isFinite(record.observedAt) || Date.now() - record.observedAt > 12000)
        return status("unknown", "连接待确认", "尚未收到这个 Houdini 的最新状态，请稍后再试。");
      if (record.status === "offline") return status("offline", "已断开", "这个 Houdini 已关闭或断开，可以选择其他已打开的窗口。");
      if (record.contractMismatch) return status("unknown", "版本待更新", "这个 Houdini 加载的插件版本不一致。请先保存工程，再重新打开这个 Houdini。");
      if (record.status === "changed" || typeof record.sceneId === "string" && record.sceneId.length > 0 &&
        typeof target.scene_id === "string" && target.scene_id.length > 0 && record.sceneId !== target.scene_id)
        return status("changed", "场景已变化", "Houdini 已重开或切换场景，请重新选择要继续的工程。");
      if (record.status !== "online") return status("unknown", "连接待确认", "暂时无法确认这个 Houdini 的连接状态。");
      if (!target.scene_epoch || !record.sceneEpoch || !target.runtime_id || !record.runtimeId)
        return status("unknown", "工程待确认", "工程身份信息尚未完整确认，请重新选择当前窗口。");
      if (target.scene_epoch !== record.sceneEpoch || target.runtime_id !== record.runtimeId)
        return status("changed", "场景已变化", "Houdini 已重开或切换场景，请重新选择要继续的工程。");
      var nativeCurrent = useCurrentActivity !== false && nativeStatuses && nativeStatuses.get && nativeStatuses.get(sessionId);
      var owner = record.ownerSessionId;
      var nativeOwner = owner && nativeStatuses && nativeStatuses.get && nativeStatuses.get(owner);
      var activeJobs = Number(record.activeJobs) > 0;
      var bridgeBusy = record.busy === true || Number(record.activeRequests) > 0 || activeJobs;
      if (nativeCurrent && nativeCurrent.running === true)
        return status("working", "对话工作中", "当前对话正在处理请求，Houdini 连接正常。", "online");
      if (owner && owner !== sessionId && (activeJobs || nativeOwner && nativeOwner.running === true))
        return status("occupied", "其他对话工作中", "另一个对话正在使用这个工程；可以绑定查看，修改时会等待其完成。", "online");
      if (activeJobs && owner === sessionId)
        return status("working", "对话工作中", "当前对话在 Houdini 中的后台操作尚未完成。", "online");
      if (bridgeBusy) return status("working", "工程处理中", "Houdini 有操作尚未完成，可以继续查看当前场景。", "online");
      return status("ready", "已就绪", "连接正常。可以查看场景，或告诉 Agent 你想完成的任务。", "online");
    }

    function HoudiniProjectMark(props) {
      var project = useHoudiniProject(props), presence = props.usePresence ? props.usePresence() : null;
      var statuses = props.useNativeStatus ? props.useNativeStatus() : null;
      var status = project && houdiniPresence(project, presence, props.sessionId, statuses);
      var display = houdiniDisplayProject(project, presence);
      return project && React.createElement("span", { className: "dsh-houdini-project-mark", role: "img",
        "aria-label": "关联工程：" + houdiniProjectName(display) + " · " + status.label,
        "data-state": status.state, "data-houdini-presence": status.status, "data-houdini-project-mark": true }, React.createElement(HoudiniProjectIcon));
    }

    function HoudiniProjectDetail(props) {
      var project = useHoudiniProject(props), presence = props.usePresence ? props.usePresence() : null;
      var statuses = props.useNativeStatus ? props.useNativeStatus() : null;
      if (!project) return null;
      var display = houdiniDisplayProject(project, presence), target = houdiniProjectTarget(display), status = houdiniPresence(project, presence, props.sessionId, statuses);
      return React.createElement("div", { className: "dsh-houdini-project-detail", "data-houdini-project-detail": true },
        React.createElement("strong", null, "关联工程 · " + houdiniProjectName(display)),
        React.createElement("div", null, status.label),
        target && target.hip_path && !target.hip_is_new && React.createElement("div", null, target.hip_path),
        React.createElement("div", null, status.detail));
    }

    function HoudiniProjectLabel(props) {
      var project = useHoudiniProject(props), presence = props.usePresence ? props.usePresence() : null;
      var statuses = props.useNativeStatus ? props.useNativeStatus() : null;
      var status = houdiniPresence(project, presence, props.sessionId, statuses), display = houdiniDisplayProject(project, presence), target = houdiniProjectTarget(display);
            return React.createElement(ui.Tooltip, { side: "bottom", align: "end", delayMs: 400, portal: true, maxWidth: 360, openOnClick: false,
        label: (target ? houdiniProjectName(display) + (target.hip_path ? "\n" + target.hip_path : "") + "\n" : "") + status.label + " · " + status.detail },
        React.createElement("button", { type: "button", className: "dsh-houdini-project-chip", onClick: props.onProjectMenuClick,
          "aria-haspopup": "menu", "aria-expanded": !!props.projectMenuOpen,
          "aria-label": "Houdini 工程：" + (target ? houdiniProjectName(display) + " · " : "") + status.label,
          "data-state": status.state, "data-houdini-presence": status.status, "data-houdini-project-label": true },
          React.createElement(HoudiniProjectIcon),
          React.createElement("span", { className: "dsh-houdini-chip-name", "data-houdini-project-name": true }, target ? houdiniProjectName(display) : "Houdini"),
          React.createElement("span", { className: "dsh-houdini-chip-status" }, React.createElement(HoudiniTargetStateIcon, { state: status.state }), status.label),
          React.createElement("svg", { width: 10, height: 10, viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: 1.3, "aria-hidden": true }, React.createElement("path", { d: "m3 4.5 3 3 3-3" }))));
    }

    function HoudiniBlankProjectLabel(props) {
      var blank = props.useSessions(function (state) { return !!(state.byId[props.sessionId] && state.byId[props.sessionId].blank); });
      return blank ? React.createElement(HoudiniProjectLabel, props) : null;
    }

    // Only unresolved UI intentions live here. Host tickets remain the sole
    // source for launch phase, process identity, receipt and binding outcome.
    function createLaunchOwnership(connection) {
      var owners = new Map(), cancelled = new Map(), running = new Map(), disposed = false;
      function claim(operation, id) {
        if (!id) return;
        var previous = owners.get(id);
        if (previous && previous !== operation) {
          if (running.has(id)) { running.get(id).abort(); running.delete(id); }
        }
        owners.set(id, operation);
        if (cancelled.get(id) !== operation) cancelled.delete(id);
      }
      function release(operation) {
        owners.forEach(function (owner, id) { if (owner === operation && !cancelled.has(id) && !operation.submitting) owners.delete(id); });
      }
      async function flush() {
        if (disposed || !connection.generation.getSnapshot()) return;
        cancelled.forEach(function (operation, id) {
          if (owners.get(id) !== operation) { cancelled.delete(id); return; }
          if (running.has(id)) return;
          var attempt = new AbortController(); running.set(id, attempt);
          connection.rpc.call("/api", "houdiniFrontend/projectLaunchDetach", { args: { input: { id: id } } },
            AbortSignal.any([attempt.signal, AbortSignal.timeout(10000)])).then(function (response) {
              if (response.ok && cancelled.get(id) === operation) {
                cancelled.delete(id); if (owners.get(id) === operation && !operation.submitting) owners.delete(id);
              }
            }).catch(function () {}).finally(function () { if (running.get(id) === attempt) running.delete(id); });
        });
      }
      function cancel(operation, id) {
        if (!id || operation.done) return;
        var current = owners.get(id);
        if (current !== operation) return;
        cancelled.set(id, operation); flush();
      }
      var unsubscribe = connection.generation.subscribe(flush);
      return { claim: claim, cancel: cancel, release: release, flush: flush,
        dispose: function () { disposed = true; unsubscribe(); running.forEach(function (attempt) { attempt.abort(); }); running.clear(); owners.clear(); cancelled.clear(); } };
    }

    function createProjectLaunchObserver(connection, ownership, options) {
      var operation = null, revision = 0, pending = null, timer = null, disposed = false;
      var view = { pending: false, ticket: null, error: "", disconnected: false, submitted: false };
      function emit(next) { view = Object.assign({}, view, next); if (!disposed && options.isCurrent()) options.emit(view); }
      function cancelPoll() { revision++; if (pending) pending.abort(); pending = null; if (timer) clearTimeout(timer); timer = null; }
      function active(current) { return !disposed && operation === current && !current.stopped && !current.done && options.isCurrent(); }
      async function call(method, input, signal) {
        var result = await connection.rpc.call("/api", "houdiniFrontend/" + method, { args: { input: input } }, signal);
        if (!result.ok) { var error = new Error(result.error && result.error.message || "没有取得启动回执。"); error.code = result.error && result.error.code; throw error; }
        return result.value;
      }
      function accept(current, ticket) {
        if (!active(current)) return;
        if (ticket.id) { current.id = ticket.id; ownership.claim(current, ticket.id); }
        current.ticket = ticket;
        if (ticket.phase === "ready") {
          current.done = true; cancelPoll(); ownership.release(current);
          emit({ pending: false, ticket: ticket, error: "", disconnected: false, submitted: true });
          options.ready(ticket); return;
        }
        if (ticket.phase === "error") { current.done = true; cancelPoll(); ownership.release(current); }
        var waiting = ticket.phase === "preparing" || ticket.phase === "waiting";
        emit({ pending: waiting, ticket: ticket, error: "", disconnected: false, submitted: true });
        if (waiting) timer = setTimeout(function () { timer = null; query(current); }, 1000);
      }
      async function query(current, method) {
        if (!active(current)) return;
        cancelPoll(); var expected = revision, generation = connection.generation.getSnapshot();
        if (!generation) { emit({ pending: false, disconnected: true }); return; }
        var attempt = new AbortController(); pending = attempt;
        try {
          var ticket = await call(method || "projectLaunchStatus", { id: current.id || current.requestId },
            AbortSignal.any([attempt.signal, AbortSignal.timeout(15000)]));
          if (active(current) && revision === expected && connection.generation.getSnapshot() === generation) accept(current, ticket);
        } catch (error) {
          if (active(current) && revision === expected && !attempt.signal.aborted)
            emit({ pending: false, error: String(error.message || error), disconnected: !connection.generation.getSnapshot(), submitted: true });
        } finally { if (pending === attempt) pending = null; }
      }
      function stop() {
        var current = operation; cancelPoll();
        if (!current || current.done || current.stopped) return;
        current.stopped = true;
        ownership.cancel(current, current.id || current.requestId);
      }
      async function submit(parameters) {
        var signature = JSON.stringify(parameters), current = operation;
        if (!current || current.done || current.stopped || current.signature !== signature) {
          stop();
          current = { requestId: options.requestId(), id: null, parameters: parameters, signature: signature,
            target: options.target(), ticket: null, done: false, stopped: false };
          operation = current; ownership.claim(current, current.requestId);
        }
        if (current.ticket && current.ticket.phase === "detached") return resume();
        cancelPoll(); var expected = revision, generation = connection.generation.getSnapshot();
        emit({ pending: true, error: "", disconnected: !generation, submitted: true, ticket: current.ticket });
        if (!generation) { emit({ pending: false }); return; }
        current.submitting = true;
        try {
          var ticket = await call("projectAction", Object.assign({}, current.parameters, { requestId: current.requestId }), AbortSignal.timeout(30000));
          if (!active(current)) { if (current.stopped) ownership.cancel(current, ticket.id || current.id || current.requestId); return; }
          if (ticket.id) { current.id = ticket.id; ownership.claim(current, ticket.id); }
          if (connection.generation.getSnapshot() !== generation || revision !== expected) return query(current);
          accept(current, ticket);
        } catch (error) {
          if (!active(current)) return;
          // Admission may have succeeded even when its reply was lost. The
          // request identity is also the ticket identity; observe it first.
          current.submissionError = String(error.message || error);
          await query(current);
          if (active(current) && !current.ticket && view.error) emit({ error: current.submissionError });
        } finally { current.submitting = false; if (current.done || current.stopped) ownership.release(current); }
      }
      function resume() {
        var current = operation;
        if (!current || !active(current)) return;
        if (options.target() !== current.target) {
          emit({ pending: false, error: "当前对话已重新选择工程。请从工程菜单选择原窗口；未覆盖当前选择。" }); return;
        }
        ownership.claim(current, current.id || current.requestId);
        emit({ pending: true, error: "", disconnected: false });
        return query(current, "projectLaunchResume");
      }
      return {
        submit: submit, resume: resume, stop: stop,
        reconnect: function () { cancelPoll(); ownership.flush(); if (operation && active(operation)) return query(operation); },
        snapshot: function () { return view; },
        sameRequest: function (parameters) { return !!(operation && !operation.done && operation.signature === JSON.stringify(parameters)); },
        dispose: function () { stop(); disposed = true; }
      };
    }

    function launchTicketMessage(ticket) {
      if (!ticket) return "正在确认本次打开请求…";
      if (ticket.message) return ticket.message;
      if (ticket.phase === "preparing") return "正在准备 Houdini 启动请求…";
      if (ticket.phase === "detached") return "已停止等待，不会取消启动或关闭 Houdini。需要时可继续连接。";
      if (ticket.phase === "error") return "暂时无法连接 Houdini，请查看具体原因。";
      return { launching: "正在启动 Houdini…", capturing: "正在读取这个 Houdini 的场景…",
        registering: "正在连接 Houdini 与 Desktop…", binding: "正在将当前对话连接到 Houdini…" }[ticket.stage] || "正在等待 Houdini 完成连接…";
    }

    // One Native window-mode scope. UI state comes from the OS response; only
    // explicit button choices are remembered while this client remains open.
    function createWindowPinUi(connection, changed, failed, options) {
      options = options || {};
      var enabled = options.enabled === true, active = false, disposed = false, scope = null, preferred = null;
      var value = { available: false, busy: enabled, pinned: null }, serial = 0, readySerial = 0, ready = Promise.resolve();
      var releases = new Set(), releasing = new Set(), retry = null;
      function publish(next) { value = next; changed(); }
      function generation() { return connection.generation.getSnapshot(); }
      function valid(owner, version, attempt) { return !disposed && active && scope === owner && generation() === version && serial === attempt; }
      async function rpc(action, owner, pinned) {
        var input = { action: action };
        if (owner) input.owner = owner;
        if (typeof pinned === "boolean") input.pinned = pinned;
        var response = await connection.rpc.call("/api", "houdiniFrontend/windowPin", { args: { input: input } }, AbortSignal.timeout(8000));
        if (!response.ok) throw new Error(response.error && response.error.message || "未能确认窗口置顶状态。");
        if (!response.value || typeof response.value.available !== "boolean" || response.value.available && typeof response.value.pinned !== "boolean")
          throw new Error("窗口置顶状态无效。");
        return response.value;
      }
      function flushReleases() {
        if (disposed || !generation()) return;
        releases.forEach(function (owner) {
          if (releasing.has(owner)) return;
          releasing.add(owner);
          rpc("release", owner).then(function () { releases.delete(owner); }).catch(function () {}).finally(function () {
            releasing.delete(owner);
            if (!disposed && releases.size && !retry) retry = setTimeout(function () { retry = null; flushReleases(); }, 1500);
          });
        });
      }
      function release(owner) { if (owner) { releases.add(owner); flushReleases(); } }
      async function set(owner, pinned, report) {
        var version = generation(), attempt = ++serial;
        publish(Object.assign({}, value, { busy: true, operation: "set" }));
        try {
          var result = await rpc("set", owner, pinned);
          if (!valid(owner, version, attempt)) return;
          preferred = result.pinned;
          publish(Object.assign({}, result, { busy: false }));
        } catch (error) {
          if (!valid(owner, version, attempt)) return;
          publish({ available: false, pinned: null, busy: false, reason: String(error.message || error) });
          if (report) failed(String(error.message || error));
        }
      }
      async function acquire() {
        if (!enabled || disposed || !active || scope || !generation()) return;
        var owner = (options.owner ? options.owner() : crypto.randomUUID().replace(/-/g, "")), version = generation(), attempt = ++serial;
        scope = owner; publish({ available: false, pinned: null, busy: true });
        try {
          var result = await rpc("activate", owner);
          if (!valid(owner, version, attempt)) { release(owner); return; }
          publish(Object.assign({}, result, { busy: false }));
          if (result.available && typeof preferred === "boolean" && result.pinned !== preferred) await set(owner, preferred, false);
        } catch (error) {
          if (!valid(owner, version, attempt)) return;
          scope = null; release(owner);
          publish({ available: false, pinned: null, busy: false, reason: String(error.message || error) });
        }
      }
      function reconnect() {
        if (!enabled || disposed) return;
        var version = generation(), stamp = ++readySerial, old = scope;
        scope = null; serial++; if (old) releases.add(old);
        publish({ available: false, pinned: null, busy: !!version });
        if (!version) return;
        // Reconcile even in Standard mode: a renderer reload must not strand
        // a topmost change owned by its previous JavaScript context.
        ready = rpc("reset").then(function () {
          if (disposed || generation() !== version || readySerial !== stamp) return;
          releases.clear(); return acquire();
        }).catch(function (error) {
          if (!disposed && generation() === version && readySerial === stamp)
            publish({ available: false, pinned: null, busy: false, reason: String(error.message || error) });
        });
      }
      var unsubscribe = enabled ? connection.generation.subscribe(reconnect) : function () {};
      if (enabled) reconnect();
      return {
        snapshot: function () { return value; },
        enter: function () { active = true; return ready.then(acquire); },
        leave: function () { active = false; serial++; var old = scope; scope = null; release(old); publish(Object.assign({}, value, { busy: false })); },
        refresh: async function () {
          if (!active || disposed || !generation()) return;
          flushReleases(); if (!scope) return ready.then(acquire); if (value.busy) return;
          var owner = scope, version = generation(), attempt = ++serial;
          try { var result = await rpc("read"); if (valid(owner, version, attempt)) publish(Object.assign({}, result, { busy: false })); }
          catch (error) { if (valid(owner, version, attempt)) publish({ available: false, pinned: null, busy: false, reason: String(error.message || error) }); }
        },
        toggle: function () { if (active && scope && value.available && !value.busy && typeof value.pinned === "boolean") return set(scope, !value.pinned, true); },
        dispose: function () { active = false; serial++; release(scope); scope = null; disposed = true; unsubscribe(); if (retry) clearTimeout(retry); }
      };
    }

    function createHoudiniDesktopUi(connection, uiSession, sessions, uiWorkspace) {
      var state = { available: false, visible: true, records: {}, observedAt: 0 }, listeners = new Set(), notice = null, serial = 0;
      var refreshPresence = function () {}, dialog = null;
      var launchOwnership = createLaunchOwnership(connection);
      var nativeWindow = typeof window !== "undefined" && window.dshDesktop && typeof window.dshDesktop.deviceInfo === "function";
      var windowPin = createWindowPinUi(connection, function () { publish(Object.assign({}, state)); }, notify, { enabled: !!nativeWindow });
      var nativeEmpty = new Map(), nativeSource = uiSession.sessionStatus || { getSnapshot: function () { return nativeEmpty; }, subscribe: function () { return function () {}; } };
      function subscribe(listener) { listeners.add(listener); return function () { listeners.delete(listener); }; }
      function snapshot() { return state; }
      function publish(next) { state = next; listeners.forEach(function (listener) { listener(); }); }
      function usePresence() { return React.useSyncExternalStore(subscribe, snapshot); }
      function useNativeStatus() { return React.useSyncExternalStore(nativeSource.subscribe, nativeSource.getSnapshot); }
      function notify(text) { notice = { id: ++serial, text: text }; publish(Object.assign({}, state)); }
      function action(kind, sessionId, hip) {
        dialog = { action: kind === "reopen" ? "open" : kind, sessionId: sessionId, hip: hip || "", token: ++serial };
        publish(Object.assign({}, state));
      }
      function ProjectDialog(props) {
        var request = props.request;
        var installationsState = React.useState([]), installations = installationsState[0], setInstallations = installationsState[1];
        var hfsState = React.useState(""), hfs = hfsState[0], setHfs = hfsState[1];
        var hipState = React.useState(request.hip), hip = hipState[0], setHip = hipState[1];
        var loadingState = React.useState(true), loading = loadingState[0], setLoading = loadingState[1];
        var installErrorState = React.useState(""), installError = installErrorState[0], setInstallError = installErrorState[1];
        var viewState = React.useState({ pending: false, ticket: null, error: "", disconnected: false, submitted: false }), view = viewState[0], setView = viewState[1];
        var observer = React.useRef(null);
        var generation = React.useSyncExternalStore(connection.generation.subscribe, connection.generation.getSnapshot);
        function current() {
          var binding = uiSession.adapter.current.getSnapshot(), row = sessions.list.getSnapshot().byId[request.sessionId];
          return dialog === request && binding && binding.key === request.sessionId && row && row.projectionValues && row.projectionValues.agentPreset === "houdini";
        }
        function target() {
          var snapshot = sessions.list.getSnapshot(), projection = snapshot.projectionsBySession && snapshot.projectionsBySession[request.sessionId];
          var value = projection && projection.values && houdiniProjectTarget(projection.values.houdiniExecutorIdentity);
          return JSON.stringify(value ? [value.executor_id, value.runtime_id, value.scene_epoch] : null);
        }
        if (!observer.current) observer.current = createProjectLaunchObserver(connection, launchOwnership, {
          isCurrent: current, target: target, emit: setView,
          requestId: function () { return crypto.randomUUID().replace(/-/g, ""); },
          ready: function () { if (dialog === request) { dialog = null; publish(Object.assign({}, state)); refreshPresence(); } }
        });
        function close() { observer.current.stop(); dialog = null; publish(Object.assign({}, state)); }
        React.useEffect(function () { return function () { observer.current.dispose(); }; }, []);
        React.useEffect(function () {
          var controller = new AbortController();
          observer.current.reconnect();
          if (!generation) { setLoading(false); return function () { controller.abort(); }; }
          setLoading(true); setInstallError("");
          connection.rpc.call("/api", "houdiniFrontend/projectInstallations", { args: {} },
            AbortSignal.any([controller.signal, AbortSignal.timeout(15000)])).then(function (response) {
              if (controller.signal.aborted) return;
              if (!response.ok) throw new Error(response.error && response.error.message || "无法读取 Houdini 安装。");
              var rows = response.value;
              setInstallations(rows); setHfs(function (previous) { return previous || (rows.length ? rows[0].hfs : ""); });
              setLoading(false);
              if (!rows.length) setInstallError("没有找到受支持的 Houdini 安装。请先安装 Houdini 和本插件的 Bridge 组件。");
            }).catch(function (error) { if (!controller.signal.aborted) { setLoading(false); setInstallError(String(error.message || error)); } });
          return function () { controller.abort(); };
        }, [generation]);
        function parameters() {
          var value = { action: request.action, sessionId: request.sessionId, hfs: hfs };
          if (request.action === "open") value.hip = hip.trim();
          return value;
        }
        var same = observer.current.sameRequest(parameters()), detached = same && view.ticket && view.ticket.phase === "detached";
        var message = view.error || (view.disconnected ? "Desktop 连接已中断；恢复后会继续查看这次打开的结果，不会再打开一个窗口。" :
          view.submitted ? launchTicketMessage(view.ticket) : loading ? "正在查找已安装的 Houdini…" : installError);
        var elapsed = view.ticket && Number.isFinite(view.ticket.elapsedMs) ? Math.floor(view.ticket.elapsedMs / 1000) : 0;
        var fieldStyle = { width: "100%", boxSizing: "border-box", border: "1px solid var(--dsw-alias-border-l2)", borderRadius: 8,
          padding: "9px 10px", background: "var(--dsw-alias-bg-layer-1)", color: "inherit", font: "inherit" };
        return React.createElement(ui.Modal, { open: true, onClose: close, title: request.action === "new" ? "新建 Houdini 工程" : "打开 Houdini 工程",
          closeLabel: "关闭打开工程对话框", footer: React.createElement(React.Fragment, null,
            React.createElement(Button, { variant: "ghost", onClick: close,
              title: view.submitted ? "不会取消启动或关闭 Houdini，只停止等待本次连接。" : undefined }, view.submitted ? "停止等待" : "取消"),
            React.createElement(Button, { disabled: view.pending || !generation || !hfs || request.action === "open" && !hip.trim(),
              onClick: function () { if (detached) observer.current.resume(); else observer.current.submit(parameters()); } },
              view.pending ? "等待工程连接…" : detached ? "继续连接原窗口" : same && view.submitted ? "重试本次请求" : request.action === "new" ? "新建并绑定" : "打开并绑定")) },
          React.createElement("div", { style: { display: "grid", gap: 16, padding: "8px 0", minWidth: 260, maxWidth: 520 }, "data-houdini-project-dialog": true },
            React.createElement("label", null, "Houdini 版本", React.createElement("select", { style: fieldStyle, value: hfs, disabled: view.pending,
              "aria-label": "Houdini 版本", onChange: function (event) { setHfs(event.target.value); } }, installations.map(function (item) {
                return React.createElement("option", { key: item.hfs, value: item.hfs }, "Houdini " + item.version);
              }))),
            request.action === "open" && React.createElement("label", null, "工程文件完整路径", React.createElement("input", { style: fieldStyle, value: hip, disabled: view.pending,
              "aria-label": "Houdini 工程路径", placeholder: "例如 E:\\projects\\scene.hip", onChange: function (event) { setHip(event.target.value); } })),
            message && React.createElement("p", { role: "status", "data-houdini-launch-stage": view.ticket && view.ticket.stage,
              style: { margin: 0, lineHeight: 1.6, overflowWrap: "anywhere" } }, message),
            view.pending && elapsed > 0 && React.createElement("span", { style: { fontSize: 12, opacity: .7 } }, "已等待 " + elapsed + " 秒")));
      }
      function Lifecycle() {
        usePresence();
        React.useEffect(function () {
          if (!nativeWindow) return;
          windowPin.enter();
          function focus() { windowPin.refresh(); }
          window.addEventListener("focus", focus);
          return function () { window.removeEventListener("focus", focus); windowPin.leave(); };
        }, []);
        var selected = React.useSyncExternalStore(uiSession.adapter.current.subscribe, uiSession.adapter.current.getSnapshot);
        React.useEffect(function () {
          if (dialog && (!selected || dialog.sessionId !== selected.key)) { dialog = null; publish(Object.assign({}, state)); }
        }, [selected && selected.key]);
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
                if (!capability.ok || !capability.value || !capability.value.desktop) return;
                publish(Object.assign({}, state, { available: true, visible: true }));
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
            publish({ available: false, visible: document.visibilityState !== "hidden", observedAt: 0, records: {} }); refresh();
          }
          refreshPresence = refresh;
          var unsubscribe = connection.generation.subscribe(changed);
          document.addEventListener("visibilitychange", changed);
          var timer = setInterval(refresh, 5000); refresh();
          return function () { stopped = true; if (pending) pending.abort(); clearInterval(timer); unsubscribe();
            document.removeEventListener("visibilitychange", changed); refreshPresence = function () {}; dialog = null; notice = null; };
        }, []);
        var current = notice;
        return React.createElement(React.Fragment, null,
          dialog && React.createElement(ProjectDialog, { key: dialog.token, request: dialog }),
          current && React.createElement(ui.Toast, { key: current.id, text: current.text, onDone: function () { if (notice === current) { notice = null; publish(Object.assign({}, state)); } } }));
      }
      function decorate(Component) { return function (props) { return React.createElement(Component, Object.assign({}, props, { usePresence: usePresence, useNativeStatus: useNativeStatus })); }; }
      function Menu(props) {
        var project = useHoudiniProject(props), presence = usePresence(), nativeStatuses = useNativeStatus();
        var row = props.useSessions(function (value) { return value.byId[props.sessionId] || null; });
        var status = houdiniPresence(project, presence, props.sessionId, nativeStatuses), target = houdiniProjectTarget(project);
        var display = houdiniDisplayProject(project, presence), displayTarget = houdiniProjectTarget(display);
        var menu = React.useState({ open: false, busy: false, message: "", loaded: false }), value = menu[0], set = menu[1];
        var pending = React.useRef(null), ticket = React.useRef(0), current = React.useRef(props.sessionId); current.current = props.sessionId;
        var windowOrder = React.useRef([]), pressedCandidate = React.useRef(null);
        var hostGeneration = React.useSyncExternalStore(connection.generation.subscribe, connection.generation.getSnapshot);
        React.useEffect(function () {
          ticket.current++; if (pending.current) pending.current.abort();
          set({ open: false, busy: false, message: "", loaded: false });
          return function () { ticket.current++; if (pending.current) pending.current.abort(); };
        }, [props.sessionId, hostGeneration]);
        async function request(method, candidate) {
          var sessionId = props.sessionId, generation = connection.generation.getSnapshot();
          if (!sessionId) return;
          if (!generation) { set(function (old) { return Object.assign({}, old, { open: true, details: "", message: "Desktop 连接已断开，请稍后重试。" }); }); return; }
          var attempt = ++ticket.current;
          if (pending.current) pending.current.abort();
          var controller = new AbortController(); pending.current = controller;
          var timeout = setTimeout(function () { controller.abort(); }, method === "prepareBridge" ? 125000 : 10000);
          set(function (old) { return Object.assign({}, old, { open: true, busy: true, details: "", message: method === "list" ? "正在查看已打开的 Houdini…" : method === "prepareBridge" ? "正在安装或更新 Houdini 组件…" : method === "clear" ? "正在取消绑定…" : "正在选择工程…" }); });
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
            var response = await connection.rpc.call("/api", method === "prepareBridge" ? "houdiniFrontend/prepareBridge" : "houdiniTargets/" + method, { args: { input: input } }, controller.signal);
            if (controller.signal.aborted || current.current !== sessionId || ticket.current !== attempt || connection.generation.getSnapshot() !== generation) return;
            if (!response.ok) throw new Error(response.error && response.error.message || "没有完成工程选择。");
            if (method === "prepareBridge") {
              set(function (old) { return Object.assign({}, old, { busy: false, message: response.value.message || "Houdini 组件已安装，新打开的 Houdini 会加载菜单。" }); });
              return;
            }
            if (sessions && sessions.refreshProjections) await sessions.refreshProjections(sessionId);
            if (controller.signal.aborted || current.current !== sessionId || ticket.current !== attempt || connection.generation.getSnapshot() !== generation) return;
            set(function (old) { return Object.assign({}, old, { busy: false, open: false, message: "" }); }); refreshPresence();
            notify(method === "clear" ? "此对话已取消工程绑定。" : "此对话已选择「" + houdiniProjectName(candidate) + "」。");
          } catch (error) {
            if (current.current === sessionId && ticket.current === attempt && connection.generation.getSnapshot() === generation) {
              var reason = String(error.message || error), folded = method === "prepareBridge" || /[\r\n]/.test(reason);
              var summary = controller.signal.aborted ? "等待响应超时，尚未确认操作结果。可以稍后重试。" :
                method === "prepareBridge" ? "未能确认 Houdini 组件安装完成，请查看原因。" :
                method === "clear" ? "尚未确认取消绑定结果，请查看原因。" : method === "list" ? "暂时无法读取窗口列表，请查看原因。" : "尚未确认工程选择结果，请查看原因。";
              set(function (old) { return Object.assign({}, old, { busy: false, message: folded || controller.signal.aborted ? summary : reason, details: folded ? reason : "" }); });
            }
          } finally { clearTimeout(timeout); if (pending.current === controller) pending.current = null; }
        }
        var currentNative = nativeStatuses && nativeStatuses.get(props.sessionId);
        var nativeRunning = currentNative && currentNative.running === true;
        var switchingDisabled = value.busy || nativeRunning;
        // The same fresh desktop observation owns both membership and status.
        // A registry hint is never another list of supposedly open windows.
        var freshPresence = presence.available && presence.visible !== false && presence.observedAt && Date.now() - presence.observedAt <= 12000;
        var rows = freshPresence ? Object.values(presence.records).filter(function (observed) {
          return observed.status !== "offline" && Number.isFinite(observed.observedAt) && Date.now() - observed.observedAt <= 12000
            && observed.candidate && observed.candidate.workbench === true && observed.candidate.state === "registered";
        }).map(function (observed) { return observed.candidate; }) : [];
        // Keep existing windows in place while this menu is open. New windows
        // append; only live presence supplies their content and action inputs.
        if (!value.open) windowOrder.current = [];
        rows.forEach(function (candidate) { if (!windowOrder.current.includes(candidate.executor_id)) windowOrder.current.push(candidate.executor_id); });
        rows.sort(function (left, right) { return windowOrder.current.indexOf(left.executor_id) - windowOrder.current.indexOf(right.executor_id); });
        var selectedCandidate = rows.find(function (candidate) { return houdiniSameTarget(target, candidate); });
        function candidateItem(candidate, index) {
          var selected = houdiniSameTarget(target, candidate);
          var candidateProject = { target: candidate }, observed = selected ? status : houdiniPresence(candidateProject, presence, props.sessionId, nativeStatuses, false);
          var label = houdiniProjectName(selected ? display : candidate), details = (selected ? displayTarget.hip_path : candidate.hip_path) || "未保存工程";
          var folders = String(candidate.hip_path || "").replace(/\\/g, "/").split("/"), folder = folders.length > 1 ? folders[folders.length - 2] : "";
          var version = String(candidate.houdini_version || "").split(".")[0];
          var context = selected ? "当前工程" : [folder, version ? "Houdini " + version : ""].filter(Boolean).join(" · ") || "Houdini 窗口";
          if (candidate.houdini_version) details += "\nHoudini " + candidate.houdini_version;
          if (candidate.pid) details += "\n进程 " + candidate.pid;
          return React.createElement(ui.MenuItemButton, { key: candidate.executor_id,
            disabled: !!switchingDisabled || candidate.state === "disconnected" || observed.state === "offline" || !candidate.hip_path,
            icon: React.createElement(HoudiniTargetStateIcon, { state: observed.state }),
            onPointerDown: function () { pressedCandidate.current = candidate; },
            onSelect: function (event) {
              var pressed = pressedCandidate.current; pressedCandidate.current = null;
              if (event && event.type === "click" && event.detail > 0 && pressed) {
                if (pressed.executor_id !== candidate.executor_id) { set(function (old) { return Object.assign({}, old, { message: "窗口列表已变化，请重新选择。" }); }); return; }
                candidate = pressed;
              }
              request("select", candidate);
            } },
            React.createElement("span", { className: "dsh-houdini-target-row", title: details + "\n" + observed.detail, "data-houdini-target": candidate.executor_id, "data-state": observed.state },
              React.createElement("span", { className: "dsh-houdini-target-title" }, label, selected && React.createElement("span", { "aria-label": "当前已选工程", className: "dsh-houdini-target-selected" }, "✓")),
              React.createElement("span", { className: "dsh-houdini-target-meta" }, context, " · ", observed.label)));
        }
        var otherCandidates = rows.filter(function (candidate) { return candidate !== selectedCandidate; });
        var projectActions = [{ id: "open", label: "打开工程…", disabled: !presence.available || !!nativeRunning },
          { id: "new", label: "新建工程…", disabled: !presence.available || !!nativeRunning }];
        if (displayTarget && displayTarget.hip_path && displayTarget.hip_is_new === false) projectActions.push({ id: "reopen", label: "打开关联工程…", disabled: !presence.available || !!nativeRunning });
        var managementActions = [];
        if (target) managementActions.push({ id: "clear", label: "取消此对话的绑定", disabled: !!switchingDisabled });
        managementActions.push({ id: "prepareBridge", label: "安装 / 更新 Houdini 组件", disabled: !presence.available || !!switchingDisabled });
        function actionItem(item) {
          return React.createElement(ui.MenuItemButton, { key: item.id, disabled: !!item.disabled,
            onSelect: function () {
              if (item.id === "clear") { request("clear"); return; }
              if (item.id === "prepareBridge") { request("prepareBridge"); return; }
              ticket.current++; if (pending.current) pending.current.abort(); pending.current = null;
              set(Object.assign({}, value, { open: false, busy: false, message: "" })); action(item.id, props.sessionId, item.id === "reopen" ? displayTarget.hip_path : "");
            } }, React.createElement("span", { "data-houdini-project-action": item.id }, item.label));
        }
        var anchor = React.createElement(HoudiniProjectLabel, Object.assign({}, props, { usePresence: usePresence, useNativeStatus: useNativeStatus,
            projectMenuOpen: value.open, onProjectMenuClick: function () { if (value.open) { ticket.current++; if (pending.current) pending.current.abort(); set(Object.assign({}, value, { open: false, busy: false })); } else request("list"); } }));
        return React.createElement(ui.Menu, { open: value.open, portal: true, compact: true, align: "end", side: "bottom", anchor: anchor,
          listClassName: "dsh-houdini-target-menu", onClose: function () { ticket.current++; if (pending.current) pending.current.abort(); set(function (old) { return Object.assign({}, old, { open: false, busy: false }); }); },
          },
          React.createElement("div", { className: "dsh-houdini-target-heading", role: "presentation" }, React.createElement("strong", null, "Houdini 工程")),
          target && React.createElement("div", { className: "dsh-houdini-target-current", "data-houdini-current-scene": true },
            selectedCandidate ? candidateItem(selectedCandidate, 0) : React.createElement("div", { className: "dsh-houdini-target-unavailable", title: status.detail },
              React.createElement(HoudiniTargetStateIcon, { state: status.state }), React.createElement("div", { className: "dsh-houdini-target-row", "data-houdini-selected-snapshot": true },
                React.createElement("span", { className: "dsh-houdini-target-title" }, houdiniProjectName(display)),
                React.createElement("span", { className: "dsh-houdini-target-meta" }, status.label)))),
          React.createElement("details", { className: "dsh-houdini-target-section", open: !target, "data-houdini-menu-section": "project" },
            React.createElement("summary", { "data-houdini-menu-toggle": "project" }, "工程"),
            target && React.createElement("dl", { className: "dsh-houdini-target-info" },
              displayTarget.hip_path && React.createElement(React.Fragment, null, React.createElement("dt", null, "工程文件"), React.createElement("dd", { "data-houdini-project-info": "hip" }, displayTarget.hip_path)),
              row && row.cwd && React.createElement(React.Fragment, null, React.createElement("dt", null, "对话文件夹"), React.createElement("dd", { "data-houdini-project-info": "cwd" }, row.cwd)),
              selectedCandidate && selectedCandidate.houdini_version && React.createElement(React.Fragment, null, React.createElement("dt", null, "Houdini"), React.createElement("dd", { "data-houdini-project-info": "version" }, selectedCandidate.houdini_version))),
            projectActions.map(actionItem)),
          React.createElement("details", { className: "dsh-houdini-target-section", "data-houdini-menu-section": "management" },
            React.createElement("summary", { "data-houdini-menu-toggle": "management" }, "管理"), managementActions.map(actionItem)),
          React.createElement("div", { className: "dsh-houdini-target-choices" },
            value.message && React.createElement("p", { role: "status", className: "dsh-houdini-target-message" }, value.message),
            value.details && React.createElement("details", { className: "dsh-houdini-target-error" }, React.createElement("summary", null, "查看原因"), React.createElement("pre", null, value.details)),
            value.loaded && !value.busy && !value.message && !target && !rows.length && React.createElement("p", { role: "status", className: "dsh-houdini-target-message" },
              freshPresence ? "还没有可选工程。在目标 Houdini 中选择 DSH-Houdini → Open Workspace 后，会显示在这里。" : "暂时无法确认工程列表，连接恢复后会自动更新。"),
            nativeRunning && React.createElement("p", { className: "dsh-houdini-target-message" }, "对话工作中，完成后可以切换窗口或取消绑定。"),
            otherCandidates.length > 0 && React.createElement("div", { className: "dsh-houdini-target-list", "aria-label": "可切换的 Houdini 窗口" },
              React.createElement("div", { className: "dsh-houdini-target-group", role: "presentation" }, target ? "其他工程" : "可选工程"), otherCandidates.map(candidateItem))));
      }
      function Label(props) {
        var row = props.useSessions(function (value) { return value.byId[props.sessionId]; });
        return row && !row.blank && row.projectionValues && row.projectionValues.agentPreset === "houdini" ? React.createElement(Menu, props) : null;
      }
      function Blank(props) {
        var row = props.useSessions(function (value) { return value.byId[props.sessionId]; });
        return row && row.blank && row.projectionValues && row.projectionValues.agentPreset === "houdini" ? React.createElement(Menu, props) : null;
      }
      function Pin(props) {
        usePresence();
        if (!nativeWindow) return null;
        var pin = windowPin.snapshot(), label = pin.busy ? (pin.operation === "set" ? "正在调整窗口置顶" : "正在读取窗口置顶状态") : !pin.available ? "窗口置顶暂不可用" : pin.pinned ? "取消窗口置顶" : "窗口置顶";
        return React.createElement(ui.Tooltip, { label: pin.reason ? label + "：" + pin.reason : label }, React.createElement(ui.Button, {
          variant: "ghost", size: "sm", className: "dsh-houdini-window-pin", style: { width: 28, height: 28, padding: 0, flex: "none" },
          "aria-label": label, "aria-pressed": typeof pin.pinned === "boolean" ? pin.pinned : undefined, "data-houdini-window-pin": true,
          disabled: !!pin.busy || !pin.available, onClick: function () { windowPin.toggle(); }
        }, React.createElement("svg", { width: 16, height: 16, viewBox: "0 0 20 20", fill: "none", stroke: "currentColor", strokeWidth: 1.5, "aria-hidden": true },
          React.createElement("path", { d: "M6 2h8l-1 5 3 3v2H4v-2l3-3z", fill: pin.pinned ? "currentColor" : "none", strokeLinecap: "round", strokeLinejoin: "round" }),
          React.createElement("path", { d: "M10 12v6", strokeLinecap: "round" }))));
      }
      function HeaderPin(props) { var row = props.useSessions(function (value) { return value.byId[props.sessionId]; }); return row && !row.blank ? React.createElement(Pin, props) : null; }
      function BlankPin(props) { var row = props.useSessions(function (value) { return value.byId[props.sessionId]; }); return row && row.blank ? React.createElement(Pin, props) : null; }
      return { Mark: decorate(HoudiniProjectMark), Detail: decorate(HoudiniProjectDetail), Label: Label, Blank: Blank, Pin: HeaderPin, BlankPin: BlankPin, Lifecycle: Lifecycle,
        dispose: function () { windowPin.dispose(); launchOwnership.dispose(); } };
    }


    // >>> houdini-node-delivery (generated by tools/gen-node-delivery-client.mjs — do not edit)
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

    // Menu requests are authenticated by the Host. This is the only browser
    // consumer; it commits the same native selection used by Desktop itself.
    function createNavigationFeedback() {
      var value = null, listeners = new Set();
      return {
        publish: function (next) { value = next; listeners.forEach(function (listener) { listener(); }); },
        subscribe: function (listener) { listeners.add(listener); return function () { listeners.delete(listener); }; },
        getSnapshot: function () { return value; }
      };
    }

    function NavigationFeedback(props) {
      var store = props.store, current = React.useSyncExternalStore(store.subscribe, store.getSnapshot);
      if (!current) return null;
      return React.createElement(ui.Toast, { role: "alert", text: current.text, onDone: function () { store.publish(null); } },
        React.createElement(Button, { size: "sm", onClick: function () { store.publish(null); current.retry(); } }, "重试"));
    }

    function installDesktopNavigation(ctx, feedbackStore) {
      if (typeof ctx.inject !== "function") return;
      ctx.inject(["connection", "sessions", "workspaces", "uiSession", "uiWorkspace", "layout"], function (scope) {
        scope.effect(function () {
          var connection = scope.get("connection"), sessions = scope.get("sessions"), workspaces = scope.get("workspaces");
          var uiSession = scope.get("uiSession"), uiWorkspace = scope.get("uiWorkspace"), layout = scope.get("layout");
          var stopped = false, after = 0, pending = null, navigating = null, retryTimer = null;
          function selected() {
            var binding = uiSession.adapter.current.getSnapshot();
            var row = binding && sessions.list.getSnapshot().byId[binding.key];
            return row ? { sessionId: row.id, cwd: row.cwd, agentPreset: row.projectionValues && row.projectionValues.agentPreset } : null;
          }
          async function call(method, input, signal) {
            var response = await connection.rpc.call("/api", "houdiniFrontend/" + method, { args: { input: input } }, signal);
            if (!response.ok) throw new Error(response.error && response.error.message || "Desktop 接入失败。");
            return response.value;
          }
          function acknowledge(sequence) { return call("desktopIntentAck", { sequence: sequence }, AbortSignal.timeout(5000)).catch(function () {}); }
          function waitFor(read, signal) {
            return new Promise(function (resolve, reject) {
              var disposers = [], finished = false, timeout = setTimeout(function () { done(new Error("Desktop 导航状态尚未就绪。")); }, 30000);
              function done(error, value) {
                if (finished) return; finished = true; clearTimeout(timeout);
                disposers.forEach(function (dispose) { dispose(); }); signal.removeEventListener("abort", aborted);
                if (error) reject(error); else resolve(value);
              }
              function aborted() { done(new Error("导航已被后续操作替代。")); }
              function check() {
                if (signal.aborted) { aborted(); return; }
                try { var value = read(workspaces.list.getSnapshot(), sessions.list.getSnapshot()); if (value !== undefined) done(null, value); }
                catch (error) { done(error); }
              }
              disposers.push(workspaces.list.subscribe(check), sessions.list.subscribe(check));
              signal.addEventListener("abort", aborted, { once: true }); check();
            });
          }
          async function navigate(intent, controller) {
            var target = intent.selection, signal = controller.signal, detach = function () {};
            var initial = selected(), initialKey = initial && initial.sessionId;
            var detachWaiting = uiSession.adapter.current.subscribe(function () {
              var w = workspaces.list.getSnapshot(), s = sessions.list.getSnapshot();
              if (w.phase === "ready" && s.phase === "ready") return;
              var next = selected();
              if (next && next.sessionId !== initialKey) { controller.abort("user-navigation"); acknowledge(intent.sequence); }
            });
            try {
              await waitFor(function (w, s) {
                if (w.state === "error") throw new Error(w.error.message);
                return w.phase === "ready" && w.state === "idle" && s.phase === "ready" ? true : undefined;
              }, signal);
              detachWaiting();
              if (signal.aborted) return;
              // A launch started from a conversation does not take the user
              // back after they have chosen another task while Houdini opens.
              var current = selected();
              if (target.source === "launch" && (!current || current.sessionId !== target.sessionId)) {
                await acknowledge(intent.sequence); return;
              }
              if (target.source !== "launch") {
                var navigation = layout.beginNavigation();
                function superseded() { controller.abort("user-navigation"); acknowledge(intent.sequence); }
                navigation.addEventListener("abort", superseded, { once: true });
                detach = function () { navigation.removeEventListener("abort", superseded); };
              }
              await sessions.refresh();
              if (sessions.refreshProjections) await sessions.refreshProjections(target.sessionId);
              await waitFor(function (w, s) {
                if (w.phase !== "ready" || w.state !== "idle" || s.phase !== "ready") return;
                if (w.archivedSessionIds.includes(target.sessionId)) throw new Error("请求的 Houdini 对话已归档。");
                var row = s.byId[target.sessionId], workspace = target.workspaceId && w.items.find(function (item) { return item.workspaceId === target.workspaceId; });
                if (!row || target.workspaceId && (!workspace || !workspace.sessionIds.includes(target.sessionId))) return;
                if (!row.projectionValues || row.projectionValues.agentPreset !== "houdini") throw new Error("请求的对话没有激活 Houdini 模式。");
                var projection = s.projectionsBySession && s.projectionsBySession[target.sessionId];
                var project = projection && projection.values && projection.values.houdiniExecutorIdentity;
                if (!project || (houdiniProjectTarget(project) || {}).executor_id !== target.executorId) return;
                return true;
              }, signal);
              if (signal.aborted) return;
              // A launch binds the originating conversation. Its projection
              // already updates in place; no UI navigation is necessary.
              if (target.source === "launch") { await acknowledge(intent.sequence); return; }
              detach(); uiWorkspace.openSession(target.sessionId);
              var actual = selected();
              if (!actual || actual.sessionId !== target.sessionId || actual.agentPreset !== "houdini") throw new Error("Desktop 尚未选中请求的 Houdini 对话。");
              await acknowledge(intent.sequence);
            } finally { detachWaiting(); detach(); }
          }
          function receive(intent) {
            if (navigating) navigating.abort("newer-intent");
            feedbackStore.publish(null);
            if (!intent.selection) return;
            var controller = new AbortController(); navigating = controller;
            navigate(intent, controller).catch(function (error) {
              if (controller.signal.aborted || stopped) return;
              feedbackStore.publish({ text: "Houdini 对话尚未打开：" + String(error.message || error),
                retry: function () { receive(intent); } });
            });
          }
          async function poll() {
            if (stopped || pending || !connection.generation.getSnapshot()) return;
            var controller = new AbortController(), generation = connection.generation.getSnapshot(); pending = controller;
            try {
              var intent = await call("desktopIntent", { after: after }, controller.signal);
              if (stopped || controller.signal.aborted || connection.generation.getSnapshot() !== generation) return;
              if (intent && intent.sequence > after) { after = intent.sequence; receive(intent); }
            } catch (_error) {
              if (!controller.signal.aborted && !stopped) retryTimer = setTimeout(function () { retryTimer = null; poll(); }, 1500);
            } finally {
              if (pending === controller) pending = null;
              if (!stopped && !controller.signal.aborted && !retryTimer) poll();
            }
          }
          var unsubscribe = connection.generation.subscribe(function () {
            if (pending) pending.abort(); pending = null;
            if (navigating) navigating.abort("connection-changed");
            after = 0; if (retryTimer) clearTimeout(retryTimer); retryTimer = null; poll();
          });
          poll();
          return function () {
            stopped = true; unsubscribe(); if (pending) pending.abort(); if (navigating) navigating.abort("disposed");
            if (retryTimer) clearTimeout(retryTimer); feedbackStore.publish(null);
          };
        }, "dsh-houdini:desktop-navigation");
      });
    }

    // Register domain interaction only while Desktop's actual selected session
    // uses Houdini. Removing an entry also removes Trace's tab from other modes.
    function installHoudiniModeSlot(scope, slots, options, Component) {
      return slots.inject(options.name, function () {
        var sessions = scope.get("sessions"), current = scope.get("uiSession").adapter.current, disposeEntry = null;
        var scheduled = null;
        function sync() {
          var binding = current.getSnapshot(), row = binding && sessions.list.getSnapshot().byId[binding.key];
          var enabled = !!(row && row.projectionValues && row.projectionValues.agentPreset === "houdini");
          if (enabled && !disposeEntry) disposeEntry = slots.register(options, Component);
          if (!enabled && disposeEntry) { disposeEntry(); disposeEntry = null; }
        }
        // Native selection releases the previous Session binding after its
        // snapshot notification. Commit a root roster change after that turn.
        function schedule() { if (scheduled === null) scheduled = setTimeout(function () { scheduled = null; sync(); }, 0); }
        var detachSession = current.subscribe(schedule), detachRows = sessions.list.subscribe(schedule); schedule();
        return function () { detachSession(); detachRows(); if (scheduled !== null) clearTimeout(scheduled); if (disposeEntry) disposeEntry(); };
      });
    }

    // Tutorial status reads the same settings as the tools. Secrets only cross
    // DSH's write-only credentials API from the native modal's password field.
    function createVideoSettings(connection, forms, remote) {
      var form = forms.get("houdini-frontend");
      function CredentialDialog(props) {
        var NativeModal = require("@deepseek-ai/dsh-client-ui-primitives").Modal;
        var password = React.useRef(null), alive = React.useRef(true);
        var busyState = React.useState(false), busy = busyState[0], setBusy = busyState[1];
        var errorState = React.useState(""), error = errorState[0], setError = errorState[1];
        React.useEffect(function () { alive.current = true; return function () { alive.current = false; if (password.current) password.current.value = ""; }; }, []);
        async function save(event) {
          if (event) event.preventDefault();
          if (busy || !props.isCurrent()) return;
          if (!password.current || !password.current.value.trim()) { setError("请输入 API Key。"); return; }
          setBusy(true); setError("");
          var sent = props.call("credentials/set", { ref: props.target.ref, value: password.current.value.trim() });
          password.current.value = "";
          try {
            await sent;
            if (props.isCurrent()) props.saved();
          } catch (failure) { if (alive.current) setError(String(failure.message || failure)); }
          finally { if (alive.current) setBusy(false); }
        }
        return React.createElement(NativeModal, { open: true, onClose: props.close,
          title: "安全录入或更换密钥", closeLabel: "关闭密钥输入", shortcutModal: "houdini-video-credential",
          description: "密钥直接保存到 DSH 凭据服务，不发送给 Agent，也不写进聊天或本插件配置。",
          footer: React.createElement(React.Fragment, null,
            React.createElement(Button, { onClick: props.close }, "取消"),
            React.createElement(Button, { variant: "primary", onClick: save, disabled: busy, "data-houdini-video-save-key": true }, busy ? "正在保存…" : "保存密钥")) },
          React.createElement("p", { style: { fontSize: 12, overflowWrap: "anywhere", lineHeight: 1.6 } }, "转录地址：" + props.target.endpoint),
          props.target.provider && React.createElement("p", { style: { fontSize: 12, lineHeight: 1.6 } },
            "此凭据与 DSH 的「" + (props.target.displayName || props.target.provider) + "」共用，更换后该服务商的其他用途也会使用新密钥。"),
          React.createElement("form", { onSubmit: save, "data-houdini-video-credential": true },
            React.createElement("label", { style: { display: "grid", gap: 8 } }, "API Key",
              React.createElement("input", { ref: password, type: "password", name: "houdini-video-api-key", autoComplete: "new-password",
                autoCapitalize: "off", spellCheck: false, disabled: busy, "data-modal-autofocus": "", "aria-label": "API Key",
                style: { width: "100%", boxSizing: "border-box", padding: "10px 12px", borderRadius: 8,
                  border: "1px solid var(--dsw-alias-border-l2)", background: "var(--dsw-alias-bg-layer-1)", color: "inherit", font: "inherit" } })),
            React.createElement("p", { role: "alert", style: { minHeight: 20, fontSize: 12 } }, error)));
      }
      function initialDraft(facts) {
        var selected = facts && facts.selected || {}, first = facts && (facts.routes || [])[0];
        return { source: selected.provider ? "provider" : "custom", provider: selected.provider || first && first.provider || "",
          endpoint: selected.endpoint || "", protocol: selected.protocol || "openai-transcriptions", model: selected.model || "",
          authentication: selected.authentication || "bearer", concurrency: selected.concurrency === undefined ? 2 : selected.concurrency,
          requestsPerSecond: selected.requestsPerSecond === undefined ? 1 : selected.requestsPerSecond };
      }
      return function VideoSettings() {
        var snapshot = React.useSyncExternalStore(function (listener) { return form.subscribe(listener); }, function () { return form.getSnapshot(); });
        var generation = React.useSyncExternalStore(connection.generation.subscribe, connection.generation.getSnapshot);
        var factsState = React.useState(null), facts = factsState[0], setFacts = factsState[1];
        var draftState = React.useState(null), draft = draftState[0], setDraft = draftState[1];
        var draftKeyState = React.useState(null), draftKey = draftKeyState[0], setDraftKey = draftKeyState[1];
        var messageState = React.useState(""), message = messageState[0], setMessage = messageState[1];
        var busyState = React.useState(false), busy = busyState[0], setBusy = busyState[1];
        var checksState = React.useState(null), checks = checksState[0], setChecks = checksState[1];
        var credentialState = React.useState(null), credentialTarget = credentialState[0], setCredentialTarget = credentialState[1];
        var requests = React.useRef(new Set()), mounted = React.useRef(true), readSequence = React.useRef(0);
        var service = facts && facts.service, credential = service && service.credential;
        var source = service && service.settingsSource, sourceForm = source ? forms.get(source.ns) : null;
        var sourceSnapshot = React.useSyncExternalStore(function (listener) { return sourceForm ? sourceForm.subscribe(listener) : function () {}; },
          function () { return sourceForm ? sourceForm.getSnapshot() : null; });
        var nextDraftKey = facts ? [generation, facts.revision, source ? source.ns : null, sourceSnapshot ? sourceSnapshot.revision : null, sourceSnapshot ? sourceSnapshot.status : null] : null;
        if ((draftKey === null) !== (nextDraftKey === null) || draftKey && nextDraftKey && draftKey.some(function (value, index) { return value !== nextDraftKey[index]; })) {
          setDraftKey(nextDraftKey); setDraft(nextDraftKey ? initialDraft(facts) : null);
        }
        function currentFacts() {
          var live = form.getSnapshot();
          if (!facts || !Number.isSafeInteger(facts.revision) || live.status !== "ready" || live.writable === false || facts.revision !== live.revision) return false;
          if (!source) return true;
          if (!sourceForm) return false;
          var provider = sourceForm.getSnapshot();
          return Number.isSafeInteger(source.revision) && provider.status === "ready" && source.revision === provider.revision;
        }
        async function call(method, args) {
          if (!generation) throw new Error("当前连接已中断，请重连后重试。");
          var controller = new AbortController(), timer = setTimeout(function () { controller.abort(); }, 20000);
          requests.current.add(controller);
          try {
            var response = await connection.rpc.call("/api", method, { args: args }, controller.signal);
            if (!mounted.current || controller.signal.aborted || connection.generation.getSnapshot() !== generation) throw new Error("连接已变化，请刷新后确认当前状态。");
            if (!response.ok) throw new Error(response.error && response.error.message || "DSH 未接受请求。");
            return response.value;
          } finally { clearTimeout(timer); requests.current.delete(controller); }
        }
        async function refresh() {
          var sequence = ++readSequence.current;
          try { var result = await call("houdiniFrontend/videoSettings", {}); if (sequence === readSequence.current) setFacts(result); }
          catch (failure) { if (mounted.current && sequence === readSequence.current && connection.generation.getSnapshot() === generation) setMessage("读取配置失败：" + String(failure.message || failure)); }
        }
        React.useEffect(function () { mounted.current = true; return function () {
          mounted.current = false; requests.current.forEach(function (request) { request.abort(); }); requests.current.clear();
        }; }, []);
        React.useEffect(function () {
          setFacts(null); setDraft(null); setChecks(null); setCredentialTarget(null);
          return function () { requests.current.forEach(function (request) { request.abort(); }); };
        }, [generation]);
        React.useEffect(function () { if (generation) refresh(); }, [generation, snapshot.revision, source ? source.ns : null,
          sourceSnapshot && sourceSnapshot.revision, sourceSnapshot && sourceSnapshot.status]);
        React.useEffect(function () {
          if (!remote || typeof remote.$on !== "function") return;
          return remote.$on("credentials/reference-updated", function () { if (generation) refresh(); });
        }, [generation]);
        function credentialCurrent(target) {
          return currentFacts() && target.generation === connection.generation.getSnapshot() && service && credential && credential.writable &&
            service.credentialRef === target.ref && service.endpoint === target.endpoint && service.protocol === target.protocol && service.provider === target.provider;
        }
        React.useEffect(function () {
          if (credentialTarget && !credentialCurrent(credentialTarget)) setCredentialTarget(null);
        }, [credentialTarget, generation, service, snapshot.revision, sourceSnapshot && sourceSnapshot.revision, sourceSnapshot && sourceSnapshot.status]);
        function change(field, value) { var next = Object.assign({}, draft); next[field] = value; setDraft(next); }
        async function save() {
          if (busy || !draft) return;
          if (!generation || !facts || !currentFacts() || !facts.writable) { setMessage("配置已变化或当前不可写，请刷新后重新确认。"); return; }
          if (draft.source === "provider" && !draft.provider || draft.source === "custom" && !draft.endpoint.trim() || !draft.protocol || !draft.model.trim()) {
            setMessage("请完整选择服务、接口协议和准确的转录模型 ID。"); return;
          }
          var concurrency = Number(draft.concurrency), rate = Number(draft.requestsPerSecond), route = (facts.routes || []).find(function (row) { return row.provider === draft.provider; });
          setBusy(true); setMessage("");
          try {
            var value = await call("houdiniFrontend/videoConfigure", { input: { provider: draft.source === "provider" ? draft.provider : "",
              endpoint: draft.source === "custom" ? draft.endpoint.trim() : "", protocol: draft.protocol, model: draft.model.trim(), authentication: draft.authentication,
              concurrency: concurrency, requests_per_second: rate, expected_revision: facts.revision,
              ...(draft.source === "provider" && route && route.settingsSource ? { expected_provider_revision: route.settingsSource.revision } : {}) } });
            setFacts(value); setMessage(value.service ? "配置已保存。请在一个获准的短片中验证实际转录。" : "配置已保存，但仍有缺项，请根据页面提示继续检查。");
          } catch (failure) { if (mounted.current) setMessage("保存失败：" + String(failure.message || failure)); }
          finally { if (mounted.current) setBusy(false); }
        }
        async function diagnose() {
          if (busy) return;
          setBusy(true); setMessage("");
          try { var result = await call("houdiniFrontend/videoDiagnostics", {}); setChecks(result); }
          catch (failure) { if (mounted.current) setMessage("检查失败：" + String(failure.message || failure)); }
          finally { if (mounted.current) setBusy(false); }
        }
        var fieldLabel = { display: "grid", gap: 6, marginTop: 14, fontSize: 13 };
        var inputStyle = { width: "100%", boxSizing: "border-box", padding: "8px 10px", borderRadius: 7,
          border: "1px solid var(--dsw-alias-border-l2)", background: "var(--dsw-alias-bg-layer-1)", color: "inherit", font: "inherit" };
        function field(label, control, hint) {
          return React.createElement("label", { style: fieldLabel }, React.createElement("span", null, label), control,
            hint ? React.createElement("span", { style: { fontSize: 12, opacity: .72 } }, hint) : null);
        }
        function select(fieldName, options, attributes) {
          return React.createElement("select", Object.assign({ value: draft ? draft[fieldName] : "", disabled: busy || !draft,
            onChange: function (event) { change(fieldName, event.target.value); }, style: inputStyle }, attributes || {}),
            options.map(function (option) { return React.createElement("option", { key: option.value, value: option.value, disabled: !!option.disabled }, option.label); }));
        }
        function input(fieldName, attributes) {
          return React.createElement("input", Object.assign({ value: draft ? draft[fieldName] : "", disabled: busy || !draft,
            onChange: function (event) { change(fieldName, event.target.value); }, style: inputStyle }, attributes || {}));
        }
        var noKey = service && service.authentication === "none";
        var status = !generation ? "连接已中断" : !facts ? "正在读取配置…" : !currentFacts() ? "正在更新配置…" : !service ? "尚未完成转录设置" :
          noKey || credential && credential.configured ? "配置已保存，实际效果以试转录为准" : "等待安全录入密钥";
        var canSave = !!(generation && facts && facts.writable && draft && currentFacts() && !busy);
        return React.createElement("section", { "data-houdini-video-settings": true, style: { maxWidth: 720, padding: "8px 4px 28px", fontSize: 14, lineHeight: 1.65 } },
          React.createElement("h2", { style: { fontSize: 20, margin: "0 0 8px" } }, "教程视频"),
          React.createElement("p", { style: { margin: 0, opacity: .8 } }, "配置讲解转文字所需的服务。聊天模型和 Houdini 工程选择保持不变；密钥只在安全输入框中录入。"),
          React.createElement("p", { role: "status", "data-houdini-video-status": true, style: { margin: "18px 0 12px", fontWeight: 600 } }, status),
          React.createElement("div", { style: { border: "1px solid var(--dsw-alias-border-l2)", borderRadius: 10, padding: 16 } },
            React.createElement("h3", { style: { margin: 0, fontSize: 15 } }, "转录服务"),
            field("地址来源", select("source", [{ value: "custom", label: "官方、中转或本机的独立转录地址" },
              { value: "provider", label: "沿用 DSH 已有服务商", disabled: !(facts && (facts.routes || []).length) }], { "data-houdini-video-source": true })),
            draft && draft.source === "provider" ? field("DSH 服务商", select("provider", (facts && facts.routes || []).map(function (row) {
              return { value: row.provider, label: row.display_name || row.provider };
            }), { "data-houdini-video-provider": true }), "复用其 API 地址和凭据引用，不修改聊天模型。") :
              field("完整转录地址", input("endpoint", { type: "url", placeholder: "https://example.com/v1/audio/transcriptions", "data-houdini-video-endpoint": true }),
                "远程服务使用 HTTPS；本机服务可使用 127.0.0.1 / localhost 的 HTTP 地址。"),
            field("接口协议", select("protocol", (facts && facts.adapters || []).map(function (row) { return { value: row.id, label: row.label }; }),
              { "data-houdini-video-protocol": true }), "必须匹配实际的文件或同步音频接口，不能按厂商名称猜测。"),
            field("转录模型 ID", input("model", { placeholder: "例如：服务文档公布的准确 ASR 模型 ID", "data-houdini-video-model": true }),
              "这是语音模型，不需要加入聊天模型目录。"),
            field("认证方式", select("authentication", [{ value: "bearer", label: "Bearer API Key" }, { value: "none", label: "本机服务不使用密钥" }], { "data-houdini-video-authentication": true })),
            React.createElement("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12 } },
              field("并发请求数", input("concurrency", { type: "number", min: 1, max: 64, step: 1, "data-houdini-video-concurrency": true })),
              field("每秒最多请求", input("requestsPerSecond", { type: "number", min: 0.1, max: 100, step: 0.1, "data-houdini-video-rate": true }))),
            React.createElement("div", { style: { display: "flex", flexWrap: "wrap", gap: 10, marginTop: 18 } },
              React.createElement(Button, { variant: "primary", disabled: !canSave, onClick: save, "data-houdini-video-save-config": true }, busy ? "正在保存…" : "保存转录配置"),
              React.createElement(Button, { disabled: busy || !generation, onClick: function () { setMessage(""); refresh(); }, "data-houdini-video-refresh": true }, "刷新状态"),
              React.createElement(Button, { disabled: busy || !generation || !currentFacts() || !service || noKey || !service.credentialRef || !credential || !credential.writable,
                "data-houdini-video-key": true, onClick: function () { setCredentialTarget({ ref: service.credentialRef, endpoint: service.endpoint,
                  protocol: service.protocol, provider: service.provider, displayName: service.displayName, generation: generation }); } }, "安全录入或更换密钥"))),
          service && React.createElement("p", { style: { fontSize: 12, overflowWrap: "anywhere", opacity: .75 } },
            "当前生效：" + service.displayName + " · " + service.model + " · " + service.endpoint +
            (noKey ? " · 不使用密钥" : credential && credential.configured ? " · 密钥已配置" : " · 密钥未配置")),
          credential && !noKey && !credential.writable && React.createElement("p", { style: { fontSize: 12 } }, "当前凭据只读，请在原生模型设置或相应凭据管理入口修改。"),
          facts && facts.diagnostics && facts.diagnostics.length > 0 && React.createElement("ul", { style: { paddingLeft: 20, fontSize: 12 } },
            facts.diagnostics.map(function (note, index) { return React.createElement("li", { key: index }, note); })),
          React.createElement("p", { role: "status", style: { minHeight: 22, margin: "12px 0", fontSize: 12 } }, message),
          React.createElement("details", { style: { marginTop: 16 } }, React.createElement("summary", { style: { cursor: "pointer" } }, "本机依赖与配置说明"),
            React.createElement("p", { style: { fontSize: 12 } }, "Python 默认使用 Houdini 自带版本，FFmpeg / ffprobe 由插件提供。此页直接保存非秘密设置；原生「设置 → 模型」仍管理聊天服务。"),
            React.createElement(Button, { disabled: busy || !generation, onClick: diagnose, "data-houdini-video-diagnose": true }, "检查本机依赖"),
            checks && React.createElement("ul", { style: { fontSize: 12 } }, (checks.dependencies || []).map(function (item) { return React.createElement("li", { key: item.name, title: item.path || "" }, item.name + "：" + (item.available ? item.version : item.error)); })),
            checks && React.createElement("p", { style: { fontSize: 12 } }, checks.note),
            checks && checks.repair && React.createElement("p", { style: { fontSize: 12 } }, checks.repair.label + "：" + checks.repair.detail)),
          React.createElement("p", { style: { fontSize: 12, opacity: .7, marginTop: 22 } }, "保存配置和检查依赖不会上传音频。实际识别能力和效果需要在任务中获准后用一个短片验证。"),
          credentialTarget && React.createElement(CredentialDialog, { key: credentialTarget.ref, target: credentialTarget, call: call,
            isCurrent: function () { return credentialCurrent(credentialTarget); }, close: function () { setCredentialTarget(null); }, saved: function () {
              setCredentialTarget(null); setMessage("密钥已保存到 DSH 凭据服务。"); refresh();
            } }));
      };
    }

    function createSupportReporter(connection) {
      return function SupportReporter(props) {
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
          link.click();
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

    function apply(ctx) {
      var navigationFeedback = createNavigationFeedback();
      installDesktopNavigation(ctx, navigationFeedback);
      var slots = ctx.get("slots");
      if (slots === undefined) return;
      ctx.effect(function () {
        if (typeof document === "undefined") return;
        var style = document.createElement("style");
        style.dataset.plugin = "dsh-houdini"; style.dataset.pluginCss = shellCssId; style.textContent = shellCss;
        document.head.appendChild(style);
        return function () { style.remove(); };
      });
      slots.inject("shell.overlay", function () {
        return slots.register({ name: "shell.overlay", id: "houdini-navigation-feedback", order: 20 },
          function NavigationFeedbackSlot() { return React.createElement(NavigationFeedback, { store: navigationFeedback }); });
      });
      if (typeof ctx.inject === "function") ctx.inject(["connection", "configForms", "remote"], function (scope) {
        var forms = scope.get("configForms");
        scope.effect(function () { return forms.whileServed(["houdini-frontend"], function () {
          return slots.inject("settings.section", function () {
            return slots.register({ name: "settings.section", id: "houdini-video", order: 15, label: "教程视频" },
              createVideoSettings(scope.get("connection"), forms, scope.get("remote")));
          });
        }); });
      });
      if (typeof ctx.inject === "function") ctx.inject(["connection", "uiSession", "sessions", "uiWorkspace"], function (scope) {
        var desktop = createHoudiniDesktopUi(scope.get("connection"), scope.get("uiSession"), scope.get("sessions"), scope.get("uiWorkspace"));
        scope.effect(function () { return desktop.dispose; });
        [["conversation.input.left", "houdini-initial-project", desktop.Blank],
          ["conversation.input.left", "houdini-initial-window-pin", desktop.BlankPin],
          ["conversation.session.header.utilities", "houdini-project-label", desktop.Label],
          ["conversation.session.header.utilities", "houdini-window-pin", desktop.Pin],
          ["shell.overlay", "houdini-project-feedback", desktop.Lifecycle],
          ["conversation.session.header.utilities", "houdini-support-report", createSupportReporter(scope.get("connection"))]].forEach(function (entry) {
          installHoudiniModeSlot(scope, slots, { name: entry[0], id: entry[1], order: 5, label: undefined }, entry[2]);
        });
      });
      if (typeof ctx.inject === "function") ctx.inject(["connection", "uiConversation"], function (scope) {
        var conversation = scope.get("uiConversation"), connection = scope.get("connection");
        if (!conversation || !connection) return;
        var delivery = nodeDeliveryFactory(React, readHoudiniCanonical);
        var deliveryCssId = "dsh-houdini/node-delivery.css";
        scope.effect(function () {
          if (typeof document === "undefined") return;
          var style = document.createElement("style");
          style.dataset.plugin = "dsh-houdini"; style.dataset.pluginCss = deliveryCssId; style.textContent = delivery.css;
          document.head.appendChild(style);
          return function () { style.remove(); };
        });
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



    }

    return { apply: apply };
  },
});
