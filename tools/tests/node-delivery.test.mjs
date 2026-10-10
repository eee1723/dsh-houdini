import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import http from 'node:http'
import {Context} from '@deepseek-ai/cordis'
import {Session} from '@deepseek-ai/dsh-session'
import {remoteMethods} from '@deepseek-ai/dsh-typert-protocol'
import {HoudiniBridge} from '../../lib/bridge.js'
import {ExecutorBinding,recordedExecutorIdentity} from '../../lib/executor-binding.js'
import {ExecutorDirectory,ExecutorRouter} from '../../lib/executor-routing.js'
import {HoudiniFrontend} from '../../lib/frontend-host.js'
import {NODE_DELIVERY_KIND,installNodeDeliveryNavigation,nodeDeliveryCoordinates,recordedNodeDelivery} from '../../lib/node-delivery.js'
import {EXPECTED_EXECUTION_CONTRACT_VERSION as version,EXPECTED_VERB_CATALOG_HASH as hash} from '../../lib/generated-verb-contract.js'

const signal=new AbortController().signal
const directory=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-node-delivery-'))
const endpoints=path.join(directory,'endpoints')
await fs.mkdir(endpoints)
const servers=[],records=[],agents=[],execs=[],reads=[],events=new Map(),scopes=[]
let refuseNavigation=false
const native=(value,callId='deliver-call')=>({type:'tool/result',seq:20,
  data:{turn:1,message:{source:{kind:'tool',callId},isError:false},meta:{canonical:value}}})
const nested=(value,callId='nested-deliver-call')=>({type:'tool/ptc-dispatch',seq:21,
  data:{turn:1,name:'houdini_exec',subCallId:callId,isError:false,
    content:[{type:'text',text:JSON.stringify({kind:'dsh-houdini/execution-v1',callId,tool:'houdini_exec',value})}]}})
