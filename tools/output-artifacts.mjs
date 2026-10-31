/** Local test/build output retention. No user profiles or scene data are managed here. */
import fs from 'node:fs/promises'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFile} from 'node:child_process'
import {promisify,parseArgs} from 'node:util'
import {randomUUID} from 'node:crypto'

const execute=promisify(execFile)
const projectRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
export const outputRoot=path.join(projectRoot,'tools/out')
export const manifestName='artifact-manifest.json'
const marker='dsh-houdini-output'
const categories={tmp:'tmp',evidence:'evidence',cache:'cache',release:'releases'}
const kinds=Object.keys(categories),isolations=['isolated','unknown'],completed=['success','failed']
const DAY=24*60*60*1000
const labelPattern=/^[a-z0-9](?:[a-z0-9._-]{0,78}[a-z0-9])?$/i
const key=value=>process.platform==='win32'?path.resolve(value).toLowerCase():path.resolve(value)
const within=(root,directory)=>{const relative=path.relative(key(root),key(directory));return relative!==''&&!path.isAbsolute(relative)&&relative!=='..'&&!relative.startsWith('..'+path.sep)}

function checkOptions({label,kind,isolation}) {
  if(typeof label!=='string'||!labelPattern.test(label))throw Error('Output label must contain 1-80 letters, numbers, dots, underscores or hyphens')
  if(!kinds.includes(kind)||!isolations.includes(isolation))throw Error('Unknown output kind or isolation declaration')
}
async function directoryWithoutLink(directory,{create=false}={}) {
  if(create)await fs.mkdir(directory,{recursive:true})
  const stat=await fs.lstat(directory)
  if(stat.isSymbolicLink()||!stat.isDirectory())throw Error('Output root/category must be a real directory: '+directory)
}
async function sourceFacts() {
  const packageJson=JSON.parse(await fs.readFile(path.join(projectRoot,'package.json'),'utf8'))
  let commit=null,dirty=null
  try {
    const results=await Promise.all([
      execute('git',['rev-parse','HEAD'],{cwd:projectRoot,windowsHide:true}),
      execute('git',['status','--porcelain','--untracked-files=normal'],{cwd:projectRoot,windowsHide:true,maxBuffer:1024*1024}),
    ])
    commit=results[0].stdout.trim();dirty=results[1].stdout.trim()!==''
  }catch{/* A source archive has no trustworthy commit or dirty fact. */}
  return {commit,dirty,packageVersion:packageJson.version,dshVersion:packageJson.engines?.dsh??null}
}
async function atomicWrite(filename,text) {
  const temporary=filename+'.'+randomUUID()+'.tmp'
  await fs.writeFile(temporary,text,{flag:'wx'})
  await fs.rename(temporary,filename)
}
async function writeManifest(directory,value) {
  await atomicWrite(path.join(directory,manifestName),JSON.stringify(value,null,2)+'\n')
  const rows=[['类别',value.kind],['批次',value.label],['版本',value.packageVersion],['DSH',value.dshVersion],
    ['Commit',value.commit],['工作树有未提交改动',value.dirty],['生成时间',value.createdAt],['完成时间',value.completedAt],
    ['结果',value.status],['隔离来源',value.isolation],['素材复用',value.reuse]]
  await atomicWrite(path.join(directory,'MANIFEST.md'),['# 输出批次信息','',
    '本文件由 artifact-manifest.json 同源生成。unreviewed 表示素材尚未通过隐私与内容复用审核。','',
    '| 字段 | 值 |','|---|---|',...rows.map(([name,entry])=>`| ${name} | ${cell(entry)} |`),''].join('\n'))
}
async function readManifest(directory,kind) {
  try {
    const filename=path.join(directory,manifestName),stat=await fs.lstat(filename)
    if(stat.isSymbolicLink()||!stat.isFile()||stat.size>65536)return null
    const value=JSON.parse(await fs.readFile(filename,'utf8'))
    if(value.schemaVersion!==1||value.tool!==marker||typeof value.label!=='string'||!labelPattern.test(value.label)||!kinds.includes(value.kind)
      ||kind&&value.kind!==kind||!isolations.includes(value.isolation)||value.reuse!=='unreviewed'
      ||!['running',...completed].includes(value.status)||!Number.isFinite(Date.parse(value.createdAt))
      ||completed.includes(value.status)&&!Number.isFinite(Date.parse(value.completedAt)))return null
    return value
  }catch(error){if(error instanceof SyntaxError||['ENOENT','ENOTDIR'].includes(error.code))return null;throw error}
}

