#!/usr/bin/env node
// trace-report：把 dsh session 的 houdini 操作 trace 生成单文件 HTML 复盘报告。
//
// 用法：
//   node tools/trace-report.mjs [sessionDir|session.jsonl.zstd] [--out <file>]
//   缺省 session：~/.dsh/sessions 下最新修改的一个。
//
// 报告内容：
//   1. 概览：工具调用统计 / 动词命中 / 裸 hou / 失败 / advisory
//   2. 词表目录（从 docs/tool-design.md 解析，按域分组，标注本次会话使用次数）
//   3. 调用时间线：按真实顺序（工具结果时间 + ledger 顺序），时间戳 + 耗时，
//      必要信息平铺，代码与完整返回折叠在 <details> 里
//   4. 分析段落：裸 hou 段落、失败调用、advisory 触发——词表改进的直接输入
//
// 数据边界：session.jsonl.zstd 是多帧拼接，按魔数 28 B5 2F FD 切帧逐段解压；
// 模型可见文本里的 `verbs (N):` 块是动词 ledger 的渲染（src/tools.ts renderVerbs）。
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { loadCatalog } from './catalog-lib.mjs';

const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..');
const DOC_PATH = path.join(REPO_ROOT, 'docs', 'tool-design.md');

// ---------- args ----------
const argv = process.argv.slice(2);
let sessionArg = null;
let outArg = null;
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === '--out') outArg = argv[++i];
  else if (!argv[i].startsWith('--')) sessionArg = argv[i];
}

function newestSession() {
  const root = path.join(os.homedir(), '.dsh', 'sessions');
  let best = null;
  for (const ws of fs.readdirSync(root)) {
    const wsDir = path.join(root, ws);
    if (!fs.statSync(wsDir).isDirectory()) continue;
    for (const sess of fs.readdirSync(wsDir)) {
      const f = path.join(wsDir, sess, 'session.jsonl.zstd');
      if (fs.existsSync(f)) {
        const m = fs.statSync(f).mtimeMs;
        if (!best || m > best.m) best = { m, file: f };
      }
    }
  }
  return best?.file;
}

let sessionFile = sessionArg;
if (sessionArg && fs.statSync(sessionArg).isDirectory()) {
  sessionFile = path.join(sessionArg, 'session.jsonl.zstd');
}
if (!sessionFile) sessionFile = newestSession();
if (!sessionFile || !fs.existsSync(sessionFile)) {
  console.error('session 文件不存在:', sessionFile);
  process.exit(1);
}

// ---------- decompress multi-frame zstd ----------
function loadEvents(file) {
  const buf = fs.readFileSync(file);
  const starts = [];
  for (let i = 0; i + 4 <= buf.length; i++) {
    if (buf[i] === 0x28 && buf[i + 1] === 0xb5 && buf[i + 2] === 0x2f && buf[i + 3] === 0xfd) starts.push(i);
  }
  const events = [];
  for (let i = 0; i < starts.length; i++) {
    const end = i + 1 < starts.length ? starts[i + 1] : buf.length;
    try {
      const out = zlib.zstdDecompressSync(buf.subarray(starts[i], end));
      for (const line of out.toString('utf8').split('\n')) {
        const t = line.trim();
        if (!t) continue;
        try { events.push(JSON.parse(t)); } catch {}
      }
    } catch {}
  }
  return events;
}

// ---------- catalog from tool-design.md ----------
// 解析逻辑在 tools/catalog-lib.mjs（与 gen-client-catalog.mjs 共用）。

// ---------- parse trace ----------
const events = loadEvents(sessionFile);
const calls = new Map();
for (const e of events) {
  if (e.type === 'tool/call') calls.set(e.data.callId, e.data);
}

const userMsgs = [];
for (const e of events) {
  if (e.type !== 'user/message') continue;
  const d = e.data || {};
  if (d.source?.kind !== 'user') continue;
  const text = (d.content || []).filter((c) => c.type === 'text').map((c) => c.text).join('\n');
  if (!text || text.startsWith('<system-reminder>') || text.startsWith('Current runtime context')) continue;
  userMsgs.push({ time: e.time, text });
}

