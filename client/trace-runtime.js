// Trace is materialized only when its conversation view opens. DSH ships one
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
      imageAttachments: sections["image-attachments"] || null,
      rollback: rollback,
      rawUsage: rawUsage,
      failed: failed,
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
}