async function newManifest({label,kind,isolation}) {
  checkOptions({label,kind,isolation})
  return {schemaVersion:1,tool:marker,label,kind,...await sourceFacts(),createdAt:new Date().toISOString(),
    status:'running',isolation,reuse:'unreviewed'}
}
/** Begin only an explicitly generated batch. Source identity is frozen before work starts. */
export async function beginDirectory(directory,{label,kind='evidence',isolation='unknown'},{root=outputRoot}={}) {
  directory=path.resolve(directory);await directoryWithoutLink(directory)
  const value=await newManifest({label,kind,isolation})
  await writeManifest(directory,value)
  if(within(root,directory))await writeIndex({root})
  return value
}
/** Complete the same source snapshot; external explicit output directories are never pruned. */
export async function finishDirectory(directory,status='success',{root=outputRoot}={}) {
  if(!completed.includes(status))throw Error('Completed output status must be success or failed')
  directory=path.resolve(directory);root=path.resolve(root);await directoryWithoutLink(directory)
  const initial=await readManifest(directory)
  if(!initial)throw Error('Output batch has no valid begin manifest: '+directory)
  if(completed.includes(initial.status)&&initial.status!==status)throw Error('Output run already finished with another status')
  const value=initial.status===status?initial:{...initial,status,completedAt:new Date().toISOString()}
  await writeManifest(directory,value)
  if(within(root,directory)) {
    const parts=path.relative(root,directory).split(path.sep)
    if(parts.length===2&&parts[0]===categories[initial.kind]) {
      if(initial.kind==='tmp'){await removeTree(directory,root);await writeIndex({root})}
      else if(initial.kind==='release')await writeIndex({root})
      else await prune({root,apply:true})
    }else await writeIndex({root})
  }
  return value
}

/** The source identity is captured when the run starts, even if the checkout changes later. */
export async function createRun({label,kind='evidence',isolation='unknown'},{root=outputRoot}={}) {
  checkOptions({label,kind,isolation})
  root=path.resolve(root)
  await directoryWithoutLink(root,{create:true})
  const category=path.join(root,categories[kind]);await directoryWithoutLink(category,{create:true})
  const directory=await fs.mkdtemp(path.join(category,label+'-'))
  await beginDirectory(directory,{label,kind,isolation},{root})
  let finishing,finalStatus
  return {directory,finish(status='success') {
    if(!completed.includes(status))return Promise.reject(Error('Completed output status must be success or failed'))
    if(finishing&&status!==finalStatus)return Promise.reject(Error('Output run already finished with another status'))
    if(!finishing) {
      finalStatus=status
      finishing=finishDirectory(directory,status,{root})
    }
    return finishing
  }}
}

/** Only call for explicitly generated current outputs; never infer an old batch's source. */
export async function stamp(directory,{label,kind='evidence',isolation='unknown',status='success'},{root=outputRoot}={}) {
  checkOptions({label,kind,isolation})
  if(!completed.includes(status))throw Error('Stamped output status must be success or failed')
  directory=path.resolve(directory);await directoryWithoutLink(directory)
  const initial=await newManifest({label,kind,isolation})
  const value={...initial,completedAt:initial.createdAt,status}
  await writeManifest(directory,value)
  if(within(root,directory))await writeIndex({root})
  return value
}
export {stamp as stampDirectory}