const steps = [];
for (const e of events) {
  if (e.type !== 'tool/result') continue;
  const msg = e.data?.message || {};
  const callId = msg.source?.callId || msg.content?.[0]?.toolCallId;
  const call = calls.get(callId);
  if (!call) continue;
  let args = {};
  try { args = JSON.parse(call.arguments || '{}'); } catch {}
  const text = (msg.content?.[0]?.content || [])
    .filter((c) => c.type === 'text').map((c) => c.text).join('\n');

  const failed = text.startsWith('Execution failed');
  const isHoudini = (call.name || '').startsWith('houdini_');

  // verbs (N): 块 —— renderVerbs 的渲染行：`i. [ok|FAIL] verb(args, kwargs) -> detail (Xms)`
  const verbs = [];
  const verbsBlock = text.match(/verbs \((\d+)\):\n([\s\S]*?)(?:\n\n|$)/);
  if (verbsBlock) {
    for (const line of verbsBlock[2].split('\n')) {
      const m = line.match(/^(\d+)\. \[(ok|FAIL)\] (\w+)\((.*)\) -> (.*) \(([\d.]+)ms\)\s*$/);
      if (m) verbs.push({ n: +m[1], ok: m[2] === 'ok', verb: m[3], argsText: m[4], detail: m[5], ms: +m[6] });
    }
  }
  const hintBlock = text.match(/hint:\n([\s\S]*?)$/);
  const houCalls = args.code ? (args.code.match(/\bhou\.\w+\(/g) || []).length : 0;
  let errorTail = null;
  if (failed) {
    const lines = text.split('\n');
    errorTail = lines.slice(-3).join('\n');
  }
  steps.push({
    time: e.time, turn: e.data?.turn, step: e.data?.step,
    tool: call.name || '?', args, code: args.code || null,
    houCalls, verbs, failed, errorTail,
    advisory: hintBlock ? hintBlock[1].trim() : null,
    resultText: text, isHoudini,
  });
}
steps.sort((a, b) => a.time - b.time);

// 动词使用统计 → 回填目录
const catalog = loadCatalog(DOC_PATH);
const verbCount = {};
for (const s of steps) for (const v of s.verbs) verbCount[v.verb] = (verbCount[v.verb] || 0) + 1;
let catalogVerbs = 0;
let usedVerbs = 0;
for (const d of catalog) {
  for (const v of d.verbs) {
    v.used = verbCount[v.name] || 0;
    catalogVerbs++;
    if (v.used > 0) usedVerbs++;
  }
}
const unknownVerbs = Object.keys(verbCount).filter(
  (n) => !catalog.some((d) => d.verbs.some((v) => v.name === n)),
);

// 概览统计
const toolCount = {};
for (const s of steps) toolCount[s.tool] = (toolCount[s.tool] || 0) + 1;
const rawHouSteps = steps.filter((s) => s.isHoudini && s.houCalls > 0 && s.verbs.length === 0);
const failedSteps = steps.filter((s) => s.failed);
const advisorySteps = steps.filter((s) => s.advisory);
const totalVerbCalls = Object.values(verbCount).reduce((a, b) => a + b, 0);

// ---------- HTML ----------
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const fmtTime = (ms) => {
  const d = new Date(ms);
  const p = (n, w = 2) => String(n).padStart(w, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};

const chip = (text, cls) => `<span class="chip ${cls}">${esc(text)}</span>`;

const catalogHtml = catalog.map((d) => `
  <div class="domain">
    <div class="domain-name">${esc(d.note)}</div>
    ${d.verbs.map((v) => `
      <div class="verb ${v.used ? 'used' : 'unused'}">
        <span class="verb-name">${esc(v.name)}</span>
        <span class="verb-sig">${esc(v.sig)}</span>
        ${v.used ? `<span class="badge ok">×${v.used}</span>` : '<span class="badge dim">未用</span>'}
        <div class="verb-desc">${esc(v.desc)}</div>
      </div>`).join('')}
  </div>`).join('');

const timelineHtml = steps.map((s, i) => {
  const verbChips = s.verbs.map((v) =>
    `<span class="chip verb-chip ${v.ok ? '' : 'fail'}" title="${esc(v.argsText)} -> ${esc(v.detail)}">${esc(v.verb)} <span class="ms">${v.ms}ms</span></span>`,
  ).join('');
  const badges = [
    s.failed ? chip('失败', 'fail') : '',
    s.houCalls > 0 ? chip(`裸 hou ×${s.houCalls}`, s.verbs.length ? 'warn' : 'bad') : '',
    s.advisory ? chip('advisory', 'warn') : '',
    s.verbs.length ? chip(`动词 ×${s.verbs.length}`, 'ok') : '',
  ].join('');
  const detailParts = [];
  if (s.code) detailParts.push(`<div class="lbl">code</div><pre>${esc(s.code)}</pre>`);
  if (Object.keys(s.args).length && !s.code) detailParts.push(`<div class="lbl">args</div><pre>${esc(JSON.stringify(s.args, null, 2))}</pre>`);
  if (s.advisory) detailParts.push(`<div class="lbl">advisory</div><pre class="adv">${esc(s.advisory)}</pre>`);
  detailParts.push(`<div class="lbl">result</div><pre>${esc(s.resultText)}</pre>`);
  return `
  <div class="step ${s.failed ? 'failed' : ''}">
    <div class="step-head">
      <span class="t">${fmtTime(s.time)}</span>
      <span class="seq">#${i + 1}</span>
      <span class="tool ${s.isHoudini ? 'hou' : ''}">${esc(s.tool)}</span>
      ${badges}
      <span class="verb-chips">${verbChips}</span>
    </div>
    <details><summary>详情</summary>${detailParts.join('')}</details>
  </div>`;
}).join('');

const rawHouHtml = rawHouSteps.length
  ? rawHouSteps.map((s) => {
      const idx = steps.indexOf(s) + 1;
      return `<div class="step"><div class="step-head"><span class="t">${fmtTime(s.time)}</span><span class="seq">#${idx}</span><span class="tool hou">${esc(s.tool)}</span>${chip(`裸 hou ×${s.houCalls}`, 'bad')}</div>
      <details><summary>代码</summary><pre>${esc(s.code)}</pre></details></div>`;
    }).join('')
  : '<p class="dim-text">无</p>';

const failedHtml = failedSteps.length
  ? failedSteps.map((s) => {
      const idx = steps.indexOf(s) + 1;
      return `<div class="step failed"><div class="step-head"><span class="t">${fmtTime(s.time)}</span><span class="seq">#${idx}</span><span class="tool hou">${esc(s.tool)}</span>${chip('失败', 'fail')}</div>
      <pre class="err">${esc(s.errorTail)}</pre>
      <details><summary>完整结果与代码</summary><pre>${esc(s.code || '')}</pre><pre>${esc(s.resultText)}</pre></details></div>`;
    }).join('')
  : '<p class="dim-text">无</p>';

const sessionId = path.basename(path.dirname(sessionFile));
const html = `<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>houdini trace 复盘 — ${esc(sessionId)}</title>
<style>
  :root { --bg:#1b1c20; --panel:#24262b; --line:#34363d; --fg:#e8e9ec; --dim:#9a9ba2;
          --ok:#4ec98a; --warn:#e5b567; --bad:#e06c75; --acc:#5b9dff; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.6 "Microsoft YaHei",system-ui,sans-serif; }
  header { padding:18px 28px; border-bottom:1px solid var(--line); }
  header h1 { margin:0 0 4px; font-size:18px; }
  header .meta { color:var(--dim); font-size:12px; }
  main { display:grid; grid-template-columns: 380px 1fr; gap:0; align-items:start; }
  .col { padding:18px 24px; }
  .col.left { border-right:1px solid var(--line); position:sticky; top:0; max-height:100vh; overflow:auto; }
  h2 { font-size:15px; margin:6px 0 12px; color:var(--acc); }
  .cards { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:8px 14px; }
  .card .num { font-size:20px; font-weight:700; }
  .card .cap { color:var(--dim); font-size:12px; }
  .domain { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin-bottom:10px; }
  .domain-name { font-weight:700; margin-bottom:6px; color:var(--acc); }
  .verb { padding:5px 6px; border-top:1px dashed var(--line); }
  .verb.unused { opacity:.55; }
  .verb-name { font-family:Consolas,monospace; font-weight:700; }
  .verb-sig { font-family:Consolas,monospace; color:var(--dim); font-size:11px; margin-left:6px; }
  .verb-desc { color:var(--dim); font-size:12px; }
  .badge { float:right; font-size:11px; border-radius:4px; padding:0 6px; }
  .badge.ok { color:var(--ok); border:1px solid var(--ok); }
  .badge.dim { color:var(--dim); border:1px solid var(--line); }
  .step { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:8px 12px; margin-bottom:8px; }
  .step.failed { border-color:var(--bad); }
  .step-head { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
  .t { font-family:Consolas,monospace; color:var(--acc); font-weight:700; }
  .seq { color:var(--dim); font-size:12px; }
  .tool { font-family:Consolas,monospace; font-size:12px; background:#313340; border-radius:4px; padding:1px 8px; }
  .tool.hou { background:#2c3a2e; color:#a6d189; }
  .chip { font-size:11px; border-radius:4px; padding:0 6px; border:1px solid var(--line); color:var(--dim); }
  .chip.ok { color:var(--ok); border-color:var(--ok); }
  .chip.warn { color:var(--warn); border-color:var(--warn); }
  .chip.bad, .chip.fail { color:var(--bad); border-color:var(--bad); }
  .verb-chips { display:flex; flex-wrap:wrap; gap:4px; }
  .verb-chip { font-family:Consolas,monospace; font-size:11px; background:#2b3049; color:#c6d0f5; border:none; border-radius:4px; padding:1px 7px; }
  .verb-chip.fail { background:#4a2b2b; color:#f0a8a8; }
  .verb-chip .ms { color:var(--dim); }
  details { margin-top:6px; }
  summary { cursor:pointer; color:var(--dim); font-size:12px; }
  pre { background:#17181b; border:1px solid var(--line); border-radius:6px; padding:8px 10px;
        overflow:auto; font:12px/1.5 Consolas,monospace; white-space:pre-wrap; word-break:break-all; }
  pre.err { color:#f0a8a8; }
  pre.adv { color:var(--warn); }
  .lbl { color:var(--dim); font-size:11px; margin-top:6px; }
  .dim-text { color:var(--dim); }
  .user-msg { background:#26313d; border:1px solid #33506b; border-radius:8px; padding:8px 12px; margin-bottom:8px; }
  .user-msg .t { color:#7ab8f5; }
</style></head><body>
<header>
  <h1>houdini trace 复盘报告</h1>
  <div class="meta">session: ${esc(sessionId)} ｜ 生成: ${esc(new Date().toLocaleString('zh-CN'))} ｜ 事件 ${events.length} 条</div>
</header>
<main>
  <div class="col left">
    <h2>词表目录（${usedVerbs}/${catalogVerbs} 个动词本次被使用）</h2>
    ${catalogHtml}
    ${unknownVerbs.length ? `<p class="dim-text">未收录进目录的动词调用: ${unknownVerbs.map(esc).join(', ')}（tool-design.md 需同步）</p>` : ''}
  </div>
  <div class="col">
    <h2>概览</h2>
    <div class="cards">
      <div class="card"><div class="num">${steps.length}</div><div class="cap">工具调用</div></div>
      <div class="card"><div class="num">${totalVerbCalls}</div><div class="cap">动词调用</div></div>
      <div class="card"><div class="num">${usedVerbs}/${catalogVerbs}</div><div class="cap">动词命中</div></div>
      <div class="card"><div class="num" style="color:${rawHouSteps.length ? 'var(--bad)' : 'var(--ok)'}">${rawHouSteps.length}</div><div class="cap">纯裸 hou 调用</div></div>
      <div class="card"><div class="num" style="color:${failedSteps.length ? 'var(--bad)' : 'var(--ok)'}">${failedSteps.length}</div><div class="cap">失败调用</div></div>
      <div class="card"><div class="num">${advisorySteps.length}</div><div class="cap">advisory 触发</div></div>
    </div>
    <p class="dim-text">工具分布: ${Object.entries(toolCount).map(([k, v]) => `${esc(k)} ×${v}`).join(' ｜ ')}</p>
    ${userMsgs.map((m) => `<div class="user-msg"><span class="t">${fmtTime(m.time)}</span> 👤 ${esc(m.text)}</div>`).join('')}
    <h2>调用时间线（真实顺序）</h2>
    ${timelineHtml}
    <h2>纯裸 hou 段落（词表改进输入）</h2>
    ${rawHouHtml}
    <h2>失败调用</h2>
    ${failedHtml}
  </div>
</main>
</body></html>`;

const outFile = outArg || path.join(REPO_ROOT, 'tools', 'out', `trace-${sessionId}.html`);
fs.mkdirSync(path.dirname(outFile), { recursive: true });
fs.writeFileSync(outFile, html);
console.log('session :', sessionFile);
console.log('events  :', events.length, '| steps:', steps.length, '| verbs:', totalVerbCalls, `(${usedVerbs}/${catalogVerbs})`);
console.log('report  :', outFile);
