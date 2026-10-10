import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import {execFileSync} from 'node:child_process';
import {Session, SESSION_FORMAT_VERSION} from '@deepseek-ai/dsh-session';
import {createSystemMessage,createUserMessage,createAssistantMessage,createToolResultMessage} from '@deepseek-ai/dsh-llm';
import {loadSessionEvents} from '../trace-session-lib.mjs';

const root = path.resolve(import.meta.dirname, '../..');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-trace-risks-'));
try {
  const event = (seq, type, data) => ({seq, time: 1000 + seq, type, data});
  const events = [
    event(1, 'request/header', {header: {
      config: {model: 'fixture-model'},
      system: '',
      tools: [{name: 'component_delegate'}, {name: 'houdini_exec'}],
    }}),
    event(2, 'user/message', {
      source: {kind: 'user'},
      content: [{type: 'text', text: '用总控统一调整四个部件，验证联动和装配不炸。'}],
    }),
    event(3, 'assistant/message', {message: {content: [{
      type: 'text',
      text: '先建立总控与装配关系，检查接地和贴合，再做证据预览。',
    }]}}),
    event(4, 'tool/call', {
      callId: 'todo',
      name: 'todo_write',
      arguments: {todos: [{content: 'Check divisions parameter', status: 'completed'}]},
    }),
    event(5, 'tool/result', {message: {
      source: {callId: 'todo'},
      content: [{type: 'tool_result', content: [{type: 'text', text: 'Updated todo list'}]}],
    }}),
    event(6, 'tool/call', {
      callId: 'render',
      name: 'houdini_exec',
      arguments: {code: 'render_view(output)'},
    }),
    event(7, 'tool/result', {
      message: {
        source: {callId: 'render'},
        content: [{type: 'tool_result', content: [{type: 'text', text: 'retained canonical result'}]}],
      },
      meta: {canonical: {
        ok: true,
        transaction: {status: 'no_scene_change'},
        execution: {read_only: false},
        verbs: [{
          verb: 'render_view',
          ok: true,
          result: {ok: true, warnings: ['attribute mismatch'], warnings_count: 1},
        }],
      }},
    }),
    event(8, 'assistant/message', {message: {
      content: [{type: 'text', text: '数值检查完成。'}],
    }}),
    event(9, 'turn/end', {turn: 1, reason: {kind: 'completed'}}),
  ];
  const input = path.join(temp, 'session.jsonl.zstd');
  const output = path.join(temp, 'evidence.json');
  fs.writeFileSync(input, zlib.zstdCompressSync(events.map((row) => JSON.stringify(row)).join('\n')));
  execFileSync(process.execPath, [
    'skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs',
    input,
    '--out',
    output,
  ], {cwd: root});
  const trace = JSON.parse(fs.readFileSync(output, 'utf8')).traces[0];

  assert.equal(trace.capabilitySnapshots.length, 1,
    'tools remain evidence when request/header.system is empty');
  assert.deepEqual(trace.capabilitySnapshots[0].availableTools, ['component_delegate', 'houdini_exec']);
  assert.equal(trace.qualityLoopEvidence.contract.requirements.controls, true);
  assert.equal(trace.qualityLoopEvidence.contract.requirements.relations, true);
  assert.equal(trace.qualityLoopEvidence.contract.fields.controls, true);
  assert.equal(trace.qualityLoopEvidence.contract.fields.relations, true);
  assert(trace.completionRisks.some((risk) => risk.code === 'render_with_warnings'));
  assert(!trace.completionRisks.some((risk) => risk.code === 'completed_vision_todo_without_image_access'),
    '`divisions` must not be parsed as the English word `vision`');

  // The current native format must pass through discovery, decompression,
  // surface reconstruction, result normalization, context extraction and HTML.
  const current = Session.create('current-trace-fixture');
  current.append('system/message',{turn:1,step:1,message:createSystemMessage('Houdini fixture.','fixture')},{surfaceOp:'append'});
  current.append('user/message',createUserMessage({source:{kind:'user'},
    content:[{type:'text',text:'Inspect the current scene.'}]}),{surfaceOp:'append'});
  const contextText='Houdini fixture scene: E:/tmp/current/test.hip';
  current.append('user/message',createUserMessage({source:{kind:'runtime-context',form:'snapshot',
    sections:[{name:'dsh-houdini:scene-context',text:contextText}]},
    content:[{type:'text',text:contextText}]}),{surfaceOp:'append'});
  current.append('request/header',{header:{config:{model:'fixture'},tools:[{name:'houdini_inspect'}]}});
  current.append('assistant/message',{turn:1,step:1,stream:[],
    message:createAssistantMessage({source:{provider:'fixture',model:'fixture'},
      content:[{type:'tool-call',id:'current-call',name:'houdini_inspect',arguments:'{}'}]})},{surfaceOp:'append'});
  current.append('tool/call',{turn:1,step:1,callId:'current-call',name:'houdini_inspect',arguments:{}});
  const directText='Current fixture result: scene_info succeeded';
  current.append('tool/result',{turn:1,step:1,message:createToolResultMessage({callId:'current-call',
    content:[{type:'text',text:directText}],isError:false}),meta:{canonical:{ok:true,verbs:[],
      execution:{runtime_id:'fixture-runtime',sequence:1,read_only:true}}}},{surfaceOp:'append'});
  current.append('assistant/message',{turn:1,step:2,stream:[],
    message:createAssistantMessage({source:{provider:'fixture',model:'fixture'},
      content:[{type:'text',text:'Inspection returned the actual scene.'}]})},{surfaceOp:'append'});
  const nativeEvents=current.snapshotEvents().map(row=>({...row,time:1000+row.seq}));
  const currentInput=path.join(temp,'session.v4.jsonl.zstd');
  const currentOutput=path.join(temp,'current-evidence.json');
  fs.writeFileSync(currentInput,zlib.zstdCompressSync([
    JSON.stringify({type:'session',version:SESSION_FORMAT_VERSION}),
    ...nativeEvents.map(row=>JSON.stringify(row)),
  ].join('\n')));
  execFileSync(process.execPath,['skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs',
    temp,'--out',currentOutput],{cwd:root});
  const currentTrace=JSON.parse(fs.readFileSync(currentOutput,'utf8')).traces[0];
  assert.equal(currentTrace.file,currentInput);
  assert.equal(currentTrace.toolCalls,1);
  assert.equal(currentTrace.unmatchedResults.length,0);
  assert.equal(currentTrace.executionCost.resultChars,directText.length);
  assert.deepEqual(currentTrace.activeJobs,[]);
  assert.deepEqual(currentTrace.unavailableResults,[]);
  assert.deepEqual(currentTrace.observationContexts,[{seq:2,time:1002,text:contextText}]);
  assert(currentTrace.requestContexts.every(row=>row.projectionComplete));
  const report=path.join(temp,'current-report.html');
  execFileSync(process.execPath,['tools/trace-report.mjs',temp,'--out',report],{cwd:root});
  assert(fs.readFileSync(report,'utf8').includes(directText),'offline HTML retains native role=tool output');
  assert(fs.readFileSync(report,'utf8').includes('无未查回回执不等于全部后台任务已完成'));

  // Submission recovery and background completion are separate. Use original
  // native/nested events: normalization excludes admission-only operations.
  const jobEvents=[];
  let jobSeq=100;
  const jobResult=(id,name,value,nested=false)=>{
    jobEvents.push(event(jobSeq++,nested?'tool/ptc-dispatch-start':'tool/call',nested
      ? {subCallId:id,parentCallId:'program',name,arguments:{}}
      : {callId:id,name,arguments:{}}));
    jobEvents.push(event(jobSeq++,nested?'tool/ptc-dispatch':'tool/result',nested
      ? {subCallId:id,parentCallId:'program',name,
         content:[{type:'text',text:JSON.stringify({kind:'dsh-houdini/execution-v1',callId:id,tool:name,value})}]}
      : {message:{source:{callId:id},content:[{type:'text',text:'Retained job observation'}]},meta:{canonical:value}}));
  };
  jobResult('running-submit','houdini_job_submit',{jobId:'native-running',requestReceipt:{
    request_ref:'running-admission',owner_call:'running-submit',status:'job_submitted'}});
  jobResult('running-recovery','houdini_request',{jobId:'native-running',requestReceipt:{
    request_ref:'running-admission',owner_call:'running-submit',status:'job_submitted',
    job_status:'running',job_finished:false}});
  jobResult('nested-submit','houdini_job_submit',{jobId:'nested-queued',requestReceipt:{
    request_ref:'nested-admission',owner_call:'nested-submit',status:'job_submitted'}},true);
  jobResult('missing-result','houdini_request',{jobId:'missing-result-job',requestReceipt:{
    request_ref:'missing-admission',owner_call:'missing-submit',status:'result_expired',
    job_status:'done',job_finished:true,job_result_available:false}});
  jobResult('cleared-submit','houdini_job_submit',{jobId:'collected-job',requestReceipt:{
    request_ref:'cleared-admission',owner_call:'cleared-submit',status:'job_submitted'}});
  jobResult('cleared-status','houdini_job_status',{jobId:'collected-job',status:'done',ok:true});
  jobResult('late-admission','houdini_request',{jobId:'collected-job',requestReceipt:{
    request_ref:'cleared-admission',owner_call:'cleared-submit',status:'job_submitted'}});
  jobEvents.push(event(jobSeq++,'turn/end',{turn:1,reason:{kind:'aborted'}}));
  const jobInput=path.join(temp,'job-session.jsonl.zstd');
  const jobOutput=path.join(temp,'job-evidence.json');
  const jobReport=path.join(temp,'job-report.html');
  fs.writeFileSync(jobInput,zlib.zstdCompressSync(jobEvents.map(row=>JSON.stringify(row)).join('\n')));
  execFileSync(process.execPath,['skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs',
    jobInput,'--out',jobOutput],{cwd:root});
  const jobTrace=JSON.parse(fs.readFileSync(jobOutput,'utf8')).traces[0];
  assert.deepEqual(jobTrace.unresolvedRequests,[],'all submission receipts were recovered; jobs stay separate');
  assert.deepEqual(jobTrace.activeJobs,[['native-running','running'],['nested-queued','queued_or_unknown']],
    'native/nested admissions remain visible without reviving a collected job');
  assert.deepEqual(jobTrace.unavailableResults,[{request_ref:'missing-admission',owner_call:'missing-submit',
    status:'finished_result_unavailable',retention_status:'result_expired',outcome:'unverified',job_id:'missing-result-job'}]);
  assert(jobTrace.completionRisks.some(risk=>risk.code==='active_houdini_jobs'));
  assert(jobTrace.completionRisks.some(risk=>risk.code==='execution_result_unavailable'));
  assert(jobTrace.executionObservationScope.includes('last retained observations'));
  const jobStdout=execFileSync(process.execPath,['tools/trace-report.mjs',jobInput,'--out',jobReport],{cwd:root,encoding:'utf8'});
  const jobHtml=fs.readFileSync(jobReport,'utf8');
  assert(jobStdout.includes('activeJobs=2 unavailableResults=1'));
  assert(jobStdout.includes('cues=[active_houdini_jobs,execution_result_unavailable'));
  assert(jobHtml.includes('后台任务仍在进行或结果尚未领取 2 项'));
  assert(jobHtml.includes('已结束但结果不可取得 1 项'));
  assert(jobHtml.includes('native-running')&&jobHtml.includes('nested-queued')&&jobHtml.includes('missing-result-job'));
  const malformed=path.join(temp,'malformed.zstd');
  fs.writeFileSync(malformed,zlib.zstdCompressSync('not-json\n'+JSON.stringify(nativeEvents[0])));
  assert.equal(loadSessionEvents(malformed).lineErrors.length,1,'invalid lines remain visible diagnostics');
} finally {
  assert.equal(path.dirname(path.resolve(temp)), path.resolve(os.tmpdir()));
  assert(path.basename(temp).startsWith('dsh-trace-risks-'));
  fs.rmSync(temp, {recursive: true, force: true});
}

console.log('trace capability, Chinese contract, render-warning and vision-token risks passed');
