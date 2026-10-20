import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import http from 'node:http'
import {createHash} from 'node:crypto'
import {resolveExecutionSource} from '../../lib/execution-source.js'
import {registerHoudiniTools} from '../../lib/tools.js'
import {HoudiniBridge} from '../../lib/bridge.js'
import {EXPECTED_EXECUTION_CONTRACT_VERSION,EXPECTED_VERB_CATALOG_HASH,EXPECTED_VERB_NAMES} from '../../lib/generated-verb-contract.js'

const directory=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-execution-source-'))
const filename=path.join(directory,'builder.py'),hash=bytes=>createHash('sha256').update(bytes).digest('hex')
const content='def build(parent):\n    return "可编辑节点"\n'
let denied=false,readFailure,readHook,resolveHook,readCalls=0,targetCalls=0,recoveryCalls=0,executions=[]
const definitions=new Map(),filesystem={
  async resolve(value,options){options.signal?.throwIfAborted();return {targetKey:path.resolve(options.cwd,value)}},
  processPath:target=>target.targetKey,processPathFromHostPath:value=>value,
  async readBytes(target,signal,limit){
    readCalls++;signal?.throwIfAborted()
    if(denied)throw Error('DSH file policy denied this read')
    if(readFailure)throw readFailure
    const bytes=await fs.readFile(target.targetKey)
    if(bytes.length>limit)throw Error('FS_TOO_LARGE')
    await readHook?.()
    return bytes
  },
}
const ctx={fs:filesystem,sandboxPolicy:{resolve:()=>({mode:'read-only',workspaceRoot:directory})},
  houdiniRecovery:{async beforeWrite(){recoveryCalls++}},tools:{register:definition=>definitions.set(definition.name,definition)}}
ctx.get=name=>ctx[name]
const exec={agent:{id:'source-owner',session:{header:{cwd:directory}}},callId:'source-call',signal:new AbortController().signal}
const receipt={ok:true,stdout:'',stderr:'',script:{path:filename,sha256:'bridge-authoritative',bytes:0}}
const fixture={async exec(...args){executions.push({kind:'exec',args});return structuredClone(receipt)},
  async submitJob(...args){executions.push({kind:'job',args});return {jobId:'123456abcdef'}}}
registerHoudiniTools(ctx,{async resolve(_exec,access){assert.equal(access.write,true);targetCalls++;await resolveHook?.();return fixture}})
const run=definitions.get('houdini_exec'),submit=definitions.get('houdini_job_submit')
async function rejectedBeforeTarget(args,pattern,call=run,context=exec){
  const targetBefore=targetCalls,recoveryBefore=recoveryCalls,executedBefore=executions.length
  await assert.rejects(call.execute(args,context),pattern)
  assert.equal(targetCalls,targetBefore,'source preflight must precede target selection')
  assert.equal(recoveryCalls,recoveryBefore,'source preflight must precede write restoration')
  assert.equal(executions.length,executedBefore,'source preflight must precede Python admission')
}

