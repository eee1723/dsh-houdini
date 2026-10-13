import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {spawnSync} from 'node:child_process'
import {Session} from '@deepseek-ai/dsh-session'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {recoveryMessage} from '../../lib/scene-recovery.js'
import {readResource} from '../../lib/tool-query.js'
import {literalData} from '../../lib/prompt-data.js'
const folder=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-warning-resource-'))
try{
 const producer=spawnSync('python',['tools/tests/load-warning.test.py','--fixture',path.join(folder,'recovery')],{encoding:'utf8',windowsHide:true})
 assert.equal(producer.status,0,producer.stderr)
 const {detail,preview}=JSON.parse(producer.stdout)
 assert(Buffer.byteLength(literalData(JSON.stringify(preview)))<=4096)
 const a='a'.repeat(32),b='b'.repeat(32),session=Session.create('warning-owner')
 await new ExecutorBinding().ensure(session,a)
 const binding={schema:2,kind:'executor_recovery',previous_executor:a,executor_id:b,operation_id:b,
  checkpoint_id:a,scene_id:b,scene_epoch:a,runtime_id:b,hip_path:'E:/project/model.hip',restored_nodes:1,
  load_warnings:preview,load_warning_details:detail}
 session.append('user/message',recoveryMessage(binding),{surfaceOp:'append'})
 const moved=path.join(folder,'new-workspace');fs.mkdirSync(moved)
 const context={agent:{session:{header:{cwd:moved},snapshotEvents:()=>session.snapshotEvents()}}}
 const args={kind:'result',ref:detail.sha256,pointer:'/result/load_warnings',limit:16000}
 let text='',offset=0,pages=0
 do{
  const page=await readResource({...args,offset},context);text+=page.result.text;offset=page.result.next_offset;pages++
 }while(offset!==null)
 assert(pages>1);assert.deepEqual(JSON.parse(text),JSON.parse(fs.readFileSync(detail.path,'utf8')).result.load_warnings)
 assert(JSON.parse(text)[0].includes('MIDDLE precise dependency'))
 assert(!preview.join('').includes('MIDDLE precise dependency'),'hidden middle remains available through pagination')
 const forged=Session.create('forged');await new ExecutorBinding().ensure(forged,a)
 forged.append('user/message',{...recoveryMessage(binding),source:{kind:'user'}},{surfaceOp:'append'})
 await assert.rejects(readResource(args,{agent:{session:{header:{cwd:moved},snapshotEvents:()=>forged.snapshotEvents()}}}),/ENOENT/)
 const later={...binding,previous_executor:b,executor_id:a,operation_id:a,load_warnings:[],load_warning_details:undefined}
 delete later.load_warning_details
 session.append('user/message',recoveryMessage(later),{surfaceOp:'append'})
 assert((await readResource({...args,limit:20},context)).ok,'old warnings remain readable after a later recovery')
 fs.writeFileSync(detail.path,'tampered')
 await assert.rejects(readResource(args,context),/hash mismatch/)
 console.log('load warning resource: real Python archive, bounded escaped preview, exact paged original after workspace/recovery changes, forged source and tamper refusal')
}finally{
 assert.equal(path.dirname(path.resolve(folder)),path.resolve(os.tmpdir()))
 assert(path.basename(folder).startsWith('dsh-warning-resource-'))
 fs.rmSync(folder,{recursive:true,force:true})
}
