// Real DSH composition and tool transport; only the remote image provider is an
// owned loopback HTTP fixture. No model API, Houdini process or user data.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import {createHash, randomUUID} from 'node:crypto'
import {deflateSync} from 'node:zlib'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {setSandboxMode} from '@deepseek-ai/dsh-sandbox-policy'
import {EXPECTED_EXECUTION_CONTRACT_VERSION, EXPECTED_VERB_CATALOG_HASH, EXPECTED_VERB_NAMES}
  from '../../lib/generated-verb-contract.js'

export const inject = ['loader', 'llm', 'settings', 'credentials', 'attachments', 'sessions', 'agents', 'sessionController', 'sandboxPolicy']
const route = 'fixture-images', model = 'fixture-image-exact', driver = 'image-fixture-driver'
const sha = bytes => createHash('sha256').update(bytes).digest('hex')
// Small complete PNGs with different pixel content make byte-identity checks
// meaningful. The native attachment decoder also verifies their actual raster.
function png(color) {
  const crc = bytes => { let value = 0xffffffff; for (const byte of bytes) {
    value ^= byte; for (let i=0;i<8;i++) value = value & 1 ? (value>>>1)^0xedb88320 : value>>>1
  } return (value^0xffffffff)>>>0 }
  const chunk = (type,data) => {
    const body=Buffer.concat([Buffer.from(type),data]), size=Buffer.alloc(4), check=Buffer.alloc(4)
    size.writeUInt32BE(data.length); check.writeUInt32BE(crc(body)); return Buffer.concat([size,body,check])
  }
  const header=Buffer.alloc(13); header.writeUInt32BE(16,0);header.writeUInt32BE(16,4);header[8]=8;header[9]=6
  const raw=Buffer.alloc(16*(16*4+1))
  for(let y=0;y<16;y++)for(let x=0;x<16;x++)Buffer.from([...color,255]).copy(raw,y*65+1+x*4)
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',deflateSync(raw)),chunk('IEND',Buffer.alloc(0))])
}
const generated = png([20,130,240]), reference = png([240,120,20])
const layout=JSON.parse(fs.readFileSync(new URL('../../houdini/project-layout.json',import.meta.url),'utf8'))
const portable=value=>value.replaceAll('\\','/')
const canonical=value=>portable(path.resolve(value)).toLowerCase()

