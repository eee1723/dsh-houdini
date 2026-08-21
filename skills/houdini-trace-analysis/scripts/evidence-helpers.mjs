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

export function collectValidationCoverage(steps) {
  const geometry = [];
  const renders = [];
  const comparisons = [];
  const vision = [];

  for (const step of steps) {
    for (const verb of step.verbs || []) {
      const { positional, kwargs } = parseLedgerArgs(verb.args ?? verb.argsText);
      const result = verbResult(verb.result ?? verb.detail);
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
        const output = result.output ?? result.image ?? kwargs.picture ?? null;
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
        const imagePath = positional[0] ?? result.path ?? null;
        const ref = kwargs.ref ?? null;
        comparisons.push({
          index: step.index,
          time: step.time,
          path: imagePath,
          ref,
          frames: uniqueFrames([frameFromPath(imagePath), frameFromPath(ref)]),
          ok: verb.ok,
        });
      }
    }

    if (String(step.tool || '').startsWith('vision_')) {
      const images = Array.isArray(step.args?.images) ? step.args.images : [];
      vision.push({
        index: step.index,
        time: step.time,
        tool: step.tool,
        images,
        frames: uniqueFrames(images.map(frameFromPath)),
      });
    }
  }

  const geometryFrames = uniqueFrames(geometry.flatMap((item) => item.frames));
  const renderFrames = uniqueFrames(renders.map((item) => item.frame));
  const framingFrames = uniqueFrames(renders.map((item) => item.framing_frame));
  const comparisonFrames = uniqueFrames(comparisons.flatMap((item) => item.frames));
  const visionFrames = uniqueFrames(vision.flatMap((item) => item.frames));
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
      all: uniqueFrames([
        ...geometryFrames,
        ...renderFrames,
        ...comparisonFrames,
        ...visionFrames,
      ]),
    },
  };
}
