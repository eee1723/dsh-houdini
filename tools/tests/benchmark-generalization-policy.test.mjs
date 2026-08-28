import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')

function walk(relative) {
  const absolute = path.join(root, relative)
  const stat = fs.statSync(absolute)
  if (stat.isFile()) return [relative]
  return fs.readdirSync(absolute, { withFileTypes: true }).flatMap((entry) => {
    const child = path.join(relative, entry.name)
    return entry.isDirectory() ? walk(child) : [child]
  })
}

// These are the surfaces automatically exposed to, or routinely read by, an executing or
// repository-maintenance agent. Evaluator-only specifications may name benchmark instances;
// production behavior surfaces may not.
const agentVisibleFiles = [
  'AGENTS.md',
  'README.md',
  'client.js',
  'docs/cross-domain-benchmark-plan.md',
  'docs/development.md',
  'docs/tool-design.md',
  ...walk('src').filter((file) => !file.endsWith('generated-verb-contract.ts')),
  ...walk('presets'),
  ...walk('skills'),
].filter((file) => /\.(?:md|mjs|ts|js|ya?ml)$/.test(file))

const protectedMarkers = [
  /BM-MECH-01/i,
  /BM-SIM-01/i,
  /BM-LOOK-01/i,
  /可调关节台灯/,
  /贴地环形\s*Pyro\s*尘爆/i,
  /Karma\s*暗调产品棚拍/i,
  /articulated desk lamp/i,
  /ground-hugging annular (?:pyro )?dust/i,
  /dark product studio shot/i,
]

for (const relative of agentVisibleFiles) {
  const text = fs.readFileSync(path.join(root, relative), 'utf8')
  for (const marker of protectedMarkers) {
    assert.doesNotMatch(text, marker, `${relative} leaks an evaluator-only benchmark marker into an agent-visible surface`)
  }
}

const plan = fs.readFileSync(path.join(root, 'docs', 'cross-domain-benchmark-plan.md'), 'utf8')
assert.match(plan, /执行信息防火墙/)
assert.match(plan, /未见留出/)
assert.match(plan, /只有未见留出实例/)
assert.match(plan, /不能证明通用能力提升/)

console.log(`benchmark generalization policy tests passed (${agentVisibleFiles.length} agent-visible files)`)
