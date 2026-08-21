import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';


const source = await readFile(new URL('../../client.js', import.meta.url), 'utf8');


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

const view = plain.registrations.houdinitrace.component;
const ledgerLine = '1. [ok] verb_help(["set_keyframes"]) -> '
  + '{"name":"set_keyframes","signature":"(node, channels) -> dict"} (0ms)';
const tree = view({
  useSession: (select) => select({
    nodes: [{
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

console.log('client launcher-session hint and ledger parser tests passed');
