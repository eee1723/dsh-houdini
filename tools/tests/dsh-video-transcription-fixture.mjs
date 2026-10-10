// Only the ASR endpoint and planning model are fixtures. Settings, credentials,
// agent scopes, native/PTC transport and the Python audio worker remain real.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import {createHash,randomUUID} from 'node:crypto'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {setSandboxMode} from '@deepseek-ai/dsh-sandbox-policy'
import {EXPECTED_EXECUTION_CONTRACT_VERSION,EXPECTED_VERB_CATALOG_HASH,EXPECTED_VERB_NAMES}
  from '../../lib/generated-verb-contract.js'

export const inject=['loader','llm','settings','credentials','sessions','agents','sessionController','sandboxPolicy','houdiniFrontend']
const provider='fixture-transcription',driver='video-fixture-driver',reference='DSH_VIDEO_FIXTURE_KEY'
const sha=value=>createHash('sha256').update(value).digest('hex')

export function apply(ctx) {
  const workspace=process.env.DSH_VIDEO_FIXTURE_WORKSPACE,base=process.env.DSH_VIDEO_FIXTURE_BASE
  const output=process.env.DSH_VIDEO_FIXTURE_OUT,restart=process.env.DSH_VIDEO_FIXTURE_PHASE==='restart'
  const workA=path.join(workspace,'prepared-a'),workB=path.join(workspace,'prepared-b')
  const requests=[],checks=[];let steps=0,failure,secret
  const report=value=>{fs.writeFileSync(output+'.tmp',JSON.stringify(value,null,2));fs.renameSync(output+'.tmp',output)}
  const fail=error=>{failure??=String(error.stack||error);report({ok:false,error:failure,requests,checks,steps})}
  const read=(work,name)=>JSON.parse(fs.readFileSync(path.join(work,name),'utf8'))
  const server=http.createServer(async(req,res)=>{
    try {
      if(req.url==='/health') {res.setHeader('content-type','application/json');res.end(JSON.stringify({ok:true,runtimeId:'b'.repeat(32),
        executorId:process.env.DSH_HOUDINI_EXECUTOR_ID,executionContractVersion:EXPECTED_EXECUTION_CONTRACT_VERSION,
        runtime:{hfs:path.dirname(path.dirname(process.env.DSH_VIDEO_FIXTURE_PYTHON)),python:process.env.DSH_VIDEO_FIXTURE_PYTHON,
          pythonVersion:process.env.DSH_VIDEO_FIXTURE_PYTHON_VERSION,executable:process.env.DSH_VIDEO_FIXTURE_PYTHON},
        verbCatalog:{hash:EXPECTED_VERB_CATALOG_HASH,names:EXPECTED_VERB_NAMES,count:EXPECTED_VERB_NAMES.length}}));return}
      if(req.url==='/context') {res.setHeader('content-type','application/json');res.end(JSON.stringify({ok:true,result:{
        hip_path:path.join(workspace,'unused.hip'),hip_is_new:false,runtime_id:'b'.repeat(32),frame:1,selection:[]}}));return}
      assert(!restart,'Completed chunks must not upload after Host restart')
      assert.equal(req.method,'POST');assert.equal(req.headers.authorization,'Bearer '+secret)
      const buffers=[];for await(const bytes of req)buffers.push(bytes)
      const body=Buffer.concat(buffers)
      let model,bytes
      if(req.url==='/v1/chat/completions') {
        assert.equal(req.headers['content-type'],'application/json')
        const value=JSON.parse(body);model=value.model
        assert.equal(model,'qwen3-asr-flash');assert.equal(value.stream,false)
        assert.deepEqual(value.asr_options,{enable_itn:false})
        assert.equal(value.messages.length,1);assert.equal(value.messages[0].role,'user')
        const audio=value.messages[0].content[0]
        assert.equal(audio.type,'input_audio');assert(audio.input_audio.data.startsWith('data:audio/wav;base64,'))
        bytes=Buffer.from(audio.input_audio.data.split(',')[1],'base64')
      } else {
        assert.equal(req.url,'/v1/audio/transcriptions','live provider address must replace the stale route')
        const form=await new Request(base+req.url,{method:'POST',headers:{'content-type':req.headers['content-type']},body}).formData()
        model=form.get('model')
        const file=form.get('file');assert.equal(file.name,'audio.wav');assert.equal(file.type,'audio/wav')
        bytes=Buffer.from(await file.arrayBuffer())
      }
      const work=model==='fixture-asr-a'?workA:workB
      assert(['fixture-asr-a','qwen3-asr-flash'].includes(model),'exact selected ASR model')
      assert.equal(bytes.toString('ascii',0,4),'RIFF')
      const hash=sha(bytes),chunk=read(work,'manifest.json').chunks.find(row=>row.sha256===hash)
      assert(chunk,'uploaded immutable audio bytes must match the real prepared manifest')
      assert(!requests.some(row=>row.model===model&&row.chunk===chunk.id),'successful audio must never be uploaded twice')
      requests.push({model,chunk:chunk.id,audio_sha256:hash,bytes:bytes.length,authorizationMatched:true})
      res.writeHead(200,{'content-type':'application/json','x-siliconcloud-trace-id':'owned-asr-'+requests.length})
      const text='Fixture transcript '+model+' '+chunk.id
      res.end(JSON.stringify(model==='qwen3-asr-flash'?{choices:[{finish_reason:'stop',message:{role:'assistant',content:text}}]}:{text}))
    } catch(error) {fail(error);res.writeHead(500,{'content-type':'application/json'});res.end('{"error":"fixture assertion failed"}')}
  })
  const ready=new Promise((resolve,reject)=>{server.once('error',reject);server.listen(Number(new URL(base).port),'127.0.0.1',resolve)})
  const text=value=>[{type:'block-start',index:0,blockType:'text'},
    {type:'block-end',index:0,block:{type:'text',text:value}},{type:'finish',reason:{kind:'stop'}}]
  ctx.on('agent/created',({agent})=>agent.ctx.tools.presentAs('both'))
  async function select(model) {
    const settings=ctx.settings.describe().find(row=>row.ns==='houdini-frontend')
    assert(settings,'root frontend settings descriptor must exist')
    await ctx.settings.mutate(settings.ns,[{op:'set',path:['videoProvider'],value:provider},
      {op:'set',path:['videoModel'],value:model},{op:'set',path:['videoPython'],value:''}],settings.revision)
    assert.equal(ctx.houdiniFrontend.videoSelection().model,model)
  }
  function validate(value,model,submitted,remaining) {
    assert.equal(value.ok,true);assert.equal(value.status,'processed');assert.equal(value.provider,provider);assert.equal(value.model,model)
    assert.equal(value.summary.submitted,submitted);assert.equal(value.summary.remaining,remaining)
    const work=model==='fixture-asr-a'?workA:workB
    assert.equal(value.protocol,model==='qwen3-asr-flash'?'qwen-chat-asr':'openai-transcriptions')
    assert.equal(read(work,'asr-config.json').protocol,model==='qwen3-asr-flash'?'qwen-chat-asr':undefined)
    assert.equal(read(work,'asr-config.json').model,model)
    assert.equal(read(work,'asr-config.json').manifest_sha256,sha(fs.readFileSync(path.join(work,'manifest.json'))))
    for(const row of requests.filter(row=>row.model===model)) {
      const outcome=read(work,`outcome-${row.chunk}-1.json`)
      assert.equal(outcome.status,'success');assert.equal(outcome.audio_sha256,row.audio_sha256)
      assert.equal(outcome.text,'Fixture transcript '+model+' '+row.chunk)
    }
  }
  class Driver extends LlmAdapter {
    async listModels(){return[{provider:driver,id:'scripted',name:'ASR integration fixture',inputModalities:['text']}]}
    async resolveModel(provider,id){return{provider,id,name:'ASR integration fixture',inputModalities:['text'],context:{contextWindow:500000}}}
    async *stream(options) {
      if(options.purpose){yield* text('ASR fixture');return}
      try {
        assert(!failure,failure);const step=steps++;assert(step<8,'scripted fixture must converge')
        const events=ctx.sessions.get(options.sessionId).snapshotEvents()
        assert(!JSON.stringify(options.messages).includes(secret),'credentials must not reach the model')
        const native=id=>events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId===id)?.data?.meta?.canonical
        if(step===1) {
          const info=native('video-0');assert.equal(info.selected.provider,provider)
          assert.equal(info.selected.model,restart?'qwen3-asr-flash':'fixture-asr-a')
          assert.equal(info.runtime.python,process.env.DSH_VIDEO_FIXTURE_PYTHON)
          assert.equal(info.runtime.pythonScope,'selected-executor')
          assert(info.runtime.ffmpeg.endsWith(path.join('runtime','video','ffmpeg','bin','ffmpeg.exe')))
          assert(info.runtime.script.endsWith(path.join('skills','houdini-video-tutorial','scripts','video_tutorial.py')))
          const discovered=info.routes.find(row=>row.provider===provider)
          assert.equal(discovered.credential.configured,true)
          assert.deepEqual(discovered.models.map(row=>row.id),['fixture-chat-only'])
          assert(!discovered.models.some(row=>row.id.startsWith('fixture-asr-')),
            'the independently selected ASR model must not be registered as a text-input chat model')
          checks.push('preset tool reads the root service selection and real credential presence')
        }
        if(restart&&step===2) {
          validate(native('video-1'),'qwen3-asr-flash',0,0);assert.equal(requests.length,0)
          checks.push('persisted settings and credential load after restart; finished work makes zero requests')
          yield* text('ASR restart fixture complete.');return
        }
        if(!restart) {
          if(step===2) {
            validate(native('video-1'),'fixture-asr-a',1,2);assert.equal(requests.length,1)
            await select('qwen3-asr-flash');checks.push('live settings mutation changes the current agent default model')
          }
          if(step===3) {
            const dispatch=events.find(e=>e.type==='tool/ptc-dispatch'&&e.data?.name==='video_transcribe')
            assert(dispatch&&!dispatch.data.isError,'real run_code must dispatch ASR')
            validate(JSON.parse(dispatch.data.content.find(b=>b.type==='text').text),'qwen3-asr-flash',1,2)
            assert.equal(requests.length,2);checks.push('real Python ASR works through native and nested tool receipts')
          }
          if(step===4) {validate(native('video-3'),'qwen3-asr-flash',1,1);assert.equal(requests.length,3)}
          if(step===5) {validate(native('video-4'),'qwen3-asr-flash',1,0);assert.equal(requests.length,4)}
          if(step===6) {
            validate(native('video-5'),'qwen3-asr-flash',0,0);assert.equal(requests.length,4)
            checks.push('partial and completed resume reuse successful chunk history without re-upload')
            yield* text('ASR integration fixture complete.');return
          }
        }
        const calls=restart?[
          ['video_models',{provider}],['video_transcribe',{work:workB,allow_upload:true,max_chunks:100}],
        ]:[
          ['video_models',{provider}],['video_transcribe',{work:workA,allow_upload:true,max_chunks:1}],
          ['run_code',{code:'const value=await tools.video_transcribe('+JSON.stringify({work:workB,allow_upload:true,max_chunks:1})+'); return value;',description:'Exercise ASR through real PTC'}],
          ['video_transcribe',{work:workB,allow_upload:true,max_chunks:1}],
          ['video_transcribe',{work:workB,allow_upload:true,max_chunks:100}],
          ['video_transcribe',{work:workB,allow_upload:true,max_chunks:100}],
        ]
        const[name,args]=calls[step];assert(options.tools.some(tool=>tool.name===name),'mounted '+name)
        yield{type:'block-start',index:0,blockType:'tool-call'}
        yield{type:'block-end',index:0,block:{type:'tool-call',id:'video-'+step,name,arguments:JSON.stringify(args)}}
        yield{type:'finish',reason:{kind:'tool-calls'}}
      } catch(error){fail(error);throw error}
    }
  }
  ctx.llm.registerAdapter([driver],new Driver())
  ctx.effect(()=>{
    queueMicrotask(async()=>{
      try {
        await ready;await ctx.loader.await()
        if(!restart) {
          let settings=ctx.settings.describe().find(row=>row.ns==='llm-pi-ai')
          await assert.rejects(()=>ctx.settings.mutate(settings.ns,[{op:'set',path:['providers',provider],value:{
            api:'openai-completions',baseURL:base+'/v1/',apiKeyEnv:reference}}],settings.revision),/resolves no models/)
          checks.push('exact DSH rejects a custom provider without a real chat catalog')
          settings=ctx.settings.describe().find(row=>row.ns==='llm-pi-ai')
          await ctx.settings.mutate(settings.ns,[{op:'set',path:['providers',provider],value:{api:'openai-completions',
            // The pinned DSH requires a chat catalog on a custom provider. ASR
            // is a separate purpose and is deliberately absent from that catalog.
            baseURL:base+'/stale/',apiKeyEnv:'DSH_VIDEO_STALE',models:[{id:'fixture-chat-only',input:['text']}]} }],settings.revision)
          settings=ctx.settings.describe().find(row=>row.ns==='llm-pi-ai')
          await ctx.settings.mutate(settings.ns,[{op:'set',path:['providers',provider,'baseURL'],value:base+'/v1/'},
            {op:'set',path:['providers',provider,'apiKeyEnv'],value:reference}],settings.revision)
          secret='fixture-only-'+randomUUID();await ctx.credentials.set(reference,secret)
          await select('fixture-asr-a');checks.push('live provider settings and stored credentials replace stale values')
        } else {
          secret=(await ctx.credentials.resolve(reference)).value
          assert(secret&&ctx.houdiniFrontend.videoSelection().model==='qwen3-asr-flash','root settings must survive Host restart')
        }
        const {sessionId}=await ctx.sessionController.create({cwd:workspace,agentPreset:'houdini'})
        setSandboxMode(ctx.sessions.get(sessionId),'workspace-write')
        await ctx.sessionController.selectModel({sessionId,provider:driver,model:'scripted'})
        await ctx.sessionController.prompt({sessionId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:'Run the owned ASR transport fixture.'}]},AbortSignal.timeout(120000))
        const agent=ctx.agents.get(sessionId);await agent.whenIdle();assert(!failure,failure)
        assert.equal(steps,restart?3:7);assert.equal(requests.length,restart?0:4)
        await ctx.sessions.flush(agent.session)
        const events=agent.session.snapshotEvents();assert(!JSON.stringify(events).includes(secret),'credentials must not enter durable events')
        report({ok:true,sessionId,workspace,checks,requests,steps,phase:restart?'restart':'initial',
          boundary:'Owned HTTP ASR and scripted planning model. Actual Python/media, exact DSH settings/credentials and native/PTC tools. No paid API, Houdini or GUI claim.'})
      }catch(error){fail(error)}
    })
    return()=>server.close()
  })
}
