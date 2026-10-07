// Public trajectory projection and accounting, independent of React rendering.
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
    if (["houdini_inspect", "houdini_ui_screenshot", "houdini_request", "houdini_resource", "houdini_capabilities", "houdini_query", "houdini_job_status"].includes(name)) return "query";
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
      const recoveryNeeded = ['unknown_transport', 'unknown_runtime', 'unknown', 'result_expired', 'result_unavailable'].includes(receiptStatus);
      const receiptState = {
        queued: '请求已排队', running: '请求执行中', job_submitted: '后台任务已提交',
        not_executed: '未执行', unknown_transport: '结果未知 · 需要查回',
        unknown_runtime: '运行环境已变化 · 结果未知', unknown: '请求结果未知',
        result_expired: '已结束 · 结果已过期', result_unavailable: '已结束 · 结果不可用',
        index: '已读取请求索引',
      }[receiptStatus];
      const jobStatus = canonical?.jobId ? canonical.status : null;
      const jobState = {queued: '后台任务排队中', running: '后台任务执行中', cancelled: '后台任务已取消'}[jobStatus];
      const attention = operationFailures > 0 || checkAttention > 0 || recoveryNeeded;
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
        : jobState || receiptState || (name === 'houdini_job_submit' && canonical?.jobId ? '后台任务已提交' : null)
          || (gateBlocked
          ? "Gate 拦截"
          : rollback
            ? "已回滚"
            : failed
              ? "失败"
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
        outcome,
        operationFailures,
        checkCounts,
        checkAttention,
        checkSummary,
        checkFindings: findings,
        attentionLevel: failed || operationFailures > 0 || checkCounts?.failed > 0 ? 'error'
          : checkCounts?.warning > 0 || recoveryNeeded ? 'warning' : 'unknown',
        attention,
        requestReceipt,
        recoveryNeeded,
        jobStatus,
        repeatedExecution: Boolean(repeatedExecution || canonical?.requestReceipt?.retrieved),
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
    const returned = entries.filter(entry => entry.name.startsWith("houdini_") && !entry.pending);
    const used = new Set(returned.flatMap(entry => entry.verbs.map(verb => verb.verb)));
    const known = catalog.flatMap(domain => domain.verbs.map(verb => verb.name));
    const accounts = requests.map(request => request.accounting).filter(Boolean);
    const toolUsage = new Map(), verbUsage = new Map();
    for (const entry of entries) {
      const count = toolUsage.get(entry.name) || { calls: 0, failed: 0, pending: 0, operationAttention: 0 };
      count.calls++;
      count.failed += Number(entry.failed);
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
}
