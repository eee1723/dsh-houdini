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
  'presets/houdini/agent.cordis.yml',
  'presets/houdini-dev/agent.cordis.yml',
  'presets/houdini-codex/agent.cordis.yml',
  'src/tools.ts',
  'client.js',
]

for (const relative of currentSurfaces) {
  const text = fs.readFileSync(path.join(root, relative), 'utf8')
  assert.doesNotMatch(text, /dsh\s*→\s*启动\s*\/\s*重启 dsh/i, `${relative} references the retired menu`)
  assert.doesNotMatch(text, /explicit Restart Services/i, `${relative} references the retired diagnostics label`)
}

const readme = fs.readFileSync(path.join(root, 'README.md'), 'utf8')
const agents = fs.readFileSync(path.join(root, 'AGENTS.md'), 'utf8')
const development = fs.readFileSync(path.join(root, 'docs', 'development.md'), 'utf8')
const codexPreset = fs.readFileSync(path.join(root, 'presets', 'houdini-codex', 'agent.cordis.yml'), 'utf8')
const profileRequirements = JSON.parse(fs.readFileSync(path.join(root, 'dsh-profile.requirements.json'), 'utf8'))
const verbCount = EXPECTED_VERB_NAMES.length
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

assert.match(readme, /Open Workspace[^\n]*已保存 `\.hip`[^\n]*DSH workspace/)
assert.match(readme, /切换 HIP 后再次点击即可切换任务边界/)
assert.match(readme, /未保存场景[^\n]*中立 scratch[^\n]*不会扩大到 `dsh-houdini`/)
assert.match(readme, /Repair and restart runtime/)
assert.match(readme, new RegExp(`${verbCount} 个意图级动词`))
assert.match(agents, new RegExp(`dsh_hou_helpers\\.py.（${verbCount} 动词）`))
assert.match(development, new RegExp(`${verbCount} 个目录入口`))
assert.match(readme, /set_object_parent\(child, parent/)
assert.match(readme, /Houdini Codex 主力模式/)
assert.match(codexPreset, /provider: codex\s+toolName: subagent_codex/)
assert.doesNotMatch(codexPreset, /name: '@deepseek-ai\/dsh-tool-subagent'\s+disabled: true\s+config:\s+provider: codex/)
assert.ok(
  profileRequirements.plugins.some((item) => item.spec === '@deepseek-ai/dsh-subagent-codex@0.1.2-rc.1'),
  'profile requirements must install the pinned Codex subagent provider',
)

console.log('current documentation consistency tests passed')
