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
  'houdini/python3.11libs/dsh_webview.py',
  'presets/houdini/agent.cordis.yml',
  'presets/houdini-dev/agent.cordis.yml',
  'src/tools.ts',
  'client.js',
]

for (const relative of currentSurfaces) {
  const text = fs.readFileSync(path.join(root, relative), 'utf8')
  assert.doesNotMatch(text, /dsh\s*→\s*启动\s*\/\s*重启 dsh/i, `${relative} references the retired menu`)
  assert.doesNotMatch(text, /explicit Restart Services/i, `${relative} references the retired diagnostics label`)
}

const readme = fs.readFileSync(path.join(root, 'README.md'), 'utf8')
const nodeTestCount = fs.readdirSync(path.join(root, 'tools', 'tests'))
  .filter((name) => name.endsWith('.test.mjs')).length
assert.match(
  readme,
  new RegExp(`${nodeTestCount} 个 Node 确定性测试文件`),
  `README must report the current ${nodeTestCount}-file Node suite`,
)
for (const skill of fs.readdirSync(path.join(root, 'skills'))) {
  const skillFile = `skills/${skill}/SKILL.md`
  if (!fs.existsSync(path.join(root, skillFile))) continue
  assert.match(readme, new RegExp(skillFile.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')), `README omits ${skillFile}`)
}

assert.match(readme, /Open Workspace[^\n]*不重载页面、不切换当前会话/)
assert.match(readme, /Repair and restart runtime/)

console.log('current documentation consistency tests passed')
