import fs from 'node:fs'
const contract=JSON.parse(fs.readFileSync(new URL('../houdini/project-layout.json',import.meta.url),'utf8'))
if(contract.schemaVersion!==1)throw Error('Unsupported project layout schema')
const labels={reference_downloaded:'下载的参考资料',reference_generated:'生成的辅助参考',texture:'材质与工程依赖',cache:'几何、模拟与通道缓存',analysis:'分析资料与诊断报告',documentation:'供用户阅读的工程与工具说明',render:'供用户保留的成图与渲染输出',visual_check:'过程检查与诊断对照图',script:'构建源码与任务脚本'}
const rows=Object.entries(contract.directories)
if(rows.length!==Object.keys(labels).length || rows.some(([role])=>!Object.hasOwn(labels,role)))throw Error('Project layout roles do not match the documented interface')
const paths=new Set()
for(const [role,item] of rows){
  if(typeof item.path!=='string'||!/^dsh-artifacts\/[a-z-]+(?:\/[a-z-]+)*$/.test(item.path)||paths.has(item.path)||typeof item.lifecycle!=='string')throw Error('Invalid directory role '+role)
  paths.add(item.path)
}
if(!/^dsh-artifacts\/[a-z-]+$/.test(contract.resultDirectory)||paths.has(contract.resultDirectory))throw Error('Invalid result directory')
const begin='<!-- project-layout:generated:start -->', end='<!-- project-layout:generated:end -->'
const table=begin+'\n| 用途 | 工程相对目录 | 生命周期标识 |\n|---|---|---|\n'
  +rows.map(([role,item])=>`| ${labels[role]}（\`${role}\`） | \`${item.path}/\` | \`${item.lifecycle}\` |`).join('\n')
  +`\n| 原始执行回执（相对DSH工作区） | \`${contract.resultDirectory}/\` | \`execution-evidence\` |\n`+end
const file=new URL('../docs/project-files.md',import.meta.url), source=fs.readFileSync(file,'utf8')
if(!source.includes(begin)||!source.includes(end))throw Error('Missing project layout documentation markers')
const output=source.slice(0,source.indexOf(begin))+table+source.slice(source.indexOf(end)+end.length)
if(process.argv.includes('--check')){if(source!==output)throw Error('Project layout documentation drift')}
else fs.writeFileSync(file,output)
console.log('Project directory contract is in sync')