let server
try {
  await fs.writeFile(filename,content)
  const digest=hash(Buffer.from(content)),entry='__result__ = build("/obj/桌子")'
  const source=await resolveExecutionSource(ctx,exec,{script:filename,expected_sha256:digest.toUpperCase(),code:entry})
  assert.equal(source.code,content)
  assert.deepEqual(source.script,{path:filename,sha256:digest,bytes:Buffer.byteLength(content),entry})
  assert.deepEqual(await resolveExecutionSource({},exec,{code:'__result__ = 7'}),{code:'__result__ = 7'},'inline code needs no filesystem')
  await rejectedBeforeTarget({},/nonempty Python/)
  await rejectedBeforeTarget({code:'  '},/nonempty Python/)
  await rejectedBeforeTarget({expected_sha256:digest,code:'pass'},/requires script/)
  await rejectedBeforeTarget({script:'relative.py'},/absolute UTF-8/)
  await rejectedBeforeTarget({script:path.join(directory,'builder.txt')},/absolute UTF-8/)
  await rejectedBeforeTarget({script:filename,expected_sha256:'bad'},/64-character/)
  await fs.writeFile(filename,content+'# changed after independent check\n')
  await rejectedBeforeTarget({script:filename,expected_sha256:digest},/SHA-256 mismatch/)
  await rejectedBeforeTarget({script:filename,expected_sha256:digest},/SHA-256 mismatch/,submit)
  await fs.writeFile(filename,Buffer.from([0xff,0xfe,0x61]))
  await rejectedBeforeTarget({script:filename},/valid UTF-8/)
  await fs.writeFile(filename,Buffer.concat([Buffer.from([0xef,0xbb,0xbf]),Buffer.from(content)]))
  const bom=await resolveExecutionSource(ctx,exec,{script:filename})
  assert.equal(bom.code.charCodeAt(0),0xfeff,'the fingerprint includes the original UTF-8 BOM')
  assert.equal(hash(Buffer.from(bom.code)),bom.script.sha256)
  await fs.writeFile(filename,content)
  denied=true
  await rejectedBeforeTarget({script:filename},/DSH file policy denied/)
  denied=false;readFailure=Error('FS_TOO_LARGE')
  await rejectedBeforeTarget({script:filename},/FS_TOO_LARGE/)
  readFailure=undefined
  const cancelled=new AbortController();cancelled.abort()
  const beforeCancelReads=readCalls
  await rejectedBeforeTarget({script:filename},/abort/i,run,{...exec,signal:cancelled.signal})
  assert.equal(readCalls,beforeCancelReads,'already-cancelled calls do not start a file read')
  const duringRead=new AbortController();readHook=async()=>duringRead.abort()
  await rejectedBeforeTarget({script:filename},/abort/i,run,{...exec,signal:duringRead.signal})
  readHook=undefined
  const readsBefore=readCalls
  resolveHook=async()=>fs.writeFile(filename,'raise RuntimeError("later version")\n')
  const result=await run.execute({script:filename,expected_sha256:digest,code:entry},exec)
  resolveHook=undefined
  assert.equal(readCalls,readsBefore+1,'the source is read exactly once before any target work')
  assert.equal(result.script.sha256,'bridge-authoritative','Host preserves the original Python receipt without synthesizing script facts')
  assert.deepEqual(executions.at(-1).args,[content,{sessionId:'source-owner',callId:'source-call'},exec.signal,undefined,false,source.script])
  assert.deepEqual(run.presentCall({script:filename,code:entry}).rawInput,{script:filename,code:entry})
  assert.match(run.output.render({},result)[0].text,/script-source:[\s\S]*bridge-authoritative/)
  assert(Object.hasOwn(run.output.schema.properties,'script'),'the public schema accepts the original script receipt')
  await run.execute({code:'__result__ = 1'},exec)
  assert.equal(executions.at(-1).args[0],'__result__ = 1')
  assert.equal(executions.at(-1).args[5],undefined)
  await fs.writeFile(filename,content)
  assert.equal((await submit.execute({script:filename,code:entry},exec)).jobId,'123456abcdef')
  assert.deepEqual(executions.at(-1),{kind:'job',args:[content,{sessionId:'source-owner',callId:'source-call'},exec.signal,undefined,source.script]})
  assert.equal((await resolveExecutionSource(ctx,exec,{script:filename})).script.entry,undefined,'script-only calls need no invocation tail')

  const received=[]
  server=http.createServer(async(request,response)=>{
    const chunks=[];for await(const chunk of request)chunks.push(chunk)
    const body=JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}')
    response.setHeader('content-type','application/json')
    if(request.url==='/requests/prepare')response.end(JSON.stringify({ok:true,runtimeId:'a'.repeat(32),requestRef:'a'.repeat(32)+'.'+'b'.repeat(32),
      executionContractVersion:EXPECTED_EXECUTION_CONTRACT_VERSION,verbCatalog:{hash:EXPECTED_VERB_CATALOG_HASH,count:EXPECTED_VERB_NAMES.length,names:EXPECTED_VERB_NAMES}}))
    else {received.push({url:request.url,body});response.end(JSON.stringify(request.url==='/jobs'?{jobId:'123456abcdef'}:receipt))}
  })
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
  const bridge=new HoudiniBridge(`http://127.0.0.1:${server.address().port}`,1000),owner={sessionId:'source-owner',callId:'source-call'}
  await bridge.exec(source.code,owner,exec.signal,undefined,false,source.script)
  await bridge.submitJob(source.code,owner,exec.signal,undefined,source.script)
  for(const request of received){assert.equal(request.body.code,content);assert.deepEqual(request.body.script,source.script);assert.equal(request.body.owner_session,owner.sessionId)}
  assert.deepEqual(received.map(request=>request.url),['/exec','/jobs'])
  await bridge.exec('pass',owner)
  assert.equal(Object.hasOwn(received.at(-1).body,'script'),false,'inline HTTP execution stays unchanged')
  console.log('Builder source is frozen once through DSH reads, checked before target/recovery, and carried unchanged through exec/jobs and original presentation')
} finally {
  if(server)await new Promise(resolve=>server.close(resolve))
  await fs.rm(directory,{recursive:true,force:true})
}
