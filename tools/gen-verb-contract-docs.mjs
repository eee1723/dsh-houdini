import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
export const sourcePath = 'houdini/verb-operation-contracts.json'
export const outputPath = 'docs/verb-contracts.md'

export function renderVerbContracts(data) {
  if (data.schema_version !== 1 || typeof data.schema_scope !== 'string' ||
      typeof data.execution_scope !== 'string' || !data.verbs || Array.isArray(data.verbs))
    throw new Error('expected schema_version=1 and a verb contract mapping')
  const out = ['# 按需动词输入与返回契约', '',
    '> 自动生成，勿手改。唯一维护源：[verb-operation-contracts.json](../houdini/verb-operation-contracts.json)。',
    '> 生成：`npm run docs:generate`；漂移检查：`npm run docs:check`。', '',
    '## 使用方式与维护范围', '',
    '模型通过 `verb_help("build_module")` 或名称列表取得简明调用资料；使用 `detail="full"` 按需查询完整说明，不把本页全部内容拼入常驻提示。',
    '`signature`、`return_type`、`call_mode` 从真实函数取得；brief 的 `doc` 是简短用途，full 才含完整 `doc`。已维护的动词在 full 中还返回 `operation_contract`，',
    '包含输入和返回字段、可执行 Python 示例、结果读取方式及接口边界。其他动词仍使用运行时签名与说明。', '',
    data.schema_scope, '', data.execution_scope, '',
    'JSON Schema是描述字段结构的格式。这里维护可序列化输入与成功动词回执的结构子集，开放未枚举的返回字段；',
    '它不在执行时验证请求，不增加流程、审批或执行门槛。失败继续使用真实异常、动词回执及恢复事实。',
    '函数签名/默认值不在JSON重复维护；节点参数、菜单与默认值由 `node_info` 或实际节点参数查询取得。', '',
    '实现：[按需运行时帮助](../houdini/python3.11libs/dsh_execution.py)、[Houdini动词](../houdini/python3.11libs/dsh_hou_helpers.py)。',
    '验证：[模块与帮助边界](../tools/tests/dsh-module-boundaries.test.py)、[生成器](../tools/gen-verb-contract-docs.mjs)。', '',
    '## 已维护目录', '', ...Object.keys(data.verbs).map(name => `- [${name}](#${name})`)]
  const fields = ['summary', 'input_schema', 'output_schema', 'examples', 'notes']
  for (const [name, contract] of Object.entries(data.verbs)) {
    if (!/^[a-z][a-z0-9_]*$/.test(name) || Object.keys(contract).some(key => !fields.includes(key)) ||
        fields.some(key => !(key in contract)) || typeof contract.summary !== 'string' ||
        !contract.input_schema || !contract.output_schema || !Array.isArray(contract.examples) ||
        !contract.examples.length || !Array.isArray(contract.notes))
      throw new Error(`${name}: invalid or unrendered contract fields`)
    out.push('', `## ${name}`, '', contract.summary, '', '### 输入结构', '',
      '```json', JSON.stringify(contract.input_schema, null, 2), '```', '',
      '### 成功动词回执的返回结构', '', '```json', JSON.stringify(contract.output_schema, null, 2), '```')
    for (const example of contract.examples) {
      if (Object.keys(example).some(key => !['title','code','read_result','tool'].includes(key)) ||
          ['title','code','read_result','tool'].some(key => typeof example[key] !== 'string' || !example[key].trim()) ||
          !['houdini_exec','houdini_inspect'].includes(example.tool))
        throw new Error(`${name}: invalid or unrendered example fields`)
      out.push('', `### ${example.title}`, '', `调用工具：\`${example.tool}\`。`, '', '```python', example.code, '```', '', example.read_result)
    }
    if (contract.notes.length) {
      if (contract.notes.some(note => typeof note !== 'string' || !note.trim()))
        throw new Error(`${name}: invalid notes`)
      out.push('', '### 接口边界', '', ...contract.notes.map(note => '- ' + note))
    }
  }
  return out.join('\n') + '\n'
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.slice(2).some(arg => arg !== '--check'))
    throw new Error('usage: node tools/gen-verb-contract-docs.mjs [--check]')
  const expected = renderVerbContracts(JSON.parse(fs.readFileSync(path.join(root, sourcePath), 'utf8')))
  const destination = path.join(root, outputPath)
  if (process.argv.includes('--check')) {
    if (!fs.existsSync(destination) || fs.readFileSync(destination, 'utf8').replaceAll('\r\n', '\n') !== expected)
      throw new Error('verb contract documentation drifted; run npm run docs:generate')
  } else fs.writeFileSync(destination, expected)
  console.log(process.argv.includes('--check') ? 'Verb contracts are in sync' : 'Verb contracts generated')
}