async function listEntries(root) {
  await directoryWithoutLink(root)
  const entries=[]
  const existingStat=async filename=>{
    try{return await fs.lstat(filename)}catch(error){if(error.code==='ENOENT')return null;throw error}
  }
  for(const item of await fs.readdir(root,{withFileTypes:true})) {
    if(item.name==='MANIFEST.md')continue
    const directory=path.join(root,item.name),stat=await existingStat(directory)
    if(!stat)continue
    const kind=Object.keys(categories).find(kind=>categories[kind]===item.name)
    if(kind&&stat.isDirectory()&&!stat.isSymbolicLink()) {
      let children
      try{children=await fs.readdir(directory,{withFileTypes:true})}catch(error){if(error.code==='ENOENT')continue;throw error}
      for(const child of children) {
        const candidate=path.join(directory,child.name),childStat=await existingStat(candidate)
        if(!childStat)continue
        entries.push({directory:candidate,relativePath:path.join(item.name,child.name),
          manifest:childStat.isDirectory()&&!childStat.isSymbolicLink()?await readManifest(candidate):null,
          category:kind,linked:childStat.isSymbolicLink()})
      }
    }else entries.push({directory,relativePath:item.name,manifest:stat.isDirectory()&&!stat.isSymbolicLink()?await readManifest(directory):null,linked:stat.isSymbolicLink()})
  }
  return entries.sort((a,b)=>a.relativePath.localeCompare(b.relativePath))
}
const cell=value=>String(value??'unknown').replaceAll('|','\\|').replace(/[\r\n]/g,' ')
export async function writeIndex({root=outputRoot}={}) {
  root=path.resolve(root);await directoryWithoutLink(root,{create:true})
  const rows=await listEntries(root)
  const deliveries=new Map()
  for(const entry of rows)if(!entry.linked&&(entry.category==='release'||!entry.category&&entry.manifest)){
    const artifact=await releaseLink(entry.directory)
    if(artifact)deliveries.set(entry,artifact)
  }
  const viewCategory=entry=>deliveries.has(entry)?'release':entry.category
  const link=relative=>'./'+relative.split(path.sep).map(encodeURIComponent).join('/')
  const lines=['# 本地输出索引','',`生成时间：${new Date().toISOString()}`,'',
    '| 去哪里找 | 内容 | 保留方式 |','|---|---|---|',
    '| [releases](./releases/) | 安装包与明确交付产物 | 不参与自动清理 |',
    '| [evidence](./evidence/) | 任务审查、测试报告与截图 | 受管证据保留30天及每组最近成功批次 |',
    '| [cache](./cache/) | 可复用下载和构建资源 | 默认保留，显式指定期限才清理 |',
    '| [tmp](./tmp/) | 可丢弃的构建/测试暂存 | 受管批次完成后清理 |',
    '| [legacy](./legacy/) | 已归档的旧布局 | 不自动清理或推断来源 |','',
    '这里只读取受管类别的一层批次和元数据，不递归历史大目录。目录位置表示用途，不证明版本、执行成功或素材已审核。历史缺少的来源保持 unknown；完整来源和 unreviewed 状态见各批次清单。','']
  for(const [kind,title] of Object.entries({release:'安装包与交付',evidence:'审查与验证',cache:'复用资源',tmp:'暂存'})) {
    const entries=rows.filter(row=>viewCategory(row)===kind)
    lines.push('## '+title,'')
    if(!entries.length){lines.push('暂无批次。','');continue}
    lines.push('| 批次 | 记录版本 | 结果 | 说明 |','|---|---|---|---|')
    for(const entry of entries){
      const m=entry.manifest
      const notes=[]
      if(entry.linked)notes.push('链接，未跟随')
      if(!m)notes.push('未采用批次清单，保留原内容')
      else if(m.kind!==kind)notes.push('旧类别记录 '+m.kind+'，未改写来源，不参与清理')
      if(!entry.category)notes.push('原路径保留')
      const artifact=deliveries.get(entry)
      if(artifact)notes.push(`[安装包](${link(path.join(entry.relativePath,artifact.file))})`)
      lines.push(`| [${cell(entry.relativePath)}](${link(entry.relativePath)}) | ${cell(m?.packageVersion)} | ${cell(m?.status)} | ${notes.join('；')} |`)
    }
    lines.push('')
  }
  const retained=rows.filter(row=>!viewCategory(row))
  if(retained.length){
    lines.push('## 保留原位置的目录与文件','',
      '这些是旧布局、说明文件或显式指定的输出。索引不替它们补造来源，也不迁移已交付路径。','',
      '| 原位置 | 已有记录 |','|---|---|')
    for(const entry of retained)lines.push(`| [${cell(entry.relativePath)}](${link(entry.relativePath)}) | ${entry.linked?'链接，未跟随':entry.manifest?cell(entry.manifest.kind+' / '+entry.manifest.packageVersion+' / '+entry.manifest.status):'unknown，保留'} |`)
    lines.push('')
  }
  await atomicWrite(path.join(root,'MANIFEST.md'),lines.join('\n')+'\n')
  return {file:path.join(root,'MANIFEST.md'),entries:rows.length,unknown:rows.filter(row=>!row.manifest).length}
}

async function releaseLink(directory) {
  try {
    const filename=path.join(directory,'release-manifest.json'),stat=await fs.lstat(filename)
    if(!stat.isFile()||stat.isSymbolicLink()||stat.size>65536)return null
    const manifest=JSON.parse(await fs.readFile(filename,'utf8'))
    if(manifest.kind!=='dsh-plugin-bundle'||typeof manifest.file!=='string'
      ||path.basename(manifest.file)!==manifest.file||!manifest.file.endsWith('.tgz'))return null
    const artifact=await fs.lstat(path.join(directory,manifest.file))
    return artifact.isFile()&&!artifact.isSymbolicLink()?{file:manifest.file}:null
  }catch(error){if(error instanceof SyntaxError||['ENOENT','ENOTDIR'].includes(error.code))return null;throw error}
}

