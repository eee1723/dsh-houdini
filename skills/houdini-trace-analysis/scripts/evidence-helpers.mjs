function tryJson(text) {
  if (typeof text !== 'string') return text;
  try { return JSON.parse(text); }
  catch { return null; }
}

export function extractAvailableSkills(text) {
  if (typeof text !== 'string' || !text.includes('<available_skills>')) return [];
  return [...text.matchAll(/^- `([^`]+)`: /gm)].map((match) => match[1]);
}

export function parseLedgerArgs(value) {
  if (Array.isArray(value)) return { positional: value, kwargs: {} };
  if (value && typeof value === 'object') return { positional: [], kwargs: value };
  const text = String(value ?? '').trim();
  if (!text) return { positional: [], kwargs: {} };

  const direct = tryJson(text);
  if (Array.isArray(direct)) return { positional: direct, kwargs: {} };
  if (direct && typeof direct === 'object') return { positional: [], kwargs: direct };

  const wrapped = tryJson(`[${text}]`);
  if (Array.isArray(wrapped)) {
    const positional = Array.isArray(wrapped[0]) ? wrapped[0] : [];
    const kwargs = wrapped[1] && !Array.isArray(wrapped[1]) && typeof wrapped[1] === 'object'
      ? wrapped[1]
      : {};
    return { positional, kwargs };
  }
  return { positional: [], kwargs: {}, unparsed: text };
}

/** Parse one rendered verb-ledger line without confusing arrows inside JSON strings/results. */
export function parseVerbLedgerLine(line) {
  if (typeof line !== 'string') return null;
  const prefix = line.match(/^(\d+)\. \[(ok|FAIL)\] (\w+)\(/);
  if (!prefix) return null;
  const tail = line.match(/ \(([\d.]+)ms\)\s*$/);
  if (!tail || tail.index === undefined) return null;
  const body = line.slice(prefix[0].length, tail.index);
  let inString = false;
  let escaped = false;
  let square = 0;
  let curly = 0;
  for (let index = 0; index < body.length; index++) {
    const char = body[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === '"') inString = false;
      continue;
    }
    if (char === '"') { inString = true; continue; }
    if (char === '[') square++;
    else if (char === ']') square--;
    else if (char === '{') curly++;
    else if (char === '}') curly--;
    else if (char === ')' && square === 0 && curly === 0 && body.startsWith(') -> ', index)) {
      return {
        ledgerIndex: Number(prefix[1]),
        ok: prefix[2] === 'ok',
        verb: prefix[3],
        args: body.slice(0, index),
        result: body.slice(index + 5),
        ms: Number(tail[1]),
      };
    }
    if (square < 0 || curly < 0) return null;
  }
  return null;
}

function nodePath(value) {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && typeof value.node === 'string') return value.node;
  return null;
}

export function findBatchSetParmOpportunities(steps, threshold = 3) {
  const opportunities = [];
  for (const step of steps) {
    const batched = new Map();
    for (const verb of step.verbs || []) {
      if (verb.verb !== 'set_parms') continue;
      const { positional } = parseLedgerArgs(verb.args ?? verb.argsText);
      const node = nodePath(positional[0]);
      const values = positional[1];
      if (!node || !values || Array.isArray(values) || typeof values !== 'object') continue;
      const fields = batched.get(node) || new Set();
      for (const name of Object.keys(values)) fields.add(name);
      batched.set(node, fields);
    }

    const byNode = new Map();
    for (const verb of step.verbs || []) {
      if (verb.verb !== 'set_parm') continue;
      const { positional } = parseLedgerArgs(verb.args ?? verb.argsText);
      const node = nodePath(positional[0]);
      const parm = typeof positional[1] === 'string' ? positional[1] : null;
      if (!node || !parm || batched.get(node)?.has(parm)) continue;
      const fields = byNode.get(node) || new Set();
      fields.add(parm);
      byNode.set(node, fields);
    }

    for (const [node, fields] of byNode) {
      if (fields.size < threshold) continue;
      opportunities.push({
        index: step.index,
        time: step.time,
        node,
        count: fields.size,
        parms: [...fields].sort(),
      });
    }
  }
  return opportunities;
}

const MUTATING_METHOD = /^(?:set|add|create|delete|destroy|remove|rename|save|cook|render|bake|lock|unlock|install|copy|move|enable|disable|press)(?:$|[A-Z_])/;
const READ_ONLY_PREFIX_COLLISIONS = new Set(['displayNode', 'renderNode']);

export function isMutatingRawMethodName(name) {
  return MUTATING_METHOD.test(String(name || '')) && !READ_ONLY_PREFIX_COLLISIONS.has(name);
}

export function rawMethodNames(code) {
  const methods = [];
  for (const match of String(code || '').matchAll(/\.([A-Za-z_]\w*)\s*\(/g)) methods.push(match[1]);
  return methods;
}

export function mutatingRawMethodNames(code) {
  return rawMethodNames(code).filter(isMutatingRawMethodName);
}

const SUPPRESSED_COOK_FAILURE = /(?:^|\n)(?:[A-Z][A-Z ]{0,24} )?cook FAIL(?:ED)?(?=[:\s]|$)/i;

/**
 * Find Houdini calls whose transport envelope succeeded while agent code
 * printed that a raw cook failed.  These are semantic/artifact failures, not
 * tool transport failures, and commonly result from catching without re-raise.
 */
export function findSuppressedCookFailures(steps) {
  return steps.filter((step) => (
    step.isHoudini
    && !step.failed
    && SUPPRESSED_COOK_FAILURE.test(String(step.resultPreview || ''))
  )).map((step) => ({
    index: step.index,
    time: step.time,
    tool: step.tool,
    resultPreview: step.resultPreview,
  }));
}

export function frameFromPath(value) {
  if (typeof value !== 'string') return null;
  const match = value.match(/(?:^|[_./\\-])f(-?\d+(?:p\d+)?)(?=[_.\\/-]|$)/i);
  if (!match) return null;
  const frame = Number(match[1].replace('p', '.'));
  return Number.isFinite(frame) ? frame : null;
}

function finiteFrame(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function uniqueFrames(values) {
  return [...new Set(values.filter((value) => value !== null))].sort((a, b) => a - b);
}

function verbResult(value) {
  if (value && typeof value === 'object') return value;
  return tryJson(value) || {};
}

/** Recover the full __result__ JSON block rendered before a truncated verb ledger. */
export function execResultFromPreview(value) {
  const text = String(value ?? '');
  const marker = '__result__:';
  const markerIndex = text.indexOf(marker);
  if (markerIndex < 0) return {};
  const start = text.indexOf('{', markerIndex + marker.length);
  if (start < 0) return {};
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < text.length; index++) {
    const char = text[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === '"') inString = false;
      continue;
    }
    if (char === '"') { inString = true; continue; }
    if (char === '{') depth++;
    else if (char === '}') {
      depth--;
      if (depth === 0) return tryJson(text.slice(start, index + 1)) || {};
    }
  }
  return {};
}

function partialJsonString(value, key) {
  const pattern = new RegExp(`"${key}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`, 'g');
  const values = [];
  for (const match of String(value ?? '').matchAll(pattern)) {
    try { values.push(JSON.parse(`"${match[1]}"`)); } catch {}
  }
  return values;
}

