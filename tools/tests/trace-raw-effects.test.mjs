import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import {execFileSync} from 'node:child_process';
import {classifyRawEffect, collectVerbAdoption} from '../../skills/houdini-trace-analysis/scripts/evidence-helpers.mjs';
import {normalizeTraceSteps} from '../normalized-trace-steps.mjs';

// Generic fixtures: no private HDA names, paths or source from user traces.
const rows = [
  {tool:'houdini_exec',code:'shutil.copy2(source, backup)',ok:false,
    usage:{gateOutcome:'blocked',suspectedMutations:[{name:'copy2',count:1}]},effect:'gate_blocked'},
  {tool:'houdini_query',code:'sys.path.remove(temp)',ok:false,
    usage:{gateOutcome:'read_only_blocked',suspectedMutations:[{name:'remove',count:1}]},effect:'gate_blocked'},
  {tool:'houdini_exec',code:'runtime.check()',ok:true,
    usage:{gateOutcome:'read_only',coveredMutations:[],suspectedMutations:[]},effect:'unknown'},
  {tool:'houdini_exec',code:'exec(source, namespace)',ok:true,
    usage:{gateOutcome:'read_only'},effect:'unknown'},
  {tool:'houdini_query',code:'__result__ = hou.frame()',ok:true,
    usage:{gateOutcome:'read_only'},effect:'read_only_query'},
  {tool:'houdini_query',code:'__result__ = definition.nonexistent()',ok:false,
    usage:{gateOutcome:'read_only'},effect:'failed'},
  {tool:'houdini_exec',code:'shutil.copy2(source, backup)',ok:true,
    usage:{gateOutcome:'exempted',suspectedMutations:[{name:'copy2',count:1}]},effect:'suspected_effect'},
  {tool:'houdini_exec',code:'n.setInput(0, source)',ok:true,
    usage:{coveredMutations:[{name:'setInput',count:1}]},effect:'mutation_candidate'},
  {tool:'houdini_exec',code:'set_parms(target, values)',ok:true,
    usage:{gateOutcome:'read_only'},verbs:[{verb:'set_parms',ok:true}],effect:'unknown'},
];
const events=[];
for(const [index,row] of rows.entries()) {
  const seq=index*2+1,callId='raw-'+index;
  events.push({seq,time:seq,type:'tool/call',data:{callId,name:row.tool,arguments:{code:row.code}}});
  events.push({seq:seq+1,time:seq+1,type:'tool/result',data:{
    // Intentionally uninformative model text: canonical evidence must win.
    message:{source:{callId},content:[{type:'tool_result',content:[{type:'text',text:'See retained result.'}]}]},
    meta:{canonical:{ok:row.ok,verbs:row.verbs||[],rawUsage:row.usage,
      transaction:{status:'no_scene_change'},execution:{read_only:row.tool==='houdini_query'}}},
  }});
}
const steps=normalizeTraceSteps(events).steps;
assert.deepEqual(steps.map(classifyRawEffect),rows.map(r=>r.effect));
assert.deepEqual(steps[0].mutatingRawMethods,[],'copy2 is deliberately not matched by the old name heuristic');
const stats=collectVerbAdoption(steps);
assert.equal(stats.rawReadOnlyCalls,1);
assert.equal(stats.rawUnknownEffectCalls,2);
assert.equal(stats.rawSuspectedEffectCalls,1);
assert.equal(stats.rawFailedCalls,1);
assert.equal(stats.blockedVerblessRawMutationCalls,2);
assert.equal(stats.successfulVerblessRawMutationCalls,1);
assert.equal(stats.successfulExecCalls,5,'denominator is all successful exec calls, not scene mutations');
assert.equal(stats.successfulExecWithVerbs,1);
assert.equal(classifyRawEffect({tool:'houdini_query',failed:true,
  resultPreview:'houdini_query is read-only and rejected this code BEFORE execution'}),'gate_blocked');
assert.equal(classifyRawEffect({tool:'houdini_exec',failed:true,
  resultPreview:'raw-hou gate: blocked BEFORE execution'}),'gate_blocked');
assert.equal(classifyRawEffect({tool:'houdini_exec',failed:false,mutatingRawMethods:['setInput']}),'mutation_candidate');
assert.equal(classifyRawEffect({tool:'houdini_exec',failed:false,mutatingRawMethods:[],
  rawUsage:{gateOutcome:'exempted'}}),'suspected_effect','an exemption with missing effect details is not read-only');
assert.equal(classifyRawEffect({tool:'houdini_query',failed:false,canonical:{execution:{read_only:false}}}),'unknown');
assert.equal(classifyRawEffect({tool:'houdini_exec',rawUsage:{gateOutcome:'read_only'},
  canonical:{rawUsage:{gateOutcome:'blocked'}}}),'gate_blocked','canonical evidence beats stale parsed text');
for(const ref of ['result_ref','request_ref','source_ref']) {
  const result=collectVerbAdoption([...steps,{tool:'houdini_query',isHoudini:true,args:{[ref]:'retained'},
    canonical:{ok:true,rawUsage:{gateOutcome:'blocked'}}}]);
  assert.equal(result.hostResultDetailReads,1);
  assert.equal(result.houdiniCalls,stats.houdiniCalls);
  assert.equal(result.blockedVerblessRawMutationCalls,2,'historical returned receipts are not new Gate executions');
}

const root=path.resolve(import.meta.dirname,'../..');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-trace-raw-'));
try {
  const input=path.join(temp,'session.jsonl.zstd'),output=path.join(temp,'evidence.json');
  fs.writeFileSync(input,zlib.zstdCompressSync(events.map(e=>JSON.stringify(e)).join('\n')));
  execFileSync(process.execPath,['skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs',input,'--out',output],{cwd:root});
  const trace=JSON.parse(fs.readFileSync(output,'utf8')).traces[0];
  assert.deepEqual(trace.verbAdoption,stats);
  assert.deepEqual(trace.execUsedForReadOnly,[],'dynamic execs cannot be certified as read-only');
  assert.equal(trace.execWithoutVerbEvidence.find(s=>s.index===1).effect,'gate_blocked');
  assert.equal(trace.execWithoutVerbEvidence.find(s=>s.index===3).effect,'unknown');
  const report=path.join(temp,'report.html');
  execFileSync(process.execPath,['tools/trace-report.mjs',input,'--out',report],{cwd:root});
  const html=fs.readFileSync(report,'utf8');
  const rawSection=html.slice(html.indexOf('<h2>无动词 Houdini 调用'));
  assert.match(rawSection,/Gate 执行前拦截/);
  assert.match(rawSection,/副作用未知（含动态调用）/);
  assert.match(rawSection,/疑似副作用 \/ 外部操作/);
  assert(!html.includes('只读探针 ×'),'unrecognized methods must never be labeled read-only in HTML');
} finally {
  assert.equal(path.dirname(path.resolve(temp)),path.resolve(os.tmpdir()));
  assert(path.basename(temp).startsWith('dsh-trace-raw-'));
  fs.rmSync(temp,{recursive:true,force:true});
}
console.log('Raw effects: canonical/legacy Gate, external effects, dynamic unknowns, detail reads, evidence and HTML passed');
