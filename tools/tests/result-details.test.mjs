import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {retainResult,readResultDetail} from '../../lib/result-details.js';
import {registerHoudiniTools} from '../../lib/tools.js';
import {normalizeTraceSteps} from '../normalized-trace-steps.mjs';

const dir=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-result-details-'));
try {
  const code='string source = "完整原始源码";\n'.repeat(2000);
  const raw={ok:true,stdout:'useful diagnostic',stderr:'',
    execution:{runtime_id:'runtime',sequence:1,observed_at:1,impact:{attempted:false,nodes:[]}},
    transaction:{status:'committed',nodes:[{identity:1,path:'/obj/a',exists:true}]},
    verbs:[{verb:'set_parms',ok:true,args:['/obj/a',{snippet:code}],kwargs:{},result:{ok:true,set:{snippet:code}},ms:1}],
    result:{payload:'原始结果'.repeat(5000)}};
  const definitions=new Map();let executions=0;
  registerHoudiniTools({tools:{register:d=>definitions.set(d.name,d)}},
    {async exec(){executions++;return raw;},async hipDir(){return dir;}});
  const context={agent:{id:'agent',session:{header:{cwd:dir}}},callId:'call'};
  const exec=definitions.get('houdini_exec'),query=definitions.get('houdini_query');
  const before=JSON.stringify(raw);
  const value=await exec.execute({code:'set_parms(...)'},context);
  assert.equal(value.details.stored,true);
  assert.deepEqual(JSON.parse(fs.readFileSync(value.details.path,'utf8')),raw);
  const compact=exec.output.render({},value)[0].text;
  const original=exec.output.render({},raw)[0].text;
  assert.ok(compact.length<original.length*0.25,[compact.length,original.length]);
  assert.ok(compact.includes('useful diagnostic') && compact.includes('result-details'));
  const meta=exec.output.presentationMeta({},value);
  assert.deepEqual(meta.canonical.verbs,raw.verbs,'durable audit retains full args/results outside model text');
  assert.equal(JSON.stringify(raw),before,'projection and retention do not mutate the original envelope');
  let collected='',offset=0;
  do {
    const page=await query.execute({result_ref:value.details.sha256,pointer:'/result/payload',offset,limit:16000},context);
    collected+=page.result.text;
    offset=page.result.next_offset;
  }while(offset!==null);
  assert.equal(JSON.parse(collected),raw.result.payload);
  assert.equal(executions,1,'detail retrieval never repeats HOM or scene edits');
  await assert.rejects(query.execute({code:'x',result_ref:value.details.sha256},context),/exactly one/);
  await assert.rejects(query.execute({code:'x',pointer:'/result'},context),/require result_ref/);
  await assert.rejects(readResultDetail(dir,'../escape'),/SHA-256/);
  await assert.rejects(readResultDetail(dir,value.details.sha256,'/missing'),/not found/);
  await assert.rejects(readResultDetail(dir,value.details.sha256,'/__proto__'),/not found/);
  await assert.rejects(readResultDetail(dir,value.details.sha256,'',0,16001),/1..16000/);
  const warning={...raw,checks:[{verb:'test_controls',status:'unverified'}],
    evidence:[{ledgerIndex:1,verb:'test_controls',ok:false,restored:false,unsupported:['external solver'],reason:'restore failed',details:code}],
    result:{ok:false,warnings:['important warning'],details:code},
    rollback:{supported:true,applied:false,error:'rollback failure'},
    imageAttachments:[{from:'source',error:'relay failed'}],advisory:'ownership boundary'};
  const warningText=exec.output.render({},await retainResult(warning,dir))[0].text;
  for(const text of ['restore failed','external solver','important warning','rollback failure','relay failed','ownership boundary'])assert.ok(warningText.includes(text),text);
  const missing=await retainResult(raw,path.join(dir,'missing-workspace'));
  assert.equal(missing.details.stored,false);
  assert.ok(exec.output.render({},missing)[0].text.includes(JSON.stringify(raw.verbs[0].args)),'retention failure disables compact rendering');
  assert.equal(await retainResult(raw,null),raw);
  const events=[{seq:1,type:'tool/call',data:{callId:'c',name:'houdini_exec',arguments:{code:'set_parms(...)'}}},
    {seq:2,type:'tool/result',data:{meta,message:{source:{callId:'c'},content:[{type:'tool_result',content:[{type:'text',text:compact}]}]}}}];
  const step=normalizeTraceSteps(events).steps[0];
  assert.equal(step.verbs[0].args,JSON.stringify(raw.verbs[0].args));
  assert.deepEqual(step.verbs[0].result,raw.verbs[0].result);
  assert.equal(step.resultText.length,compact.length,'cost counts actual model text, not expanded audit metadata');
  fs.writeFileSync(value.details.path,'tampered');
  await assert.rejects(readResultDetail(dir,value.details.sha256),/hash mismatch/);
  assert.equal((await retainResult(raw,dir)).details.stored,false,'existing corrupt artifacts are not silently overwritten');
  console.log(`result details: compact ${compact.length}/${original.length} chars; canonical roundtrip, paged query, caution/failure fallback and tamper protection passed`);
} finally {
  assert.equal(path.dirname(path.resolve(dir)),path.resolve(os.tmpdir()));
  assert.ok(path.basename(dir).startsWith('dsh-result-details-'));
  fs.rmSync(dir,{recursive:true,force:true});
}
