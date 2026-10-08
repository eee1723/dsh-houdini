import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import { spawnSync } from 'node:child_process'
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

// An installed package has compiled registrations but no TypeScript source.
// Both modes must still detect real registration drift rather than skip it.
const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-skill-audit-'))
try {
  const skill = path.join(fixture, 'skills', 'fixture-skill')
  fs.mkdirSync(skill, {recursive: true})
  fs.mkdirSync(path.join(fixture, 'lib'))
  fs.writeFileSync(path.join(skill, 'SKILL.md'), '---\nname: fixture-skill\ndescription: audit fixture\n---\nFixture body.\n')
  const registration = "const SKILLS = [{ name: 'fixture-skill', dir: 'fixture-skill' }];\n"
  fs.writeFileSync(path.join(fixture, 'lib', 'skill.js'), registration)
  const audit = path.join(root, 'skills/houdini-skill-governance/scripts/audit-houdini-skills.mjs')
  const run = () => {
    const result = spawnSync(process.execPath, [audit, '--root', fixture, '--strict', '--json'],
      {cwd: os.tmpdir(), encoding: 'utf8', windowsHide: true})
    return {code: result.status, report: JSON.parse(result.stdout)}
  }
  let result = run()
  assert.equal(result.code, 0)
  assert.deepEqual(result.report.registry, {path: 'lib/skill.js', kind: 'installed'})
  fs.writeFileSync(path.join(fixture, 'lib', 'skill.js'), 'const SKILLS = [];\n')
  result = run()
  assert.equal(result.code, 1)
  assert(result.report.issues.some(issue => issue.code === 'UNREGISTERED_SKILL'))
  fs.mkdirSync(path.join(fixture, 'src'))
  fs.writeFileSync(path.join(fixture, 'src', 'skill.ts'), registration)
  result = run()
  assert.equal(result.code, 0, 'source audit must use maintained source even before a rebuild')
  assert.deepEqual(result.report.registry, {path: 'src/skill.ts', kind: 'source'})
} finally {
  assert.equal(path.dirname(path.resolve(fixture)), path.resolve(os.tmpdir()))
  assert(path.basename(fixture).startsWith('dsh-skill-audit-'))
  fs.rmSync(fixture, {recursive: true, force: true})
}
console.log('Bundled skill registration/resource roots and source/installed audit passed; not a model activation test')
