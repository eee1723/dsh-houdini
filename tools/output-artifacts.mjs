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
const kinds=['tmp','evidence','cache'],isolations=['isolated','unknown'],completed=['success','failed']
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
    if(parts.length===2&&parts[0]===initial.kind) {
      if(initial.kind==='tmp'){await removeTree(directory,root);await writeIndex({root})}
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
  const category=path.join(root,kind);await directoryWithoutLink(category,{create:true})
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
    if(kinds.includes(item.name)&&stat.isDirectory()&&!stat.isSymbolicLink()) {
      let children
      try{children=await fs.readdir(directory,{withFileTypes:true})}catch(error){if(error.code==='ENOENT')continue;throw error}
      for(const child of children) {
        const candidate=path.join(directory,child.name),childStat=await existingStat(candidate)
        if(!childStat)continue
        entries.push({directory:candidate,relativePath:path.join(item.name,child.name),
          manifest:childStat.isDirectory()&&!childStat.isSymbolicLink()?await readManifest(candidate,item.name):null,
          linked:childStat.isSymbolicLink()})
      }
    }else entries.push({directory,relativePath:item.name,manifest:stat.isDirectory()&&!stat.isSymbolicLink()?await readManifest(directory):null,linked:stat.isSymbolicLink()})
  }
  return entries.sort((a,b)=>a.relativePath.localeCompare(b.relativePath))
}
const cell=value=>String(value??'unknown').replaceAll('|','\\|').replace(/[\r\n]/g,' ')
export async function writeIndex({root=outputRoot}={}) {
  root=path.resolve(root);await directoryWithoutLink(root,{create:true})
  const rows=await listEntries(root)
  const lines=['# 本地输出索引','',`生成时间：${new Date().toISOString()}`,'',
    '此索引只读取目录第一层及受管类别下的批次元数据，不递归历史目录。unknown 表示来源未核实；不根据时间推测版本。',
    '所有素材的复用状态均为 unreviewed（尚未审核）。隔离环境声明不能代替逐项隐私与内容审核。','',
    '| 批次 | 类别 | 版本 / DSH | Commit / dirty | 结果 | 隔离来源 | 复用状态 | 生成时间 |',
    '|---|---|---|---|---|---|---|---|']
  for(const entry of rows) {
    const m=entry.manifest,link='./'+entry.relativePath.split(path.sep).map(encodeURIComponent).join('/')
    lines.push(`| [${cell(entry.relativePath)}](${link})${entry.linked?'（链接，未跟随）':''} | ${cell(m?.kind)} | ${cell(m?m.packageVersion+' / '+m.dshVersion:null)} | ${cell(m?String(m.commit??'unknown')+' / '+String(m.dirty??'unknown'):null)} | ${cell(m?.status)} | ${cell(m?.isolation)} | ${cell(m?.reuse)} | ${cell(m?.createdAt)} |`)
  }
  await atomicWrite(path.join(root,'MANIFEST.md'),lines.join('\n')+'\n')
  return {file:path.join(root,'MANIFEST.md'),entries:rows.length,unknown:rows.filter(row=>!row.manifest).length}
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
  for(const kind of kinds) {
    try{await directoryWithoutLink(path.join(root,kind))}catch(error){if(error.code!=='ENOENT')throw error}
  }
  const rows=(await listEntries(root)).filter(row=>row.manifest&&row.relativePath.split(path.sep).length===2)
  const latest=new Map()
  for(const row of rows.filter(row=>row.manifest.status==='success')) {
    const group=row.manifest.kind+'\0'+row.manifest.label,previous=latest.get(group)
    if(!previous||Date.parse(row.manifest.completedAt)>Date.parse(previous.manifest.completedAt))latest.set(group,row)
  }
  const candidates=[],kept=[]
  for(const row of rows) {
    const m=row.manifest,days=m.kind==='tmp'?7:m.kind==='evidence'?30:cacheDays
    const group=m.kind+'\0'+m.label
    if(!completed.includes(m.status)||latest.get(group)===row||days===undefined||now-Date.parse(m.completedAt)<days*DAY) {
      kept.push(row.relativePath);continue
    }
    candidates.push({directory:row.directory,relativePath:row.relativePath,label:m.label,kind:m.kind,status:m.status,completedAt:m.completedAt})
  }
  const deleted=[],errors=[]
  if(apply)for(const candidate of candidates) {
    try {
      const category=path.join(root,candidate.kind)
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
  if(values.help||!command){console.log('output-artifacts.mjs index | prune [--apply] [--cache-days N] | begin <output-directory> --label NAME [--kind evidence] [--isolation unknown] | finish <output-directory> --status success|failed | stamp <new-output-directory> --label NAME [--kind evidence] [--isolation unknown] [--status success]');return}
  if(extra.length||!['stamp','begin','finish'].includes(command)&&directory)throw Error('Unexpected output command arguments')
  let result
  if(command==='index')result=await writeIndex()
  else if(command==='prune')result=await prune({apply:values.apply,cacheDays:values['cache-days']===undefined?undefined:Number(values['cache-days'])})
  else if(command==='begin'&&directory)result=await beginDirectory(directory,{label:values.label,kind:values.kind??'evidence',isolation:values.isolation??'unknown'})
  else if(command==='finish'&&directory)result=await finishDirectory(directory,values.status??'success')
  else if(command==='stamp'&&directory)result=await stamp(directory,{label:values.label,kind:values.kind??'evidence',isolation:values.isolation??'unknown',status:values.status??'success'})
  else throw Error('Unknown output command')
  console.log(JSON.stringify(result,null,2))
  if(result.errors?.length)process.exitCode=1
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(error=>{console.error(error.message||error);process.exitCode=1})