function partialJsonArray(value, key) {
  const match = String(value ?? '').match(new RegExp(`"${key}"\\s*:\\s*(\\[[^\\]]*\\])`));
  return match ? tryJson(match[1]) : null;
}

function partialJsonNumber(value, key) {
  const match = String(value ?? '').match(new RegExp(`"${key}"\\s*:\\s*(-?[\\d.]+)`));
  return match ? Number(match[1]) : null;
}

/** Ordered unique render outputs visible anywhere in the unabridged tool result. */
export function renderOutputsFromPreview(value) {
  return [...new Set(partialJsonString(value, 'output'))];
}

const VISION_REFUSAL = [
  /无法.{0,20}(?:查看|看到|访问|读取|分析).{0,20}(?:图像|图片|图)/i,
  /模型仅接受文本输入/i,
  /图片已被省略/i,
  /(?:cannot|can't|unable to).{0,30}(?:view|see|access|inspect|analy[sz]e).{0,20}images?/i,
  /images?.{0,20}(?:omitted|not (?:available|provided|attached))/i,
];

/** Distinguish tool transport, image delivery, setup, and actual semantic inspection. */
export function classifyVisionEvidence(step) {
  const tool = String(step.tool || '');
  const semanticTools = new Set([
    'read_image', 'vision_glance', 'vision_ground', 'vision_detect',
    'vision_long_screenshot_ocr',
  ]);
  const role = tool === 'vision_present'
    ? 'presentation'
    : tool === 'vision_bootstrap'
      ? 'setup'
      : semanticTools.has(tool)
        ? 'inspection'
        : 'pixel';
  const transportOk = !step.failed;
  const text = String(step.resultPreview ?? step.resultText ?? '').trim();
  const structured = tryJson(text);
  const structuredFailure = structured && typeof structured === 'object' && structured.ok === false;
  const textualRefusal = VISION_REFUSAL.some((pattern) => pattern.test(text));
  const semanticFailure = !transportOk || Boolean(structuredFailure) || textualRefusal;
  const images = Array.isArray(step.args?.images)
    ? step.args.images
    : Array.isArray(step.args?.paths)
      ? step.args.paths
      : [step.args?.path, step.args?.file_path, step.args?.image].filter(Boolean);
  return {
    role,
    transportOk,
    semanticOk: role === 'inspection' ? !semanticFailure : null,
    // Backward-compatible summary: setup/presentation can succeed as tools,
    // but callers must require role=inspection && semanticOk for visual proof.
    ok: role === 'inspection' ? !semanticFailure : transportOk && !structuredFailure,
    reason: !transportOk
      ? 'tool_transport_failed'
      : structuredFailure
        ? String(structured.code || structured.reason || 'structured_result_ok_false')
        : textualRefusal
          ? 'textual_image_access_refusal'
          : null,
    images,
    frames: uniqueFrames(images.map(frameFromPath)),
  };
}

/** Metrics that separate vocabulary breadth from actual execution adoption. */
export function isStructuredHoudiniCall(step) {
  return step.tool==='houdini_exec' && !step.code && Boolean(step.args?.delivery || step.args?.review || step.args?.review_test)
}

export function collectVerbAdoption(steps) {
  const houdini = steps.filter((step) => step.isHoudini);
  const structured = houdini.filter(isStructuredHoudiniCall);
  const python = houdini.filter(step=>!isStructuredHoudiniCall(step));
  const withVerbs = houdini.filter((step) => (step.verbs || []).length > 0);
  const verbCalls = houdini.reduce((sum, step) => sum + (step.verbs || []).length, 0);
  const rawReadOnly = python.filter((step) => (
    !(step.verbs || []).length && !(step.mutatingRawMethods || []).length
  ));
  const exec = python.filter((step) => step.tool === 'houdini_exec');
  const successfulExec = exec.filter((step) => !step.failed);
  const successfulExecWithVerbs = successfulExec.filter((step) => (step.verbs || []).length > 0);
  const verblessRawMutation = houdini.filter((step) => (
    !(step.verbs || []).length && (step.mutatingRawMethods || []).length > 0
  ));
  const blockedRawMutation = verblessRawMutation.filter((step) => (
    step.failed && /raw-hou gate: blocked BEFORE execution/i.test(String(step.resultPreview ?? step.resultText ?? ''))
  ));
  const successfulRawMutation = verblessRawMutation.filter((step) => !step.failed);
  const pct = (part, total) => total ? Math.round((part / total) * 1000) / 10 : null;
  return {
    houdiniCalls: houdini.length,
    callsWithVerbs: withVerbs.length,
    callCoveragePct: pct(withVerbs.length, houdini.length),
    verbCalls,
    verbDensity: houdini.length ? Math.round((verbCalls / houdini.length) * 100) / 100 : 0,
    rawReadOnlyCalls: rawReadOnly.length,
    execCalls: exec.length,
    successfulExecCalls: successfulExec.length,
    successfulExecWithVerbs: successfulExecWithVerbs.length,
    successfulExecVerbCoveragePct: pct(successfulExecWithVerbs.length, successfulExec.length),
    blockedVerblessRawMutationCalls: blockedRawMutation.length,
    successfulVerblessRawMutationCalls: successfulRawMutation.length,
    ...(structured.length ? {structuredCalls:structured.length,pythonCalls:python.length,
      pythonCallCoveragePct:pct(withVerbs.length,python.length)} : {}),
  };
}

const OPEN_ENDED_QUALITY_REQUEST = /(?:程序化|细节丰富|高质量|写实|逼真|真实感|电影感|镜头级|可靠(?:的)?验证|复杂(?:资产|模型)|真实\s*solver|有效缓存|可重算|产品视觉开发|正式(?:的)?\s*(?:Karma\s*)?渲染|(?:可调|可以调节|参数化).{0,16}(?:效果|模拟|系统)|procedural|high[- ]?quality|detail(?:ed| rich)|realistic|cinematic|shot[- ]?quality|reliable (?:verification|validation)|real solver|valid cache|recomputable|product lookdev|final Karma render|(?:adjustable|configurable|parameterized).{0,16}(?:effect|simulation|system))/i;
const EXTERNAL_TRUTH_SIGNAL = /(?:(?:符合|属于|处于|均在).{0,40}(?:真实|现实|行业|规格|标准|范围)|(?:典型|真实|行业|标准).{0,40}(?:标定|尺寸|规格|比例|范围|标准)|(?:real[- ]?world|industry|spec(?:ification)?|physically accurate).{0,40}(?:dimension|proportion|range|standard|accurate))/i;
const ASSUMPTION_BOUNDARY = /(?:无外部参考|没有外部参考|基于假设|假设值|(?:值|比例|尺寸|数值|典型值).{0,16}假设|非已核实规格|未验证|内部一致|风格化|用户授权|用户选择|no external reference|assum(?:e|ed|ption)|unverified|stylized)/i;
const UNVERIFIED_MARKER = /(?:unverified|未验证|无法验证|待验证)/i;
const COMPLETION_MARKER = /(?:^|[\s：:。])(?:完成|已完成|交付|complete(?:d)?|delivered)(?:[\s：:。]|$)/i;
const REQUESTED_GOAL_SIGNALS = [
  ['cinematic', /(?:电影感|cinematic)/i],
  ['quality', /(?:高质量|镜头级|产品级|high[- ]?quality|shot[- ]?quality|production[- ]?quality)/i],
  ['realism', /(?:写实|逼真|真实感|realistic|photoreal)/i],
  ['adjustability', /(?:可调|可以调节|参数化|adjustable|configurable|parameterized)/i],
  ['animation', /(?:动画|动态|animation|motion)/i],
  ['simulation', /(?:模拟|仿真|simulation)/i],
  ['rendering', /(?:渲染|render(?:ing)?)/i],
  ['verification', /(?:可靠(?:的)?验证|可靠(?:的)?验收|reliable (?:verification|validation))/i],
];
const MUTATING_VERBS = new Set([
  'scene_save', 'scene_save_as', 'tab_create', 'tab_apply', 'connect', 'set_object_parent', 'disconnect_input', 'rename_node', 'delete_node', 'set_parm', 'set_parms',
  'set_keyframes', 'create_spare_parms', 'set_timeline', 'create_bookmark', 'delete_bookmark',
  'hda_create', 'hda_set_section', 'hda_patch_section', 'hda_set_interface', 'sop_set_output',
  'set_object_visible', 'set_display', 'layout_nodes',
]);
const QUERY_SIDE_EFFECT_VERBS = new Set([
  ...MUTATING_VERBS,
  'cook_node', 'verify_network', 'build_module', 'test_controls', 'render_frame', 'render_view', 'viewport_screenshot',
]);
const VALIDATION_VERBS = new Set([
  'cook_node', 'describe', 'geo_piece_stats', 'geo_attrib_stats', 'geo_frame_diff', 'render_view',
  'render_frame', 'render_check', 'verify_network', 'geo_point_spacing', 'geo_check_interfaces', 'test_controls',
]);
const RELATION_PATTERN = /(?:coincident|共轴|轴线|anchor(?:ed)? endpoint|锚点|端点|distance|距离|clearance|间隙|intersection|相交|穿插|contact|接触|contain(?:ed)?|包含|insert(?:ed)?|插入|tangent|切线|deviation|偏差)/ig;

export function findQueryMutationSteps(steps) {
  return (steps || []).filter((step) => (
    step.tool === 'houdini_query'
    && (
      (step.mutatingRawMethods || []).length > 0
      || (step.verbs || []).some((verb) => QUERY_SIDE_EFFECT_VERBS.has(verb.verb))
    )
  )).map((step) => ({
    index: step.index,
    time: step.time,
    tool: step.tool,
    codePreview: step.codePreview,
    mutatingRawMethods: step.mutatingRawMethods || [],
    mutatingVerbs: [...new Set(
      (step.verbs || []).map((verb) => verb.verb).filter((name) => QUERY_SIDE_EFFECT_VERBS.has(name)),
    )],
  }));
}

function messageText(messages) {
  return (messages || []).map((message) => String(message?.text || '')).filter(Boolean).join('\n');
}

function stepIndex(step, fallback) {
  return Number.isFinite(step?.index) ? step.index : fallback;
}

function sceneMutation(step) {
  if (step.failed) return false;
  if ((step.verbs || []).some((verb) => verb.verb === 'build_module' && parseLedgerArgs(verb.args ?? verb.argsText).kwargs.dry_run !== true)) return true;
  if ((step.verbs || []).some((verb) => MUTATING_VERBS.has(verb.verb))) return true;
  return (step.mutatingRawMethods || []).some((name) => !['save', 'render'].includes(String(name)));
}

function stableValue(value) {
  try { return JSON.stringify(value); }
  catch { return String(value); }
}

function isObjectRoot(node) {
  return typeof node === 'string' && /^\/obj\/[^/]+$/.test(node);
}

function specDefaults(spec, target = {}) {
  for (const item of Array.isArray(spec) ? spec : []) {
    if (!item || typeof item !== 'object') continue;
    if (item.type === 'folder') specDefaults(item.parms, target);
    else if (typeof item.name === 'string' && Object.hasOwn(item, 'default')) {
      target[item.name] = item.default;
    }
  }
  return target;
}

function setParmEvents(steps) {
  const events = new Map();
  const controlNodes = new Set();
  for (const step of steps) {
    if (step.failed) continue;
    for (const verb of step.verbs || []) {
      if (verb.verb !== 'create_spare_parms') continue;
      const { positional } = parseLedgerArgs(verb.args ?? verb.argsText);
      const node = nodePath(positional[0]);
      if (node) controlNodes.add(node);
    }
  }
  for (let offset = 0; offset < steps.length; offset++) {
    const step = steps[offset];
    const index = stepIndex(step, offset + 1);
    if (step.failed) continue;
    for (const verb of step.verbs || []) {
      if (verb.ok === false) continue;
      const { positional, kwargs } = parseLedgerArgs(verb.args ?? verb.argsText);
      const node = nodePath(positional[0]);
      if (!node || (!isObjectRoot(node) && !controlNodes.has(node))) continue;
      if (verb.verb === 'create_spare_parms') {
        const result = verbResult(verb.result ?? verb.detail);
        const values = result.leaf_values || specDefaults(kwargs.spec);
        if (!values || Array.isArray(values) || typeof values !== 'object') continue;
        for (const [parm, value] of Object.entries(values)) {
          const key = `${node}\u0000${parm}`;
          const list = events.get(key) || [];
          list.push({ index, node, parm, value, stable: stableValue(value), source: 'default' });
          events.set(key, list);
        }
        continue;
      }
      if (!['set_parm', 'set_parms'].includes(verb.verb)) continue;
      const values = verb.verb === 'set_parm'
        ? { [positional[1]]: positional[2] }
        : positional[1];
      if (!values || Array.isArray(values) || typeof values !== 'object') continue;
      for (const [parm, value] of Object.entries(values)) {
        if (!parm || parm === 'undefined') continue;
        const result = verbResult(verb.result ?? verb.detail);
        if (result.failed && Object.hasOwn(result.failed, parm)) continue;
        const key = `${node}\u0000${parm}`;
        const list = events.get(key) || [];
        list.push({ index, node, parm, value, stable: stableValue(value) });
        events.set(key, list);
      }
    }
  }
  return events;
}

function restoredPerturbations(steps) {
  const validations = steps.map((step, offset) => ({
    index: stepIndex(step, offset + 1),
    valid: !step.failed && (
      step.tool === 'houdini_query'
      || (step.verbs || []).some((verb) => VALIDATION_VERBS.has(verb.verb))
    ),
  })).filter((item) => item.valid).map((item) => item.index);
  const restored = [];
  for (const list of setParmEvents(steps).values()) {
    if (list.length < 3 || list[0].stable !== list.at(-1).stable) continue;
    const changed = list.slice(1, -1).find((item) => item.stable !== list[0].stable);
    if (!changed) continue;
    const restore = list.at(-1);
    const validationSteps = validations.filter((index) => index >= changed.index && index <= restore.index);
    if (!validationSteps.length) continue;
    restored.push({
      node: list[0].node,
      parm: list[0].parm,
      original: list[0].value,
      changed: changed.value,
      restored: restore.value,
      setSteps: list.map((item) => item.index),
      validationSteps,
    });
  }
  return restored;
}

function latestGeometryCounts(steps, fromIndex) {
  let latest = null;
  const patterns = [
    /(?:"?points"?|pts|点)\s*[:=]?\s*([\d,]+)[\s,;/|，／]*(?:"?prims"?|primitives?|面)\s*[:=]?\s*([\d,]+)/ig,
    /([\d,]+)\s*(?:点|points?)\s*(?:\/|／|,|，|和|and)\s*([\d,]+)\s*(?:面|prim(?:s|itives?)?)/ig,
  ];
  for (let offset = 0; offset < steps.length; offset++) {
    const step = steps[offset];
    const index = stepIndex(step, offset + 1);
    if (index < fromIndex || step.failed) continue;
    const text = String(step.resultText ?? step.resultPreview ?? '');
    for (const pattern of patterns) {
      for (const match of text.matchAll(pattern)) {
        latest = {
          index,
          points: Number(match[1].replaceAll(',', '')),
          prims: Number(match[2].replaceAll(',', '')),
        };
      }
    }
  }
  return latest;
}

function finalGeometryCountClaim(assistantMessages) {
  const final = String(assistantMessages?.at(-1)?.text || '');
  const matches = [...final.matchAll(/([\d,]+)\s*(?:点|points?)\s*(?:\/|／|,|，|和|and)\s*([\d,]+)\s*(?:面|prim(?:s|itives?)?)/ig)];
  if (!matches.length) return null;
  const match = matches.at(-1);
  return {
    points: Number(match[1].replaceAll(',', '')),
    prims: Number(match[2].replaceAll(',', '')),
  };
}

/**
 * Deterministic evidence for the open-ended quality loop (HTA-023 family).
 * It reports observable gates; it does not pretend regexes can judge artistic quality.
 */
export function collectQualityLoopEvidence({
  steps = [], userMessages = [], assistantMessages = [], availableTools = [], activatedSkills = [],
} = {}) {
  const request = messageText(userMessages);
  const assistant = messageText(assistantMessages);
  const applicable = OPEN_ENDED_QUALITY_REQUEST.test(request);
  const indexed = steps.map((step, offset) => ({ ...step, code: step.code, resultText: step.resultText,
    index: stepIndex(step, offset + 1) }));
  const firstMutation = indexed.find(sceneMutation) || null;
  const firstMutationTime = firstMutation?.time ?? Infinity;
  const confirmedChoiceText = indexed.filter(step => step.tool === 'ask_user_question'
    && !step.failed && (!firstMutation || step.index < firstMutation.index)).flatMap(step => {
    const result = tryJson(String(step.resultText ?? step.resultPreview ?? ''));
    return (Array.isArray(result?.answers) ? result.answers : []).flatMap(answer => {
      const question = step.args?.questions?.find(q => q.id === answer.id);
      const selected = Array.isArray(answer.selected) ? answer.selected : [];
      if (!selected.length) return [];
      return selected.map(label => {
        const option = question?.options?.find(o => o.label === label);
        return `${question?.header ?? ''}: ${label} ${option?.description ?? ''}`;
      });
    });
  });
  const preMutationText = [
    ...confirmedChoiceText,
    messageText(
      assistantMessages.filter((message) => !Number.isFinite(message.time) || message.time <= firstMutationTime),
    ),
    ...indexed.filter((step) => (
      (!firstMutation || step.index < firstMutation.index)
      && ['create_goal', 'todo_write'].includes(String(step.tool || ''))
    )).map((step) => JSON.stringify(step.args || {})),
  ].filter(Boolean).join('\n');
  const contractFields = {
    target: /(?:目标|对象|效果|target|deliverable|交付)/i.test(preMutationText),
    referenceStatus: /(?:参考|来源|无外部参考|假设|reference|source)/i.test(preMutationText),
    qualityLod: /(?:质量(?:标准|门|级别)|LOD|轮廓级|镜头级|产品级|预览级|观察距离|quality bar|quality level)/i.test(preMutationText),
    simplifications: /(?:简化|省略|不做|允许.*(?:略|省)|边界|simplif|omit|out of scope)/i.test(preMutationText),
    unitsDimensions: /(?:单位|尺寸|范围|半径|长度|角度|米|厘米|mm|cm|\bm\b|units?|dimensions?)/i.test(preMutationText),
    controls: /(?:控制参数|可调参数|需要暴露|spare parm|HDA interface|controls?)/i.test(preMutationText),
    relations: /(?:连接|共轴|轴线|端点|包含|间隙|穿插|接触|关系|relations?|clearance|intersection)/i.test(preMutationText),
    evidencePlan: /(?:验证|验收|证据|视角|特写|render|evidence|check)/i.test(preMutationText),
  };
  const requiresControls = /(?:程序化|可调|可以调节|参数化|procedural|adjustable|configurable|parameterized)/i.test(request);
  const requiresRelations = /(?:连接|装配|机械|结构|穿插|间隙|自行车|汽车|车辆|产品|建筑|角色|assembly|mechanical|structur|intersection|clearance)/i.test(request);
  const requiredContractFields = [
    'referenceStatus', 'qualityLod', 'simplifications',
    ...(requiresControls ? ['controls'] : []),
    ...(requiresRelations ? ['relations'] : []),
    'evidencePlan',
  ];
  const missingContractFields = requiredContractFields.filter((name) => !contractFields[name]);

  const researchSteps = indexed.filter((step) => /(?:web_search|browser|research)/i.test(String(step.tool || '')))
    .map((step) => step.index);
  const userProvidedReference = /(?:https?:\/\/|参考(?:图|文件|链接|如下)|规格表|用户提供|attached reference|reference (?:image|file|link))/i.test(request);
  const userAuthorizedNoResearch = /(?:不要|无需|不需要|不用).{0,12}(?:外部)?参考|(?:风格化|抽象).{0,12}(?:即可|就行)|(?:比例|尺寸|造型).{0,12}(?:你决定|自行决定)|no (?:external )?reference|do not research/i.test(request);
  const qualityContractLoadSteps = indexed.filter((step) => (
    /#\s*程序化 SOP 质量合同/i.test(String(step.resultText ?? step.resultPreview ?? ''))
    || /#\s*Procedural SOP Quality Contract/i.test(String(step.resultText ?? step.resultPreview ?? ''))
  )).map((step) => step.index);
  const externalTruthClaims = (assistantMessages || []).filter((message) => EXTERNAL_TRUTH_SIGNAL.test(String(message.text || '')));
  const unsupportedExternalTruthClaims = externalTruthClaims.filter(
    (message) => !ASSUMPTION_BOUNDARY.test(String(message.text || '')),
  ).map((message) => ({ time: message.time, text: String(message.text || '').slice(0, 500) }));
  const assumptionBoundaryDisclosed = ASSUMPTION_BOUNDARY.test(preMutationText) || ASSUMPTION_BOUNDARY.test(assistant);

  const firstRender = indexed.find((step) => (
    !step.failed && (step.verbs || []).some((verb) => ['render_view', 'render_frame'].includes(verb.verb))
  )) || null;
  const tabCreatesBeforeFirstRender = indexed
    .filter((step) => !firstRender || step.index < firstRender.index)
    .reduce((sum, step) => sum + (step.verbs || []).filter((verb) => verb.verb === 'tab_create' && verb.ok !== false).length, 0);
  const skeletonCheckpointMentions = (assistantMessages || []).filter((message) => {
    const text = String(message.text || '');
    return /(?:骨架|中心线|代理体|anchors?).{0,60}(?:验证|验收|通过|成功|check|validate)/i.test(text)
      || /(?:验证|验收|通过|成功|check|validate).{0,60}(?:骨架|中心线|代理体|anchors?)/i.test(text);
  }).map((message) => ({ time: message.time, text: String(message.text || '').slice(0, 300) }));
  if (firstRender) {
    for (const verb of firstRender.verbs || []) {
      if (verb.verb !== 'render_view' || verb.ok === false) continue;
      const target = nodePath(parseLedgerArgs(verb.args ?? verb.argsText).positional[0]);
      if (target && /(?:skeleton|proxy|blockout|anchors?|骨架|代理)/i.test(target)) {
        skeletonCheckpointMentions.push({time: firstRender.time, index: firstRender.index,
          text: `Explicit skeleton/proxy render target: ${target}`, source: 'render_target'});
      }
    }
  }

  const relationshipProbeSteps = [];
  const relationshipKeywords = new Set();
  for (const step of indexed) {
    if (!step.failed && (step.verbs || []).some(v => v.verb === 'geo_check_interfaces'
        || (v.verb === 'build_module' && verbResult(v.result ?? v.detail).interface_checks))) {
      relationshipProbeSteps.push(step.index);
      relationshipKeywords.add('declared_final_surface_interfaces');
    }
    const code = String(step.code || '');
    const hits = [...code.matchAll(RELATION_PATTERN)].map((match) => match[0].toLowerCase());
    if (!hits.length || step.failed) continue;
    // Mixed edit+measurement is legitimate. A mere relationship comment in
    // construction code is not a probe; require geometry access and output.
    if (sceneMutation(step) && !(/geometry\(|boundingBox\(|attribValue\(|\.position\(/.test(code)
        && /print\(|__result__\s*=/.test(code))) continue;
    relationshipProbeSteps.push(step.index);
    for (const hit of hits) relationshipKeywords.add(hit);
  }

  const perturbations = restoredPerturbations(indexed);
  const controlTests = indexed.flatMap(step => (step.verbs || []).filter(v => v.verb === 'test_controls')
    .map(v => ({index:step.index, ...verbResult(v.result ?? v.detail)})));
  for(const step of indexed.filter(s=>s.args?.review_test && !s.failed)) {
    const result=execResultFromPreview(step.resultText || step.resultPreview || '');
    if(result?.cases?.length)controlTests.push({index:step.index,...result,results:result.cases,
      executed:result.cases.some(c=>c.actual_values && c.restored===true)});
  }
  const lastMutation = [...indexed].reverse().find(sceneMutation) || null;
  const latestCounts = latestGeometryCounts(indexed, lastMutation?.index ?? 0);
  const finalCountClaim = finalGeometryCountClaim(assistantMessages);
  const finalCountMatchesEvidence = !finalCountClaim || !latestCounts
    ? null
    : finalCountClaim.points === latestCounts.points && finalCountClaim.prims === latestCounts.prims;
  const checkpoints = new Map();
  for (const step of indexed) {
    for (const verb of step.verbs || []) {
      if (!['verify_network','build_module'].includes(verb.verb)) continue;
      const raw = verbResult(verb.result ?? verb.detail);
      const r = raw.validation || raw;
      if (typeof r.output !== 'string' || typeof r.ok !== 'boolean') continue;
      // A successful check in a different scope cannot erase a failed one.
      const key = JSON.stringify([r.output, r.scope, r.scope_signature ?? r.checked_nodes ?? null]);
      checkpoints.set(key, {index: step.index, output:r.output, scope:r.scope ?? null,
        ok:r.ok, reasons:r.failure_reasons ?? (r.nonempty === false ? ['empty_output'] : [])});
    }
  }

  return {
    applicable,
    outputCheckpoints: [...checkpoints.values()],
    requestSignals: [...new Set(request.match(OPEN_ENDED_QUALITY_REQUEST) || [])],
    available: {
      webSearch: availableTools.some((name) => /web_search|browser/i.test(String(name))),
      tools: [...new Set(availableTools)].sort(),
    },
    contract: {
      firstMutationIndex: firstMutation?.index ?? null,
      requirements: { controls: requiresControls, relations: requiresRelations },
      fields: contractFields,
      missing: missingContractFields,
    },
    reference: {
      researchSteps,
      userProvidedReference,
      userAuthorizedNoResearch,
      qualityContractRequired: applicable && activatedSkills.includes('houdini-sop-workflow'),
      qualityContractLoadSteps,
      externalTruthClaimCount: externalTruthClaims.length,
      unsupportedExternalTruthClaims,
      assumptionBoundaryDisclosed,
    },
    skeleton: {
      firstRenderIndex: firstRender?.index ?? null,
      tabCreatesBeforeFirstRender,
      checkpointMentions: skeletonCheckpointMentions,
    },
    relations: {
      probeSteps: [...new Set(relationshipProbeSteps)],
      keywords: [...relationshipKeywords].sort(),
    },
    perturbation: {
      restored: perturbations,
      controlTests,
    },
    freshness: {
      lastMutationIndex: lastMutation?.index ?? null,
      latestGeometryCounts: latestCounts,
      finalGeometryCountClaim: finalCountClaim,
      finalCountMatchesEvidence,
    },
  };
}

/**
 * Find user-requested quality dimensions that the final delivery itself leaves
 * unverified while also presenting the task as complete. This is an audit risk,
 * not an automatic artistic-quality verdict.
 */
export function requestedGoalReportedUnverified(userMessages = [], assistantMessages = []) {
  const request = messageText(userMessages);
  const final = String(assistantMessages?.at(-1)?.text || '');
  if (!COMPLETION_MARKER.test(final)) return [];
  const unverifiedLines = final.split(/\r?\n/).filter((line) => UNVERIFIED_MARKER.test(line));
  if (!unverifiedLines.length) return [];
  return REQUESTED_GOAL_SIGNALS.flatMap(([signal, pattern]) => {
    if (!pattern.test(request)) return [];
    const line = unverifiedLines.find((candidate) => pattern.test(candidate));
    return line ? [{ signal, line: line.trim().slice(0, 500) }] : [];
  });
}

export function qualityLoopRisks(evidence) {
  const risks = [];
  if (!evidence) return risks;
  if (evidence.applicable && evidence.contract.missing.length) {
    risks.push({
      code: 'quality_contract_incomplete',
      detail: `Open-ended quality contract is missing: ${evidence.contract.missing.join(', ')}.`,
    });
  }
  if (evidence.reference.qualityContractRequired && !evidence.reference.qualityContractLoadSteps.length) {
    risks.push({
      code: 'quality_contract_reference_not_loaded',
      detail: 'houdini-sop-workflow was active for an open-ended quality task, but its procedural quality contract was not loaded.',
    });
  }
  if (evidence.available.webSearch
      && evidence.reference.externalTruthClaimCount
      && !evidence.reference.userProvidedReference
      && !evidence.reference.userAuthorizedNoResearch
      && !evidence.reference.researchSteps.length) {
    risks.push({
      code: 'external_reference_available_but_unused',
      detail: 'External-truth language was used while web/research capability was available, but no research call was recorded.',
    });
  }
  if (evidence.reference.unsupportedExternalTruthClaims.length) {
    risks.push({
      code: 'external_truth_without_source',
      detail: `${evidence.reference.unsupportedExternalTruthClaims.length} external-truth claim(s) lack a source or an assumption boundary.`,
    });
  }
  if (evidence.applicable
      && evidence.skeleton.firstRenderIndex
      && evidence.skeleton.tabCreatesBeforeFirstRender >= 20
      && !evidence.skeleton.checkpointMentions.length) {
    risks.push({
      code: 'late_first_visual_validation',
      detail: `${evidence.skeleton.tabCreatesBeforeFirstRender} nodes were created before the first render without an explicit skeleton/proxy checkpoint.`,
    });
  }
  if (evidence.applicable && evidence.contract.fields.controls && !evidence.perturbation.restored.length
      && !(evidence.perturbation.controlTests || []).some(t => (t.ok === true || t.executed === true) && t.restored === true && t.results?.length)) {
    risks.push({
      code: 'procedural_control_not_perturbed',
      detail: 'The task promised configurable controls, but no set → validate → restore perturbation was observed on a declared user-control node.',
    });
  }
  if (evidence.applicable && evidence.contract.fields.relations && !evidence.relations.probeSteps.length) {
    risks.push({
      code: 'relationship_contract_without_evidence',
      detail: 'The pre-mutation contract promised module relationships, but no relationship-oriented probe was observed.',
    });
  }
  if (evidence.freshness.finalCountMatchesEvidence === false) {
    risks.push({
      code: 'stale_final_geometry_counts',
      detail: 'The final points/prims claim does not match the latest post-mutation geometry evidence.',
      claim: evidence.freshness.finalGeometryCountClaim,
      evidence: evidence.freshness.latestGeometryCounts,
    });
  }
  const unresolved = (evidence.outputCheckpoints || []).filter(c => !c.ok);
  if (unresolved.length) risks.push({code:'unresolved_output_checkpoints',
    detail:'Output checkpoints failed without a later successful check of the same output/scope. Diagnostic probes may be intentional; review against the deliverable contract.',
    checkpoints:unresolved});
  return risks;
}

export function completedVisionTodoWithoutEvidence(latestTodo, successfulVisionEvidence = []) {
  if ((successfulVisionEvidence || []).length > 0) return false;
  return Boolean((latestTodo || []).some((item) => {
    const content = String(item?.content || '');
    return item?.status === 'completed'
      && /(?:vision|视觉|图像检查|图片检查)/i.test(content)
      && !/(?:unverified|未验证|无法|失败|不可用|凭据|待用户|人工确认|交给用户)/i.test(content);
  }));
}

export function collectValidationCoverage(steps) {
  const geometry = [];
  const renders = [];
  const comparisons = [];
  const vision = [];

  for (const step of steps) {
    const fullResult = step.resultText ?? step.resultPreview;
    const execResult = execResultFromPreview(fullResult);
    const renderOutputs = renderOutputsFromPreview(fullResult);
    let renderOutputIndex = 0;
    for (const verb of step.verbs || []) {
      const { positional, kwargs } = parseLedgerArgs(verb.args ?? verb.argsText);
      const ledgerResult = verbResult(verb.result ?? verb.detail);
      const result = Object.keys(ledgerResult).length ? ledgerResult : execResult;
      if (verb.verb === 'geo_frame_diff') {
        const frameA = finiteFrame(positional[1]);
        const frameB = finiteFrame(positional[2]);
        geometry.push({
          index: step.index,
          time: step.time,
          node: nodePath(positional[0]),
          attrib: kwargs.attrib ?? positional[3] ?? 'P',
          frame_a: frameA,
          frame_b: frameB,
          frames: uniqueFrames([frameA, frameB]),
          ok: verb.ok,
        });
      } else if (verb.verb === 'render_view' || verb.verb === 'render_frame') {
        const frame = finiteFrame(kwargs.frame ?? result.frame);
        const framingFrame = finiteFrame(kwargs.framing_frame ?? result?.framing?.frame);
        const output = result.output ?? result.image ?? kwargs.picture
          ?? renderOutputs[renderOutputIndex] ?? null;
        renderOutputIndex++;
        renders.push({
          index: step.index,
          time: step.time,
          verb: verb.verb,
          target: nodePath(positional[0]),
          frame: frame ?? frameFromPath(output),
          framing_frame: framingFrame,
          output,
          ok: verb.ok,
        });
      } else if (verb.verb === 'render_check') {
        const partial = verb.result ?? verb.detail;
        const imagePath = positional[0] ?? result.path ?? null;
        const ref = kwargs.ref ?? null;
        const contentBbox = result.content_bbox ?? result.contentBbox
          ?? partialJsonArray(partial, 'content_bbox') ?? null;
        const width = result.width ?? partialJsonNumber(partial, 'width');
        const height = result.height ?? partialJsonNumber(partial, 'height');
        const imageSize = result.size ?? result.image_size
          ?? (width !== null && height !== null ? [width, height] : null);
        const touchesEdge = Array.isArray(contentBbox) && contentBbox.length === 4
          && Array.isArray(imageSize) && imageSize.length >= 2
          ? contentBbox[0] <= 0 || contentBbox[1] <= 0
            || contentBbox[2] >= Number(imageSize[0]) - 1
            || contentBbox[3] >= Number(imageSize[1]) - 1
          : null;
        comparisons.push({
          index: step.index,
          time: step.time,
          path: imagePath,
          ref,
          content_bbox: contentBbox,
          image_size: imageSize,
          touches_edge: touchesEdge,
          frames: uniqueFrames([frameFromPath(imagePath), frameFromPath(ref)]),
          ok: verb.ok,
        });
      }
    }

    if (String(step.tool || '').startsWith('vision_') || step.tool === 'read_image') {
      const outcome = classifyVisionEvidence(step);
      vision.push({
        index: step.index,
        time: step.time,
        tool: step.tool,
        ...outcome,
      });
    }
  }

  const geometryFrames = uniqueFrames(geometry.flatMap((item) => item.frames));
  const renderFrames = uniqueFrames(renders.map((item) => item.frame));
  const framingFrames = uniqueFrames(renders.map((item) => item.framing_frame));
  const comparisonFrames = uniqueFrames(comparisons.flatMap((item) => item.frames));
  const visionFrames = uniqueFrames(vision.flatMap((item) => item.frames));
  const visionInspectionFrames = uniqueFrames(
    vision.filter((item) => item.role === 'inspection').flatMap((item) => item.frames),
  );
  return {
    geometry,
    renders,
    comparisons,
    vision,
    frames: {
      geometry: geometryFrames,
      render: renderFrames,
      framing: framingFrames,
      comparison: comparisonFrames,
      vision: visionFrames,
      visionInspection: visionInspectionFrames,
      all: uniqueFrames([
        ...geometryFrames,
        ...renderFrames,
        ...comparisonFrames,
        ...visionFrames,
      ]),
    },
  };
}
