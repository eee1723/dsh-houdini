import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const preferred = JSON.parse(fs.readFileSync(path.join(root, 'dsh-runtime-compatibility.json'), 'utf8')).preferredVersion
const upstreamPackage = path.join(root, 'node_modules/@deepseek-ai/dsh-web-app')
const installed = JSON.parse(fs.readFileSync(path.join(upstreamPackage, 'package.json'), 'utf8'))
assert.equal(installed.version, preferred, 'compare presets against the exact qualified DSH version')
const require = createRequire(path.join(upstreamPackage, 'package.json'))
const yaml = require('js-yaml')
const jsExpression = new yaml.Type('tag:yaml.org,2002:js', { kind: 'scalar', construct: text => text })
const schema = yaml.DEFAULT_SCHEMA.extend([jsExpression])

const parse = file => yaml.load(fs.readFileSync(file, 'utf8'), { schema })
const standard = parse(path.join(upstreamPackage, 'presets/standard.patch.yml'))[0].insert[0].config.plugins
const patch = parse(path.join(root, 'presets/houdini/cordis.patch.yml'))
const declarations = patch.flatMap(row => row.insert || []).filter(row => row.name === '@deepseek-ai/dsh-agent-preset')
const frontend = patch.flatMap(row => row.insert || []).filter(row => row.name === 'dsh-houdini')
assert.equal(frontend.length, 1, 'browser delivery has one root entry')
assert.equal(declarations.length, 1)
assert.equal(declarations[0].config.id, 'houdini')
assert.equal(patch.find(row => row.id === 'agent-preset-registry').config.default, 'houdini')
for (const id of ['standard', 'ptc', 'minimal', 'cordis']) {
  assert.equal(patch.find(row => row.id === 'preset-' + id).disabled, true)
}
function rows(entries) {
  const found = new Map()
  function visit(entries, parent = '') {
    for (const entry of entries) {
      const key = `${parent}/${entry.id}`
      assert.ok(!found.has(key), `duplicate preset row ${key}`)
      const own = { ...entry }
      if (Array.isArray(own.config)) delete own.config
      found.set(key, own)
      if (Array.isArray(entry.config)) visit(entry.config, key)
    }
  }
  visit(entries)
  return found
}

const standardRows = rows(standard)
// This standard row is disabled upstream and its plugin is not required by the
// Houdini profile. New active standard rows must be included in our preset.
assert.equal(standardRows.get('/tool-plugin-manager')?.disabled, true,
  'review plugin-manager policy when the standard preset changes')
const omitted = new Set(['/persona', '/tool-plugin-manager'])
assert.deepEqual(fs.readdirSync(path.join(root, 'presets')), ['houdini'])
const actual = rows(declarations[0].config.plugins)
for (const [key, standardRow] of standardRows) {
  if (omitted.has(key)) continue
  assert.deepEqual(actual.get(key), standardRow, `Houdini drifted from standard DSH row ${key}`)
}
assert.deepEqual([...actual.keys()].filter(key => !standardRows.has(key)), ['/houdini'])
assert.equal(actual.get('/houdini').name, 'dsh-houdini/agent')
assert.deepEqual(actual.get('/houdini').isolate,{houdiniNodeDelivery:true},
  'the preset navigation service must live in the DSH isolate realm')
assert.equal(actual.get('/houdini').config.productMode, undefined)
assert.equal(actual.get('/present').name, '@deepseek-ai/dsh-tool-present')
assert.equal(actual.get('/persona').config.prefix,
  fs.readFileSync(path.join(root, 'presets/houdini/persona.md'), 'utf8').trim(),
  'the delivered persona must be the maintained source, not a second prompt copy')
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'))
assert.deepEqual(manifest.dsh.bundle.patch, ['./presets/houdini/cordis.patch.yml'])
assert.equal(fs.existsSync(path.join(root, 'cordis.patch.yml')), false, 'Houdini mounts only in its preset scope')
console.log('One scoped Houdini preset retains qualified DSH standard capability and file delivery')
