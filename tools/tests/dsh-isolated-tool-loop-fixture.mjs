// Real Team and tools, real independent Houdini workers; only planning is scripted.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import http from 'node:http'
import {randomUUID,createHash} from 'node:crypto'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {setSandboxMode} from '@deepseek-ai/dsh-sandbox-policy'
import {EXPECTED_EXECUTION_CONTRACT_VERSION,EXPECTED_VERB_CATALOG_HASH,EXPECTED_VERB_NAMES} from '../../lib/generated-verb-contract.js'
import {fixturePresentation} from './fixture-presentation.mjs'

export const inject=['loader','llm','sessions','agents','sessionController','subagents','jobs','attachments','tools']
const provider='isolated-team-fixture',model='scripted-local'
const digest=bytes=>createHash('sha256').update(bytes).digest('hex')
const finish=text=>[{type:'block-start',index:0,blockType:'text'},
  {type:'block-end',index:0,block:{type:'text',text}},{type:'finish',reason:{kind:'stop'}}]
const tool=(id,name,args)=>[{type:'block-start',index:0,blockType:'tool-call'},
  {type:'block-end',index:0,block:{type:'tool-call',id,name,arguments:JSON.stringify(args)}},
  {type:'finish',reason:{kind:'tool-calls'}}]

function builder(){
  // The small image is rendered by actual Karma CPU, never replaced by a PNG fixture.
  return `g=tab_create('/obj','geo',name='team_box')
n=tab_create(g,'box',name='OUT')
c=tab_create('/obj','cam',name='team_camera')
camera_fit(c,n,width=64,height=64)
imp=tab_create('/stage','sceneimport',name='scene')
set_parms(imp,{'objects':g.path()+' '+c.path(),'forceobjects':g.path()+' '+c.path()})
tab_apply('/stage','lop_karma_setup')
settings=hou.node('/stage/karmarendersettings')
rop=hou.node('/stage/usdrender_rop1')
connect(imp,settings)
set_parms(settings,{'camera':'/team_camera','pathtracedsamples':2,'engine':'cpu'})
set_parms(rop,{'husk_enable_headlight':1,'husk_headlight':'distant'})
product=tab_create('/stage','pythonscript',name='product')
connect(settings,product)
connect(product,rop)
set_parms(rop,{'loppath':product.path()})
set_parms(product,{'python':"from pxr import UsdRender,Gf\\ns=hou.pwd().editableStage()\\nfor p in s.Traverse():\\n    if p.GetTypeName() == 'RenderProduct':\\n        UsdRender.Product(p).CreateResolutionAttr(Gf.Vec2i(64,64))".replace('\\\\n','\\n')})
__result__={'marker':'ISOLATED_TEAM_BUILT','points':len(n.geometry().points()),'primitives':len(n.geometry().prims())}
`
}

