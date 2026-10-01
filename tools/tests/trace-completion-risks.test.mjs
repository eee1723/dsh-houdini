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
  assert.deepEqual(currentTrace.observationContexts,[{seq:2,time:1002,text:contextText}]);
  assert(currentTrace.requestContexts.every(row=>row.projectionComplete));
  const report=path.join(temp,'current-report.html');
  execFileSync(process.execPath,['tools/trace-report.mjs',temp,'--out',report],{cwd:root});
  assert(fs.readFileSync(report,'utf8').includes(directText),'offline HTML retains native role=tool output');
  const malformed=path.join(temp,'malformed.zstd');
  fs.writeFileSync(malformed,zlib.zstdCompressSync('not-json\n'+JSON.stringify(nativeEvents[0])));
  assert.equal(loadSessionEvents(malformed).lineErrors.length,1,'invalid lines remain visible diagnostics');
} finally {
  assert.equal(path.dirname(path.resolve(temp)), path.resolve(os.tmpdir()));
  assert(path.basename(temp).startsWith('dsh-trace-risks-'));
  fs.rmSync(temp, {recursive: true, force: true});
}

console.log('trace capability, Chinese contract, render-warning and vision-token risks passed');