export function apply(ctx) {
  const output=process.env.DSH_IMAGE_FIXTURE_OUT, workspace=process.env.DSH_IMAGE_FIXTURE_WORKSPACE
  const base=process.env.DSH_HOUDINI_BRIDGE_URL, secret='fixture-only-'+randomUUID()
  const projects={B:process.env.DSH_IMAGE_FIXTURE_PROJECT_B,C:process.env.DSH_IMAGE_FIXTURE_PROJECT_C}
  const sourceRelative=layout.directories.reference_downloaded.path+'/source.png'
  const requests=[], checks=[], providerReads=[], artifacts=[], bridgeReads=[]
  let failure, steps=0, hipProject='B', explicitBridgeReads
  const report=value=>{fs.writeFileSync(output+'.tmp',JSON.stringify(value,null,2));fs.renameSync(output+'.tmp',output)}
  const fail=error=>{failure??=String(error.stack||error);report({ok:false,error:failure,requests,checks,steps})}
  const server=http.createServer(async(req,res)=>{
    try {
      if(req.url==='/context') {
        const root=portable(projects[hipProject]),hip=root+'/owned-'+hipProject+'.hip'
        bridgeReads.push({route:req.url,hip,providerRequests:requests.length})
        res.setHeader('content-type','application/json');res.end(JSON.stringify({ok:true,result:{hip_path:hip,hip_is_new:false,
          runtime_id:'a'.repeat(32),observed_at:Date.now()/1000,frame:1,selection:[],
          project_layout:{schema_version:layout.schemaVersion,available:true,hip_path:hip,project_root:root,
            directories:Object.fromEntries(Object.entries(layout.directories).map(([role,value])=>[role,root+'/'+value.path]))}}}));return
      }
      if(req.url==='/health') {bridgeReads.push({route:req.url});res.setHeader('content-type','application/json');res.end(JSON.stringify({ok:true,runtimeId:'a'.repeat(32),
        executorId:process.env.DSH_HOUDINI_EXECUTOR_ID,executionContractVersion:EXPECTED_EXECUTION_CONTRACT_VERSION,
        verbCatalog:{hash:EXPECTED_VERB_CATALOG_HASH,names:EXPECTED_VERB_NAMES,count:EXPECTED_VERB_NAMES.length}}));return}
      assert(['/v1/images/generations','/v1/images/edits'].includes(req.url),'unexpected provider path '+req.url)
      assert.equal(req.method,'POST');assert(req.headers.authorization==='Bearer '+secret,'provider authorization matches fixture credential')
      assert.equal(req.headers['x-fixture-live'],'updated-through-settings')
      const chunks=[];for await(const bytes of req)chunks.push(bytes)
      const body=Buffer.concat(chunks), evidence={path:req.url,method:req.method,authorizationMatched:true}
      if(req.url.endsWith('/edits')) {
        assert.match(req.headers['content-type'],/^multipart\/form-data; boundary=/)
        const form=await new Request(base+req.url,{method:'POST',headers:{'content-type':req.headers['content-type']},body}).formData()
        assert.equal(form.get('model'),model);assert.equal(form.get('n'),'1');assert.equal(form.get('output_format'),'png')
        const images=form.getAll('image[]');assert.equal(images.length,1)
        const uploaded=Buffer.from(await images[0].arrayBuffer())
        assert.equal(sha(uploaded),sha(reference),'reference pixels, not a prompt URL, must reach HTTP provider')
        assert.equal(images[0].type,'image/png');assert.equal(images[0].name,'source.png')
        evidence.referenceSHA256=sha(uploaded);evidence.fields=[...form.keys()]
      } else {
        const payload=JSON.parse(body);assert.equal(payload.model,model);assert.equal(payload.n,1);assert.equal(payload.output_format,'png')
        assert.equal(payload.prompt,'Generate the owned fixture image.');evidence.fields=Object.keys(payload)
      }
      requests.push(evidence)
      // Simulate Save As while an image request is running. The already observed
      // B destination must remain fixed; only the next call may observe C.
      if(req.url.endsWith('/edits')) {hipProject='C';evidence.saveAsDuringRequest='C'}
      if(explicitBridgeReads!==undefined) {
        assert.equal(bridgeReads.length,explicitBridgeReads,'explicit output must not resolve or contact the Bridge')
        evidence.bridgeReadsDuringExplicit=bridgeReads.length-explicitBridgeReads
        explicitBridgeReads=undefined
      }
      res.writeHead(200,{'content-type':'application/json','x-request-id':'fixture-image-'+requests.length})
      res.end(JSON.stringify({data:[{b64_json:generated.toString('base64')}],usage:{images:1}}))
    } catch(error) {fail(error);res.writeHead(500,{'content-type':'application/json'});res.end(JSON.stringify({error:{message:'owned fixture assertion failed'}}))}
  })
  const ready=new Promise((resolve,reject)=>{server.once('error',reject);server.listen(Number(new URL(base).port),'127.0.0.1',resolve)})
  ctx.on('agent/created',({agent})=>{agent.ctx.tools.presentAs('both')})
  const chunks=text=>[{type:'block-start',index:0,blockType:'text'},{type:'block-end',index:0,block:{type:'text',text}},{type:'finish',reason:{kind:'stop'}}]
  async function validateImages(content,label) {
    const image=content.find(block=>block.type==='image'), file=content.find(block=>block.type==='file')
    assert(image,label+' native image block');assert(file,label+' original file block')
    const preview=await ctx.attachments.readImage(image.attachment)
    assert.equal(preview.ref.width,16);assert.equal(preview.ref.height,16)
    const parts=[];for await(const part of ctx.attachments.readFileStream(file.attachment))parts.push(part)
    assert.equal(sha(Buffer.concat(parts)),sha(generated),label+' original attachment readback must be lossless')
    assert.equal(sha(fs.readFileSync(ctx.attachments.fileHostPath(file.attachment))),sha(generated))
    checks.push(label+' native image and original attachment readback')
  }
  function validateArtifact(value,label,project,purpose='reference') {
    assert.equal(value.status,'saved');assert.equal(value.sha256,sha(generated))
    const artifact=value.artifact,role=purpose==='texture'?'texture':'reference_generated'
    assert.equal(artifact.output_policy,'managed');assert.equal(artifact.role,role)
    assert.equal(artifact.purpose,purpose);assert.equal(artifact.lifecycle,layout.directories[role].lifecycle)
    assert.equal(canonical(artifact.project_root),canonical(projects[project]))
    assert.equal(canonical(artifact.hip_path),canonical(path.join(projects[project],'owned-'+project+'.hip')))
    assert.equal(canonical(artifact.managed_root),canonical(path.join(projects[project],layout.directories[role].path)))
    assert.equal(canonical(path.dirname(artifact.actual_path)),canonical(artifact.managed_root))
    assert.equal(canonical(value.output),canonical(artifact.actual_path))
    assert.equal(sha(fs.readFileSync(artifact.actual_path)),sha(generated))
    assert.equal(artifact.observed_identity.executor_id,process.env.DSH_HOUDINI_EXECUTOR_ID)
    assert.equal(artifact.observed_identity.runtime_id,'a'.repeat(32))
    assert.equal(portable(path.relative(projects[project],artifact.actual_path)),artifact.hip_relative_path)
    artifacts.push({label,...artifact});checks.push(label+' uses observed HIP '+project+' and shared directory contract')
    return artifact
  }
  function validateModelReceipt(options,callId,artifact,label) {
    const visible=options.messages.find(m=>m.role==='tool'&&m.toolCallId===callId)
    assert(visible?.content.some(b=>b.type==='image'),label+' image must reach actual adapter request')
    assert(visible.content.some(b=>b.type==='text'&&b.text.startsWith('[File "'+path.basename(artifact.actual_path)+'"')
      &&b.text.includes('verbatim read-only copy saved at')),label+' original must have a readable model-facing handle')
    assert(visible.content.some(b=>b.type==='text'&&b.text.includes(artifact.actual_path)),label+' model sees resolved actual destination')
    providerReads.push({step:steps-1,transport:label,image:true,fileHandle:true,actualPath:artifact.actual_path})
  }
  class Driver extends LlmAdapter {
    async listModels(){return[{provider:driver,id:'scripted',name:'Image integration fixture',inputModalities:['text','image']}]}
    async resolveModel(provider,id){return{provider,id,name:'Image integration fixture',inputModalities:['text','image'],context:{contextWindow:500000}}}
    async *stream(options) {
      if(options.purpose){yield* chunks('Image fixture');return}
      try {
        assert(!failure,failure);const step=steps++;assert(step<=7,'scripted fixture must converge')
        const events=ctx.sessions.get(options.sessionId).snapshotEvents()
        assert(!JSON.stringify(options.messages).includes(secret),'credentials must not appear in model messages')
        if(step===1) {
          const discovery=events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='image-0')?.data?.meta?.canonical
          assert.equal(discovery.routes.length,1);assert.equal(discovery.routes[0].provider,route)
          assert.equal(discovery.routes[0].models[0].id,model);assert.equal(discovery.routes[0].support,'unverified')
          checks.push('actual settings-backed provider discovery')
        }
        if(step===2) {
          const event=events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='image-1')
          assert(event,'denied managed image must return through the native tool transport')
          assert.match(JSON.stringify(event.data),/outside the current DSH writable workspace/)
          assert.equal(requests.length,0,'workspace denial must happen before any provider request')
          assert(!fs.existsSync(path.join(projects.B,'dsh-reference')),'denial must not create managed output directories')
          const session=ctx.sessions.get(options.sessionId)
          assert.equal(ctx.sandboxPolicy.resolve({session}).mode,'workspace-write')
          // This is an explicit test-owner change through DSH's real session
          // policy API, scoped to an owned temporary fixture. Production never
          // widens a user's policy to make managed output succeed.
          setSandboxMode(session,'danger-full-access')
          assert.equal(ctx.sandboxPolicy.resolve({session}).mode,'danger-full-access')
          checks.push('workspace A denies HIP B before billing; owned fixture explicitly changes native session policy')
        }
        if(step===3) {
          const event=events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='image-2')
          const value=event?.data?.meta?.canonical
          const artifact=validateArtifact(value,'native-reference-B','B')
          assert.deepEqual(value.actual_dimensions,{width:16,height:16})
          assert.equal(value.requested.size,'1024x1024')
          assert.equal(value.warnings.length,1,'actual provider size mismatch remains visible')
          await validateImages(event.data.message.content,'native-reference-B')
          validateModelReceipt(options,'image-2',artifact,'native')
        }
        if(step===4) {
          const nested=events.find(e=>e.type==='tool/ptc-dispatch'&&e.data?.name==='image_generate')
          assert(nested&&!nested.data.isError,'real run_code must dispatch image_generate')
          await validateImages(nested.data.content,'ptc')
          const value=JSON.parse(nested.data.content.find(b=>b.type==='text').text)
          const artifact=validateArtifact(value,'ptc-texture-B','B','texture')
          assert.equal(hipProject,'C','fixture must really change the observed HIP during the provider request')
          const forwarded=options.messages.filter(m=>m.content.some(b=>b.type==='text'&&b.text.startsWith('[File "'+path.basename(artifact.actual_path)+'"')))
          assert.equal(forwarded.length,1,'PTC must forward the image result once')
          assert(forwarded[0].content.some(b=>b.type==='image'))
          assert(forwarded[0].content.some(b=>b.type==='text'&&b.text.includes('verbatim read-only copy saved at')))
          assert(options.messages.some(m=>m.content.some(b=>b.type==='text'&&b.text.includes(artifact.actual_path))),
            'PTC model sees actual B path even after Save As to C')
          providerReads.push({step,transport:'ptc',image:true,fileHandle:true,actualPath:artifact.actual_path})
          assert.equal(requests.length,2,'one generation and one edit, without retry')
          assert(!fs.existsSync(path.join(projects.C,'dsh-texture')),'in-flight Save As must not retarget the generated texture')
          checks.push('in-flight Save As preserves B destination')
        }
        if(step===5) {
          const event=events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='image-4')
          const artifact=validateArtifact(event?.data?.meta?.canonical,'native-reference-C','C')
          await validateImages(event.data.message.content,'native-reference-C')
          validateModelReceipt(options,'image-4',artifact,'native')
          explicitBridgeReads=bridgeReads.length
          checks.push('next managed call observes new HIP C')
        }
        if(step===6) {
          const event=events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='image-5')
          const value=event?.data?.meta?.canonical,artifact=value?.artifact
          assert.equal(value.status,'saved');assert.equal(artifact.output_policy,'explicit')
          assert.equal(canonical(artifact.actual_path),canonical(path.join(workspace,'dsh-texture/explicit.png')))
          for(const key of ['project_root','managed_root','hip_path','hip_relative_path','observed_identity'])assert.equal(artifact[key],null)
          assert.equal(sha(fs.readFileSync(artifact.actual_path)),sha(generated))
          await validateImages(event.data.message.content,'explicit')
          validateModelReceipt(options,'image-5',artifact,'native')
          assert.equal(requests.length,4);assert.equal(requests.at(-1).bridgeReadsDuringExplicit,0)
          artifacts.push({label:'explicit-workspace-A',...artifact})
          checks.push('explicit relative output preserves workspace A semantics without Bridge access')
        }
        if(step===7) {
          const delivery=events.filter(e=>e.type==='deliverables/presented')
          assert.equal(delivery.length,1);assert.equal(delivery[0].data.files.length,artifacts.length)
          assert.deepEqual(delivery[0].data.files.map(f=>f.path),artifacts.map(artifact=>artifact.actual_path))
          checks.push('real present tool delivered returned actual paths for every generated file')
          yield* chunks('Owned image fixture completed.');return
        }
        const calls=[
          ['image_models',{provider:route,query:'fixture-image'}],
          ['image_generate',{provider:route,model,prompt:'Generate the owned fixture image.'}],
          ['image_generate',{provider:route,model,prompt:'Generate the owned fixture image.',size:'1024x1024'}],
          ['run_code',{code:'const value = await tools.image_generate('+JSON.stringify({provider:route,model,prompt:'Edit the uploaded fixture pixels.',
            purpose:'texture',output:'edited.png',references:[sourceRelative]})+'); return {ok:value.ok,output:value.output,artifact:value.artifact,sha256:value.sha256};',description:'Exercise real managed texture edit via PTC'}],
          ['image_generate',{provider:route,model,prompt:'Generate the owned fixture image.',output:'next.png'}],
          ['image_generate',{provider:route,model,prompt:'Generate the owned fixture image.',output_policy:'explicit',output:'dsh-texture/explicit.png'}],
          ['present',{files:artifacts.map(artifact=>({path:artifact.actual_path,description:artifact.label}))}],
        ]
        const[name,args]=calls[step];assert(options.tools.some(tool=>tool.name===name),'mounted tool '+name)
        yield{type:'block-start',index:0,blockType:'tool-call'}
        yield{type:'block-end',index:0,block:{type:'tool-call',id:'image-'+step,name,arguments:JSON.stringify(args)}}
        yield{type:'finish',reason:{kind:'tool-calls'}}
      } catch(error){fail(error);throw error}
    }
  }
  ctx.llm.registerAdapter([driver],new Driver())
  ctx.effect(()=>{
    queueMicrotask(async()=>{
      try {
        await ready;await ctx.loader.await()
        fs.mkdirSync(path.dirname(path.join(workspace,sourceRelative)),{recursive:true})
        fs.writeFileSync(path.join(workspace,sourceRelative),reference)
        let initial=ctx.settings.describe().find(item=>item.ns==='llm-pi-ai')
        assert(initial,'real pi-ai settings descriptor exists')
        await ctx.settings.mutate(initial.ns,[{op:'set',path:['providers',route],value:{
          api:'openai-completions',baseURL:base+'/stale/',apiKeyEnv:'DSH_IMAGE_FIXTURE_STALE',
          models:[{id:model,input:['text','image']}],
        }}],initial.revision)
        initial=ctx.settings.describe().find(item=>item.ns==='llm-pi-ai')
        await ctx.settings.mutate(initial.ns,[
          {op:'set',path:['providers',route,'baseURL'],value:base+'/v1/'},
          {op:'set',path:['providers',route,'apiKeyEnv'],value:'DSH_IMAGE_FIXTURE_KEY'},
          {op:'set',path:['providers',route,'headers'],value:{'X-Fixture-Live':'updated-through-settings'}},
        ],initial.revision)
        await ctx.credentials.set('DSH_IMAGE_FIXTURE_KEY',secret)
        const configured=ctx.llm.listConfigurableProviders().find(item=>item.provider===route)
        assert.equal(configured.settingsNs,initial.ns);assert.deepEqual(configured.settingsPath,['providers',route])
        checks.push('real live settings mutation and credential storage')
        const {sessionId}=await ctx.sessionController.create({cwd:workspace,agentPreset:'houdini'})
        setSandboxMode(ctx.sessions.get(sessionId),'workspace-write')
        await ctx.sessionController.selectModel({sessionId,provider:driver,model:'scripted'})
        await ctx.sessionController.prompt({sessionId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:'Run the isolated image tools integration fixture.'}]},AbortSignal.timeout(90000))
        const agent=ctx.agents.get(sessionId);await agent.whenIdle();assert(!failure,failure)
        assert.equal(steps,8);assert.equal(requests.length,4);assert.equal(artifacts.length,4)
        await ctx.sessions.flush(agent.session)
        const events=agent.session.snapshotEvents();assert(!JSON.stringify(events).includes(secret),'credentials must not enter durable events')
        report({ok:true,sessionId,workspace,projects,checks,requests,providerReads,artifacts,bridgeReads,events,referenceSHA256:sha(reference),generatedSHA256:sha(generated),
          boundary:'Loopback provider only. No paid API, live Houdini or visual-semantic quality claim. Frontend GUI was not exercised.'})
      }catch(error){fail(error)}
    })
    return()=>server.close()
  })
}
