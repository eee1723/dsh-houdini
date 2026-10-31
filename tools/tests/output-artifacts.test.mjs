import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {spawnSync} from 'node:child_process'
import {createRun,beginDirectory,finishDirectory,stampDirectory,writeIndex,prune,removeTree,manifestName} from '../output-artifacts.mjs'

const fixture=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-output-artifacts-')),root=path.join(fixture,'out')
const cliTemporary=process.platform==='win32'?path.join(os.homedir(),'AppData/Local/Temp'):os.tmpdir(),ownedExternal=[]
const DAY=24*60*60*1000,now=Date.now(),old=new Date(now-40*DAY).toISOString()
async function age(run) {
  const filename=path.join(run.directory,manifestName),m=JSON.parse(await fs.readFile(filename,'utf8'))
  await fs.writeFile(filename,JSON.stringify({...m,createdAt:old,completedAt:old}))
}
try {
  const first=await createRun({label:'browser',isolation:'isolated'},{root})
  await fs.writeFile(path.join(first.directory,'shot.png'),'fixture only')
  const started=JSON.parse(await fs.readFile(path.join(first.directory,manifestName),'utf8'))
  const originalPath=process.env.PATH
  let metadata
  try{process.env.PATH='';metadata=await first.finish('success')}finally{if(originalPath===undefined)delete process.env.PATH;else process.env.PATH=originalPath}
  await first.finish('success')
  const sourceKeys=['commit','dirty','packageVersion','dshVersion']
  assert.deepEqual(sourceKeys.map(name=>metadata[name]),sourceKeys.map(name=>started[name]),'finish keeps the start source snapshot even if git is no longer discoverable')
  assert.equal(metadata.reuse,'unreviewed');assert.equal(metadata.isolation,'isolated')
  assert.equal(metadata.status,'success');assert.equal(typeof metadata.packageVersion,'string')
  assert.ok('commit' in metadata&&'dirty' in metadata&&'dshVersion' in metadata)
  await assert.rejects(first.finish('failed'),/another status/)
  const latest=await createRun({label:'browser',isolation:'isolated'},{root});await latest.finish('success');await age(first);await age(latest)
  // Give the latest run a later completed fact while keeping it older than retention.
  const latestFile=path.join(latest.directory,manifestName),latestData=JSON.parse(await fs.readFile(latestFile,'utf8'))
  await fs.writeFile(latestFile,JSON.stringify({...latestData,completedAt:new Date(now-39*DAY).toISOString()}))
  const temporary=await createRun({label:'temporary',kind:'tmp'},{root});await temporary.finish('failed')
  assert.equal(await fs.stat(temporary.directory).then(()=>true,()=>false),false,'completed scratch is removed immediately')
  const failed=await createRun({label:'failed-browser',kind:'tmp'},{root})
  const failedFile=path.join(failed.directory,manifestName),failedData=JSON.parse(await fs.readFile(failedFile,'utf8'))
  await fs.writeFile(failedFile,JSON.stringify({...failedData,status:'failed',completedAt:old}));await age(failed)
  const running=await createRun({label:'in-progress',kind:'tmp'},{root})
  const unknown=path.join(root,'old-unknown');await fs.mkdir(unknown);await fs.writeFile(path.join(unknown,'shot.png'),'unreviewed legacy')
  const unknownManaged=path.join(root,'tmp','unknown');await fs.mkdir(unknownManaged)
  const outside=path.join(fixture,'outside');await fs.mkdir(outside);await fs.writeFile(path.join(outside,'sentinel.txt'),'keep')
  await fs.symlink(outside,path.join(first.directory,'external'),process.platform==='win32'?'junction':'dir')
  const plan=await prune({root,now})
  assert.deepEqual(new Set(plan.candidates.map(row=>row.directory)),new Set([first.directory,failed.directory]))
  assert.ok(await fs.stat(first.directory),'preview must not remove outputs')
  const applied=await prune({root,now,apply:true})
  assert.deepEqual(applied.errors,[]);assert.equal(applied.deleted.length,2)
  assert.equal(await fs.readFile(path.join(outside,'sentinel.txt'),'utf8'),'keep','junction target stays intact')
  for(const directory of [latest.directory,running.directory,unknown,unknownManaged])assert.ok((await fs.stat(directory)).isDirectory())
  const index=await writeIndex({root}),markdown=await fs.readFile(index.file,'utf8')
  assert.match(markdown,/old-unknown/);assert.match(markdown,/unknown/);assert.match(markdown,/unreviewed/)
  assert.doesNotMatch(markdown,/sentinel/,'index never scans into old directories or junction targets')
  const automaticOld=await createRun({label:'automatic-retention'},{root});await automaticOld.finish('success');await age(automaticOld)
  const automaticNew=await createRun({label:'automatic-retention'},{root});await automaticNew.finish('success')
  assert.equal(await fs.stat(automaticOld.directory).then(()=>true,()=>false),false,'finishing evidence automatically prunes its expired earlier success')
  assert.ok((await fs.stat(automaticNew.directory)).isDirectory());assert.ok((await fs.stat(unknown)).isDirectory(),'automatic pruning still preserves unknown history')
  const disappearing=path.join(root,'tmp','disappearing');await fs.mkdir(disappearing)
  const originalLstat=fs.lstat
  try {
    fs.lstat=async(filename,...args)=>{if(filename===disappearing)await fs.rmdir(disappearing);return originalLstat(filename,...args)}
    await writeIndex({root})
  }finally{fs.lstat=originalLstat}
  try {
    fs.lstat=async(filename,...args)=>{if(filename===unknown)throw Object.assign(Error('fixture permission denied'),{code:'EACCES'});return originalLstat(filename,...args)}
    await assert.rejects(writeIndex({root}),/fixture permission denied/,'only concurrent disappearance is ignored')
  }finally{fs.lstat=originalLstat}
  const cache=await createRun({label:'media',kind:'cache'},{root});await cache.finish('failed');await age(cache)
  assert.equal((await prune({root,now})).candidates.some(row=>row.directory===cache.directory),false)
  assert.equal((await prune({root,now,cacheDays:10})).candidates.some(row=>row.directory===cache.directory),true)
  const release=await createRun({label:'0.1.5-dev',kind:'release'},{root})
  assert.equal(path.dirname(release.directory),path.join(root,'releases'))
  await fs.writeFile(path.join(release.directory,'plugin.tgz'),'installable fixture')
  await fs.writeFile(path.join(release.directory,'release-manifest.json'),JSON.stringify({kind:'dsh-plugin-bundle',file:'plugin.tgz'}))
  await release.finish('success');await age(release)
  const secondRelease=await createRun({label:'0.1.5-dev',kind:'release'},{root})
  await secondRelease.finish('success');await age(secondRelease)
  assert.equal((await prune({root,now,cacheDays:0})).candidates.some(row=>row.kind==='release'),false,
    'release artifacts never inherit evidence or cache expiry')
  // Existing explicitly delivered paths and their historical kind stay intact.
  const legacyRelease=path.join(root,'releases','old-explicit');await fs.mkdir(legacyRelease)
  await beginDirectory(legacyRelease,{label:'old-release',kind:'evidence'},{root})
  await finishDirectory(legacyRelease,'success',{root})
  await age({directory:legacyRelease})
  assert.equal((await prune({root,now,cacheDays:0})).candidates.some(row=>row.directory===legacyRelease),false)
  await writeIndex({root})
  const grouped=await fs.readFile(path.join(root,'MANIFEST.md'),'utf8')
  assert(grouped.includes('## 安装包与交付')&&grouped.includes('## 审查与验证'))
  assert(grouped.includes('/plugin.tgz)'),'index exposes the actual local package inside releases')
  assert(grouped.includes('旧类别记录 evidence'),'presentation does not rewrite historical source metadata')
  assert.equal(JSON.parse(await fs.readFile(path.join(legacyRelease,manifestName),'utf8')).kind,'evidence')
  const stamped=path.join(root,'release');await fs.mkdir(stamped)
  assert.equal((await stampDirectory(stamped,{label:'release-0.1.2'},{root})).reuse,'unreviewed')
  assert.match(await fs.readFile(path.join(stamped,'MANIFEST.md'),'utf8'),/unreviewed/)
  const external=await fs.mkdtemp(path.join(cliTemporary,'dsh-output-cli-'));ownedExternal.push(external)
  const tool=path.resolve('tools/output-artifacts.mjs')
  const began=spawnSync(process.execPath,[tool,'begin',external,'--label','release-build','--kind','evidence','--isolation','unknown'],{encoding:'utf8',windowsHide:true})
  assert.equal(began.status,0,began.stderr)
  const buildStart=JSON.parse(began.stdout);assert.equal(buildStart.status,'running')
  const finished=spawnSync(process.execPath,[tool,'finish',external,'--status','success'],{env:{...process.env,PATH:''},encoding:'utf8',windowsHide:true})
  assert.equal(finished.status,0,finished.stderr)
  const buildFinish=JSON.parse(finished.stdout)
  assert.deepEqual([...sourceKeys,'createdAt'].map(name=>buildFinish[name]),[...sourceKeys,'createdAt'].map(name=>buildStart[name]),'separate CLI finish keeps the build start source without git')
  assert.deepEqual(await finishDirectory(external,'success',{root}),buildFinish,'same terminal status is idempotent')
  await assert.rejects(finishDirectory(external,'failed',{root}),/another status/)
  assert.ok((await fs.stat(external)).isDirectory(),'external output stays outside cleanup')
  const externalTmp=path.join(fixture,'external-temporary');await fs.mkdir(externalTmp)
  await beginDirectory(externalTmp,{label:'interrupted-output',kind:'tmp'},{root})
  const restarted=await beginDirectory(externalTmp,{label:'explicit-output',kind:'tmp'},{root})
  assert.equal(restarted.status,'running');assert.equal(restarted.label,'explicit-output','explicit begin starts a new batch after an interrupted prior run')
  await finishDirectory(externalTmp,'failed',{root})
  assert.ok((await fs.stat(externalTmp)).isDirectory(),'explicit external tmp is not a managed cleanup scope')
  await assert.rejects(finishDirectory(outside,'success',{root}),/valid begin manifest/)
  await assert.rejects(removeTree(root,root),/below/)
  await assert.rejects(removeTree(outside,root),/below/)
  await assert.rejects(createRun({label:'../escape'},{root}),/label/)
  const linkedRoot=path.join(fixture,'linked-output');await fs.symlink(root,linkedRoot,process.platform==='win32'?'junction':'dir')
  await assert.rejects(prune({root:linkedRoot,apply:true}),/real directory/)
  const linkedCategory=path.join(root,'cache-link');await fs.rename(path.join(root,'cache'),linkedCategory)
  await fs.symlink(outside,path.join(root,'cache'),process.platform==='win32'?'junction':'dir')
  await assert.rejects(prune({root,apply:true}),/real directory/)
  assert.equal(await fs.readFile(path.join(outside,'sentinel.txt'),'utf8'),'keep')
  await fs.unlink(path.join(root,'cache'));await fs.rename(linkedCategory,path.join(root,'cache'))
  await fs.unlink(linkedRoot)
  console.log('Output artifacts: source metadata, unreviewed index, retention preview/apply, latest success, unknown/running preservation and junction isolation passed')
}finally {
  for(const directory of ownedExternal) {
    assert.equal(path.dirname(directory),path.resolve(cliTemporary));assert.ok(path.basename(directory).startsWith('dsh-output-cli-'))
    await fs.rm(directory,{recursive:true,force:true})
  }
  assert.equal(path.dirname(fixture),path.resolve(os.tmpdir()))
  assert.ok(path.basename(fixture).startsWith('dsh-output-artifacts-'))
  await fs.rm(fixture,{recursive:true,force:true})
}