async function removeTreeWithoutFollowingLinks(directory) {
  const stat=await fs.lstat(directory)
  if(stat.isSymbolicLink()){await fs.unlink(directory);return}
  if(!stat.isDirectory()){await fs.unlink(directory);return}
  for(const name of await fs.readdir(directory))await removeTreeWithoutFollowingLinks(path.join(directory,name))
  await fs.rmdir(directory)
}
/** Explicit local boundary, checked before recursion. Child junction targets are never visited. */
export async function removeTree(directory,boundary=outputRoot) {
  directory=path.resolve(directory);boundary=path.resolve(boundary)
  if(!within(boundary,directory))throw Error('Cleanup target must be below its explicit boundary')
  await directoryWithoutLink(boundary)
  let realDirectory
  try{realDirectory=await fs.realpath(directory)}catch(error){if(error.code==='ENOENT')return false;throw error}
  const realBoundary=await fs.realpath(boundary)
  if(!within(realBoundary,realDirectory))throw Error('Cleanup target escaped its explicit boundary')
  await removeTreeWithoutFollowingLinks(directory)
  return true
}
export async function prune({root=outputRoot,apply=false,cacheDays,now=Date.now()}={}) {
  root=path.resolve(root);await directoryWithoutLink(root)
  if(cacheDays!==undefined&&(!Number.isFinite(cacheDays)||cacheDays<0))throw Error('Cache retention days must be a nonnegative number')
  if(!Number.isFinite(now))throw Error('Invalid retention time')
  // Reject linked category roots before inspecting or deleting any run.
  for(const directory of Object.values(categories)) {
    try{await directoryWithoutLink(path.join(root,directory))}catch(error){if(error.code!=='ENOENT')throw error}
  }
  const rows=(await listEntries(root)).filter(row=>row.manifest&&row.category===row.manifest.kind&&row.relativePath.split(path.sep).length===2)
  const latest=new Map()
  for(const row of rows.filter(row=>row.manifest.status==='success')) {
    const group=row.manifest.kind+'\0'+row.manifest.label,previous=latest.get(group)
    if(!previous||Date.parse(row.manifest.completedAt)>Date.parse(previous.manifest.completedAt))latest.set(group,row)
  }
  const candidates=[],kept=[]
  for(const row of rows) {
    const m=row.manifest,days=m.kind==='tmp'?7:m.kind==='evidence'?30:m.kind==='cache'?cacheDays:undefined
    const group=m.kind+'\0'+m.label
    if(!completed.includes(m.status)||latest.get(group)===row||days===undefined||now-Date.parse(m.completedAt)<days*DAY) {
      kept.push(row.relativePath);continue
    }
    candidates.push({directory:row.directory,relativePath:row.relativePath,label:m.label,kind:m.kind,status:m.status,completedAt:m.completedAt})
  }
  const deleted=[],errors=[]
  if(apply)for(const candidate of candidates) {
    try {
      const category=path.join(root,categories[candidate.kind])
      await directoryWithoutLink(root);await directoryWithoutLink(category);await directoryWithoutLink(candidate.directory)
      if(path.dirname(candidate.directory)!==category)throw Error('Cleanup target escaped the output category')
      await removeTree(candidate.directory,root);deleted.push(candidate.relativePath)
    }catch(error){errors.push({directory:candidate.relativePath,error:String(error.message||error)})}
  }
  if(apply)await writeIndex({root})
  return {apply,candidates,kept,deleted,errors}
}

async function main() {
  const {values,positionals}=parseArgs({allowPositionals:true,options:{
    label:{type:'string'},kind:{type:'string'},isolation:{type:'string'},status:{type:'string'},
    'cache-days':{type:'string'},apply:{type:'boolean',default:false},help:{type:'boolean'},
  }})
  const [command,directory,...extra]=positionals
  if(values.help||!command){console.log('output-artifacts.mjs index | create --label NAME [--kind evidence|release|cache|tmp] [--isolation unknown] | prune [--apply] [--cache-days N] | begin <output-directory> --label NAME [--kind evidence] [--isolation unknown] | finish <output-directory> --status success|failed | stamp <new-output-directory> --label NAME [--kind evidence] [--isolation unknown] [--status success]');return}
  if(extra.length||!['stamp','begin','finish'].includes(command)&&directory)throw Error('Unexpected output command arguments')
  let result
  if(command==='index')result=await writeIndex()
  else if(command==='create'){
    const run=await createRun({label:values.label,kind:values.kind??'evidence',isolation:values.isolation??'unknown'})
    result={directory:run.directory,manifest:path.join(run.directory,manifestName)}
  }
  else if(command==='prune')result=await prune({apply:values.apply,cacheDays:values['cache-days']===undefined?undefined:Number(values['cache-days'])})
  else if(command==='begin'&&directory)result=await beginDirectory(directory,{label:values.label,kind:values.kind??'evidence',isolation:values.isolation??'unknown'})
  else if(command==='finish'&&directory)result=await finishDirectory(directory,values.status??'success')
  else if(command==='stamp'&&directory)result=await stamp(directory,{label:values.label,kind:values.kind??'evidence',isolation:values.isolation??'unknown',status:values.status??'success'})
  else throw Error('Unknown output command')
  console.log(JSON.stringify(result,null,2))
  if(result.errors?.length)process.exitCode=1
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(error=>{console.error(error.message||error);process.exitCode=1})
