import fs from 'node:fs'
import ts from 'typescript'
const source=new URL('../src/tool-catalog.ts',import.meta.url)
const code=ts.transpileModule(fs.readFileSync(source,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
const exports={}
new Function('exports',code)(exports)
const rows=Object.entries(exports.PLUGIN_TOOLS)
const text='# Houdini 工具说明\n\n'
  +'本页由[src/tool-catalog.ts](../src/tool-catalog.ts)生成，代码注册与Trace工具说明共用这一份职责目录。Houdini参数及执行以[src/tools.ts](../src/tools.ts)为准，Host生图以[image-generation](../src/image-generation.ts)、教程离线处理以[video-process](../src/video-process.ts)、转录以[video-transcription](../src/video-transcription.ts)为准。\n\n'
  +'系统提供准确的场景信息、充分的批量操作、真实反馈和观察结果。理解需求、选择方法、安排步骤与判断效果由模型负责；领域知识按任务需要读取。\n\n'
  +'| 工具 | 为什么存在 | 输入 | 返回 | 执行位置 |\n|---|---|---|---|---|\n'
  +rows.map(([name,row])=>`| \`${name}\` · ${row.label} | ${row.purpose} | ${row.input} | ${row.output} | ${row.execution} |`).join('\n')
  +'\n\n观察现场和读取历史分开，是因为前者读取当前Houdini，后者可以在Houdini离线时使用。查回执行分开，是因为响应丢失后应取回原结果。长任务的提交、等待和取消分开表达各自真实状态。\n\n'
  +'保存、渲染、节点发现与几何检查属于可组合的Python能力，详见[动词目录](tool-design.md)。领域工作方法在[skills](../skills/)维护；任务计划使用DSH已有能力。\n\n'
  +'验证入口：[工具注册与展示](../tools/tests/houdini-tool-presentation.test.mjs)、[请求查回](../tools/tests/request-recovery.test.mjs)、[历史结果](../tools/tests/result-details.test.mjs)。\n'
const output=new URL('../docs/tools.md',import.meta.url)
if(process.argv.includes('--check')) {
  if(!fs.existsSync(output)||fs.readFileSync(output,'utf8')!==text) throw Error('Tool documentation drift')
} else fs.writeFileSync(output,text)
console.log('Tool documentation is in sync')
