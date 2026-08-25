import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'

const source = await readFile(new URL('../../plugins/dsh-vision-fallback/client.js', import.meta.url), 'utf8')
assert(!source.includes('自动识图分组'))
assert(!source.includes('model-directory'))

let moduleRegistration
let slotRegistration
const mutations = []
const view = {
  ns: 'vision-fallback',
  schema: {},
  value: { model: 'qwen/qwen3-vl-plus' },
  applies: 'live',
  secrets: [{ path: ['apiKey'], set: false }],
  revision: 2,
}
const api = {
  settings: {
    describe: async () => ({ result: { ok: true, value: { writable: true, namespaces: [view] } } }),
    mutate: async (payload) => {
      mutations.push(payload)
      return {
        result: {
          ok: true,
          value: {
            ...view,
            value: { model: 'qwen/qwen3-vl-max' },
            secrets: [{ path: ['apiKey'], set: true }],
            revision: 3,
          },
        },
      }
    },
  },
}
const slots = {
  inject: (name, install) => {
    assert.equal(name, 'settings.plugins.tab')
    install()
  },
  register: (options, component) => {
    slotRegistration = { options, component }
    return () => {}
  },
}
const React = {
  createElement: (type, props, ...children) => ({ type, props: props ?? {}, children }),
  useSyncExternalStore: (_subscribe, getSnapshot) => getSnapshot(),
}
const context = vm.createContext({
  console,
  document: { querySelector: () => ({}), createElement: () => ({ dataset: {} }), head: { appendChild: () => {} } },
  window: { __ModuleLoader__: { load: value => { moduleRegistration = value } } },
  Set,
})
vm.runInContext(source, context, { filename: 'vision-fallback/client.js' })
assert.equal(moduleRegistration.id, 'dsh-vision-fallback')
const plugin = moduleRegistration.factory(name => {
  assert.equal(name, 'react')
  return React
})
assert.deepEqual([...plugin.inject], ['slots', 'connection', 'remote'])
plugin.apply({
  get: name => name === 'slots'
    ? slots
    : name === 'connection'
      ? { api }
      : name === 'remote'
        ? { $on: () => () => {} }
        : undefined,
  effect: install => install(),
})
await Promise.resolve()
await Promise.resolve()
await new Promise(resolve => setImmediate(resolve))

assert.equal(slotRegistration.options.id, 'vision-fallback')
assert.equal(slotRegistration.options.label, '视觉备用')

function flatten(node, rows = []) {
  if (!node || typeof node !== 'object') return rows
  rows.push(node)
  for (const child of node.children ?? []) {
    if (Array.isArray(child)) child.forEach(entry => flatten(entry, rows))
    else flatten(child, rows)
  }
  return rows
}

let nodes = flatten(slotRegistration.component())
const inputs = nodes.filter(node => node.type === 'input')
assert.equal(inputs.length, 2)
assert.equal(inputs[0].props.type, 'password')
assert.equal(inputs[1].props.value, 'qwen/qwen3-vl-plus')
inputs[0].props.onChange({ target: { value: ' secret-key ' } })
inputs[1].props.onChange({ target: { value: 'qwen/qwen3-vl-max' } })

nodes = flatten(slotRegistration.component())
const save = nodes.find(node => node.type === 'button' && node.children.includes('保存'))
assert(save)
assert.equal(save.props.disabled, false)
save.props.onClick()
await Promise.resolve()
await Promise.resolve()
await new Promise(resolve => setImmediate(resolve))

assert.equal(mutations.length, 1)
assert.equal(mutations[0].ns, 'vision-fallback')
assert.equal(mutations[0].expectedRevision, 2)
assert.deepEqual(JSON.parse(JSON.stringify(mutations[0].ops)), [
  { op: 'set', path: ['apiKey'], value: 'secret-key' },
  { op: 'set', path: ['model'], value: 'qwen/qwen3-vl-max' },
])

console.log('vision fallback client settings tests passed')
