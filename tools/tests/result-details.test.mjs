import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {retainResult,readResultDetail} from '../../lib/result-details.js';
import {registerHoudiniTools} from '../../lib/tools.js';
import {normalizeTraceSteps} from '../normalized-trace-steps.mjs';
import {readResource} from '../../lib/tool-query.js';
import {HoudiniToolRuntime} from '../../lib/tool-runtime.js';
import {LIVE_JOB_KIND,LIVE_JOB_RESULT} from '../../lib/dsh-adapter.js';

// Use retention's native async resolver: Windows short names can survive realpathSync.
const dir=await fs.promises.realpath(fs.mkdtempSync(path.join(os.tmpdir(),'dsh-result-details-')));
try {
  const code='string source = "完整原始源码";\n'.repeat(2000);
  const raw={ok:true,stdout:'useful diagnostic',stderr:'',
    execution:{runtime_id:'runtime',sequence:1,observed_at:1,impact:{attempted:false,nodes:[]}},
    transaction:{status:'committed',nodes:[{identity:1,path:'/obj/a',exists:true}]},
    verbs:[{verb:'set_parms',ok:true,check_status:'passed',args:['/obj/a',{snippet:code}],kwargs:{},result:{ok:true,set:{snippet:code}},ms:1}],
    result:{payload:'原始结果'.repeat(5000)}};
  const definitions=new Map();let executions=0;
  registerHoudiniTools({tools:{register:d=>definitions.set(d.name,d)}},
    {async exec(){executions++;return raw;},async hipDir(){return dir;}});
  const context={agent:{id:'agent',session:{header:{cwd:dir}}},callId:'call'};
  const exec=definitions.get('houdini_exec'),query=definitions.get('houdini_resource');
  const before=JSON.stringify(raw);
  const readonlyWorkspace=path.join(dir,'readonly-workspace');fs.mkdirSync(readonlyWorkspace);
  const readonlyContext={...context,agent:{...context.agent,session:{header:{cwd:readonlyWorkspace}}}};
  const readonlyRuntime=new HoudiniToolRuntime({get:name=>name==='sandboxPolicy'?{
    resolve:({session})=>{assert.equal(session,readonlyContext.agent.session);return {mode:'read-only'};},
  }:undefined},{});
  for(const result of [await readonlyRuntime.result(raw,readonlyContext,{}),await readonlyRuntime.retain(raw,readonlyContext)]) {
    assert.equal(result.ok,true,'archive policy never changes the successful operation outcome');
    assert.equal(result.details.stored,false);assert.match(result.details.error,/read-only/);
    const {details,...original}=result;assert.deepEqual(original,raw,'the complete original receipt survives read-only archival');
    assert.ok(exec.output.render({},result)[0].text.includes(JSON.stringify(raw.verbs[0].args)),
      'read-only archival keeps complete inline rendering');
  }
  assert.deepEqual(fs.readdirSync(readonlyWorkspace),[],'read-only result presentation creates no project files or directories');
  const value=await exec.execute({code:'set_parms(...)'},context);
  assert.equal(value.details.stored,true);
  assert.equal(path.relative(dir,value.details.path),path.join('dsh-artifacts','results',value.details.sha256+'.json'));
  const legacy=path.join(dir,'.dsh-houdini-results',value.details.sha256+'.json');
  fs.mkdirSync(path.dirname(legacy));fs.copyFileSync(value.details.path,legacy);
  assert.equal((await readResultDetail(dir,value.details.sha256,'/result/payload',0,16000,legacy)).result.text,
    JSON.stringify(raw.result.payload,null,2).slice(0,16000),'recorded legacy paths remain readable');
  const redirected=path.join(dir,'redirected'),outside=path.join(dir,'outside');
  fs.mkdirSync(redirected);fs.mkdirSync(outside);
  fs.symlinkSync(outside,path.join(redirected,'dsh-artifacts'),process.platform==='win32'?'junction':'dir');
  assert.equal((await retainResult(raw,redirected)).details.stored,false);
  assert.deepEqual(fs.readdirSync(outside),[],'reject a redirected artifact root before creating children');
  fs.unlinkSync(path.join(redirected,'dsh-artifacts'));
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
    const page=await query.execute({kind:"result",ref:value.details.sha256,pointer:'/result/payload',offset,limit:16000},context);
    collected+=page.result.text;
    offset=page.result.next_offset;
  }while(offset!==null);
  assert.equal(JSON.parse(collected),raw.result.payload);
  assert.equal(executions,1,'detail retrieval never repeats HOM or scene edits');
  const catalog=Array.from({length:1100},(_,i)=>({name:'parameter_'+i,menu:[{token:'x',label:'X'}]}));
  const catalogEnvelope=await retainResult({ok:true,stdout:'',stderr:'',verbs:[{verb:'list_parms',ok:true,result:catalog}]},dir);
  const leaf=await readResultDetail(dir,catalogEnvelope.details.sha256,'/verbs/0/result/1099/menu/0/token');
  assert.equal(JSON.parse(leaf.result.text),'x','large typed catalogs remain addressable below the array item');
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
  const moved=path.join(dir,'save-as');fs.mkdirSync(moved);
  const args={kind:'result',ref:value.details.sha256,pointer:'/result/payload',limit:16000};
  const native=events;
  const nested=[
    {type:'tool/ptc-dispatch-start',data:{subCallId:'nested',name:'houdini_exec'}},
    {type:'tool/ptc-dispatch',data:{subCallId:'nested',name:'houdini_exec',content:[{type:'text',text:JSON.stringify({
      kind:'dsh-houdini/execution-v1',callId:'nested',tool:'houdini_exec',value,
    })}]}},
  ];
  const nativeRead={job:{kind:LIVE_JOB_KIND,id:'houdini-live-details'},text:JSON.stringify({kind:LIVE_JOB_RESULT,job_id:'houdini-live-details',value})};
  const nativeJob=[{type:'tool/call',data:{callId:'job-read',name:'job_output'}},
    {type:'tool/result',data:{message:{source:{callId:'job-read'},content:[{type:'text',text:'[output truncated]'}]},meta:{canonical:nativeRead}}}];
  const nestedJob=[{type:'tool/ptc-dispatch-start',data:{subCallId:'nested-job',name:'job_output'}},
    {type:'tool/ptc-dispatch',data:{subCallId:'nested-job',name:'job_output',content:[{type:'text',text:JSON.stringify({
      kind:'dsh-houdini/execution-v1',callId:'nested-job',tool:'job_output',value:nativeRead})}]}}];
  const metadataJob=structuredClone(nestedJob);metadataJob[1].data.meta={canonical:nativeRead};metadataJob[1].data.content=[{type:'text',text:'[output truncated]'}];
  for(const history of [native,nested,nativeJob,nestedJob,metadataJob]) {
    const context={agent:{session:{header:{cwd:moved},snapshotEvents:()=>structuredClone(history)}}};
    const page=await readResource(args,context);
    assert.equal(page.result.text,JSON.stringify(raw.result.payload,null,2).slice(0,16000),
      'native and nested execution/job results survive a saved-project directory change');
  }
  const generic=structuredClone(nativeJob);generic[1].data.meta.canonical.job.kind='bash';
  // Real checker archives use builder/check names and live inside the original
  // run, not the Host's content-addressed results directory. Both run and read
  // expose them, including failed checks and in-progress worker observations.
  const isolatedFile=path.join(dir,'executions','builder.json'),checkFile=path.join(dir,'executions','check-mechanical.json');
  fs.mkdirSync(path.dirname(isolatedFile));fs.copyFileSync(value.details.path,isolatedFile);fs.copyFileSync(value.details.path,checkFile);
  const execution={ok:false,details:{...value.details,path:isolatedFile}};
  const checkExecution={ok:false,details:{...value.details,path:checkFile}};
  const isolatedValues=[
    {kind:'isolated-houdini',run_directory:dir,ok:true,report:{result:{builder:execution}}},
    {kind:'isolated-houdini',run_directory:dir,report:{ok:false,result:{checks:[{id:'mechanical',execution:checkExecution}]}}},
    {kind:'isolated-houdini',run_directory:dir,report:{finished:false},progress:{builder:execution}},
  ];
  for(const isolated of isolatedValues)for(const ptc of [false,true]){
    const history=ptc?[
      {type:'tool/ptc-dispatch-start',data:{subCallId:'iso',name:'houdini_isolated'}},
      {type:'tool/ptc-dispatch',data:{subCallId:'iso',name:'houdini_isolated',meta:{canonical:isolated}}},
    ]:[
      {type:'tool/call',data:{callId:'iso',name:'houdini_isolated'}},
      {type:'tool/result',data:{message:{source:{callId:'iso'}},meta:{canonical:isolated}}},
    ];
    const page=await readResource(args,{agent:{session:{header:{cwd:moved},snapshotEvents:()=>history}}});
    assert.equal(page.result.text,JSON.stringify(raw.result.payload,null,2).slice(0,16000));
    const forged=structuredClone(history);
    const data=forged[1].data.meta.canonical;
    delete data.report;delete data.progress;data.result={builder:execution};
    await assert.rejects(readResource(args,{agent:{session:{header:{cwd:moved},snapshotEvents:()=>forged}}}),/ENOENT/,
      'an arbitrary authored result cannot register an archive');
  }
  const wrongName=path.join(dir,'executions','other.json');fs.copyFileSync(value.details.path,wrongName);
  await assert.rejects(readResultDetail(moved,value.details.sha256,'',0,6000,wrongName),/declared isolated archive/);
  const misplaced=path.join(dir,'builder.json');fs.copyFileSync(value.details.path,misplaced);
  const misplacedValue={kind:'isolated-houdini',run_directory:dir,report:{result:{builder:{...execution,
    details:{...execution.details,path:misplaced}}}}};
  const misplacedHistory=[{type:'tool/call',data:{callId:'iso',name:'houdini_isolated'}},
    {type:'tool/result',data:{message:{source:{callId:'iso'}},meta:{canonical:misplacedValue}}}];
  await assert.rejects(readResource(args,{agent:{session:{header:{cwd:moved},snapshotEvents:()=>misplacedHistory}}}),/ENOENT/,
    'a same-named file outside the recorded run executions directory is not an archive');
  fs.writeFileSync(isolatedFile,'tampered');
  await assert.rejects(readResultDetail(moved,value.details.sha256,'',0,6000,isolatedFile),/hash mismatch/);
  for(const history of [
    [{type:'user/message',data:{content:[{type:'text',text:JSON.stringify(value)}]}}],
    [{...events[0],data:{...events[0].data,name:'unrelated_tool'}},events[1]],
    [events[1]],
    generic,
  ]) {
    await assert.rejects(readResource(args,{agent:{session:{header:{cwd:moved},snapshotEvents:()=>history}}}),/ENOENT/);
  }
  fs.writeFileSync(value.details.path,'tampered');
  await assert.rejects(readResource(args,{agent:{session:{header:{cwd:moved},snapshotEvents:()=>native}}}),/hash mismatch/);
  await assert.rejects(readResultDetail(dir,value.details.sha256),/hash mismatch/);
  assert.equal((await retainResult(raw,dir)).details.stored,false,'existing corrupt artifacts are not silently overwritten');
  console.log(`result details: compact ${compact.length}/${original.length} chars; canonical roundtrip, paged query, caution/failure fallback and tamper protection passed`);
} finally {
  assert.equal(path.dirname(dir),await fs.promises.realpath(os.tmpdir()));
  assert.ok(path.basename(dir).startsWith('dsh-result-details-'));
  fs.rmSync(dir,{recursive:true,force:true});
}
