import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';


const source = await readFile(new URL('../../client.js', import.meta.url), 'utf8');
const packageManifest = JSON.parse(await readFile(new URL('../../package.json', import.meta.url), 'utf8'));
assert(packageManifest.dsh.client.inject.includes('@deepseek-ai/dsh-client-ui-trajectory'));


async function run(href) {
  let registration;
  const opened = [];
  const replaced = [];
  const injected = [];
  const registrations = {};
  const sessions = {
    refresh: async () => {},
    open: (id) => { opened.push(id); },
  };
  const slots = {
    inject: (_name, install) => { install(); },
    register: (options, component) => {
      registrations[options.id] = { options, component };
      return () => {};
    },
  };
  const window = {
    location: { href },
    history: {
      state: { retained: true },
      replaceState: (state, title, url) => { replaced.push({ state, title, url }); },
    },
    __ModuleLoader__: {
      load: (value) => { registration = value; },
    },
  };
  const context = vm.createContext({
    URL,
    console,
    document: {
      querySelector: () => ({}),
      createElement: () => ({ dataset: {} }),
      head: { appendChild: () => {} },
    },
    window,
  });
  vm.runInContext(source, context, { filename: 'client.js' });
  assert.equal(registration.id, 'dsh-houdini');
  const plugin = registration.factory((name) => {
    if (name === 'react') {
      return {
        createElement: (type, props, ...children) => ({ type, props: props ?? {}, children }),
        useState: value => [value, () => {}],
        useMemo: fn => fn(),
        useEffect: () => {},
        useRef: value => ({ current: value }),
      };
    }
    throw new Error(`unexpected client dependency: ${name}`);
  });
  plugin.apply({
    get: (name) => name === 'slots' ? slots : undefined,
    inject: (deps, callback) => {
      injected.push([...deps]);
      callback({ get: (name) => name === 'sessions' ? sessions : undefined });
    },
  });
  await Promise.resolve();
  await Promise.resolve();
  return { opened, replaced, injected, registrations };
}


const hinted = await run(
  'http://127.0.0.1:3081/?dsh-houdini-session=session-target&retained=yes#conversation',
);
assert.deepEqual(hinted.injected, [['sessions']]);
assert.deepEqual(hinted.opened, ['session-target']);
assert.deepEqual(hinted.replaced, [{
  state: { retained: true },
  title: '',
  url: '/?retained=yes#conversation',
}]);

const plain = await run('http://127.0.0.1:3081/');
assert.deepEqual(plain.injected, []);
assert.deepEqual(plain.opened, []);
assert.deepEqual(plain.replaced, []);
const watermark = plain.registrations['houdini-watermark'].component;
assert(watermark({sessionId:'s',useSessions:fn=>fn({byId:{s:{projectionValues:{agentPreset:'houdini'}}}})}),
  'DSH 0.1.2 projected preset must show Houdini mode');
assert.equal(watermark({sessionId:'s',useSessions:fn=>fn({byId:{s:{agentPreset:'houdini',projectionValues:{agentPreset:'cordis'}}}})}),null,
  'current projected preset must override legacy stored value');

const view = plain.registrations.houdinitrace.component;
const ledgerLine = '1. [ok] verb_help(["set_keyframes"]) -> '
  + '{"name":"set_keyframes","signature":"(node, channels) -> dict"} (0ms)';
const tree = view({
  useTrajectory: (select) => select({
    eventNodes: [{
      kind: 'tool-result',
      seq: 4,
      time: 100,
      call: { name: 'houdini_query', argsRaw: '{}' },
      content: [{ type: 'text', text: `Executed successfully.\n\nverbs (1):\n${ledgerLine}` }],
    }],
  }),
});
const titles = [];
const visit = (node) => {
  if (node === null || node === undefined || typeof node !== 'object') return;
  if (typeof node.props?.title === 'string') titles.push(node.props.title);
  for (const child of node.children ?? []) {
    if (Array.isArray(child)) child.forEach(visit);
    else visit(child);
  }
};
visit(tree);
assert(titles.includes(
  '["set_keyframes"] -> {"name":"set_keyframes","signature":"(node, channels) -> dict"}',
));

