import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { EXPECTED_VERB_NAMES } from '../../lib/generated-verb-contract.js'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const currentSurfaces = [
  'README.md',
  'AGENTS.md',
  'docs/setup.md',
  'houdini/install.py',
  'houdini/python3.11libs/dsh_launcher.py',
  'houdini/python3.11libs/dsh_webview.py',
  'presets/houdini/cordis.patch.yml',
  'src/tools.ts',
  'client.js',
]

for (const relative of currentSurfaces) {
  const text = fs.readFileSync(path.join(root, relative), 'utf8')
  assert.doesNotMatch(text, /dsh\s*→\s*启动\s*\/\s*重启 dsh/i, `${relative} references the retired menu`)
  assert.doesNotMatch(text, /explicit Restart Services/i, `${relative} references the retired diagnostics label`)
}

const readme = fs.readFileSync(path.join(root, 'README.md'), 'utf8')
const development = fs.readFileSync(path.join(root, 'docs', 'development.md'), 'utf8')
const verbCount = EXPECTED_VERB_NAMES.length
for (const skill of fs.readdirSync(path.join(root, 'skills'))) {
  const skillFile = `skills/${skill}/SKILL.md`
  if (!fs.existsSync(path.join(root, skillFile))) continue
  assert.match(readme, new RegExp(skillFile.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')), `README omits ${skillFile}`)
}

assert.match(readme,/DSH 0.2.0-rc.2/);
assert.match(readme,/docs\/tools.md/);
console.log('current documentation consistency tests passed')
