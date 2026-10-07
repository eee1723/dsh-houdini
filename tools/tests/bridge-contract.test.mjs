import assert from 'node:assert/strict';
import http from 'node:http';
import { HoudiniBridge } from '../../lib/bridge.js';
import {
  EXPECTED_VERB_CATALOG_HASH,
  EXPECTED_VERB_NAMES,
  EXPECTED_EXECUTION_CONTRACT_VERSION,
} from '../../lib/generated-verb-contract.js';

let stale = true;
let execCalls = 0;
let uiCalls = 0;
let uiListCalls = 0;
let lastExecBody = null;
let lastUiBody = null;
let lastUiListBody = null;
let lastPrepareBody = null;
let semanticVersion = EXPECTED_EXECUTION_CONTRACT_VERSION;
const server = http.createServer((request, response) => {
  response.setHeader('content-type', 'application/json');
  if (request.url === '/health') {
    response.end(JSON.stringify({
      ok: true,
      executionContractVersion: semanticVersion,
      verbCatalog: stale
        ? { hash: 'old', count: 1, names: ['scene_info'] }
        : {
            hash: EXPECTED_VERB_CATALOG_HASH,
            count: EXPECTED_VERB_NAMES.length,
            names: EXPECTED_VERB_NAMES,
          },
    }));
    return;
  }
  if (request.url === '/requests/prepare') {
    let body = '';
    request.setEncoding('utf8');
    request.on('data', (chunk) => { body += chunk; });
    request.on('end', () => {
      lastPrepareBody = JSON.parse(body);
      response.end(JSON.stringify({
        ok: true,
        runtimeId: 'c'.repeat(32),
        executionContractVersion: semanticVersion,
        verbCatalog: stale
          ? { hash: 'old', count: 1, names: ['scene_info'] }
          : {
              hash: EXPECTED_VERB_CATALOG_HASH,
              count: EXPECTED_VERB_NAMES.length,
              names: EXPECTED_VERB_NAMES,
            },
        requestRef: 'c'.repeat(32) + '.' + 'd'.repeat(32),
      }));
    });
    return;
  }
  if (request.url === '/exec') {
    let body = '';
    request.setEncoding('utf8');
    request.on('data', (chunk) => { body += chunk; });
    request.on('end', () => {
      execCalls++;
      lastExecBody = JSON.parse(body);
      response.end(JSON.stringify({
        ok: true,
        stdout: '',
        stderr: '',
      }));
    });
    return;
  }
  if (request.url === '/ui/list') {
    let body='';request.setEncoding('utf8');
    request.on('data',chunk=>{body+=chunk;});
    request.on('end',()=>{
      uiListCalls++;lastUiListBody=JSON.parse(body);
      response.end(JSON.stringify({ok:true,stdout:'',stderr:'',result:{surfaces:[{target:'ui:fixture',kind:'qt_window',supported:true}]},
        requestReceipt:{request_ref:lastUiListBody.request_ref,runtime_id:'c'.repeat(32),status:'done'}}));
    });
    return;
  }
  if (request.url === '/ui/capture') {
    let body = '';
    request.setEncoding('utf8');
    request.on('data', chunk => { body += chunk; });
    request.on('end', () => {
      uiCalls++; lastUiBody = JSON.parse(body);
      response.end(JSON.stringify({ok:true,stdout:'',stderr:'',result:{scene_writes:0,semantic_status:'unverified'},
        transaction:{status:'no_scene_change'},requestReceipt:{request_ref:lastUiBody.request_ref,runtime_id:'c'.repeat(32),status:'done'}}));
    });
    return;
  }
  response.statusCode = 404;
  response.end('{}');
});

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
try {
  const address = server.address();
  assert(address && typeof address === 'object');
  const url = `http://127.0.0.1:${address.port}`;
  const owner = { sessionId: 'session-owner', callId: 'call-1' };

  await assert.rejects(
    new HoudiniBridge(url, 1000).exec('__result__ = 1', owner),
    /修复并重启运行环境[\s\S]*contract mismatch/,
  );
  assert.equal(execCalls, 0, 'mismatch must fail before scene code reaches /exec');
  await assert.rejects(new HoudiniBridge(url,1000).captureUi({target:'ui:fixture'},owner),/contract mismatch/);
  assert.equal(uiCalls,0,'stale catalog rejects capture before the UI business route; prepare remains the non-HOM handshake');

  stale = false;
  const bridge = new HoudiniBridge(url, 1000);
  const result = await bridge.exec('__result__ = 1', owner);
  assert.equal(result.ok, true);
  assert.equal(execCalls, 1);
  assert.equal(lastPrepareBody.owner_session, 'session-owner', 'ticket preparation carries the session identity');
  assert.deepEqual(lastExecBody.expected_contract, {version: EXPECTED_EXECUTION_CONTRACT_VERSION, hash: EXPECTED_VERB_CATALOG_HASH});
  assert.equal(lastExecBody.owner_session, 'session-owner');
  assert.equal(lastExecBody.owner_call, 'call-1');
  assert.equal(lastExecBody.request_ref, 'c'.repeat(32) + '.' + 'd'.repeat(32), 'every HTTP execution carries a one-time ticket');
  semanticVersion--;
  await assert.rejects(bridge.exec('__result__ = 2', owner), /contract mismatch.*semantics/);
  assert.equal(execCalls, 1, 'same-name stale semantics must fail before /exec even immediately after a successful check');
  semanticVersion = EXPECTED_EXECUTION_CONTRACT_VERSION;
  await bridge.exec('__result__ = 3', owner, undefined, undefined, true);
  assert.equal(lastExecBody.read_only, 'true', 'query must use the read-only bridge boundary');
  assert.equal(execCalls, 2, 'one admitted exec per public scene call; no hidden workspace probe');
  const uiOptions={target:'ui:fixture',path:'layout.png',output_policy:'managed'};
  const uiResult=await bridge.captureUi(uiOptions,owner);
  assert.equal(uiResult.ok,true);assert.equal(uiCalls,1);
  assert.deepEqual(lastUiBody,{...uiOptions,owner_session:owner.sessionId,owner_call:owner.callId,
    expected_contract:{version:EXPECTED_EXECUTION_CONTRACT_VERSION,hash:EXPECTED_VERB_CATALOG_HASH},
    request_ref:'c'.repeat(32)+'.'+'d'.repeat(32)},'capture submits fixed UI options and the prepared same-runtime ticket, with no Python code');
  assert.equal(Object.hasOwn(lastUiBody,'code'),false);
  const listed=await bridge.listUi(owner);
  assert.equal(listed.result.surfaces[0].target,'ui:fixture');assert.equal(uiListCalls,1);
  assert.deepEqual(lastUiListBody,{owner_session:owner.sessionId,owner_call:owner.callId,
    expected_contract:{version:EXPECTED_EXECUTION_CONTRACT_VERSION,hash:EXPECTED_VERB_CATALOG_HASH},
    request_ref:'c'.repeat(32)+'.'+'d'.repeat(32)},'discovery carries only its original request provenance');
  await bridge.captureUi({target:'ui:fixture',path:'existing.png'},owner);
  assert.equal(uiCalls,2);
  assert.deepEqual(Object.keys(lastUiBody).sort(),['target','path','owner_session','owner_call','expected_contract','request_ref'].sort());
  semanticVersion--;
  await assert.rejects(bridge.captureUi(uiOptions,owner),/contract mismatch.*semantics/);
  await assert.rejects(bridge.listUi(owner),/contract mismatch.*semantics/);
  assert.equal(uiCalls,2,'fresh prepare checks reject same-name stale semantics before any UI preparation request');
  assert.equal(uiListCalls,1,'UI target discovery also refuses stale contracts before dispatch');
  semanticVersion=EXPECTED_EXECUTION_CONTRACT_VERSION;
  await assert.rejects(new HoudiniBridge(url,1000,'a'.repeat(32)).captureUi(uiOptions,owner),/executor mismatch/);
  assert.equal(uiCalls,2,'explicit target mismatch stops at ticket/contract facts before preparing any native UI');

  // Identity is validated before ANY network activity: /health, /requests/prepare
  // and business routes all stay untouched for missing/blank/mistyped owners.
  let countedRequests = 0;
  const counting = http.createServer((request, response) => {
    countedRequests++;
    response.setHeader('content-type', 'application/json');
    response.end('{}');
  });
  await new Promise((resolve) => counting.listen(0, '127.0.0.1', resolve));
  try {
    const counted = new HoudiniBridge(`http://127.0.0.1:${counting.address().port}`, 1000);
    const badOwners = [undefined, null, 'owner', 7, {}, {sessionId: 's'}, {sessionId: '', callId: 'c'},
      {sessionId: 's', callId: ''}, {sessionId: 's', callId: '  '}, {sessionId: 5, callId: 'c'},
      {sessionId: 's', callId: 0}, {sessionId: 's', callId: null}];
    for (const bad of badOwners) {
      await assert.rejects(counted.exec('pass', bad), /identity/);
      await assert.rejects(counted.submitJob('pass', bad), /identity/);
      await assert.rejects(counted.jobStatus('a'.repeat(12), bad), /identity/);
      await assert.rejects(counted.cancelJob('a'.repeat(12), bad), /identity/);
      await assert.rejects(counted.captureUi({target:'ui:fixture'},bad),/identity/);
      await assert.rejects(counted.listUi(bad),/identity/);
    }
    assert.equal(countedRequests, 0, 'invalid owner must fail before /health, /requests/prepare and business routes');
  } finally {
    await new Promise((resolve) => counting.close(resolve));
  }

  // A new Host must stop at the non-HOM health check against an old Bridge:
  // job-control POSTs are never sent and no ticket is prepared for them.
  let prepareRequests = 0, jobControlPosts = 0;
  const oldBridgeServer = http.createServer((request, response) => {
    response.setHeader('content-type', 'application/json');
    if (request.url === '/health') {
      response.end(JSON.stringify({
        ok: true,
        executionContractVersion: EXPECTED_EXECUTION_CONTRACT_VERSION - 1,
        verbCatalog: {hash: EXPECTED_VERB_CATALOG_HASH, count: EXPECTED_VERB_NAMES.length, names: EXPECTED_VERB_NAMES},
      }));
      return;
    }
    if (request.url === '/requests/prepare') { prepareRequests++; response.end('{}'); return; }
    if (request.url.endsWith('/status') || request.url.endsWith('/cancel')) { jobControlPosts++; }
    response.end('{}');
  });
  await new Promise((resolve) => oldBridgeServer.listen(0, '127.0.0.1', resolve));
  try {
    const legacy = new HoudiniBridge(`http://127.0.0.1:${oldBridgeServer.address().port}`, 1000);
    await assert.rejects(legacy.jobStatus('a'.repeat(12), owner), /contract mismatch/);
    await assert.rejects(legacy.cancelJob('a'.repeat(12), owner), /contract mismatch/);
    assert.equal(jobControlPosts, 0, 'job control must not reach an owner-ignoring old Bridge');
    assert.equal(prepareRequests, 0, 'job control must not prepare execution tickets');
  } finally {
    await new Promise((resolve) => oldBridgeServer.close(resolve));
  }
} finally {
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}

console.log('bridge contract handshake tests passed');
