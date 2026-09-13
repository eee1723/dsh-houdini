import assert from 'node:assert/strict';
import {collectHostWork,collectRetryWork} from '../../skills/houdini-trace-analysis/scripts/evidence-helpers.mjs';
const rows=[
 {index:1,turn:1,tool:'write',args:{file_path:'Z:\\tmp\\probe.py'}},
 {index:2,turn:1,tool:'pwsh',args:{command:'python probe.py'},resultPreview:'FAIL'},
 {index:3,turn:1,tool:'read',args:{file_path:'Z:/tmp/probe.py'}},
 {index:4,turn:1,tool:'write',args:{file_path:'Z:/tmp/probe.py'},failed:true},
 {index:5,turn:1,tool:'pwsh',args:{command:'python probe.py'}},
 {index:6,turn:1,tool:'houdini_query',args:{}},
 {index:7,turn:1,tool:'edit',args:{file_path:'Z:/tmp/probe.py'}},
 {index:8,turn:2,tool:'pwsh',args:{command:'python other.py'}},
];
const r=collectHostWork(rows);
assert.equal(r.fileWrites.length,1);
assert.deepEqual(r.fileWrites[0].steps,[1,4,7]);
assert.equal(r.fileWrites[0].failedCalls,1);
assert.deepEqual(r.repeatedCommands[0].steps,[2,5]);
assert.equal(r.repeatedCommands[0].failedCalls,0,'printed FAIL is not a tool failure');
assert.deepEqual(r.hostIntervalsWithoutHoudiniCalls.map(x=>x.hostCalls),[4,1,1]);
assert.deepEqual(collectRetryWork(rows).hostWork,r);
assert.deepEqual(collectHostWork([]).fileWrites,[]);
assert.equal(collectHostWork([{index:1,turn:1,tool:'pwsh',args:{command:'echo PASS'}}]).repeatedCommands.length,0);
console.log('host work evidence: exact repetition, boundaries and no semantic failure inference passed');
