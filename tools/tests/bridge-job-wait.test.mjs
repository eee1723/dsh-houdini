import assert from 'node:assert/strict';
import {HoudiniBridge} from '../../lib/bridge.js';
import {EXPECTED_EXECUTION_CONTRACT_VERSION,EXPECTED_VERB_CATALOG_HASH,EXPECTED_VERB_NAMES} from '../../lib/generated-verb-contract.js';

const originalFetch=globalThis.fetch;
const originalTimeout=AbortSignal.timeout;
const clockDescriptor=Object.getOwnPropertyDescriptor(performance,'now');
let clock=0,clockReadMs=0,handler,calls,timeoutDelays;
const owner={sessionId:'long-poll-owner',callId:'status-call'};
const jobId='a'.repeat(12);
const health={ok:true,executionContractVersion:EXPECTED_EXECUTION_CONTRACT_VERSION,
  verbCatalog:{hash:EXPECTED_VERB_CATALOG_HASH,count:EXPECTED_VERB_NAMES.length,names:EXPECTED_VERB_NAMES}};
const snapshot=status=>({jobId,status,ok:status==='done',stdout:'',stderr:''});
const reset=next=>{clock=0;clockReadMs=0;calls=[];timeoutDelays=[];handler=next;return new HoudiniBridge('http://127.0.0.1:8765',1000)};
const restoreClock=()=>{if(clockDescriptor)Object.defineProperty(performance,'now',clockDescriptor);else delete performance.now};
Object.defineProperty(performance,'now',{configurable:true,value:()=>{const now=clock;clock+=clockReadMs;return now}});
AbortSignal.timeout=delay=>{timeoutDelays.push(delay);return originalTimeout(delay)};
globalThis.fetch=async(url,init)=>{
  init.signal.throwIfAborted();
  const path=new URL(url).pathname;
  if(path==='/health')return Response.json(health);
  assert.equal(path,`/jobs/${jobId}/status`,'long polling never resubmits scene code or the job');
  const body=JSON.parse(init.body);calls.push(body);
  assert.equal(body.owner_session,owner.sessionId);assert.equal(body.owner_call,owner.callId);
  assert.deepEqual(body.expected_contract,{version:EXPECTED_EXECUTION_CONTRACT_VERSION,hash:EXPECTED_VERB_CATALOG_HASH});
  return Response.json(await handler(body,init));
};
try{
  let bridge=reset(body=>{clock+=body.wait*1000;return snapshot('running')});
  assert.equal((await bridge.jobStatus(jobId,owner,600)).status,'running');
  assert.deepEqual(calls.map(body=>body.wait),[240,240,120],
    'each HTTP wait stays below the observed 300s headers limit while the caller deadline remains 600s');

  bridge=reset(body=>{clock+=body.wait*1000;return snapshot('queued')});
  await bridge.jobStatus(jobId,owner,900);
  assert.deepEqual(calls.map(body=>body.wait),[240,240,120],'the Bridge 600s total cap still applies');

  bridge=reset(body=>{clock+=calls.length===1?body.wait*1000:15000;return snapshot(calls.length===1?'running':'done')});
  assert.equal((await bridge.jobStatus(jobId,owner,600)).status,'done');
  assert.deepEqual(calls.map(body=>body.wait),[240,240],'a terminal result ends the call immediately');
  assert.equal(clock,255000);

  for(const status of ['failed','cancelled']){
    bridge=reset(()=>snapshot(status));
    assert.equal((await bridge.jobStatus(jobId,owner,600)).status,status);
    assert.equal(calls.length,1,'failed/cancelled job states are terminal, not status retries');
  }
  bridge=reset(()=>snapshot('running'));
  await bridge.jobStatus(jobId,owner);
  assert.equal(calls.length,1);assert.equal(Object.hasOwn(calls[0],'wait'),false);
  bridge=reset(body=>{clock+=body.wait*1000;return snapshot('running')});
  await bridge.jobStatus(jobId,owner,90);
  assert.deepEqual(calls.map(body=>body.wait),[90],'short waits still use a single HTTP query');

  bridge=reset(body=>{clock+=body.wait*1000;return snapshot('running')});
  clockReadMs=0.003;
  await bridge.jobStatus(jobId,owner,120);
  assert.equal(calls.length,1);
  assert.ok(!Number.isInteger(calls[0].wait*1000),'sub-millisecond clock reads reproduce the observed fractional delay');
  const transportBudget=1000+calls[0].wait*1000+10000;
  assert.ok(timeoutDelays.at(-1)>=transportBudget&&timeoutDelays.at(-1)-transportBudget<1,
    'the integer transport timer does not expire before the fractional poll and its margin');

  bridge=reset(body=>{clock+=body.wait*1000;return snapshot('running')});
  clockReadMs=0.003;
  await bridge.jobStatus(jobId,owner,600);
  assert.equal(calls.length,3);
  assert.ok(calls.every(body=>body.wait<=240),'fractional clocks preserve the HTTP header wait bound');
  const totalWait=calls.reduce((total,body)=>total+body.wait,0);
  assert.ok(totalWait<=600&&totalWait>599.9999,'timer rounding does not extend the caller wait budget');
  assert.ok(timeoutDelays.every(Number.isInteger),'every transport timer passes the native integer-delay contract');

  bridge=reset(()=>{throw new TypeError('fetch failed')});
  await assert.rejects(bridge.jobStatus(jobId,owner,600),/fetch failed/);
  assert.equal(calls.length,1,'an uncertain transport result is reported, never automatically retried');

  const cancellation=new AbortController();
  bridge=reset(body=>{clock+=body.wait*1000;cancellation.abort(new Error('author cancelled'));return snapshot('running')});
  await assert.rejects(bridge.jobStatus(jobId,owner,600,cancellation.signal),/author cancelled/);
  assert.equal(calls.length,1,'cancellation prevents the next read-only status query');

  restoreClock();
  bridge=reset(()=>snapshot('done'));
  assert.equal((await bridge.jobStatus(jobId,owner,120)).status,'done',
    'the real performance clock can complete a 120s status query without an integer-delay error');
  assert.equal(calls.length,1);
  assert.ok(calls[0].wait>119&&calls[0].wait<=120);
  assert.ok(timeoutDelays.every(Number.isInteger));
}finally{
  globalThis.fetch=originalFetch;
  AbortSignal.timeout=originalTimeout;
  restoreClock();
}
console.log('Bridge long polls use integer timers and preserve deadline, ownership and terminal/unknown/cancel facts below the Node 300s HTTP header timeout');