function textContent(node) {
  if (node === null || node === undefined) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textContent).join(' ');
  if (typeof node !== 'object') return '';
  return (node.children ?? []).map(textContent).join(' ');
}

const mixedRawUsage = {
  directCalls: [{ name: 'hou.node', count: 1 }],
  coveredMutations: [],
  suspectedMutations: [],
  gateOutcome: 'read_only',
};
const blockedRawUsage = {
  directCalls: [{ name: 'hou.hipFile.save', count: 1 }],
  coveredMutations: [],
  suspectedMutations: [{ name: 'save', count: 1 }],
  gateOutcome: 'blocked',
};
const traceProps = {
  useSession: (select) => select({
    views: new Map([['trajectory', { eventNodes: [
      {
        kind: 'tool-result', seq: 10, time: 1000,
        call: { name: 'houdini_exec', argsRaw: JSON.stringify({ code: "n = hou.node('/obj')\n__result__ = scene_info()" }) },
        content: [{ type: 'text', text: [
          'Executed successfully.',
          'stdout:\n[verb] scene_info([]) -> {} (0ms)\ninspection complete',
          '__result__:\n{"ok":true,"nodes":[]}',
          `raw-usage:\n${JSON.stringify(mixedRawUsage, null, 2)}`,
          `verbs (1):\n1. [ok] scene_info([]) -> {"ok":true} (0ms)`,
        ].join('\n\n') }],
      },
      {
        kind: 'tool-result', seq: 11, time: 2000,
        call: { name: 'houdini_exec', argsRaw: JSON.stringify({ code: 'hou.hipFile.save()' }) },
        content: [{ type: 'text', text: [
          'Execution failed:\nraw-hou gate: blocked BEFORE execution (the verb vocabulary is the primary interface; raw hou is gated).',
          `raw-usage:\n${JSON.stringify(blockedRawUsage, null, 2)}`,
        ].join('\n\n') }],
      },
      {
        kind: 'tool-result', seq: 12, time: 3000,
        call: {
          name: 'houdini_exec',
          argsRaw: JSON.stringify({
            code: 'hou.hipFile.save()',
            allow_raw: '词表没有 HIP 保存动词',
          }),
        },
        content: [{ type: 'text', text: 'Executed successfully.\n\nstdout:\n[gate] raw-hou exemption: 词表没有 HIP 保存动词' }],
      },
      {
        kind: 'tool-result', seq: 13, time: 4000,
        call: { name: 'houdini_exec', argsRaw: JSON.stringify({ code: "layout_nodes('/obj')\ndisplay_node('/obj/bike/OUT')" }) },
        content: [{ type: 'text', text: [
          'Execution failed:\nValueError: display output is ambiguous',
          'rollback:\n{"supported":true,"applied":true,"scope":"Houdini undoable scene edits only"}',
          'verbs (2):\n1. [ok] layout_nodes(["/obj"]) -> {"nodes":12} (2ms)\n2. [FAIL] display_node(["/obj/bike/OUT"]) -> error: ambiguous (0ms)',
        ].join('\n\n') }],
      },
    ] }]]),
  }),
};
const traceTree = view(traceProps);
const traceText = textContent(traceTree).replace(/\s+/g, ' ');
assert.match(traceText, /Gate 拦截/);
assert.match(traceText, /已回滚/);
assert.match(traceText, /执行代码/);
assert.match(traceText, /动词证据/);
assert.match(traceText, /查看原始工具结果/);
assert.match(traceText, /提示词与上下文/);
assert(!traceText.includes('成功修改含动词'), 'analysis metrics must not crowd the main timeline');
const snapshot = traceProps.useSession(s=>s.views.get('trajectory'));
const entries = view.model(snapshot).entries;
assert.equal(entries[0].rawMode, 'read_only');
assert.equal(entries[0].directHouCount, 1);
assert.equal(entries[0].verbs.length, 1);
assert.equal(entries[1].gateBlocked, true);
assert.equal(entries[2].rawMode, 'exempted');
assert.equal(entries[3].rollbackApplied, true);

console.log('client launcher-session hint and ledger parser tests passed');
