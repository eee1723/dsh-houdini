import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import {execFileSync} from 'node:child_process';

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
  assert(!trace.completionRisks.some((risk) => risk.code === 'completed_vision_todo_without_evidence'),
    '`divisions` must not be parsed as the English word `vision`');
} finally {
  assert.equal(path.dirname(path.resolve(temp)), path.resolve(os.tmpdir()));
  assert(path.basename(temp).startsWith('dsh-trace-risks-'));
  fs.rmSync(temp, {recursive: true, force: true});
}

console.log('trace capability, Chinese contract, render-warning and vision-token risks passed');
