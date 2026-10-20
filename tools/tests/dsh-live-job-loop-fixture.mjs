// Real native jobs, tool dispatch and HOM; only planning and fixture release are controlled.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {randomUUID,createHash} from 'node:crypto'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {setSandboxMode} from '@deepseek-ai/dsh-sandbox-policy'
import {fixturePresentation} from './fixture-presentation.mjs'
import {executionHistory} from '../../lib/execution-history.js'

export const inject=['loader','llm','sessions','agents','sessionController','jobs','attachments']
const provider='live-job-fixture',model='scripted-local'
const finish=text=>[{type:'block-start',index:0,blockType:'text'},
  {type:'block-end',index:0,block:{type:'text',text}},{type:'finish',reason:{kind:'stop'}}]
const call=(id,name,args)=>[{type:'block-start',index:0,blockType:'tool-call'},
  {type:'block-end',index:0,block:{type:'tool-call',id,name,arguments:JSON.stringify(args)}},
  {type:'finish',reason:{kind:'tool-calls'}}]

export function apply(ctx){
  const config=JSON.parse(fs.readFileSync(process.env.DSH_LIVE_JOB_FIXTURE,'utf8'))
  const {directory,phase}=config,output=path.join(directory,phase+'-result.json')
  const checks=[],requests=[],handles={},values={}
  let stage=0,failure,sessionId,complete
  const done=new Promise(resolve=>{complete=resolve})
  const report=value=>{fs.writeFileSync(output+'.tmp',JSON.stringify(value,null,2));fs.renameSync(output+'.tmp',output)}
  const events=()=>ctx.sessions.get(sessionId)?.snapshotEvents()??[]
  const text=message=>(message?.content??[]).filter(b=>b.type==='text').map(b=>b.text).join('\n')
  const native=id=>events().findLast(e=>e.type==='tool/result'&&e.data?.message?.source?.callId===id)?.data?.meta?.canonical
  const nested=name=>events().findLast(e=>e.type==='tool/ptc-dispatch'&&e.data?.name===name)
  const nestedValue=event=>{
    assert(event?.data?.meta&&Object.hasOwn(event.data.meta,'canonical'),
      'current PTC results must use DSH canonical metadata')
    assert(!(event.data.content??[]).some(block=>{
      try{return JSON.parse(block.text).kind==='dsh-houdini/execution-v1'}catch{return false}
    }),'current PTC logs must not duplicate canonical data in a plugin wrapper')
    return event.data.meta.canonical
  }
  const emitted=id=>events().findLast(e=>e.type==='tool/result'&&e.data?.message?.source?.callId===id)
  const parseResult=content=>{
    for(const line of content.split('\n')){try{const value=JSON.parse(line);if(value.kind==='dsh-houdini/live-job-result-v1')return value}catch{}}
    throw Error('Native job_output must carry the original self-identified Houdini result: '+content.slice(0,1600))
  }
  const fullResult=id=>parseResult(native(id)?.text??text(emitted(id)?.data?.message))
  const waitFor=async(file)=>{
    const deadline=Date.now()+15000
    while(!fs.existsSync(file)){assert(Date.now()<deadline,'Owned Houdini fixture did not enter its job: '+file);await new Promise(resolve=>setTimeout(resolve,25))}
  }
  const release=name=>fs.writeFileSync(path.join(directory,'release-'+name),'release')
  const code=(name,hold=true)=>`from pathlib import Path
import time
Path(${JSON.stringify(path.join(directory,'entered-'+name))}).write_text('entered')
${hold?`deadline=time.monotonic()+90
while not Path(${JSON.stringify(path.join(directory,'release-'+name))}).exists():
    if time.monotonic()>deadline: raise RuntimeError('owned fixture release timed out')
    time.sleep(0.02)` : ''}
node=tab_create('/obj','geo',name='__livejobs_${name}')
${name==='native'?`from dsh_media_output import report_image
report_image(${JSON.stringify(path.join(directory,'reported-image.png'))})`:''}
__result__={'marker':'${name==='lost'?'TRANSPORT_LOST':name}','node':node.path()${['native','running'].includes(name)?",'payload':'LIVE_BULK_HEAD:'+'x'*70000+':LIVE_BULK_TAIL'":''}}
`
  const captureHandle=(name,value,rootCallId)=>{
    assert(value?.job_id,'submission/recovery must expose the native DSH job id')
    handles[name]=value
    const registration=events().findLast(e=>e.type==='job/registered'&&e.data?.jobId===value.job_id)
    assert(registration,'native job registration must be durable in the same session')
    assert.equal(registration.data.owner,sessionId)
    assert.equal(registration.data.toolCall.rootCallId,rootCallId)
    assert.equal(ctx.jobs.get(value.job_id,sessionId).owner,sessionId)
    return value
  }
  const checkValue=(name,envelope)=>{
    assert.equal(envelope.job_id,handles[name].job_id)
    const value=envelope.value
    if(handles[name].jobId)assert.equal(value.jobId,handles[name].jobId)
    else {assert.match(value.jobId,/^[0-9a-f]{12}$/);handles[name]={...handles[name],jobId:value.jobId}}
    if(name!=='queued'){
      assert.equal(value.ok,true,JSON.stringify(value))
      assert.equal(value.status,'done')
      assert.equal(value.result.node,'/obj/__livejobs_'+name)
      assert.equal(value.execution.owner_session,sessionId)
      assert.equal(value.execution.executor_id,process.env.DSH_HOUDINI_EXECUTOR_ID)
      assert.equal(ctx.jobs.get(envelope.job_id,sessionId).status,'completed')
    }else{
      assert.equal(value.status,'cancelled')
      assert.equal(ctx.jobs.get(envelope.job_id,sessionId).status,'killed')
    }
    values[name]=value
    const history=executionHistory(events())
    assert(!history.activeJobs.some(([id])=>id===value.jobId),'the same collected terminal result must clear active execution state')
    return value
  }
  const notice=(options,name)=>{
    assert(options.messages.some(message=>message.source?.kind==='tool-jobs'&&text(message).includes(handles[name].job_id)),
      'the actual next model request must receive the native completion notice for '+name)
  }
  const checkImage=async(options,label)=>{
    const actual=fs.readFileSync(path.join(directory,'reported-image.png'))
    const refs=options.messages.flatMap(message=>message.content??[]).filter(block=>block.type==='image'&&block.attachment)
    assert(refs.length,'the actual provider request must receive the recovered original image: '+label)
    const found=await Promise.all(refs.map(async block=>{
      const value=await ctx.attachments.readImage(block.attachment)
      return value.data.length===actual.length&&createHash('sha256').update(value.data).digest('hex')===createHash('sha256').update(actual).digest('hex')
    }))
    assert(found.some(Boolean),'the attachment must contain the exact original Bridge media bytes')
  }
  const presentation=fixturePresentation(ctx)
  const dispatch=(id,name,args,next)=>{presentation.after(id,next);return call(id,name,args)}
  class Driver extends LlmAdapter{
    async listModels(){return[{provider,id:model,name:'Owned live job integration',inputModalities:['text','image']}]}
    async resolveModel(route,id){return{provider:route,id,name:'Owned live job integration',inputModalities:['text','image'],context:{contextWindow:500000}}}
    async *stream(options){
      if(options.purpose){yield*finish('Live job integration');return}
      try{
        requests.push({stage,sessionId:options.sessionId,tools:options.tools.map(t=>t.name)})
        assert.equal(options.sessionId,sessionId)
        assert(!options.tools.some(t=>['houdini_job_status','houdini_job_cancel'].includes(t.name)),
          'native jobs must replace duplicate public status/cancel controls')
        if(phase==='restart'){
          if(stage===0){stage++;yield*dispatch('restart-lookup','houdini_request',{request_ref:handles.restart.requestReceipt.request_ref},'job_output');return}
          if(stage===1){
            const value=native('restart-lookup')
            assert.equal(value.jobId,handles.restart.jobId)
            const old=handles.restart.job_id
            captureHandle('restart',value,'restart-lookup')
            assert.notEqual(value.job_id,old,'a reopened Host creates one new local observer, not a pretend durable native registry')
            assert.equal(value.status,'running','Host reopening must leave the original HOM job running')
            release('restart');stage++;yield*dispatch('restart-output','job_output',{job_id:value.job_id,wait:true,timeout_ms:20000},'houdini_inspect');return
          }
          if(stage===2){checkValue('restart',fullResult('restart-output'));checks.push('cold Host loads the same session and reattaches to original Bridge work without resubmission');stage++;yield*dispatch('restart-observe','houdini_inspect',{code:"__result__=[n.path() for n in hou.node('/obj').children() if n.name().startswith('__livejobs_')]"});return}
          if(stage===3){
            const names=native('restart-observe').result
            assert.deepEqual([...names].sort(),['lost','native','restart','running'].map(name=>'/obj/__livejobs_'+name).sort())
            const metrics=await fetch(process.env.DSH_HOUDINI_BRIDGE_URL+'/fixture-metrics').then(r=>r.json())
            const submissions=metrics.calls.filter(row=>row.path==='/jobs')
            assert.equal(submissions.length,5,'four executed jobs plus the single queued cancellation; recovery never resubmits')
            assert.equal(metrics.dropped.length,1)
            checks.push('native, nested, cancelled, lost-response and reopened jobs share exact original execution identities and execute once')
            complete();stage++;yield*finish('Original live-job results verified after reopening the Host.');return
          }
          throw Error('Unexpected restart stage '+stage)
        }
        if(stage===0){stage++;yield*dispatch('native-submit','houdini_job_submit',{code:code('native')});return}
        if(stage===1){
          captureHandle('native',native('native-submit'),'native-submit')
          const peer=await ctx.sessionController.create({cwd:directory,agentPreset:'houdini'})
          assert(!ctx.jobs.list(peer.sessionId).some(job=>job.id===handles.native.job_id))
          assert.throws(()=>ctx.jobs.get(handles.native.job_id,peer.sessionId))
          assert.throws(()=>ctx.jobs.kill(handles.native.job_id,peer.sessionId))
          checks.push('another conversation cannot inspect or cancel the original session native job')
          await waitFor(path.join(directory,'entered-native'));release('native');stage++;yield*finish('Await the native completion notice.');return
        }
        if(stage===2){notice(options,'native');checks.push('native unawaited completion wakes the original owning session');stage++;yield*dispatch('native-output','job_output',{job_id:handles.native.job_id},'houdini_request');return}
        if(stage===3){
          const value=checkValue('native',fullResult('native-output'))
          assert.equal(value.result.payload,'LIVE_BULK_HEAD:'+'x'.repeat(70000)+':LIVE_BULK_TAIL')
          assert(native('native-output').text.length>70000,'the durable native job_output retains its complete generic value')
          const visible=text(options.messages.find(message=>message.role==='tool'&&message.toolCallId==='native-output'))
          assert(Buffer.byteLength(visible)<=ctx.jobs.get(handles.native.job_id,sessionId).outputLimitBytes,
            'the model-facing read respects its producer byte cap')
          checks.push('large native job output keeps its exact complete durable result while bounding the model presentation')
          stage++;yield*dispatch('native-lookup','houdini_request',{request_ref:handles.native.requestReceipt.request_ref},'run_code');return
        }
        if(stage===4){
          const read=native('native-lookup');assert.equal(read.result.node,values.native.result.node);assert.equal(read.execution.sequence,values.native.execution.sequence)
          await checkImage(options,'native receipt lookup')
          checks.push('native job_output and receipt recovery consume the same real execution result')
          stage++;yield*dispatch('running-submit','run_code',{code:'await tools.houdini_request('+JSON.stringify({request_ref:handles.native.requestReceipt.request_ref})+'); return await tools.houdini_job_submit('+JSON.stringify({code:code('running')})+');',description:'Read original job media and start one controlled running HOM job'},'job_kill');return
        }
        if(stage===5){
          await checkImage(options,'nested receipt lookup')
          checks.push('native and nested receipt collection deliver the exact original media bytes to the next model request')
          const value=nestedValue(nested('houdini_job_submit'));captureHandle('running',value,'running-submit')
          const registered=events().findLast(e=>e.type==='job/registered'&&e.data.jobId===value.job_id)
          assert.notEqual(registered.data.toolCall.callId,registered.data.toolCall.rootCallId,'PTC preserves exact subcall identity')
          await waitFor(path.join(directory,'entered-running'));stage++;yield*dispatch('running-kill','job_kill',{job_id:value.job_id},'houdini_request');return
        }
        if(stage===6){
          assert.equal(ctx.jobs.get(handles.running.job_id,sessionId).status,'stopping','a cancellation request cannot claim running HOM stopped')
          stage++;yield*dispatch('running-lookup','houdini_request',{request_ref:handles.running.requestReceipt.request_ref},'run_code');return
        }
        if(stage===7){
          const read=native('running-lookup');assert.equal(read.status,'running');assert.match(read.advisory,/cannot be interrupted|Running HOM/i)
          release('running');stage++;yield*finish('The same running HOM job is still responsible for its actual result.');return
        }
        if(stage===8){notice(options,'running');checks.push('running HOM cancellation remains stopping until actual completion and still delivers its completed notice');stage++;yield*dispatch('running-output','run_code',{code:'return await tools.job_output('+JSON.stringify({job_id:handles.running.job_id})+');',description:'Collect the same completed running HOM job through nested native jobs'},'houdini_job_submit');return}
        if(stage===9){
          const output=nested('job_output');assert(output&&!output.data.isError,JSON.stringify(output))
          const original=nestedValue(output)
          const value=checkValue('running',parseResult(original?.text??(output.data.content??[]).filter(b=>b.type==='text').map(b=>b.text).join('\n')))
          assert(original?.text.length>70000,'the PTC durable generic result stays complete before presentation retention')
          assert.equal(value.result.payload,'LIVE_BULK_HEAD:'+'x'.repeat(70000)+':LIVE_BULK_TAIL')
          checks.push('nested job_output preserves its complete generic value and the same original execution facts')
          fs.writeFileSync(path.join(directory,'pause-pump'),'paused');stage++;yield*dispatch('queued-submit','houdini_job_submit',{code:code('queued',false)},'job_kill');return
        }
        if(stage===10){captureHandle('queued',native('queued-submit'),'queued-submit');stage++;yield*dispatch('queued-kill','job_kill',{job_id:handles.queued.job_id},'job_output');return}
        if(stage===11){
          const stopped=await ctx.jobs.wait(handles.queued.job_id,20000,sessionId)
          assert.equal(stopped.status,'killed','keep the fixture queue paused until remote cancellation is actually confirmed')
          fs.rmSync(path.join(directory,'pause-pump'));stage++;yield*dispatch('queued-output','job_output',{job_id:handles.queued.job_id,wait:true,timeout_ms:20000},'houdini_job_submit');return
        }
        if(stage===12){checkValue('queued',fullResult('queued-output'));assert(!fs.existsSync(path.join(directory,'entered-queued')));checks.push('queued job_kill prevents its HOM body from ever executing');stage++;yield*dispatch('lost-submit','houdini_job_submit',{code:code('lost')},'job_output');return}
        if(stage===13){
          captureHandle('lost',native('lost-submit'),'lost-submit')
          assert.equal(handles.lost.requestReceipt.status,'unknown_transport','the relay lost the admitted response')
          await waitFor(path.join(directory,'entered-lost'));release('lost');stage++;yield*dispatch('lost-output','job_output',{job_id:handles.lost.job_id,wait:true,timeout_ms:20000},'houdini_job_submit');return
        }
        if(stage===14){checkValue('lost',fullResult('lost-output'));checks.push('lost admission response recovers its original request without replay');stage++;yield*dispatch('restart-submit','houdini_job_submit',{code:code('restart')});return}
        if(stage===15){captureHandle('restart',native('restart-submit'),'restart-submit');await waitFor(path.join(directory,'entered-restart'));checks.push('running original job is retained for a separate Host reopen');complete();stage++;yield*finish('The next Host must recover this original running job.');return}
        throw Error('Unexpected initial stage '+stage)
      }catch(error){failure=String(error.stack??error);complete();report({ok:false,error:failure,stage,checks,handles,requests});throw error}
    }
  }
  ctx.llm.registerAdapter([provider],new Driver())
  ctx.effect(()=>{queueMicrotask(async()=>{
    try{
      await ctx.loader.await()
      if(phase==='restart'){
        const prior=JSON.parse(fs.readFileSync(path.join(directory,'initial-result.json'),'utf8'))
        sessionId=prior.sessionId;Object.assign(handles,prior.handles)
        await ctx.sessionController.resolveAgent(sessionId)
        assert(!ctx.jobs.list(sessionId).some(job=>job.id===handles.restart.job_id),'a new Host has no stale in-process job controller')
      }else{
        ;({sessionId}=await ctx.sessionController.create({cwd:directory,agentPreset:'houdini'}))
        setSandboxMode(ctx.sessions.get(sessionId),'workspace-write')
      }
      await ctx.sessionController.selectModel({sessionId,provider,model})
      await ctx.sessionController.prompt({sessionId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:
        phase==='restart'?'Recover the original owned Houdini job after reopening this Host.':'Exercise native jobs in this disposable Houdini session.'}]},AbortSignal.timeout(120000))
      await Promise.race([done,new Promise((_,reject)=>setTimeout(()=>reject(Error('Native completion/recovery loop timed out')),120000))])
      await ctx.agents.get(sessionId).whenIdle();assert(!failure,failure)
      await ctx.sessions.flush(ctx.sessions.get(sessionId))
      fs.writeFileSync(path.join(directory,phase+'-events.json'),JSON.stringify(events(),null,2))
      report({ok:true,sessionId,stage,checks,handles,values,requests,boundary:'Real pinned DSH jobs/native/PTC and a disposable HOM Bridge; scripted planning only.'})
    }catch(error){report({ok:false,error:String(error.stack??error),sessionId,stage,checks,handles,requests})}
  })})
}
