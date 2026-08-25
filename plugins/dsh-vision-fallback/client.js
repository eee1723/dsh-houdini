// dsh-vision-fallback client half: one compact Settings tab for a write-only
// API key and one provider/model route. It intentionally registers no model
// adapter and never contributes entries to the model directory.
window.__ModuleLoader__.load({
  id: "dsh-vision-fallback",
  factory: function (require) {
    var React = require("react");
    var NS = "vision-fallback";

    var css =
      ".dvf-card{max-width:680px;border:1px solid var(--dsw-alias-border-l2);border-radius:12px;" +
      "background:var(--dsw-alias-bg-layer-2);padding:18px 18px 14px;color:var(--dsw-alias-label-primary)}" +
      ".dvf-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}" +
      ".dvf-title{margin:0;font-size:16px;line-height:1.45;font-weight:600}" +
      ".dvf-desc{margin:4px 0 0;font-size:13px;line-height:1.55;color:var(--dsw-alias-label-tertiary)}" +
      ".dvf-state{flex:none;border-radius:999px;padding:2px 9px;font-size:11px;line-height:18px;" +
      "background:var(--dsw-alias-bg-module-platform);color:var(--dsw-alias-label-secondary)}" +
      ".dvf-field{display:flex;flex-direction:column;gap:6px;padding:12px 0}" +
      ".dvf-field+.dvf-field{border-top:1px solid var(--dsw-alias-border-l2)}" +
      ".dvf-labelrow{display:flex;align-items:center;justify-content:space-between;gap:12px}" +
      ".dvf-label{font-size:13px;line-height:1.5;font-weight:500}" +
      ".dvf-clear{appearance:none;border:0;background:none;padding:0;color:var(--dsw-alias-label-secondary);" +
      "font:inherit;font-size:12px;cursor:pointer}" +
      ".dvf-input{box-sizing:border-box;width:100%;height:36px;padding:0 12px;border:1px solid var(--dsw-alias-border-l2);" +
      "border-radius:8px;background:var(--dsw-alias-bg-layer-3);color:var(--dsw-alias-label-primary);font:inherit;font-size:13px}" +
      ".dvf-input:focus-visible,.dvf-clear:focus-visible,.dvf-save:focus-visible{outline:2px solid var(--dsw-alias-brand-primary);outline-offset:1px}" +
      ".dvf-input:disabled,.dvf-clear:disabled,.dvf-save:disabled{opacity:.45;cursor:default}" +
      ".dvf-hint{margin:0;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-tertiary)}" +
      ".dvf-error{margin:0 auto 0 0;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-error)}" +
      ".dvf-actions{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding-top:12px;border-top:1px solid var(--dsw-alias-border-l2)}" +
      ".dvf-save{appearance:none;border:0;border-radius:8px;padding:6px 16px;background:var(--dsw-alias-label-primary);" +
      "color:var(--dsw-alias-bg-layer-3);font:inherit;font-size:13px;cursor:pointer}" +
      "@media(max-width:560px){.dvf-card{padding:15px 14px 12px}.dvf-head{gap:10px}}";

    if (typeof document !== "undefined" && document.querySelector('style[data-plugin-css="dsh-vision-fallback"]') === null) {
      var tag = document.createElement("style");
      tag.dataset.pluginCss = "dsh-vision-fallback";
      tag.textContent = css;
      document.head.appendChild(tag);
    }

    function messageOf(response) {
      var error = response && response.result && response.result.error;
      return error && (error.message || error.code) ? String(error.message || error.code) : "保存失败，请重试";
    }

    function keyConfigured(view) {
      var secrets = view && Array.isArray(view.secrets) ? view.secrets : [];
      return secrets.some(function (entry) {
        return entry && entry.set === true && Array.isArray(entry.path) && entry.path.length === 1 && entry.path[0] === "apiKey";
      });
    }

    function createController(api) {
      var listeners = new Set();
      var view;
      var state = {
        status: "loading",
        writable: false,
        configured: false,
        key: "",
        model: "qwen/qwen3-vl-plus",
        savedModel: "qwen/qwen3-vl-plus",
        saving: false,
        error: "",
        saved: false,
      };

      function publish(patch) {
        state = Object.assign({}, state, patch);
        listeners.forEach(function (listener) { listener(); });
      }

      function accept(next, writable) {
        view = next;
        var model = next && next.value && typeof next.value.model === "string"
          ? next.value.model
          : "qwen/qwen3-vl-plus";
        publish({
          status: "ready",
          writable: writable !== false,
          configured: keyConfigured(next),
          key: "",
          model: model,
          savedModel: model,
          saving: false,
          error: "",
        });
      }

      async function load() {
        try {
          var response = await api.settings.describe({});
          if (!response.result.ok) throw new Error(messageOf(response));
          var body = response.result.value;
          var next = body.namespaces.find(function (entry) { return entry.ns === NS; });
          if (!next) {
            publish({ status: "unavailable", writable: false, error: "配置服务尚未加载，请重启 DSH 服务" });
            return;
          }
          accept(next, body.writable);
        } catch (error) {
          publish({ status: "unavailable", writable: false, error: error instanceof Error ? error.message : String(error) });
        }
      }

      async function mutate(ops) {
        if (!view || state.saving || ops.length === 0) return;
        publish({ saving: true, saved: false, error: "" });
        try {
          var response = await api.settings.mutate({ ns: NS, ops: ops, expectedRevision: view.revision });
          if (!response.result.ok) throw new Error(messageOf(response));
          accept(response.result.value, state.writable);
          publish({ saved: true });
        } catch (error) {
          publish({ saving: false, saved: false, error: error instanceof Error ? error.message : String(error) });
          void load();
        }
      }

      return {
        getSnapshot: function () { return state; },
        subscribe: function (listener) { listeners.add(listener); return function () { listeners.delete(listener); }; },
        load: load,
        editKey: function (value) { publish({ key: value, saved: false, error: "" }); },
        editModel: function (value) { publish({ model: value, saved: false, error: "" }); },
        save: function () {
          var key = state.key.trim();
          var model = state.model.trim();
          var ops = [];
          if (key) ops.push({ op: "set", path: ["apiKey"], value: key });
          if (model && model !== state.savedModel) ops.push({ op: "set", path: ["model"], value: model });
          void mutate(ops);
        },
        clearKey: function () { void mutate([{ op: "unset", path: ["apiKey"] }]); },
      };
    }

    function apply(ctx) {
      var slots = ctx.get("slots");
      var connection = ctx.get("connection");
      if (!slots || !connection) return;
      var controller = createController(connection.api);

      function VisionFallbackSettings() {
        var state = React.useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
        var ready = state.status === "ready";
        var dirty = state.key.trim() !== "" || state.model.trim() !== state.savedModel;
        var invalid = state.model.trim() === "" || state.model.indexOf("/") <= 0;
        var disabled = !ready || !state.writable || state.saving;
        var status = state.status === "loading" ? "加载中" : state.configured ? "Key 已设置" : "未设置 Key";

        return React.createElement(
          "section",
          { className: "dvf-card", "aria-labelledby": "dvf-title" },
          React.createElement(
            "div",
            { className: "dvf-head" },
            React.createElement("div", null,
              React.createElement("h3", { id: "dvf-title", className: "dvf-title" }, "备用视觉模型"),
              React.createElement("p", { className: "dvf-desc" }, "当前模型不能看图时，vision_describe 会使用这里的模型。")
            ),
            React.createElement("span", { className: "dvf-state" }, status)
          ),
          React.createElement(
            "div",
            { className: "dvf-field" },
            React.createElement("div", { className: "dvf-labelrow" },
              React.createElement("label", { className: "dvf-label", htmlFor: "dvf-api-key" }, "API Key"),
              state.configured
                ? React.createElement("button", { type: "button", className: "dvf-clear", disabled: disabled, onClick: controller.clearKey }, "移除 Key")
                : null
            ),
            React.createElement("input", {
              id: "dvf-api-key", className: "dvf-input", type: "password", autoComplete: "off",
              value: state.key, disabled: disabled,
              placeholder: state.configured ? "留空保持现有 Key" : "粘贴 API Key",
              onChange: function (event) { controller.editKey(event.target.value); },
            }),
            React.createElement("p", { className: "dvf-hint" }, "Key 只写入本机设置，不会显示或加入模型列表。")
          ),
          React.createElement(
            "div",
            { className: "dvf-field" },
            React.createElement("label", { className: "dvf-label", htmlFor: "dvf-model" }, "模型"),
            React.createElement("input", {
              id: "dvf-model", className: "dvf-input", type: "text", value: state.model, disabled: disabled,
              placeholder: "qwen/qwen3-vl-plus",
              "aria-invalid": invalid ? "true" : undefined,
              onChange: function (event) { controller.editModel(event.target.value); },
            }),
            React.createElement("p", { className: "dvf-hint" }, "使用 provider/model 格式；provider 决定兼容接口。")
          ),
          React.createElement(
            "div",
            { className: "dvf-actions" },
            state.error ? React.createElement("p", { className: "dvf-error", role: "alert" }, state.error) : null,
            state.saved ? React.createElement("span", { className: "dvf-hint" }, "已保存") : null,
            React.createElement("button", {
              type: "button", className: "dvf-save", disabled: disabled || !dirty || invalid,
              onClick: controller.save,
            }, state.saving ? "保存中…" : "保存")
          )
        );
      }

      slots.inject("settings.plugins.tab", function () {
        return slots.register({
          name: "settings.plugins.tab",
          id: "vision-fallback",
          order: 10,
          label: "视觉备用",
        }, VisionFallbackSettings);
      });

      ctx.effect(function () {
        var remote = ctx.get("remote");
        var off = remote && remote.$on
          ? remote.$on("settings/document-updated", function (namespace) { if (!namespace || namespace === NS) void controller.load(); })
          : function () {};
        void controller.load();
        return off;
      }, "vision-fallback: settings sync");
    }

    return { inject: ["slots", "connection", "remote"], apply: apply };
  },
});
