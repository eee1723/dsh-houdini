import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const preferred = JSON.parse(fs.readFileSync(path.join(root, 'dsh-runtime-compatibility.json'), 'utf8')).preferredVersion
const upstreamPackage = path.join(root, 'node_modules/@deepseek-ai/dsh-agent-presets')
const installed = JSON.parse(fs.readFileSync(path.join(upstreamPackage, 'package.json'), 'utf8'))
assert.equal(installed.version, preferred, 'compare presets against the exact qualified DSH version')
const require = createRequire(path.join(upstreamPackage, 'package.json'))
const yaml = require('js-yaml')
const jsExpression = new yaml.Type('tag:yaml.org,2002:js', { kind: 'scalar', construct: text => text })
const schema = yaml.DEFAULT_SCHEMA.extend([jsExpression])

const upstream = fs.readFileSync(path.join(upstreamPackage, 'presets/standard/agent.cordis.yml'), 'utf8')
function rows(source) {
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
  visit(yaml.load(source, { schema }))
  return found
}

const standardRows = rows(upstream)
// This standard row is disabled upstream and its plugin is not required by the
// Houdini profile. New active standard rows must be included in both presets.
assert.equal(standardRows.get('/tool-plugin-manager')?.disabled, true,
  'review plugin-manager policy when the standard preset changes')
const omitted = new Set(['/persona', '/tool-plugin-manager'])
for (const name of ['houdini', 'houdini-dev']) {
  const source = fs.readFileSync(path.join(root, 'presets', name, 'agent.cordis.yml'), 'utf8')
  const actual = rows(source)
  for (const [key, standardRow] of standardRows) {
    if (omitted.has(key)) continue
    if (key === '/delegation/tool-ralph') {
      assert.equal(standardRow.disabled, true, 'review Ralph policy when standard DSH changes')
      const { disabled, ...enabledStandardRow } = standardRow
      assert.deepEqual(actual.get(key), enabledStandardRow,
        `${name} changed the existing Ralph exception beyond enabling it`)
      continue
    }
    assert.deepEqual(actual.get(key), standardRow, `${name} drifted from standard DSH row ${key}`)
  }
  assert.deepEqual([...actual.keys()].filter(key => !standardRows.has(key)), ['/houdini'],
    `${name} has an unreviewed addition beyond standard DSH and Houdini`)
  assert.equal(actual.get('/houdini')?.name, 'dsh-houdini', `${name} lost the Houdini layer`)
  assert.equal(actual.get('/present')?.name, '@deepseek-ai/dsh-tool-present', `${name} must expose file delivery`)
}

const production = fs.readFileSync(path.join(root, 'presets/houdini/agent.cordis.yml'), 'utf8')
assert.match(production, /call present on its authoritative path before the final response/)
assert.match(production, /Do not present visual checks, diagnostics, cache files/)
assert.match(production, /Session workspace, which may differ from \$HIP/)
console.log('Houdini presets retain qualified DSH standard rows and explicit file delivery')
