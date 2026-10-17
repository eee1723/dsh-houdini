// Exercise the exact prepared DSH Web composition, its mounted read_image,
// durable attachments and real pi-ai HTTP adapter against an owned provider.
// No external API, user credential, live Houdini or model semantics are used.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {spawn} from 'node:child_process';
import {deflateSync} from 'node:zlib';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
export const inject=['loader','llm','settings','credentials','attachments','sessions','agents','sessionController'];

function fixturePng(variant) {
  const width=2560,height=1920,raw=Buffer.alloc(height*(width*4+1));
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const offset=y*(width*4+1)+1+x*4;
    const grid=x%128<6||y%96<6,marker=x>width*.2&&x<width*.4&&y>height*.3&&y<height*.5;
    raw[offset]=grid?240:marker?80+variant*50:30+Math.floor(x/16)%160;
    raw[offset+1]=grid?240:marker?180-variant*40:35+Math.floor(y/16)%150;
    raw[offset+2]=grid?240:marker?40:40+variant*60;raw[offset+3]=255;
  }
  const crc=bytes=>{let value=0xffffffff;for(const byte of bytes){value^=byte;for(let i=0;i<8;i++)value=value&1?(value>>>1)^0xedb88320:value>>>1}return(value^0xffffffff)>>>0};
  const chunk=(type,data)=>{const body=Buffer.concat([Buffer.from(type),data]),size=Buffer.alloc(4),check=Buffer.alloc(4);size.writeUInt32BE(data.length);check.writeUInt32BE(crc(body));return Buffer.concat([size,body,check])};
  const header=Buffer.alloc(13);header.writeUInt32BE(width);header.writeUInt32BE(height,4);header[8]=8;header[9]=6;
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',deflateSync(raw)),chunk('IEND',Buffer.alloc(0))]);
}

