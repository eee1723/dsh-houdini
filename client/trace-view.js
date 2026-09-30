function createTraceView(React, catalog, sources, trace, css) {
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
}
