import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import {execFileSync} from 'node:child_process';
import {normalizeTraceSteps} from '../normalized-trace-steps.mjs';
import {processOutcomeFor} from '../../skills/houdini-trace-analysis/scripts/evidence-helpers.mjs';

// Reduced test69 native outcomes retain their original error/trailer and event
// sequence; task-specific image processing code and file paths are unnecessary.
const events=JSON.parse(fs.readFileSync(new URL('./fixtures/test69-shell-exits.json',import.meta.url),'utf8'));
const native=normalizeTraceSteps(events).steps;
assert.deepEqual(native.map(s=>s.resultSeq),[756,767]);
for(const step of native){
  assert.equal(step.failed,false,'successful tool delivery is separate from the process outcome');
  assert.deepEqual(step.processOutcome,{status:'failed',exitCode:1,source:'shell_result_trailer'});
}
const nested=events.map(e=>e.type==='tool/call'
  ? {...e,type:'tool/ptc-dispatch-start',data:{...e.data,subCallId:e.data.callId,parentCallId:'program'}}
  : {...e,type:'tool/ptc-dispatch',data:{subCallId:e.data.message.source.callId,parentCallId:'program',name:'pwsh',
      isError:e.data.message.isError,content:e.data.message.content}});
assert.deepEqual(normalizeTraceSteps(nested).steps.map(s=>s.processOutcome),native.map(s=>s.processOutcome));
for(const tool of ['pwsh','bash']){
  assert.equal(processOutcomeFor(tool,'Error was handled\n[exit code: 0]').status,'succeeded');
  assert.equal(processOutcomeFor(tool,'Error: sample, not an exit fact').status,'unknown');
  assert.equal(processOutcomeFor(tool,'[exit code: 1]\nmore output').status,'unknown','only the terminal shell trailer is evidence');
  assert.equal(processOutcomeFor(tool,'[exit code: 1]\n[exit code: 0]').exitCode,0);
  assert.equal(processOutcomeFor(tool,'[exit code: 1]',{exitCode:0}).status,'succeeded','structured result wins over arbitrary text');
  assert.equal(processOutcomeFor(tool,'[exit code: 1]',{exitCode:null}).status,'unknown','structured unknown must not become a guessed text status');
  assert.equal(processOutcomeFor(tool,'Error: harmless output').status,'unknown','absence of a trailer does not prove exit zero');
  assert.deepEqual(processOutcomeFor(tool,'[timed out after 30000ms]\n[exit code: 1]'),
    {status:'interrupted',exitCode:1,source:'shell_result_trailer',interruption:'timed_out'});
  assert.equal(processOutcomeFor(tool,'[stopped: tool call aborted]\n[exit code: 1]').status,'interrupted');
  assert.equal(processOutcomeFor(tool,'[killed by signal: SIGTERM]').interruption,'signal');
  assert.equal(processOutcomeFor(tool,'[exit code: 0]',{exitCode:0,timedOut:true}).status,'interrupted','termination takes precedence over exit code zero');
  assert.equal(processOutcomeFor(tool,'[stopped: fake]\n[exit code: 1]',{exitCode:0,timedOut:false,aborted:false,signal:null}).status,'succeeded','structured completion takes precedence over printed markers');
}
assert.equal(processOutcomeFor('read','[exit code: 1]'),null);
assert.equal(processOutcomeFor('houdini_exec','[exit code: 1]'),null);
const printedError=structuredClone(events.slice(0,2));
printedError[1].data.message.content=[{type:'text',text:'Error: handled message\n[exit code: 0]'}];
assert.equal(normalizeTraceSteps(printedError).steps[0].failed,false,'shell diagnostic text is not tool delivery failure');
assert.equal(normalizeTraceSteps(printedError).steps[0].processOutcome.status,'succeeded');
printedError[1].data.message.isError=true;
assert.equal(normalizeTraceSteps(printedError).steps[0].failed,true,'real tool delivery failures still count separately');
for(const source of [events,nested]){
  const structured=structuredClone(source);
  for(const event of structured) if(event.type==='tool/result'||event.type==='tool/ptc-dispatch')event.data.meta={exitCode:0};
  assert(normalizeTraceSteps(structured).steps.every(step=>step.processOutcome.status==='succeeded'),'native and nested metadata must reach the common projection');
}
const interrupted=structuredClone(events.slice(0,2));
interrupted[0].seq=800;interrupted[0].data.callId='interrupted-process';
interrupted[1].seq=801;interrupted[1].data.message.source.callId='interrupted-process';
interrupted[1].data.message.content=[{type:'text',text:'partial output\n[timed out after 30000ms]\n[exit code: 1]'}];
const interruptedStep=normalizeTraceSteps(interrupted).steps[0];
assert.equal(interruptedStep.failed,false);
assert.equal(interruptedStep.processOutcome.status,'interrupted');

// Exercise the public extractor and standalone HTML from real source events,
// not only the helper. No process in the fixture is executed.
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-trace-process-'));
try{
  const session=path.join(directory,'session.jsonl.zstd'),json=path.join(directory,'evidence.json'),html=path.join(directory,'report.html');
  fs.writeFileSync(session,zlib.zstdCompressSync(Buffer.from([...events,...interrupted].map(e=>JSON.stringify(e)).join('\n'))));
  execFileSync(process.execPath,['skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs',session,'--out',json],{cwd:new URL('../../',import.meta.url),stdio:'pipe'});
  const evidence=JSON.parse(fs.readFileSync(json,'utf8'));
  assert.deepEqual(evidence.traces[0].failedCalls,[]);
  assert.deepEqual(evidence.traces[0].processFailures.map(s=>s.resultSeq),[756,767]);
  assert.equal(evidence.aggregate.processFailures,2);
  assert.equal(evidence.aggregate.processInterruptions,1);
  assert.equal(evidence.traces[0].processInterruptions[0].interruption,'timed_out');
  execFileSync(process.execPath,['tools/trace-report.mjs',session,'--out',html],{cwd:new URL('../../',import.meta.url),stdio:'pipe'});
  const report=fs.readFileSync(html,'utf8');
  assert(report.includes('命令进程退出失败（独立统计）'));
  assert.equal(report.match(/进程退出 1/g).length,2);
  assert(report.includes('进程终止 · timed_out'));
}finally{
  assert.equal(path.dirname(path.resolve(directory)),path.resolve(os.tmpdir()));
  assert(path.basename(directory).startsWith('dsh-trace-process-'));
  fs.rmSync(directory,{recursive:true,force:true});
}
console.log('Actual test69 shell exits: native/nested, transport distinction, structured precedence, extractor and HTML passed');
