// Scripted model and health metadata only; DSH, tool scopes, file policy and media CLI remain real.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import {randomUUID,createHash} from 'node:crypto'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {setSandboxMode} from '@deepseek-ai/dsh-sandbox-policy'
import {EXPECTED_EXECUTION_CONTRACT_VERSION,EXPECTED_VERB_CATALOG_HASH,EXPECTED_VERB_NAMES} from '../../lib/generated-verb-contract.js'
export const inject=['loader','llm','settings','sessions','agents','sessionController','sandboxPolicy','houdiniFrontend']
export function apply(ctx){
  const workspace=process.env.DSH_LOCAL_VIDEO_WORKSPACE,output=process.env.DSH_LOCAL_VIDEO_RESULT
  const frames=path.join(workspace,'frames'),index=path.join(workspace,'index'),indexFile=path.join(index,'index.json')
  const source=path.join(workspace,'source.mp4'),sourceHash=createHash('sha256').update(fs.readFileSync(source)).digest('hex')
  const driver='local-video-fixture',checks=[];let steps=0,failure
  const report=value=>fs.writeFileSync(output,JSON.stringify(value,null,2))
  const server=http.createServer(async(req,res)=>{
    res.setHeader('content-type','application/json')
    const health={ok:true,executorId:process.env.DSH_HOUDINI_EXECUTOR_ID,runtimeId:'b'.repeat(32),houVersion:'22.0.368',
      executionContractVersion:EXPECTED_EXECUTION_CONTRACT_VERSION,verbCatalog:{hash:EXPECTED_VERB_CATALOG_HASH,count:EXPECTED_VERB_NAMES.length,names:EXPECTED_VERB_NAMES},
      runtime:{hfs:process.env.DSH_LOCAL_VIDEO_HFS,python:process.env.DSH_LOCAL_VIDEO_PYTHON,pythonVersion:process.env.DSH_LOCAL_VIDEO_PYTHON_VERSION,executable:path.join(process.env.DSH_LOCAL_VIDEO_HFS,'bin','houdini.exe')}}
    if(req.url==='/health'){res.end(JSON.stringify(health));return}
    if(req.url==='/requests/prepare'){res.end(JSON.stringify({...health,requestRef:'b'.repeat(32)+'.'+randomUUID().replaceAll('-','')}));return}
    if(req.url==='/context'){res.end(JSON.stringify({ok:true,result:{hip_path:path.join(workspace,'unused.hip'),hip_is_new:false,frame:1,selection:[]}}));return}
    res.writeHead(404);res.end('{}')
  })
  const ready=new Promise((resolve,reject)=>{server.once('error',reject);server.listen(Number(new URL(process.env.DSH_HOUDINI_BRIDGE_URL).port),'127.0.0.1',resolve)})
  const text=value=>[{type:'block-start',index:0,blockType:'text'},{type:'block-end',index:0,block:{type:'text',text:value}},{type:'finish',reason:{kind:'stop'}}]
  class Driver extends LlmAdapter{
    async listModels(){return[{provider:driver,id:'scripted',name:'Local evidence fixture',inputModalities:['text']}]}
    async resolveModel(provider,id){return{provider,id,name:'Local evidence fixture',inputModalities:['text'],context:{contextWindow:300000}}}
    async *stream(options){
      if(options.purpose){yield*text('Local video fixture');return}
      try{
        const step=steps++;assert(step<8,'fixture converges')
        const events=ctx.sessions.get(options.sessionId).snapshotEvents()
        const native=id=>events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId===id)?.data?.meta?.canonical
        if(step===1){
          const info=native('local-0');assert.equal(info.runtime.pythonScope,'selected-executor')
          assert.equal(info.runtime.python,process.env.DSH_LOCAL_VIDEO_PYTHON);assert.equal(info.runtime.executorId,'a'.repeat(32))
          checks.push('native configuration follows selected executor metadata when Host HFS is absent')
        }
        if(step===2){const value=native('local-1');assert(value.ok,value.error);assert.equal(value.result.frames,2);assert.equal(value.cloud_request,false)
          assert(fs.existsSync(path.join(frames,'frames.json')));checks.push('native offline review writes actual PTS evidence without shell')}
        if(step===3){
          const dispatch=events.find(e=>e.type==='tool/ptc-dispatch'&&e.data?.name==='video_process');assert(dispatch&&!dispatch.data.isError)
          const value=JSON.parse(dispatch.data.content.find(b=>b.type==='text').text);assert(value.ok,value.error)
          assert(fs.existsSync(indexFile));checks.push('nested tool uses same offline CLI and workspace output policy')
        }
        if(step===5){assert(!events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='local-4')?.data?.message?.isError)
          checks.push('module authoring uses DSH native write')}
        if(step===6){const value=native('local-5');assert(value.ok,value.error);assert.equal(value.result.modules[0].purpose,'Inspect source frames')
          checks.push('native query consumes the actual written module interface and source hash')}
        if(step===7){const outcome=events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='local-6')
          assert(outcome.data.message.isError,'outside output is rejected by real DSH tool call')
          assert.equal(createHash('sha256').update(fs.readFileSync(source)).digest('hex'),sourceHash)
          checks.push('outside destination rejected, source immutable, no paid API')
          yield*text('Local evidence fixture complete.');return}
        let call
        if(step===0)call=['video_models',{}]
        if(step===1)call=['video_process',{operation:'review',options:{video:source,output:frames,start:0,duration:2,interval:1}}]
        if(step===2)call=['run_code',{code:'return await tools.video_process('+JSON.stringify({operation:'index-init',options:{frames_dir:frames,output:index}})+');',description:'Exercise native nested local evidence operation'}]
        if(step===3)call=['read',{file_path:indexFile}]
        if(step===4){const draft=JSON.parse(fs.readFileSync(indexFile,'utf8'));draft.chapters=[{id:'chapter-source',title:'Source',ranges:[[0,2]]}]
          draft.modules=[{id:'source-module',title:'Source',ranges:[[0,2]],purpose:'Inspect source frames',inputs:['source video'],outputs:['observations'],depends_on:[],questions:[],unknowns:['Not semantically reviewed'],evidence:[]}]
          call=['write',{file_path:indexFile,content:JSON.stringify(draft)}]}
        if(step===5)call=['video_process',{operation:'read-index',options:{index:indexFile}}]
        if(step===6)call=['video_process',{operation:'review',options:{video:source,output:path.join(path.dirname(workspace),'forbidden-output'),duration:2}}]
        const[name,args]=call;assert(options.tools.some(tool=>tool.name===name))
        yield{type:'block-start',index:0,blockType:'tool-call'}
        yield{type:'block-end',index:0,block:{type:'tool-call',id:'local-'+step,name,arguments:JSON.stringify(args)}}
        yield{type:'finish',reason:{kind:'tool-calls'}}
      }catch(error){failure=String(error.stack||error);report({ok:false,error:failure,steps,checks});throw error}
    }
  }
  ctx.llm.registerAdapter([driver],new Driver())
  ctx.on('agent/created',({agent})=>agent.ctx.tools.presentAs('both'))
  ctx.effect(()=>{queueMicrotask(async()=>{
    try{
      await ready;await ctx.loader.await()
      const settings=ctx.settings.describe().find(row=>row.ns==='houdini-frontend')
      await ctx.settings.mutate(settings.ns,[{op:'set',path:['videoPython'],value:''}],settings.revision)
      const {sessionId}=await ctx.sessionController.create({cwd:workspace,agentPreset:'houdini'})
      setSandboxMode(ctx.sessions.get(sessionId),'workspace-write')
      await ctx.sessionController.selectModel({sessionId,provider:driver,model:'scripted'})
      await ctx.sessionController.prompt({sessionId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:'Run the local evidence transport fixture.'}]},AbortSignal.timeout(90000))
      await ctx.agents.get(sessionId).whenIdle();assert(!failure,failure);assert.equal(steps,8)
      report({ok:true,sessionId,steps,checks,boundary:'Exact DSH native/PTC, real Python/private FFmpeg/file policy, fixture planning model and health metadata. No Houdini scene, cloud API, artwork or GUI claim.'})
    }catch(error){report({ok:false,error:String(error.stack||error),steps,checks})}
  });return()=>server.close()})
}
