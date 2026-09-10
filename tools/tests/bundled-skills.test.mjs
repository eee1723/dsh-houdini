import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { registerBundledSkills } from '../../lib/skill.js'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const registrations = []
registerBundledSkills({ skills: { register(s) { registrations.push(s); return () => {} } } })
const directories = fs.readdirSync(path.join(root, 'skills')).filter(name =>
  fs.existsSync(path.join(root, 'skills', name, 'SKILL.md')))
assert.deepEqual(registrations.map(s => s.name).sort(), directories.sort())
assert.equal(new Set(registrations.map(s => s.name)).size, registrations.length)
for (const s of registrations) {
  assert.equal(s.source, 'bundled')
  assert.equal(s.resourceBase.kind, 'directory')
  assert.equal(path.dirname(s.path), s.resourceBase.path.replace(/[\\/]$/, ''))
  const source = fs.readFileSync(s.path, 'utf8')
  assert.equal(s.content, source.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '').trim())
  assert(s.description && !s.description.includes('\n'))
  const refDir = path.join(s.resourceBase.path, 'references')
  if (fs.existsSync(refDir)) for (const name of fs.readdirSync(refDir)) {
    assert(fs.statSync(path.join(refDir, name)).isFile())
  }
}
assert(registrations.some(s => s.name === 'houdini-cop-workflow'))
console.log('Bundled skill registration/resource roots passed; not a model activation test')
