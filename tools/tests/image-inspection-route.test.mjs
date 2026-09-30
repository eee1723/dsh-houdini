import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {attachImages,imageBlocks,visualCapability} from '../../lib/image-output.js';
import {installSceneContext} from '../../lib/context.js';
import {registerHoudiniTools} from '../../lib/tools.js';
const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-native-images-'));
const value={ok:true,stdout:'',stderr:'',images:[
  'C:/project/dsh-visual-checks/run-a/a.png',
  'C:/project/dsh-visual-checks/run-a/b.png',
]};
let fetched=0,saved=0,sceneCalls=0;const deferred=[];
const exec={agent:{id:'image-session',options:{provider:'old',model:'wrong'},session:{header:{cwd},requestHeader:()=>({config:{provider:'active',model:'native'}})}},callId:'image-call',signal:new AbortController().signal};
const refs=[];
const attachments={imageLimits:{mediaTypes:['image/png'],maxImageBytes:100,maxMessageImageBytes:150},async saveImage({data,name}){saved++;const ref={attachmentId:'image-'+saved,mediaType:'image/png',bytes:data.length,width:1,height:1,name};refs.push(ref);return ref}};
let modalities=['text','image'];
const ctx={on(){},get:n=>n==='attachments'?attachments:n==='llm'?{async resolveModelInfo(p,m){assert.equal(p,'active');assert.equal(m,'native');return {inputModalities:modalities}}}:undefined};
const bridge={async fetchMedia(_p,_signal,cap){fetched++;assert(cap>0);return Buffer.from('image')},async exec(){sceneCalls++;return value},async hipDir(){return cwd},async jobStatus(){return {...value,jobId:'abcdef123456',status:'done'}}};
try{
 const result=await attachImages(value,exec,bridge,ctx);
 assert.equal(result.media,undefined);assert.equal(imageBlocks(result).length,2);assert.deepEqual(fs.readdirSync(cwd),[],'no workspace media copy');
 assert.deepEqual(imageBlocks(result).map(b=>b.attachment),refs);
 assert(result.imageAttachments.every(i=>i.semantic_status==='unverified'),'transport is not semantic verification');
 await attachImages(value,{...exec,parent:{},deferContext:m=>deferred.push(m)},bridge,ctx);
 assert.equal(deferred.length,0,'DSH owns nested image forwarding');
 const defs=new Map();registerHoudiniTools({...ctx,tools:{register:d=>defs.set(d.name,d)}},bridge);
 for(const name of ['houdini_exec','houdini_job_status']){
  const tool=defs.get(name);const args=name==='houdini_exec'?{code:'render'}:{jobId:'abcdef123456'};
  const output=await tool.execute(args,exec);assert.equal(tool.output.render(args,output).filter(b=>b.type==='image').length,2);
 }
 assert.equal(sceneCalls,1);
 modalities=['text'];const before=fetched;
 const refused=await attachImages(value,exec,bridge,ctx);assert.equal(fetched,before);assert.equal(imageBlocks(refused).length,0);assert.match(refused.imageAttachments[0].error,/does not declare image input/);
 const missing=await attachImages(value,exec,bridge,{});assert.match(missing.imageAttachments[0].error,/unavailable/);
 modalities=['image'];const failed=await attachImages(value,exec,{fetchMedia:async()=>{throw Error('transport unavailable')}},ctx);
 assert.equal(failed.ok,true,'image failure must not cause scene replay');assert.equal(imageBlocks(failed).length,0);
 const failedCapture={...value,ok:false,error:'viewport restoration failed',images:[value.images[0]]};
 const callsBeforeFailureAttachment=sceneCalls;
 const attachedFailure=await attachImages(failedCapture,exec,bridge,ctx);
 assert.equal(attachedFailure.ok,false);assert.equal(imageBlocks(attachedFailure).length,1);
 assert.equal(sceneCalls,callsBeforeFailureAttachment,'failed diagnostic attachment must not replay HOM');
 const exr=await attachImages({...value,images:['C:/project/a.exr']},exec,bridge,ctx);assert.match(exr.imageAttachments[0].error,/format unsupported/);
 const abort=new AbortController();const pending=attachImages(value,{...exec,signal:abort.signal},{}, {get:n=>n==='attachments'?attachments:{resolveModelInfo:()=>new Promise(()=>{})}});abort.abort();assert.equal(imageBlocks(await pending).length,0);
 assert.deepEqual(fs.readdirSync(cwd),[]);
}finally{assert.equal(path.dirname(cwd),path.resolve(os.tmpdir()));fs.rmdirSync(cwd)}
console.log('native image attachments: current route, nested context, job output, failures, no media files');

// Preflight runs before any render/HOM and before the first model request.
const hooks={},contexts=[];let lookups=0;
let model='text-only';const input={agent:{options:{provider:'stale',model:'stale'},
  session:{requestHeader:()=>({config:{provider:'current',model}}),snapshotEvents:()=>[],header:{}}},
  signal:new AbortController().signal};
const services={attachments,llm:{async resolveModelInfo(provider,name){lookups++;assert.equal(provider,'current');return {inputModalities:name==='vision'?['text','image']:['text']}}}};
const preflightCtx={get:n=>services[n],tools:{register(){}},systemPrompt:{context:c=>contexts.push(c)},on:(n,f)=>hooks[n]=f};
const beforePreflight=fetched;
assert.equal((await visualCapability(input,preflightCtx)).status,'unsupported');
assert.equal(fetched,beforePreflight);
installSceneContext(preflightCtx,{sceneContext(){throw Error('preflight must not render/query HOM')}});
async function prepare(variables){
 const assembly={contexts:structuredClone(contexts),tools:[{name:'houdini_inspect'}],variables};
 await hooks['system-prompt/assemble'](assembly,{agent:input.agent,scope:{},signal:input.signal},async()=>assembly);
 return {contexts:assembly.contexts};
}
let prepared=await prepare();
assert(prepared.contexts.some(b=>b.text?.includes('"status":"unsupported"')));
const lookedUp=lookups;await prepare();assert.equal(lookups,lookedUp,'unchanged route metadata is cached');
model='vision';prepared=await prepare();
assert(prepared.contexts.some(b=>b.text?.includes('"status":"available"')));
assert.equal(lookups,lookedUp+1,'route changes invalidate preflight cache');
const defs2=new Map();registerHoudiniTools({...preflightCtx,tools:{register:d=>defs2.set(d.name,d)}},{});
assert.equal((await defs2.get('houdini_capabilities').execute({},input)).result.status,'available');

assert.equal(fetched,beforePreflight,'capability route never fetches an image');
const previousAttachments=services.attachments;delete services.attachments;
prepared=await prepare();
assert(prepared.contexts.some(b=>b.text?.includes('"status":"unavailable"')),
  'channel loss invalidates a previously available same-route preflight');
services.attachments=previousAttachments;
model='text-only';
prepared=await prepare({provider:'current',model:'vision'});
assert(prepared.contexts.some(b=>b.text?.includes('"status":"available"')),
  'newly assembled model selection outranks a stale previous request header');