export function apply(ctx){
  const config=JSON.parse(fs.readFileSync(process.env.DSH_ISOLATED_TOOL_FIXTURE,'utf8'))
  const {workspace,output,hfs,hython,python}=config
  const checks=[],requests=[],sessions=new Set(),sessionRefs=new Map(),runtimeReads=[],images=[],runs={}
  let failure,childId,childStage=0,preflightStage=0,polls=0,childDone=false,leadId,jobId,nativeImage,ptcImage
  const evidence=()=>({requests,checks,runtimeReads,images,runs,leadId,childId})
  const report=value=>{fs.writeFileSync(output+'.tmp',JSON.stringify(value,null,2));fs.renameSync(output+'.tmp',output)}
  const events=id=>(sessionRefs.get(id)??ctx.sessions.get(id))?.snapshotEvents()??[]
  const native=(id,call)=>events(id).findLast(e=>e.type==='tool/result'&&e.data?.message?.source?.callId===call)?.data?.meta?.canonical
  const nested=(id,name)=>events(id).findLast(e=>e.type==='tool/ptc-dispatch'&&e.data?.name===name)
  const resultText=event=>(event?.data?.content??[]).filter(b=>b.type==='text').map(b=>b.text).join('\n')
  const recordEvents=()=>{for(const id of sessions)fs.writeFileSync(output+'.'+id+'.events.json',JSON.stringify(events(id),null,2))}
  const fail=async error=>{
    failure??=String(error.stack??error)
    for(const id of sessions)for(const job of ctx.jobs.list(id))if(['running','stopping'].includes(job.status)){
      try{await ctx.jobs.kill(job.id,id)}catch{}
    }
    recordEvents();report({ok:false,error:failure,...evidence()})
  }
  const fixture=path.join(workspace,'fixtures');fs.mkdirSync(fixture)
  const writeManifest=(name,script,render=false)=>{
    fs.writeFileSync(path.join(fixture,name+'.py'),script)
    const file=path.join(fixture,name+'.json')
    fs.writeFileSync(file,JSON.stringify({script:name+'.py',checks:[
      {id:'cook',kind:'cook',node:'/obj/team_box/OUT',frame:1,expect:{points:8,primitives:6}},
      ...(render?[{id:'cpu',kind:'render',node:'/stage/usdrender_rop1',frame:1,file:'image.png'}]:[]),
    ]}))
    return file
  }
  const bad=writeManifest('failure',"raise RuntimeError('ISOLATED_TEAM_EXPECTED_FAILURE')\n")
  const good=writeManifest('success',builder(),true)
  const invalid=path.join(fixture,'invalid.json')
  fs.writeFileSync(invalid,JSON.stringify({script:'success.py',hip:'invalid-unused.hip'}))
  const slow=writeManifest('slow',"import time\ntime.sleep(60)\ng=tab_create('/obj','geo',name='team_box')\nn=tab_create(g,'box',name='OUT')\n")
  const directory=name=>path.join(workspace,name)
  const args=(manifest,name,background=false)=>({operation:'run',manifest,output_dir:directory(name),timeout_seconds:120,memory_mb:4096,background})
  const readFull=(value,name)=>{
    assert.equal(value.kind,'isolated-houdini')
    const file=value.report_path??value.report?.details?.path??value.details?.path
    assert(file&&path.resolve(file)===path.join(directory(name),'report.json'),'authoritative report path must identify this run')
    const raw=JSON.parse(fs.readFileSync(file,'utf8'));runs[name]={path:file,ok:raw.ok,finished:raw.finished,worker:raw.worker,runtime:raw.result?.runtime,builder:raw.result?.builder}
    return raw
  }
  const returnedImage=(value,name)=>{
    const found=[]
    const visit=v=>{if(typeof v==='string'&&path.isAbsolute(v)&&/\.png$/i.test(v)&&fs.existsSync(v))found.push(v)
      else if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object')Object.values(v).forEach(visit)}
    visit(value)
    const actual=path.join(directory(name),'artifacts/cpu/image.png')
    assert(found.some(file=>path.resolve(file)===actual),'tool must expose its actual render path')
    return actual
  }
  const observeImages=async(options,label)=>{
    const refs=options.messages.flatMap(m=>m.content??[]).filter(b=>b.type==='image'&&b.attachment).map(b=>b.attachment)
    assert(refs.length,'the actual next model request must carry image attachment blocks: '+label)
    for(const ref of refs){const read=await ctx.attachments.readImage(ref);images.push({label,name:ref.name,width:ref.width,height:ref.height,bytes:read.data.length,sha256:digest(read.data)})}
    assert(refs.some(ref=>ref.width===64&&ref.height===64),'actual Karma image dimensions must reach the model')
  }
  // Only metadata discovery is a fixture. Production preset registration,
  // connection resolution and tool execution remain untouched and inherited.
  const server=http.createServer((req,res)=>{
    runtimeReads.push({method:req.method,path:req.url})
    res.setHeader('content-type','application/json')
    if(req.method==='GET'&&req.url==='/health'){
      res.end(JSON.stringify({ok:true,runtimeId:'a'.repeat(32),executionContractVersion:EXPECTED_EXECUTION_CONTRACT_VERSION,
        verbCatalog:{hash:EXPECTED_VERB_CATALOG_HASH,names:EXPECTED_VERB_NAMES,count:EXPECTED_VERB_NAMES.length},
        runtime:{hfs,python,pythonVersion:config.pythonVersion}}));return
    }
    if(req.url==='/context'){res.end(JSON.stringify({ok:true,result:{hip_path:'unused-fixture.hip',hip_is_new:true,frame:1,selection:[]}}));return}
    res.writeHead(500);res.end(JSON.stringify({error:'Fixture refuses all live execution requests'}))
  })
  const ready=new Promise((resolve,reject)=>{server.once('error',reject);server.listen(config.bridgePort,'127.0.0.1',resolve)})
  const presentation=fixturePresentation(ctx)
  ctx.on('agent/created',({agent})=>{sessions.add(agent.id);sessionRefs.set(agent.id,agent.session)})
  class Driver extends LlmAdapter{
    async listModels(){return[{provider,id:model,name:'Scripted isolated Team integration',inputModalities:['text','image']}]}
    async resolveModel(route,id){return{provider:route,id,name:'Scripted isolated Team integration',inputModalities:['text','image'],context:{contextWindow:500000}}}
    async *stream(options){
      if(options.purpose){yield*finish('Isolated Team integration');return}
      try{
        assert(!failure,failure)
        const own=ctx.sessions.get(options.sessionId),isChild=Boolean(own.header.parentSession)
        requests.push({sessionId:options.sessionId,parent:own.header.parentSession??null,stage:isChild?childStage:'lead',tools:options.tools.map(t=>t.name)})
        fs.writeFileSync(output+'.progress.json',JSON.stringify(evidence(),null,2))
        assert(requests.length<35,'scripted integration must converge')
        const emit=(id,name,value)=>{assert(options.tools.some(t=>t.name===name),'actual presentation must expose '+name);return tool(id,name,value)}
        if(!isChild){
          leadId=options.sessionId
          assert(options.tools.some(t=>t.name==='houdini_isolated'),'Host root tool reaches the Houdini preset')
          if(!events(leadId).some(e=>e.type==='tool/call'&&e.data?.name==='spawn_teammate')){
            yield*emit('lead-spawn','spawn_teammate',{name:'isolated-worker',description:'Exercise real isolated Houdini execution',context:'fresh',prompt:'ISOLATED_TOOL_CHILD: run the controlled independent Houdini fixture, report actual errors, inspect its images, cancel your own background run, and send lead the result.'});return
          }
          if(!childDone){yield*emit('lead-wait-'+requests.length,'wait_agent',{timeout_ms:10000});return}
          yield*finish('Actual isolated Team child completed all transport checks. Image semantics remain unverified.');return
        }
        childId=options.sessionId;assert.equal(own.header.parentSession,leadId)
        if(preflightStage===0){preflightStage++;yield*emit('child-preflight','houdini_isolated',args(invalid,'preflight'));return}
        if(preflightStage===1){
          const actual=native(childId,'child-preflight')
          assert.equal(actual?.kind,'isolated-houdini')
          assert.match(actual.error,/exactly one of script\/hip/,'checker preflight cause must survive when no report was created')
          const delivered=options.messages.find(m=>m.role==='tool'&&m.toolCallId==='child-preflight')
          const visible=(delivered?.content??[]).filter(b=>b.type==='text').map(b=>b.text).join('\n')
          assert.match(visible,/exactly one of script\/hip/,'the next real model request must receive the actionable preflight reason')
          assert(!/FsError|ENOENT/.test(actual.error),'a missing report must not replace the checker diagnosis')
          assert.equal(actual.process.exit_code,1)
          assert.equal(fs.existsSync(path.join(directory('preflight'),'report.json')),false,'invalid manifest must fail before worker/report creation')
          runs.preflight={error:actual.error,exit_code:actual.process.exit_code,report_created:false}
          checks.push('real Team child receives the checker preflight cause even when no worker/report exists')
          preflightStage++
        }
        if(childStage===0){childStage++;yield*emit('child-failure','houdini_isolated',args(bad,'failed'));return}
        if(childStage===1){
          const raw=readFull(native(childId,'child-failure'),'failed');assert.equal(raw.ok,false)
          assert(JSON.stringify(raw).includes('ISOLATED_TEAM_EXPECTED_FAILURE'),'actual builder exception survives model-facing tool')
          checks.push('real Team child received actual isolated builder failure')
          childStage++;yield*emit('child-native','houdini_isolated',args(good,'native'));return
        }
        if(childStage===2){
          const value=native(childId,'child-native'),raw=readFull(value,'native');assert.equal(raw.ok,true)
          assert.equal(raw.result.builder.result.marker,'ISOLATED_TEAM_BUILT');assert(raw.result.checks.every(c=>c.status==='passed'))
          nativeImage=returnedImage(value,'native');await observeImages(options,'native-return')
          checks.push('native production tool built, cooked and Karma-rendered a new independent HIP')
          childStage++;presentation.after('child-read-native','run_code');yield*emit('child-read-native','read_image',{file_path:nativeImage});return
        }
        if(childStage===3){
          await observeImages(options,'native-read-image');checks.push('real native read_image exposes rendered bytes to the next model request')
          childStage++;yield*emit('child-ptc','run_code',{code:'return await tools.houdini_isolated('+JSON.stringify(args(good,'ptc'))+');',description:'Run the same isolated builder through native PTC dispatch'});return
        }
        if(childStage===4){
          const dispatch=nested(childId,'houdini_isolated');assert(dispatch&&!dispatch.data.isError,'real PTC sub-dispatch settled successfully')
          const raw=JSON.parse(fs.readFileSync(path.join(directory('ptc'),'report.json'),'utf8'));assert.equal(raw.ok,true)
          assert(resultText(dispatch).includes('isolated-houdini'),'nested durable receipt preserves tool identity')
          const actual=dispatch.data.meta?.canonical
          assert(actual,'nested production presentation must retain its canonical receipt')
          readFull(actual,'ptc');ptcImage=returnedImage(actual,'ptc')
          assert.notEqual(raw.result.runtime.runtime_id,runs.native.runtime.runtime_id,'each run must use another Houdini runtime')
          runs.ptc={runtime:raw.result.runtime,worker:raw.worker};await observeImages(options,'ptc-return')
          checks.push('real PTC dispatch and attachment ferry preserve an independent runtime and render')
          childStage++;presentation.after('child-read-ptc','houdini_isolated');yield*emit('child-read-ptc','run_code',{code:'return await tools.read_image('+JSON.stringify({file_path:ptcImage})+');',description:'Inspect the actual isolated render through PTC read_image'});return
        }
        if(childStage===5){await observeImages(options,'ptc-read-image');checks.push('nested read_image exposes the actual rendered image to the model');childStage++;yield*emit('child-background','houdini_isolated',args(slow,'cancelled',true));return}
        if(childStage===6){
          jobId??=native(childId,'child-background')?.job_id;assert(jobId,'background tool must return native DSH job id')
          const progress=path.join(directory('cancelled'),'worker-result.json')
          const phase=fs.existsSync(progress)?JSON.parse(fs.readFileSync(progress,'utf8')).phase:null
          if(phase!=='builder'){assert(polls++<12,'real worker must start before cancellation');yield*emit('child-poll-'+polls,'job_output',{job_id:jobId,wait:true,timeout_ms:1000});return}
          childStage++;yield*emit('child-kill','job_kill',{job_id:jobId});return
        }
        if(childStage===7){childStage++;yield*emit('child-job-end','job_output',{job_id:jobId,wait:true,timeout_ms:20000});return}
        if(childStage===8){
          const received=events(childId).findLast(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='child-job-end')
          assert(received&&!received.data.message.isError,'native job_output must return successfully')
          const observed=ctx.jobs.get(jobId,childId)
          assert(observed&&['killed','failed','completed'].includes(observed.status),'native job must be terminal')
          childStage++;yield*emit('child-read-cancel','houdini_isolated',{operation:'read',output_dir:directory('cancelled')});return
        }
        if(childStage===9){
          const raw=readFull(native(childId,'child-read-cancel'),'cancelled');assert(raw.finished&&raw.ok===false)
          assert.equal(raw.worker.status,'cancelled')
          assert(Number.isInteger(raw.worker.returncode),'terminal cancellation must include the actual worker exit')
          checks.push('native DSH job_kill cancels only this real worker; read returns its terminal evidence')
          childStage++;yield*emit('child-report','send_message',{target:'lead',message:'ISOLATED_TOOL_CHILD_VERIFIED: actual builder error, native/PTC Karma images, read_image and native job cancellation passed. Semantic image quality remains unverified.'});return
        }
        childDone=true;yield*finish('ISOLATED_TOOL_CHILD_VERIFIED');return
      }catch(error){await fail(error);throw error}
    }
  }
  ctx.llm.registerAdapter([provider],new Driver())
  ctx.effect(()=>{queueMicrotask(async()=>{
    try{
      await ready;await ctx.loader.await()
      const created=await ctx.sessionController.create({cwd:workspace,agentPreset:'houdini'})
      leadId=created.sessionId
      // An explicit full-access diagnostic separates transport failures from
      // Windows token admission. Normal qualification uses workspace-write.
      setSandboxMode(ctx.sessions.get(leadId),config.sandboxMode??'workspace-write')
      await ctx.sessionController.selectModel({sessionId:leadId,provider,model})
      await ctx.sessionController.prompt({sessionId:leadId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:'Create one actual Team teammate to execute the isolated Houdini integration fixture.'}]},AbortSignal.timeout(210000))
      const lead=ctx.agents.get(leadId)
      for(let i=0;i<8;i++){await lead.whenIdle();if(!await ctx.subagents.waitForChildren(lead)&&childDone)break}
      assert(childDone&&!failure,failure??'child did not finish')
      const leadEvents=events(leadId),members=leadEvents.filter(e=>e.type==='team/member'&&e.data?.member?.phase==='active')
      assert.equal(members.length,1);assert(leadEvents.some(e=>e.type==='subagent/catalog'))
      assert(leadEvents.some(e=>e.type==='user/message'&&JSON.stringify(e.data).includes('ISOLATED_TOOL_CHILD_VERIFIED')),'actual Team peer result must reach Lead')
      assert(runtimeReads.some(r=>r.path==='/health'),'production tool must discover runtime through the configured metadata route')
      assert(runtimeReads.every(r=>r.path==='/context'||r.path==='/health'),'no operation may be sent to live Houdini')
      // The normal subagent manager flushes and disposes a settled child.
      // Flush only residents; retained immutable Session handles supply evidence.
      for(const id of sessions){const resident=ctx.sessions.get(id);if(resident)await ctx.sessions.flush(resident)}
      recordEvents();checks.push('real Team creation, independent child session, persisted native/PTC events and peer result delivery')
      report({ok:true,realTeamChildren:members.length,sandboxMode:config.sandboxMode??'workspace-write',...evidence(),boundary:'Exact DSH Team/Agent/tool/job/attachment loop with inherited production tool registration, actual disposable hython and Karma CPU. Only health/context metadata and model planning are controlled fixtures. Sandbox mode: '+(config.sandboxMode??'workspace-write')+'. No user live Houdini/HIP, external model API, GUI or semantic visual quality claim.'})
    }catch(error){await fail(error)}
  });return()=>server.close()})
}
