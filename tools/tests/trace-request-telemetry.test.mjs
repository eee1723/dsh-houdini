import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import {execFileSync} from 'node:child_process';
const root = path.resolve(import.meta.dirname,'../..');
const temp = fs.mkdtempSync(path.join(os.tmpdir(),'dsh-trace-request-'));
try {
  const event = (seq,type,data) => ({seq,time:1000+seq,type,data});
  const events = [
    event(1,'user/message',{source:{kind:'user'},content:[{type:'text',text:'请做一个细致的近景资产，表面质感需要参考。'}]}),
    event(2,'turn/end',{turn:1,reason:{kind:'error',error:{code:'INVALID_REQUEST',message:'model unavailable'}}}),
    event(3,'user/message',{source:{kind:'user'},content:[{type:'text',text:'继续'}]}),
    event(4,'tool/call',{callId:'call',name:'houdini_query',arguments:{code:'print(hou.applicationVersionString())'}}),
    event(5,'tool/result',{turn:2,step:1,message:{source:{callId:'call'},content:[{type:'tool_result',content:[{type:'text',text:'21.0'}]}]}}),
    event(6,'assistant/chunk',{turn:2,step:1,chunk:{type:'usage',usage:{inputTokens:10,cacheReadTokens:30,outputTokens:2,totalTokens:42}}}),
    event(7,'turn/end',{turn:2,reason:{kind:'completed'}}),
  ];
  const input = path.join(temp,'session.jsonl.zstd');
  const output = path.join(temp,'evidence.json');
  fs.writeFileSync(input,zlib.zstdCompressSync(events.map(e=>JSON.stringify(e)).join('\n')));
  execFileSync(process.execPath,['skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs',input,'--out',output],{cwd:root});
  const t=JSON.parse(fs.readFileSync(output,'utf8')).traces[0];
  assert.equal(t.taskTiming.initialRequest.seq,1,'continue after provider failure is not the original request');
  assert.equal(t.taskTiming.firstToolLatencyMs,3);
  assert.equal(t.qualityLoopEvidence.applicable,true);
  assert.equal(t.requestTelemetry.last.inputWithCache,40);
  assert.equal(t.requestTelemetry.upstreamTurnErrors.length,1);
  assert.equal(t.failedCalls.length,0,'provider error is separate from tool failure');
  assert.equal(t.retryWork.codeCalls,1);
  const report = path.join(temp,'report.html');
  execFileSync(process.execPath,['tools/trace-report.mjs',input,'--out',report],{cwd:root});
  const html=fs.readFileSync(report,'utf8');
  assert.ok(html.includes('model unavailable') && html.includes('40 tokens'));
} finally {
  assert.equal(path.dirname(path.resolve(temp)),path.resolve(os.tmpdir()));
  assert.ok(path.basename(temp).startsWith('dsh-trace-request-'));
  fs.rmSync(temp,{recursive:true,force:true});
}
console.log('trace original-request/quality/provider-error/usage extraction and HTML regression passed');
