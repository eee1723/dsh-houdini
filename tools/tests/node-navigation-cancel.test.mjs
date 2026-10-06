import assert from 'node:assert/strict'
import http from 'node:http'
import {HoudiniBridge} from '../../lib/bridge.js'
import {EXPECTED_EXECUTION_CONTRACT_VERSION as version,EXPECTED_VERB_CATALOG_HASH as hash} from '../../lib/generated-verb-contract.js'

const executor='a'.repeat(32),runtime='b'.repeat(32),owner={sessionId:'navigation-task',callId:'navigation-click'}
const requests=[],pending=new Map()
let issued=0
const server=http.createServer(async(request,response)=>{
  response.setHeader('content-type','application/json')
  assert.equal(request.headers['x-dsh-houdini-executor'],executor)
  let raw='';for await(const chunk of request)raw+=chunk
  const body=JSON.parse(raw);requests.push({path:request.url,body})
  assert.equal(body.owner_session,owner.sessionId)
  if(request.url==='/requests/prepare') {
    assert.equal(body.request_kind,'node_navigation')
    response.end(JSON.stringify({ok:true,executorId:executor,runtimeId:runtime,
      executionContractVersion:version,verbCatalog:{hash},requestRef:runtime+'.'+String(++issued).padStart(32,'0')}))
    return
  }
  assert.equal(body.owner_call,owner.callId)
  assert.deepEqual(body.expected_contract,{version,hash})
  if(request.url==='/nodes/navigate') {
    assert.deepEqual(body.reference,{id:'c'.repeat(32)})
    assert.equal(body.expected_hip,'E:/工程/自行车 "交付".hip')
    assert.equal(body.code,undefined)
    pending.set(body.request_ref,response)
    return
  }
  assert.equal(request.url,'/nodes/cancel')
  pending.get(body.request_ref)?.end(JSON.stringify({ok:false,stdout:'',stderr:'',error:'cancelled before dispatch'}))
  pending.delete(body.request_ref)
  response.end(JSON.stringify({ok:true,status:'not_executed',cancelled:true}))
})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const url='http://127.0.0.1:'+server.address().port
const waitQueued=async()=>{
  for(let tries=0;tries<200&&!pending.size;tries++)await new Promise(resolve=>setTimeout(resolve,5))
  assert.equal(pending.size,1,'the navigation request must be admitted before cancellation')
}
try {
  for(const unload of [false,true]) {
    const interaction=new AbortController(),lifetime=new AbortController()
    const bridge=new HoudiniBridge(url,2000,executor,lifetime.signal)
    const call=bridge.navigateNode({id:'c'.repeat(32)},'E:/工程/自行车 "交付".hip',owner,interaction.signal)
    const rejected=assert.rejects(call,/failed|aborted|cancelled/i)
    await waitQueued()
    if(unload)lifetime.abort(new Error('preset disposed'))
    else interaction.abort(new Error('selected task changed'))
    await rejected
    assert.equal(pending.size,0,'independent cleanup reaches the Bridge after the interaction/lifetime ended')
    assert.equal(requests.at(-1).path,'/nodes/cancel')
  }
  const before=requests.length,aborted=new AbortController();aborted.abort()
  await assert.rejects(new HoudiniBridge(url,2000,executor).navigateNode(
    {id:'c'.repeat(32)},'E:/asset.hip',owner,aborted.signal))
  assert.equal(requests.length,before,'already cancelled navigation submits no HTTP request')
  assert.equal(requests.filter(request=>request.path==='/nodes/cancel').length,2)
  console.log('navigation transport: fixed Unicode target, selected-task abort and disposed-Bridge cleanup passed')
} finally {
  server.closeAllConnections()
  await new Promise(resolve=>server.close(resolve))
}
