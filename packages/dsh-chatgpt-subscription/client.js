// Native settings only. Account records, authorization and inference stay in the Host.
window.__ModuleLoader__.load({
  id: "dsh-chatgpt-subscription",
  factory: function (require) {
    var React = require("react"), ui = require("@deepseek-ai/dsh-client-ui-primitives");
    var css = ".cgs-page{color:var(--dsw-alias-label-primary);max-width:880px;min-width:0;padding:4px 0 20px;font-size:13px;line-height:1.6}.cgs-page h2{font-size:18px;margin:0 0 8px}.cgs-page h3{font-size:14px;margin:0}.cgs-page p{margin:6px 0}.cgs-muted{color:var(--dsw-alias-label-secondary)}.cgs-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px}.cgs-card{border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-lg);background:var(--dsw-alias-bg-layer-1);padding:16px;margin-top:16px;min-width:0;overflow-wrap:anywhere}.cgs-row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 0;border-bottom:1px solid var(--dsw-alias-border-l2)}.cgs-row:last-child{border-bottom:0;padding-bottom:0}.cgs-row .cgs-actions{margin:0}.cgs-facts{display:grid;grid-template-columns:auto minmax(0,1fr);gap:6px 16px;margin:12px 0}.cgs-facts dt{color:var(--dsw-alias-label-secondary)}.cgs-facts dd{margin:0;overflow-wrap:anywhere}.cgs-notice{padding:10px 12px;background:var(--dsw-alias-bg-layer-2);border-radius:var(--dsw-radius-md);overflow-wrap:anywhere}.cgs-error{color:var(--dsw-alias-label-primary);border-left:3px solid var(--dsw-alias-state-error-primary);padding:8px 12px}.cgs-page details{margin-top:12px}.cgs-page summary{cursor:pointer;color:var(--dsw-alias-label-secondary)}.cgs-page ul{padding-left:20px}.cgs-page a,.cgs-modal a{color:var(--dsw-alias-link)}.cgs-modal p{line-height:1.7;overflow-wrap:anywhere}.cgs-account-name{font-weight:600}.cgs-account-meta{font-size:12px;color:var(--dsw-alias-label-secondary)}";

    function usageUrl(value) { return value === "https://chatgpt.com/settings/usage" ? value : null; }
    function launchUrl(value) {
      try {
        var url = new URL(value);
        return url.protocol === "http:" && url.hostname === "127.0.0.1" && !!url.port && !url.username && !url.password &&
          !url.search && !url.hash && /^\/launch\/[A-Za-z0-9_-]{32,128}$/.test(url.pathname) ? url.href : null;
      } catch (_) { return null; }
    }
    function label(account) { return account.identity && (account.identity.email || account.identity.name) || account.label || "ChatGPT 账号"; }
    function accountStatus(account) {
      if (account.verificationPending) return "登录验证尚未完成";
      if (account.status === "connected") return "已连接";
      if (account.status === "reauth_required") return "需要重新登录";
      return "未连接";
    }
    function failure(error) { return { message: String(error && error.message || error || "操作未完成"), code: error && error.code }; }

    function createSettings(connection) {
      return function SubscriptionSettings() {
        var generation = React.useSyncExternalStore(connection.generation.subscribe, connection.generation.getSnapshot);
        var viewState = React.useState(null), view = viewState[0], setView = viewState[1];
        var busyState = React.useState(null), busy = busyState[0], setBusy = busyState[1];
        var errorState = React.useState(null), error = errorState[0], setError = errorState[1];
        var messageState = React.useState(""), message = messageState[0], setMessage = messageState[1];
        var loginState = React.useState(false), loginOpen = loginState[0], setLoginOpen = loginState[1];
        var confirmState = React.useState(null), confirm = confirmState[0], setConfirm = confirmState[1];
        var dismissedState = React.useState(null), dismissedNotice = dismissedState[0], setDismissedNotice = dismissedState[1];
        var mounted = React.useRef(false), reading = React.useRef(null), acting = React.useRef(null), polling = React.useRef(null), latest = React.useRef(null);
        var data = view && view.generation === generation ? view.value : null;
        var accounts = data ? data.accounts : [], active = accounts.find(function (account) { return account.id === data.activeAccountId; });
        var login = data && data.login, pending = login && login.status === "pending";
        latest.current = data;

        function current(owner) { return mounted.current && connection.generation.getSnapshot() === owner; }
        async function remote(method, input, controller) {
          var timer = setTimeout(function () { controller.abort(); }, 30000);
          try {
            var response = await connection.rpc.call("/api", "chatgptSubscription/" + method,
              { args: input === undefined ? {} : { input: input } }, controller.signal);
            if (controller.signal.aborted) throw new Error("请求已超时或中断，结果尚未确认。");
            if (!response.ok) throw response.error || new Error("操作未完成，请重试。");
            return response.value;
          } finally { clearTimeout(timer); }
        }
        function abort(reference) { if (reference.current) reference.current.abort(); reference.current = null; }
        async function read(owner) {
          abort(reading);
          var controller = new AbortController(); reading.current = controller;
          try {
            var value = await remote("status", undefined, controller);
            if (current(owner) && !controller.signal.aborted && reading.current === controller) setView({ generation: owner, value: value });
          } catch (problem) {
            if (current(owner) && reading.current === controller) setError(failure(problem));
          } finally { if (reading.current === controller) reading.current = null; }
        }
        async function act(method, input, success) {
          var owner = connection.generation.getSnapshot();
          if (!owner || acting.current || !current(owner)) return;
          abort(reading); abort(polling);
          var controller = new AbortController(); acting.current = controller;
          setBusy(method); setError(null); setMessage("");
          try {
            var value = await remote(method, input, controller);
            if (!current(owner) || controller.signal.aborted || acting.current !== controller) return;
            if (success) success(value);
            await read(owner);
          } catch (problem) {
            if (current(owner) && acting.current === controller) {
              setError(failure(controller.signal.aborted ? new Error("本次操作的结果未确认，请刷新状态查看。") : problem));
              // Only re-read facts after an uncertain response. Never repeat login or a mutation.
              await read(owner);
            }
          } finally {
            if (acting.current === controller) { acting.current = null; if (current(owner)) setBusy(null); }
          }
        }
        React.useEffect(function () {
          mounted.current = true;
          setView(null); setBusy(null); setError(null); setMessage(""); setConfirm(null); setLoginOpen(false); setDismissedNotice(null);
          if (generation) read(generation);
          return function () { mounted.current = false; abort(reading); abort(acting); abort(polling); };
        }, [generation]);
        React.useEffect(function () {
          if (!generation || !pending || busy) return;
          var owner = generation, identifier = login.attemptId, stopped = false, timer;
          async function poll() {
            var controller = new AbortController(); polling.current = controller;
            try {
              var value = await remote("loginStatus", { attemptId: identifier }, controller);
              if (!stopped && current(owner) && !controller.signal.aborted) {
                setView(function (previous) {
                  if (!previous || previous.generation !== owner || previous.value.login && previous.value.login.attemptId !== identifier) return previous;
                  return { generation: owner, value: Object.assign({}, previous.value, { login: value }) };
                });
                if (value.status !== "pending") {
                  setLoginOpen(false);
                  if (value.status === "failed") setError(value.error || { message: "登录未完成，请重试。" });
                  if (value.status === "authorized") { setError(null); setMessage("账号已连接。调用授权和模型目录以当前状态为准。"); }
                  if (value.status === "cancelled") { setError(null); setMessage("登录已取消。"); }
                  await read(owner);
                  return;
                }
              }
            } catch (problem) {
              if (!stopped && current(owner) && polling.current === controller) { setError(failure(problem)); await read(owner); }
            } finally { if (polling.current === controller) polling.current = null; }
            if (!stopped && current(owner)) timer = setTimeout(poll, 1500);
          }
          timer = setTimeout(poll, 1000);
          return function () { stopped = true; clearTimeout(timer); abort(polling); };
        }, [generation, pending && login.attemptId, !!busy]);

        function begin(input) { setLoginOpen(true); return act("beginLogin", input); }
        function cancel() {
          return act("cancelLogin", { attemptId: login.attemptId }, function (result) {
            setLoginOpen(false);
            if (result.status === "authorized") setMessage("授权已在取消前完成，请核对当前账号状态。");
            else if (result.status === "cancelled") setMessage("登录已取消。");
            else if (result.status === "failed") setError(result.error || { message: "登录未完成，请查看当前状态。" });
            else setMessage("已提交取消，请以当前登录状态为准。");
          });
        }
        async function copyLogin() {
          var owner = generation, identifier = pending && login.attemptId, url = pending && launchUrl(login.launchUrl);
          if (!url || busy || !identifier) return;
          try {
            await navigator.clipboard.writeText(url);
            var now = latest.current && latest.current.login;
            if (current(owner) && now && now.status === "pending" && now.attemptId === identifier) setMessage("临时登录入口已复制，请在浏览器打开。此入口只在本次登录期间有效。");
          } catch (_) { if (current(owner)) setError({ message: "未能复制。请使用“重新打开浏览器”，或检查浏览器的剪贴板权限。" }); }
        }
        function dismissPlanNotice(account) {
          if (acting.current) return;
          setDismissedNotice({ generation: generation, accountId: account.id });
          return act("acknowledgePlanNotice", { accountId: account.id });
        }
        function button(text, onClick, options) {
          return React.createElement(ui.Button, Object.assign({ onClick: onClick, disabled: !generation || !!busy, variant: "outline" }, options), text);
        }
        var allowed = active && active.status === "connected" && !active.verificationPending;
        var notice = allowed && active.sharing && active.needsPlanNotice &&
          !(dismissedNotice && dismissedNotice.generation === generation && dismissedNotice.accountId === active.id) && !busy ? active : null;
        var usage = data && usageUrl(data.usageUrl), safeLaunch = pending && launchUrl(login.launchUrl);
        var progress = { beginLogin: "正在准备浏览器授权…", reopenBrowser: "正在打开浏览器…", cancelLogin: "正在取消登录…",
          selectAccount: "正在切换订阅账号…", disconnect: "正在断开账号…", models: "正在读取模型目录…", acknowledgePlanNotice: "正在保存确认…" };
        return React.createElement("section", { className: "cgs-page", "data-chatgpt-subscription-settings": true },
          React.createElement("h2", null, "ChatGPT 订阅"),
          React.createElement("p", { className: "cgs-muted" }, "连接 ChatGPT 账号，为支持的请求使用你授权的计划额度。模型仍在 DSH 原生模型菜单中选择。"),
          !generation ? React.createElement("p", { role: "status" }, "与 DSH 的连接已中断，恢复后会重新读取账号状态。") :
            !data ? React.createElement("p", { role: "status" }, error ? "暂时无法读取账号状态。" : "正在读取账号状态…") : null,
          error ? React.createElement("p", { className: "cgs-error", role: "alert" }, error.message) : null,
          busy ? React.createElement("p", { role: "status", className: "cgs-muted" }, progress[busy] || "正在处理…") : null,
          message ? React.createElement("p", { className: "cgs-notice", role: "status" }, message) : null,
          data ? React.createElement(React.Fragment, null,
            React.createElement("div", { className: "cgs-card" },
              React.createElement("h3", null, "当前订阅账号"),
              React.createElement("dl", { className: "cgs-facts" },
                React.createElement("dt", null, "账号"), React.createElement("dd", null, active ? label(active) : "尚未选择"),
                React.createElement("dt", null, "连接"), React.createElement("dd", null, active ? accountStatus(active) : "未连接"),
                React.createElement("dt", null, "调用授权"), React.createElement("dd", null, allowed && active.sharing ? "已允许使用 ChatGPT 计划额度" : "尚未取得订阅调用授权"),
                React.createElement("dt", null, "模型目录"), React.createElement("dd", null, data.catalogRead ? "已读取 " + data.models.length + " 项" : "尚未读取此账号的目录")),
              React.createElement("p", { className: "cgs-muted" }, "以上状态不代表真实请求已成功。本页不调用模型生成内容，实际结果以对话中的回复或报错为准。"),
              React.createElement("div", { className: "cgs-actions" },
                button("Continue with ChatGPT", function () { return begin({ newAccount: true }); }, { variant: "primary", disabled: !generation || !!busy || !!pending, "data-cgs-connect": true }),
                button(busy === "models" ? "正在读取目录…" : "刷新模型目录", function () { return act("models", { refresh: true }, function () { setMessage("目录已刷新。请在对话的原生模型菜单中选择；这里不会改变默认模型。"); }); },
                  { disabled: !allowed || !active.sharing || !!busy || !!pending, "data-cgs-models": true }),
                usage ? React.createElement("a", { href: usage, target: "_blank", rel: "noopener noreferrer" }, "查看与管理用量") : null),
              accounts.length && !pending ? React.createElement("p", { className: "cgs-muted" }, "Continue with ChatGPT 可添加其他账号；已有账号需要补充授权时，请使用下面的账号操作。") : null,
              pending ? React.createElement("div", { className: "cgs-notice", style: { marginTop: 12 } },
                React.createElement("p", { role: "status" }, login.message || "等待你在浏览器中完成授权…"),
                button("查看登录进度", function () { setLoginOpen(true); })) : null,
              data.catalogRead ? React.createElement("details", null, React.createElement("summary", null, "查看已读取的模型目录"),
                React.createElement("p", { className: "cgs-muted" }, "目录只读；此客户端支持的模型以 DSH 模型菜单为准。"),
                data.models.length ? React.createElement("ul", null, data.models.map(function (model) { return React.createElement("li", { key: model.id }, model.name,
                  model.supported === false ? React.createElement("span", { className: "cgs-muted" }, " — ", model.unsupportedReason || "此客户端尚未支持") : null); })) : React.createElement("p", null, "服务返回的目录为空。")) : null),
            accounts.length ? React.createElement("div", { className: "cgs-card" }, React.createElement("h3", null, "已记录的账号"),
              accounts.map(function (account) {
                var connected = account.status === "connected" && !account.verificationPending;
                return React.createElement("div", { className: "cgs-row", key: account.id },
                  React.createElement("div", null,
                    React.createElement("div", { className: "cgs-account-name" }, label(account), account.active ? " · 当前" : ""),
                    React.createElement("div", { className: "cgs-account-meta" }, accountStatus(account), connected && account.sharing ? " · 已授权计划额度" : "")),
                  React.createElement("div", { className: "cgs-actions" },
                    !connected ? button("重新连接", function () { return begin({ accountId: account.id }); }, { disabled: !!busy || !!pending }) : null,
                    connected && !account.sharing ? button("授权计划额度", function () { return begin({ accountId: account.id }); }, { disabled: !!busy || !!pending }) : null,
                    connected && !account.active ? button("设为当前账号", function () { return act("selectAccount", { accountId: account.id }, function () { setMessage("已切换订阅账号，默认模型保持原选择。"); }); }, { disabled: !!busy || !!pending }) : null,
                    connected || account.verificationPending ? button("断开…", function () { setConfirm({ generation: generation, accountId: account.id, label: label(account) }); }, { disabled: !!busy || !!pending }) : null));
              }), React.createElement("p", { className: "cgs-muted" }, "切换账号只影响之后的新请求；断开账号会结束该账号正在进行的订阅请求。默认模型仍由你在 DSH 中选择。")) : null,
            React.createElement("details", null, React.createElement("summary", null, "技术详情"),
              React.createElement("p", null, "提供方：", React.createElement("code", null, data.provider)),
              React.createElement("p", null, "本机凭据保护：", data.protection),
              error && error.code ? React.createElement("p", null, "错误代码：", error.code) : null)) : null,
          React.createElement("div", { className: "cgs-actions" }, button(busy ? "正在处理…" : "刷新状态", function () { setError(null); setMessage(""); return read(generation); }, { "data-cgs-refresh": true })),
          React.createElement(ui.Modal, { open: !!(loginOpen && pending), title: "在浏览器中完成 ChatGPT 授权", closeLabel: "收起登录进度", className: "cgs-modal",
            onClose: function () { setLoginOpen(false); },
            footer: React.createElement(React.Fragment, null,
              button("收起", function () { setLoginOpen(false); }, { disabled: false }),
              button(busy === "cancelLogin" ? "正在取消…" : "取消登录", cancel)) },
            React.createElement("p", { role: "status" }, pending && (login.message || "等待浏览器授权结果…")),
            error ? React.createElement("p", { className: "cgs-error", role: "alert" }, error.message) : null,
            message ? React.createElement("p", { role: "status" }, message) : null,
            React.createElement("p", null, "请在系统浏览器中完成登录和权限选择。收起此窗口不会取消登录。"),
            React.createElement("div", { className: "cgs-actions" },
              button("重新打开浏览器", function () { return act("reopenBrowser", { attemptId: login.attemptId }); }),
              button("复制临时登录入口", copyLogin, { disabled: !!busy || !safeLaunch }))),
          React.createElement(ui.Modal, { open: !!(confirm && confirm.generation === generation), title: "断开 ChatGPT 账号？", closeLabel: "取消断开", className: "cgs-modal",
            onClose: function () { setConfirm(null); }, footer: React.createElement(React.Fragment, null,
              button("取消", function () { setConfirm(null); }, { disabled: false }),
              button("断开账号", function () { var selected = confirm; setConfirm(null); return act("disconnect", { accountId: selected.accountId }, function (result) { setMessage(result.message || "已断开此账号。"); }); }, { variant: "primary" })) },
            React.createElement("p", null, confirm && confirm.label), React.createElement("p", null, "此插件会解除本机连接并尝试撤销远端授权。正在使用此账号的订阅请求将结束；其他提供方、会话和已选模型保持。")),
          React.createElement(ui.Modal, { open: !!notice, title: "已允许使用你的 ChatGPT 计划", closeLabel: "知道了", className: "cgs-modal",
            onClose: function () { if (notice) return dismissPlanNotice(notice); },
            footer: button("知道了", function () { if (notice) return dismissPlanNotice(notice); }, { variant: "primary" }) },
            React.createElement("p", null, "当你在 DSH 模型菜单选择 ChatGPT 订阅提供方时，符合条件的请求将使用你授权的计划额度。此授权不代表刚刚已经发送请求。"),
            usage ? React.createElement("a", { href: usage, target: "_blank", rel: "noopener noreferrer" }, "在 ChatGPT 设置中管理用量") : null));
      };
    }

    function apply(ctx) {
      var slots = ctx.get("slots");
      if (!slots) return;
      ctx.effect(function () {
        if (typeof document === "undefined") return;
        var style = document.createElement("style"); style.dataset.plugin = "dsh-chatgpt-subscription"; style.textContent = css;
        document.head.appendChild(style); return function () { style.remove(); };
      });
      ctx.inject(["connection"], function (scope) {
        return slots.inject("settings.section", function () {
          return slots.register({ name: "settings.section", id: "chatgpt-subscription", order: 40, label: "ChatGPT 订阅" }, createSettings(scope.get("connection")));
        });
      });
    }
    return { apply: apply };
  }
});
