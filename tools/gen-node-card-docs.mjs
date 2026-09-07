#!/usr/bin/env node
// Canonical node cards -> human-readable reference. No HOM, network or defaults snapshot.
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
export const sourcePath = 'houdini/node-operation-contracts.json'
export const outputPath = 'docs/node-operation-cards.md'
const keys = (obj, allowed, where) => {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj) || Object.keys(obj).some(k => !allowed.includes(k)))
    throw new Error(`${where}: unsupported fields or shape`)
}
const strings = (items, where, nonempty = true) => {
  if (!Array.isArray(items) || (nonempty && !items.length) || items.some(s => typeof s !== 'string' || !s.trim()) || new Set(items).size !== items.length)
    throw new Error(`${where}: expected unique nonempty strings`)
}
const inline = text => '`' + text.replaceAll('`', '\\`').replaceAll('\n', ' ') + '`'

export function validateNodeCards(data) {
  keys(data, ['schema_version', 'cards'], 'root')
  if (data.schema_version !== 2 || !data.cards || Array.isArray(data.cards) || typeof data.cards !== 'object' || !Object.keys(data.cards).length)
    throw new Error('expected schema_version=2 and nonempty cards')
  const ids = new Set()
  for (const [family, c] of Object.entries(data.cards)) {
    if (!/^[a-z][a-z0-9_]*$/.test(family)) throw new Error('invalid card family')
    keys(c, ['id','source','notes','node_types','tested_versions','critical_parameters','decisions'], family)
    if (typeof c.id !== 'string' || !/^[a-z0-9-]+$/.test(c.id) || ids.has(c.id)) throw new Error(`${family}: invalid/duplicate card id`)
    ids.add(c.id)
    if (typeof c.source !== 'string' || !c.source.startsWith('https://www.sidefx.com/docs/')) throw new Error(`${family}: expected official source`)
    strings(c.notes, `${family}.notes`)
    for (const k of ['node_types','tested_versions','critical_parameters']) if (k in c) strings(c[k], `${family}.${k}`)
    if ('decisions' in c) {
      if (!Array.isArray(c.decisions)) throw new Error(`${family}: decisions must be an array`)
      const decisionIds = new Set()
      for (const d of c.decisions) {
        keys(d, ['id','any_of','guidance'], `${family}.decision`)
        if (typeof d.id !== 'string' || !/^[a-z0-9_]+$/.test(d.id) || decisionIds.has(d.id)) throw new Error(`${family}: invalid/duplicate decision id`)
        decisionIds.add(d.id)
        if (typeof d.guidance !== 'string' || !d.guidance.trim() || !Array.isArray(d.any_of) || !d.any_of.length) throw new Error(`${family}: invalid decision`)
        for (const option of d.any_of) {
          strings(option, `${family}.${d.id}.any_of`)
          if (option.some(n => !c.critical_parameters?.includes(n))) throw new Error(`${family}: decision field absent from critical_parameters`)
        }
      }
    }
  }
  return data
}

export function renderNodeCards(data) {
  validateNodeCards(data)
  const digest = crypto.createHash('sha256').update(JSON.stringify(data)).digest('hex')
  const out = ['# 节点操作卡参考', '',
    '> 自动生成，勿手改。唯一数据源：[node-operation-contracts.json](../houdini/node-operation-contracts.json)。',
    '> 生成：`npm run docs:generate`；只读校验：`npm run docs:check`；正常构建会自动更新。', '',
    `Schema: ${data.schema_version} · Cards: ${Object.keys(data.cards).length} · Source SHA-256: \`${digest}\``, '',
    '## 数据与设计契约', '',
    '- JSON维护输入语义、决策、反例与来源；本页逐项镜像，英文操作说明不另行手译成第二份真相。',
    '- `id`标识知识修订；`node_types`限定精确类型，省略时按现有family规则匹配。`tested_versions`是证据范围，省略不表示已验证所有版本。',
    '- `critical_parameters`只维护关键参数名；实际类型、默认值、组件名、菜单token/set_value由Houdini运行时模板提供，不在文档固化菜单索引。',
    '- `decisions[].any_of`列出备选字段组合：满足任一组合仅表示显式提供字段，不证明值或建模意图正确。`guidance`解释决策边界。',
    '- `node_info`返回不受普通filter/limit裁切的`operation_parameters`及缺字段提示；静态模板不等于Shelf初始化后的实际值。',
    '- `build_module.operation_advisories`按类型/缺字段合并，最多16条并报告总数/截断。不阻断、不改默认值、不cook、不解析VEX；未决选择可先dry_run。',
    '- 精确类型不匹配时不套用受限卡；复制返回值不应修改缓存。新增字段必须同时更新生成器、运行时消费者和测试。', '',
    '实现：[卡加载器](../houdini/python3.11libs/dsh_operation_cards.py)、[node_info](../houdini/python3.11libs/dsh_hou_helpers.py)、[模块构建](../houdini/python3.11libs/dsh_sop_contracts.py)。',
    '契约：[工具设计](tool-design.md)；验证：[节点行为回归](../tools/tests/dsh-node-knowledge.test.py)。', '', '## 卡片目录', '']
  for (const family of Object.keys(data.cards)) out.push(`- [${family}](#${family})`)
  for (const [family, c] of Object.entries(data.cards)) {
    out.push('', `## ${family}`, '', `标识：${inline(c.id)}。来源：[SideFX 官方说明](${c.source})。`, '',
      `精确类型：${c.node_types?.map(inline).join('、') || '未另限定（按family匹配）'}。`,
      `已测版本：${c.tested_versions?.map(inline).join('、') || '此卡未列出，不外推版本保证'}。`)
    if (c.critical_parameters) out.push('', '关键运行时参数：' + c.critical_parameters.map(inline).join('、') + '。')
    if (c.decisions?.length) {
      out.push('', '### 构建前决策', '')
      for (const d of c.decisions) out.push(`- ${inline(d.id)}：${d.any_of.map(option => option.map(inline).join(' + ')).join(' **或** ')}。${d.guidance}`)
    }
    out.push('', '### 操作与边界', '', ...c.notes.map(n => '- ' + n))
  }
  return out.join('\n') + '\n'
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.slice(2).some(x => x !== '--check')) throw new Error('usage: node tools/gen-node-card-docs.mjs [--check]')
  const expected = renderNodeCards(JSON.parse(fs.readFileSync(path.join(root, sourcePath), 'utf8')))
  const target = path.join(root, outputPath)
  const current = fs.existsSync(target) ? fs.readFileSync(target, 'utf8').replaceAll('\r\n', '\n') : ''
  if (current !== expected) {
    if (process.argv.includes('--check')) throw new Error(`${outputPath} drifted; run npm run docs:generate`)
    fs.writeFileSync(target, expected)
    console.log(`${outputPath} generated`)
  } else console.log(`${outputPath} is in sync`)
}