const clone=value=>JSON.parse(JSON.stringify(value))
try {
  for(let i=0;i<2;i++) {
    const executor=String(i+1).repeat(32),runtime=String(i+3).repeat(32),task='node-task-'+i
    const hip=path.join(directory,task+' "参数".hip')
    const session=Session.create(task,[],{version:4,id:task,createdAt:1,isSeeded:false,agentPreset:'houdini'})
    await new ExecutorBinding().ensure(session,executor)
    session.append('tool/call',{turn:1,step:1,callId:'deliver-call',name:'houdini_exec',arguments:'{}'})
    session.append('tool/call',{turn:1,step:1,callId:'file-call',name:'read',arguments:'{}'})
    const ctx=new Context(),agent={id:task,status:'idle',session,ctx}
    agents.push(agent)
    const server=http.createServer(async(req,res)=>{
      res.setHeader('content-type','application/json')
      let text='';for await(const chunk of req)text+=chunk
      const body=text?JSON.parse(text):{}
      if(req.headers['x-dsh-houdini-executor']!==executor) {res.writeHead(409);res.end('{}');return}
      if(req.url==='/health'||req.url==='/requests/prepare') {
        res.end(JSON.stringify({ok:true,executorId:executor,runtimeId:runtime,houVersion:'22.0.368',
          executionContractVersion:version,verbCatalog:{hash},requestRef:runtime+'.'+'a'.repeat(32)}));return
      }
      assert.equal(req.url,'/nodes/navigate')
      assert.equal(body.owner_session,task,'navigation must use the task that owns this executor')
      assert.match(body.owner_call,/^node-navigation-/,'UI navigation receives its own request identity')
      assert.equal(body.code,undefined,'navigation route never accepts free Python')
      assert.deepEqual(body.reference,{id:String(i+5).repeat(32)},'historical path/label/type are not locators')
      assert.equal(body.expected_hip,hip,'expected HIP is read from the original execution envelope')
      execs.push({task,body})
      // Interleave the two requests to expose global-current-target mistakes.
      await new Promise(resolve=>setTimeout(resolve,i?1:10))
      res.end(JSON.stringify(refuseNavigation?{ok:false,error:'Traceback (most recent call last):\nValueError: Node delivery UUID is missing',
        verbs:[{verb:'focus_node',ok:false,error:'Node delivery UUID is missing'}],stdout:'',stderr:''}
        :{ok:true,stdout:'',stderr:'',result:{id:String(i+5).repeat(32),path:'/obj/renamed_control_'+i}}))
    })
    servers.push(server)
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
    const record={schema:1,executor_id:executor,registration_id:String(i+7).repeat(32),runtime_id:runtime,
      installation:directory,bridge_url:'http://127.0.0.1:'+server.address().port,
      houdini_version:'22.0.368',pid:300+i,state:'registered',task_id:task,hip_path:hip}
    records.push(record)
    await fs.writeFile(path.join(endpoints,executor+'.json'),JSON.stringify(record))
    const value={ok:true,stdout:'',stderr:'',outcome:{operations:{failed:0}},
      result:{kind:NODE_DELIVERY_KIND,nodes:[{id:String(i+5).repeat(32),path:'/obj/old_control_'+i,
        label:'工程控制 '+i,role:'control',type:'null'}]},
      execution:{executor_id:executor,runtime_id:'9'.repeat(32),hip_path:hip,owner_session:task}}
    value.verbs=[{verb:'present_nodes',ok:true,result:value.result}]
    value.result={entries:value.result,other:'wrapped business result'}
    events.set(task,native(value))
  }
  const router=new ExecutorRouter(new ExecutorDirectory(directory,directory),2000,new ExecutorBinding(),
    session=>recordedExecutorIdentity(session.snapshotEvents()))
  for(const agent of agents) {
    const scope=await agent.ctx.plugin({apply(ctx){installNodeDeliveryNavigation(ctx,router)}})
    scopes.push(scope)
  }
  const root=new Context()
  root.provide('agents',{get:id=>agents.find(agent=>agent.id===id)})
  let incorrectWindow
  root.provide('sessionQuery',{async readEvent(request) {
    reads.push(request)
    if(incorrectWindow)return incorrectWindow
    const event=events.get(request.sessionId)
    if(!event||request.seq!==event.seq)throw new Error('Session event not found')
    return {session:{id:request.sessionId},target:event}
  }})
  const frontend=new HoudiniFrontend(root)
  assert.deepEqual(remoteMethods(frontend).map(method=>method.method),['videoSettings','videoDiagnostics','capabilities','openNode'])
  assert.equal(frontend.capabilities().nodeDeliveries,true)
  const coordinates=i=>({sessionId:agents[i].id,eventSeq:20,index:0})
  assert.deepEqual(await Promise.all([0,1].map(i=>frontend.openNode(coordinates(i),signal))),
    [0,1].map(i=>({id:String(i+5).repeat(32),path:'/obj/renamed_control_'+i})),
    'two tasks navigate through their own bound executor, despite an old recorded runtime')
  assert.deepEqual(reads[0],{sessionId:agents[0].id,seq:20,before:0,after:0})
  assert.equal(execs.length,2)

  const original=clone(events.get(agents[0].id))
  async function rejectEvent(change,message,input=coordinates(0)) {
    const event=clone(original);change(event)
    events.set(agents[0].id,event)
    const count=execs.length
    await assert.rejects(frontend.openNode(input,signal),message)
    assert.equal(execs.length,count,'rejected delivery must not reach the scene queue')
    events.set(agents[0].id,clone(original))
  }
  await rejectEvent(event=>{event.data.message.isError=true},/successful original batch/)
  await rejectEvent(event=>{event.data.meta.canonical.ok=false},/successful original batch/)
  await rejectEvent(event=>{event.data.meta.canonical.outcome.operations.failed=1},/failed operations/)
  await rejectEvent(event=>{event.data.meta.canonical.verbs=[{verb:'set_parm',ok:false}]},/failed operations/)
  await rejectEvent(event=>{event.data.meta.canonical.execution.owner_session=agents[1].id},/another task/)
  await rejectEvent(event=>{event.data.meta.canonical.execution.executor_id=records[1].executor_id},/another Houdini executor/)
  await rejectEvent(event=>{event.data.meta.canonical.execution.hip_is_new=true},/saved HIP/)
  await rejectEvent(event=>{event.data.meta.canonical.verbs[0].result.nodes[0].id='malicious code()'},/not found/)
  await rejectEvent(event=>{event.type='assistant/message'},/successful original batch/)
  await rejectEvent(event=>{event.data.message.source.callId='file-call'},/not a recorded Houdini tool/)
  await rejectEvent(event=>{event.data.message.source.callId='unknown-call'},/not a recorded Houdini tool/)
  await rejectEvent(()=>{},/not found/,{...coordinates(0),index:1})
  await rejectEvent(()=>{},/call does not match/,{...coordinates(0),callId:'other-call'})
  const beforeInvalid=execs.length
  for(const input of [null,{...coordinates(0),path:'/obj/untrusted'},
    {...coordinates(0),eventSeq:0},{...coordinates(0),eventSeq:1.5},{...coordinates(0),index:-1},
    {...coordinates(0),callId:''}])
    assert.throws(()=>nodeDeliveryCoordinates(input),/Expected the selected/)
  await assert.rejects(frontend.openNode({...coordinates(0),eventSeq:1000},signal),/event not found/)
  await assert.rejects(frontend.openNode({...coordinates(0),sessionId:'not-open'},signal),/original node delivery task/)
  incorrectWindow={session:{id:agents[1].id},target:clone(original)}
  await assert.rejects(frontend.openNode(coordinates(0),signal),/requested task\/event/)
  incorrectWindow={session:{id:agents[0].id},target:{...clone(original),seq:999}}
  await assert.rejects(frontend.openNode(coordinates(0),signal),/requested task\/event/)
  incorrectWindow=undefined
  assert.equal(execs.length,beforeInvalid)

  const ptc=nested(original.data.meta.canonical)
  events.set(agents[0].id,ptc)
  const ptcCoordinates={...coordinates(0),eventSeq:21,callId:'nested-deliver-call'}
  assert.equal(recordedNodeDelivery(ptc,ptcCoordinates).reference.id,'5'.repeat(32))
  assert.equal((await frontend.openNode(ptcCoordinates,signal)).path,'/obj/renamed_control_0')
  ptc.data.isError=true
  await assert.rejects(frontend.openNode(ptcCoordinates,signal),/successful original batch/)
  ptc.data.isError=false
  await assert.rejects(frontend.openNode({...ptcCoordinates,callId:'outer-ptc-call'},signal),/call does not match/)
  events.set(agents[0].id,clone(original))

  // The launcher single-executor mode reuses its existing Bridge, without a discovery fallback.
  await scopes[0].dispose()
  const single=await agents[0].ctx.plugin({apply(ctx){installNodeDeliveryNavigation(ctx,
    new HoudiniBridge(records[0].bridge_url,2000,records[0].executor_id))}})
  scopes[0]=single
  assert.equal((await frontend.openNode(coordinates(0),signal)).id,'5'.repeat(32))
  const retained=agents[0].ctx.get('houdiniNodeDelivery')
  await single.dispose()
  await assert.rejects(retained.open(recordedNodeDelivery(original,coordinates(0)),agents[0],signal),/unloaded/)
  await assert.rejects(frontend.openNode(coordinates(0),signal),/no Houdini navigation service/)
  scopes[0]=await agents[0].ctx.plugin({apply(ctx){installNodeDeliveryNavigation(ctx,router)}})

  refuseNavigation=true
  await assert.rejects(frontend.openNode(coordinates(0),signal),error=>error.message==='Node delivery UUID is missing',
    'navigation shows the actual operation cause without the Python stack')
  refuseNavigation=false
  const aborted=new AbortController();aborted.abort(new Error('click cancelled'))
  await assert.rejects(frontend.openNode(coordinates(0),aborted.signal),/click cancelled/)
  console.log('node delivery: native/PTC coordinates, task and executor routing, HIP/UUID navigation, reopen and failed-operation refusal passed')
} finally {
  await Promise.all(scopes.map(scope=>scope.dispose()))
  await Promise.all(servers.map(server=>new Promise(resolve=>server.close(resolve))))
  await fs.rm(directory,{recursive:true,force:true})
}
