// Official Host + production tool pipeline; only the Bridge is controlled.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import http from 'node:http'
import {randomUUID} from 'node:crypto'
import {LlmAdapter,createUserMessage,createToolResultMessage} from '@deepseek-ai/dsh-llm'
import {EXPECTED_EXECUTION_CONTRACT_VERSION as version,EXPECTED_VERB_CATALOG_HASH as hash} from '../../lib/generated-verb-contract.js'

export const inject=['loader','workspaceRegistry','sessionController','sessions','agents','houdiniTargets','tools','llm']
const id=()=>randomUUID().replaceAll('-',''),tick=()=>new Promise(resolve=>setTimeout(resolve,10))
export function apply(ctx) {
  const root=process.env.DSH_MENU_FIXTURE_ROOT,output=path.join(root,'result.json'),registry=path.join(process.env.DSH_HOME,'dsh-houdini/executors/endpoints')
  let report,stopped=false,releaseBusy,enteredBusy=false
  const gate=new Promise(resolve=>releaseBusy=resolve),records=[],claims=[],executions=[]
  const write=value=>{fs.writeFileSync(output+'.tmp',JSON.stringify(value,null,2));fs.renameSync(output+'.tmp',output)}
  const publish=record=>{fs.mkdirSync(registry,{recursive:true});fs.writeFileSync(path.join(registry,record.executor_id+'.json'),JSON.stringify(record))}
  const server=http.createServer(async(request,response)=>{
    try {
      const record=records.find(row=>row.executor_id===request.headers['x-dsh-houdini-executor']);assert(record)
      let raw='';for await(const block of request)raw+=block;const body=raw?JSON.parse(raw):{}
      const health={ok:true,executorId:record.executor_id,runtimeId:record.runtime_id,sceneEpoch:record.scene_epoch,
        houVersion:record.houdini_version,executionContractVersion:version,verbCatalog:{hash},activeRequests:0,activeJobs:0}
      let result
      if(request.url==='/health')result=health
      else if(request.url==='/context')result={ok:true,result:{hip_path:record.hip_path,hip_is_new:false,frame:1,selection:[]}}
      else if(request.url==='/requests/prepare')result={...health,requestRef:record.runtime_id+'.'+id()}
      else if(request.url==='/executor/claim'){
        assert.equal(body.registration_id,record.registration_id);assert.equal(body.expected_hip,record.hip_path)
        claims.push(body.task_id);record.task_id=body.task_id;publish(record);result={ok:true}
      }else if(request.url==='/exec'){
        assert.equal(body.owner_session,record.task_id,'real Houdini exec must first obtain its exact writer')
        assert.equal(body.code,'__result__ = {"menu_writer_fixture": True}')
        executions.push({sessionId:body.owner_session,callId:body.owner_call})
        result={ok:true,stdout:'',stderr:'',result:{menu_writer_fixture:true},execution:{executor_id:record.executor_id,
          runtime_id:record.runtime_id,scene_id:record.scene_id,scene_epoch:record.scene_epoch,hip_path:record.hip_path,
          hip_is_new:false,sequence:executions.length,observed_at:Date.now()/1000,read_only:false}}
      }else throw Error('Unexpected controlled Bridge route '+request.url)
      response.setHeader('content-type','application/json');response.end(JSON.stringify(result))
    }catch(error){response.statusCode=500;response.end(JSON.stringify({ok:false,error:String(error.stack||error)}))}
  })
  const ready=new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
  class BusyAdapter extends LlmAdapter {
    async listModels(){return[{provider:'menu-busy',id:'gate',name:'Local deterministic gate',inputModalities:['text']}]}
    async resolveModel(provider,id){return{provider,id,name:'Local deterministic gate',inputModalities:['text'],context:{contextWindow:100000}}}
    async *stream(options){
      if(!options.purpose){enteredBusy=true;await gate}
      yield{type:'block-start',index:0,blockType:'text'}
      yield{type:'block-end',index:0,block:{type:'text',text:'Owned fixture completed.'}}
      yield{type:'finish',reason:{kind:'stop'}}
    }
  }
  ctx.llm.registerAdapter(['menu-busy'],new BusyAdapter())
  let restorePresentation
  async function executeWriter(agent){
    const turn=agent.session.snapshotEvents().filter(event=>event.type==='turn/start').length+1,callId='writer-'+id()
    agent.session.append('turn/start',{turn})
    agent.session.append('user/message',createUserMessage({source:{kind:'user'},content:[{type:'text',text:'Execute the owned controlled Bridge writer fixture.'}]}),{surfaceOp:'append'})
    const arguments_={code:'__result__ = {"menu_writer_fixture": True}'}
    agent.session.append('tool/call',{turn,step:1,callId,name:'houdini_exec',arguments:JSON.stringify(arguments_)})
    restorePresentation=agent.ctx.tools.presentAs('native')
    const result=await ctx.tools.execute({agent,callId,name:'houdini_exec',arguments:arguments_,signal:AbortSignal.timeout(15000)})
    assert.equal(result.isError,false,JSON.stringify(result));assert.equal(result.value.ok,true,JSON.stringify(result))
    agent.session.append('tool/result',{turn,step:1,message:createToolResultMessage({callId,content:result.content,isError:result.isError}),
      ...(result.meta===undefined?{}:{meta:result.meta})},{surfaceOp:'append'})
    agent.session.append('turn/end',{turn,reason:{kind:'completed'}})
    assert.equal(await ctx.sessions.flush(agent.session),true)
    return result
  }
  async function menu(record){
    const descriptor=JSON.parse(fs.readFileSync(path.join(process.env.DSH_HOME,'dsh-houdini/desktop.json'),'utf8'))
    const payload={executorId:record.executor_id,registrationId:record.registration_id,requestId:id(),expectedHip:record.hip_path}
    assert.equal('sessionId'in payload,false)
    const response=await fetch('http://127.0.0.1:'+descriptor.port+'/open-workspace',{method:'POST',
      headers:{'content-type':'application/json',authorization:'Bearer '+descriptor.token},body:JSON.stringify(payload),signal:AbortSignal.timeout(15000)})
    const result=await response.json();assert.equal(result.ok,true,JSON.stringify(result));return result.value
  }
  ctx.effect(()=>{
    queueMicrotask(async()=>{
      try{
        await ready;await ctx.loader.await()
        for(let index=0;index<2;index++){
          const folder=path.join(root,'scene-'+index);fs.mkdirSync(folder,{recursive:true})
          const record={schema:1,executor_id:id(),registration_id:id(),runtime_id:id(),installation:process.env.DSH_MENU_PLUGIN_ROOT,
            bridge_url:'http://127.0.0.1:'+server.address().port,houdini_version:'22.0.368',pid:process.pid,state:'registered',task_id:null,
            hip_path:path.join(folder,'owned.hip'),hip_is_new:false,workbench:true,workspace_path:folder,scene_id:id(),scene_epoch:id()}
          records.push(record);publish(record)
        }
        const record=records[0],workspace=await ctx.workspaceRegistry.create(path.join(root,'scene-0'),'Owned menu fixture')
        const created=await ctx.sessionController.create({workspaceId:workspace.id,agentPreset:'houdini'})
        const agent=ctx.agents.get(created.sessionId),select=async(owner,target)=>ctx.houdiniTargets.select({sessionId:owner.id,
          executorId:target.executor_id,registrationId:target.registration_id,expectedHip:target.hip_path,
          runtimeId:target.runtime_id,sceneEpoch:target.scene_epoch},AbortSignal.timeout(10000))
        await select(agent,record);assert.equal(record.task_id,null,'selection does not grant writer')
        await executeWriter(agent);assert.equal(record.task_id,agent.id)
        const claimsAfterExecution=claims.length,eventsBeforeMenu=agent.session.seq
        const original=await menu(record)
        assert.equal(original.sessionId,agent.id,'real writer conversation must resume without a menu sessionId argument')
        assert.equal(original.workspaceId,workspace.id);assert.equal(claims.length,claimsAfterExecution);assert.equal(agent.session.seq,eventsBeforeMenu)
        await ctx.sessionController.selectModel({sessionId:agent.id,provider:'menu-busy',model:'gate'})
        await ctx.sessionController.prompt({sessionId:agent.id,requestId:id(),mode:'queue',content:[{type:'text',text:'Wait at the local fixture gate.'}]},AbortSignal.timeout(15000))
        const deadline=Date.now()+10000;while(!enteredBusy){assert(Date.now()<deadline);await tick()}
        assert.notEqual(agent.status,'idle')
        const busy=await menu(record);assert.equal(busy.sessionId,agent.id,'busy writer navigation never reselects/claims')
        assert.equal(claims.length,claimsAfterExecution);releaseBusy();await agent.whenIdle()
        await select(agent,records[1])
        const changed=await menu(record);assert.notEqual(changed.sessionId,agent.id,'a previous writer now targeting another scene cannot be reused')
        assert.equal((await ctx.houdiniTargets.list({sessionId:agent.id})).selectedTarget.executor_id,records[1].executor_id)
        await ctx.workspaceRegistry.archiveSession(agent.id)
        const archived=await menu(record);assert.notEqual(archived.sessionId,agent.id)
        const standard=await ctx.sessionController.create({cwd:path.join(root,'standard'),agentPreset:'standard'})
        record.task_id=standard.sessionId;publish(record)
        const otherMode=await menu(record);assert.notEqual(otherMode.sessionId,standard.sessionId)
        const ungroupedFolder=path.join(root,'ungrouped');fs.mkdirSync(ungroupedFolder)
        const ungrouped=await ctx.sessionController.create({cwd:ungroupedFolder,agentPreset:'houdini'})
        const ungroupedAgent=ctx.agents.get(ungrouped.sessionId);await select(ungroupedAgent,record);await executeWriter(ungroupedAgent)
        const counts=ctx.workspaceRegistry.list().filter(row=>row.sessionIds.includes(ungroupedAgent.id)).length
        assert.equal(counts,0)
        const returned=await menu(record);assert.equal(returned.sessionId,ungroupedAgent.id);assert.equal(returned.workspaceId,undefined)
        report={ok:true,officialHost:true,controlledBridge:true,paidModelCalls:0,originalSessionId:agent.id,menuSessionId:original.sessionId,
          writerExecutions:executions.length,claims:claims.length,busyReused:true,changedTargetNotReused:true,archivedNotReused:true,
          otherModeNotReused:true,ungroupedSessionId:ungroupedAgent.id,ungroupedMembershipsBeforeBrowser:0}
        write(report)
      }catch(error){write({ok:false,error:String(error.stack||error)})}
    })
    const timer=setInterval(()=>{
      if(!report||report.browserConfirmed||!fs.existsSync(path.join(root,'browser-done.json')))return
      try{
        report.ungroupedMembershipsAfterBrowser=ctx.workspaceRegistry.list().filter(row=>row.sessionIds.includes(report.ungroupedSessionId)).length
        assert.equal(report.ungroupedMembershipsAfterBrowser,0);report.browserConfirmed=true;write(report)
      }catch(error){write({ok:false,error:String(error.stack||error)})}
    },50)
    return()=>{stopped=true;clearInterval(timer);releaseBusy();restorePresentation?.();server.close()}
  })
}
