import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const currentSurfaces = [
  'README.md',
  'AGENTS.md',
  'docs/setup.md',
  'houdini/install.py',
  'houdini/python3.11libs/dsh_launcher.py',
  'houdini/python3.11libs/dsh_desktop_client.py',
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
assert.ok(readme.includes('](skills/)'), 'README links to the skill directory')

const preferred=JSON.parse(fs.readFileSync(path.join(root,'dsh-runtime-compatibility.json'),'utf8')).preferredVersion
assert.ok(readme.replaceAll('`','').includes('DSH '+preferred), 'README identifies the supported DSH version');
assert.match(readme,/docs\/tools.md/);
console.log('current documentation consistency tests passed')