export function apply(ctx) {
  const output=process.env.DSH_IMAGE_CONSUMPTION_OUT,workspace=process.env.DSH_IMAGE_CONSUMPTION_WORKSPACE;
  const runtime=process.env.DSH_IMAGE_CONSUMPTION_RUNTIME;
  assert(output&&workspace&&runtime,'explicit isolated fixture paths required');
  const require=createRequire(path.join(runtime,'node_modules/@deepseek-ai/dsh/lib/bin.js'));
  const sharp=require('sharp');
  const route='image-consumption-fixture',model='owned-image-model',secret='owned-fixture-'+randomUUID();
  const files=['reference.png','A.png','B.png'].map(name=>path.join(workspace,name));
  const originals=files.map(file=>({path:file,sha256:sha(fs.readFileSync(file))}));
  const requests=[],transforms=[],checks=[],network=[];let phase='baseline',failure,first=true,currentSession,ownedOrigin;
  const report=value=>{fs.writeFileSync(output+'.tmp',JSON.stringify(value,null,2));fs.renameSync(output+'.tmp',output)};
  const fail=error=>{failure??=String(error.stack??error);if(currentSession)fs.writeFileSync(output+'.events.json',JSON.stringify(currentSession.snapshotEvents(),null,2));report({ok:false,error:failure,requests,transforms,checks,network})};
  const nativeFetch=globalThis.fetch;
  globalThis.fetch=async(...args)=>{const request={url:String(args[0]?.url??args[0])};network.push(request);try{assert.equal(new URL(request.url).origin,ownedOrigin,'fixture fetch must stay on the owned loopback provider');return await nativeFetch(...args)}catch(error){request.error=String(error);request.cause=String(error.cause);throw error}};
  const originalRead=ctx.attachments.readImageRequest.bind(ctx.attachments);
  ctx.attachments.readImageRequest=async(ref,target,signal)=>{
    const value=await originalRead(ref,target,signal);
    transforms.push({phase,attachmentId:ref.attachmentId,name:ref.name,stored:{width:ref.width,height:ref.height,bytes:ref.bytes},target,
      request:{width:value.width,height:value.height,bytes:value.bytes,sha256:sha(value.data),variantId:value.variantId,mediaType:value.mediaType}});
    return value;
  };
  function respond(res,delta,finish) {
    res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-cache'});
    const send=(delta,finish_reason=null)=>res.write('data: '+JSON.stringify({id:'chatcmpl-owned',object:'chat.completion.chunk',created:1,model,
      choices:[{index:0,delta,finish_reason}]})+'\n\n');
    send({role:'assistant',...delta});send({},finish);res.end('data: [DONE]\n\n');
  }
  const server=http.createServer(async(req,res)=>{
    try{
      assert.equal(req.url,'/v1/chat/completions');assert.equal(req.headers.authorization,'Bearer '+secret);
      const chunks=[];for await(const bytes of req)chunks.push(bytes);const body=Buffer.concat(chunks),payload=JSON.parse(body);
      const images=[],handles=[];
      for(const message of payload.messages??[])for(const block of Array.isArray(message.content)?message.content:typeof message.content==='string'?[{type:'text',text:message.content}]:[]){
        if(block.type==='image_url'){
          const match=/^data:([^;]+);base64,(.*)$/.exec(block.image_url.url);assert(match,'loopback provider must receive inline image bytes');
          const data=Buffer.from(match[2],'base64'),metadata=await sharp(data).metadata();
          images.push({mediaType:match[1],bytes:data.length,sha256:sha(data),width:metadata.width,height:metadata.height,detail:block.image_url.detail??null});
        }else if(block.type==='text'&&block.text.includes('request preview'))handles.push(block.text);
      }
      assert.equal(payload.reasoning_effort,'high','selected high reasoning must reach the real adapter HTTP payload');
      requests.push({phase,path:req.url,payloadBytes:body.length,imageCount:images.length,images,handles,model:payload.model,reasoningEffort:payload.reasoning_effort});
      if(first){
        first=false;assert(payload.tools.some(row=>row.function?.name==='read_image'),'real mounted read_image declaration must reach pi-ai');
        respond(res,{tool_calls:files.map((file,index)=>({index,id:'owned-read-'+index,type:'function',function:{name:'read_image',arguments:JSON.stringify({file_path:file})}}))},'tool_calls');
      }else respond(res,{content:'Owned provider fixture complete. Image semantics remain unverified.'},'stop');
    }catch(error){fail(error);if(!res.headersSent)res.writeHead(500,{'content-type':'application/json'});res.end(JSON.stringify({error:{message:'Owned fixture assertion failed'}}))}
  });
  const ready=new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve)});
  ctx.on('agent/created',({agent})=>agent.ctx.tools.presentAs('native'));
  ctx.effect(()=>{
    queueMicrotask(async()=>{
      try{
        await ready;await ctx.loader.await();
        ownedOrigin='http://127.0.0.1:'+server.address().port;const baseURL=ownedOrigin+'/v1';
        let setting=ctx.settings.describe().find(row=>row.ns==='llm-pi-ai');assert(setting,'real pi-ai settings section is mounted');
        await ctx.settings.mutate(setting.ns,[{op:'set',path:['providers',route],value:{api:'openai-completions',baseURL,
          apiKeyEnv:'OWNED_IMAGE_FIXTURE_KEY',reasoning:'high',timeoutMs:10000,retryPolicy:{mode:'normal',maxRetries:0},models:[{id:model,input:['text','image'],reasoningEfforts:{high:'high'},contextWindow:500000,maxTokens:1024}]}}],setting.revision);
        await ctx.credentials.set('OWNED_IMAGE_FIXTURE_KEY',secret);
        const {sessionId}=await ctx.sessionController.create({cwd:workspace,agentPreset:'standard'});
        currentSession=ctx.sessions.get(sessionId);
        await ctx.sessionController.selectModel({sessionId,provider:route,model});
        const prompt=async text=>{await ctx.sessionController.prompt({sessionId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text}]},AbortSignal.timeout(60000));await ctx.agents.get(sessionId).whenIdle();assert(!failure,failure);
          const terminal=ctx.sessions.get(sessionId).snapshotEvents().findLast(event=>event.type==='turn/end');
          assert(terminal?.data?.reason?.kind!=='error',JSON.stringify(terminal));};
        await prompt('Read the three owned fixture images with the declared read_image tool.');
        const session=ctx.sessions.get(sessionId),readResults=session.snapshotEvents().filter(event=>event.type==='tool/result');
        assert.equal(readResults.length,3);assert(readResults.every(event=>!event.data.message.isError),'real filesystem/image tools succeeded');
        const refs=readResults.map(event=>event.data.message.content.find(block=>block.type==='image')?.attachment);assert(refs.every(Boolean));
        const storedBefore=await Promise.all(refs.map(async ref=>({attachmentId:ref.attachmentId,name:ref.name,sha256:sha((await ctx.attachments.readImage(ref)).data)})));
        for(const [name,budget]of [['one-megapixel',1048576],['restored',4194304]]){
          phase=name;setting=ctx.settings.describe().find(row=>row.ns==='llm-pi-ai');
          await ctx.settings.mutate(setting.ns,[{op:'set',path:['providers',route,'requestImagePixelBudget'],value:budget}],setting.revision);
          await prompt('Continue without tools; keep the original reference and both A/B observations available.');
        }
        const withImages=requests.filter(row=>row.imageCount);assert.equal(withImages.length,3);assert(withImages.every(row=>row.imageCount===3),'policy must preserve reference and both A/B image occurrences');
        const [baseline,small,restored]=withImages;
        for(const request of withImages){
          // Native image preparation is concurrent. Match each wire handle by
          // durable identity, not by the order asynchronous transforms finished.
          const prepared=request.handles.map(handle=>{
            const matching=transforms.filter(row=>row.phase===request.phase&&handle.includes('('+row.attachmentId+')'));
            assert.equal(matching.length,1,'each wire image must identify one prepared durable source');
            return matching[0];
          });
          assert.equal(request.handles.length,3,'provider must receive handles for every retained image');
          assert.deepEqual(request.images.map(row=>row.sha256),prepared.map(row=>row.request.sha256),'actual HTTP image bytes must be the native request-image versions');
          assert.deepEqual(prepared.map(row=>row.attachmentId),refs.map(row=>row.attachmentId),'reference/A/B durable identities must stay stable');
          request.handles.forEach((text,index)=>assert(text.includes(`request preview ${request.images[index].width}x${request.images[index].height}px`),'model handle must describe the actual transmitted image size'));
        }
        assert(baseline.images.every(row=>row.width*row.height<=4194304));assert(small.images.every(row=>row.width*row.height<=1048576));
        assert(small.images.every((row,index)=>row.width<baseline.images[index].width&&row.height<baseline.images[index].height));
        assert.deepEqual(restored.images,baseline.images,'restoring route policy must recover the exact original request versions');
        // Pixel budgeting is distinct from encoded bytes. For a compressible
        // WebP source, resizing can select JPEG and increase the wire payload.
        // Report the measured sizes rather than assuming either must decrease.
        const storedAfter=await Promise.all(refs.map(async ref=>({attachmentId:ref.attachmentId,name:ref.name,sha256:sha((await ctx.attachments.readImage(ref)).data)})));
        assert.deepEqual(storedAfter,storedBefore);assert.deepEqual(files.map(file=>({path:file,sha256:sha(fs.readFileSync(file))})),originals);
        const events=session.snapshotEvents();assert(!events.some(event=>event.type==='image/offload'||event.type.startsWith('compaction/')));
        assert(!JSON.stringify(events).includes(secret),'fixture credentials must not enter durable events');
        await ctx.sessions.flush(session);
        checks.push('real mounted read_image; pi-ai HTTP capture; live native profile mutation; all reference/A/B images retained; exact restored request bytes; unchanged files and durable attachments; no offload or compaction');
        report({ok:true,dshVersion:'0.2.1-rc.2',nodeVersion:process.version,runtimeFixRevision:JSON.parse(fs.readFileSync(path.join(runtime,'.dsh-runtime-fixes.json'),'utf8')).revision,sessionId,preset:'standard',workspace,checks,requests,transforms,network,originals,stored:storedAfter,
          boundary:'Exact prepared DSH Web composition and real pi-ai adapter; loopback provider only. No paid model, user secrets, Houdini scene or GUI. Request size/bytes and retention were measured; semantic image quality, model token usage and fees were not measured.'});
      }catch(error){fail(error)}
    });
    return()=>{globalThis.fetch=nativeFetch;ctx.attachments.readImageRequest=originalRead;server.closeAllConnections();server.close()};
  });
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const [runtimeArg,outputArg]=process.argv.slice(2);assert(runtimeArg,'usage: node tools/tests/dsh-image-consumption-fixture.mjs <prepared-runtime> [output-root]');
  const runtime=path.resolve(runtimeArg),outputRoot=path.resolve(outputArg??path.join(root,'tools/out/system-feedback-cost'));
  const version=JSON.parse(fs.readFileSync(path.join(runtime,'node_modules/@deepseek-ai/dsh/package.json'),'utf8')).version;assert.equal(version,'0.2.1-rc.2');
  const marker=JSON.parse(fs.readFileSync(path.join(runtime,'.dsh-runtime-fixes.json'),'utf8'));assert.equal(marker.dshVersion,version);
  fs.mkdirSync(outputRoot,{recursive:true});const run=fs.mkdtempSync(path.join(outputRoot,'image-consumption-'));
  const workspace=path.join(run,'workspace'),home=path.join(run,'home'),temp=path.join(run,'temp'),output=path.join(run,'report.json');fs.mkdirSync(workspace);fs.mkdirSync(home);fs.mkdirSync(temp);
  for(const [index,name]of ['reference.png','A.png','B.png'].entries())fs.writeFileSync(path.join(workspace,name),fixturePng(index));
  const patch=path.join(run,'fixture.patch.yml');fs.writeFileSync(patch,'- id: session-title-llm\n  disabled: true\n- id: spill-local\n  config:\n    root: '+JSON.stringify(path.join(run,'spill').replaceAll('\\','/'))+'\n    cleanupPeriodDays: 0\n- insert:\n    - id: image-consumption-fixture\n      name: '+JSON.stringify(fileURLToPath(import.meta.url).replaceAll('\\','/'))+'\n');
  const env=Object.fromEntries(['PATH','Path','SystemRoot','WINDIR','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA','COMSPEC','PATHEXT'].filter(name=>process.env[name]!==undefined).map(name=>[name,process.env[name]]));
  Object.assign(env,{TEMP:temp,TMP:temp,DSH_HOME:home,DSH_IMAGE_CONSUMPTION_OUT:output,DSH_IMAGE_CONSUMPTION_WORKSPACE:workspace,DSH_IMAGE_CONSUMPTION_RUNTIME:runtime});
  const cli=path.join(runtime,'node_modules/@deepseek-ai/dsh/lib/bin.js'),log=fs.openSync(path.join(run,'host.log'),'w');
  const child=spawn(process.execPath,[cli,'web','--patch',patch,'--host','127.0.0.1','--port','0','--no-open'],{cwd:workspace,env,stdio:['ignore',log,log],windowsHide:true});
  let exited;child.on('exit',code=>{exited=code});const deadline=Date.now()+90000;
  try{while(!fs.existsSync(output)&&exited===undefined&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,100));
    assert(fs.existsSync(output),'DSH fixture did not produce a report; inspect '+path.join(run,'host.log'));
    const result=JSON.parse(fs.readFileSync(output,'utf8'));assert(result.ok,result.error);console.log(JSON.stringify({ok:true,report:output,requests:result.requests.map(({phase,imageCount,payloadBytes,images})=>({phase,imageCount,payloadBytes,images}))},null,2));
  }finally{if(exited===undefined)child.kill('SIGTERM');fs.closeSync(log)}
}
