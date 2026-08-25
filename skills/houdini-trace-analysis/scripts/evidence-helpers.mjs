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

export function rawMethodNames(code) {
  const methods = [];
  for (const match of String(code || '').matchAll(/\.([A-Za-z_]\w*)\s*\(/g)) methods.push(match[1]);
  return methods;
}

export function mutatingRawMethodNames(code) {
  return rawMethodNames(code).filter(
    (name) => MUTATING_METHOD.test(name) && !READ_ONLY_PREFIX_COLLISIONS.has(name),
  );
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
  const role = tool === 'vision_present'
    ? 'presentation'
    : tool === 'vision_bootstrap'
      ? 'setup'
      : 'inspection';
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
      : [step.args?.path, step.args?.image].filter(Boolean);
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
export function collectVerbAdoption(steps) {
  const houdini = steps.filter((step) => step.isHoudini);
  const withVerbs = houdini.filter((step) => (step.verbs || []).length > 0);
  const verbCalls = houdini.reduce((sum, step) => sum + (step.verbs || []).length, 0);
  const rawReadOnly = houdini.filter((step) => (
    !(step.verbs || []).length && !(step.mutatingRawMethods || []).length
  ));
  const exec = houdini.filter((step) => step.tool === 'houdini_exec');
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
  };
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
