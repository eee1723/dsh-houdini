import {fixtureProjectionContext,fixtureSession} from './fixture-session.mjs'
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {attachImages,imageBlocks,visualCapability} from '../../lib/image-output.js';
import {registerHoudiniTools} from '../../lib/tools.js';
const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-native-images-'));
const value={ok:true,stdout:'',stderr:'',images:[
  'C:/project/dsh-artifacts/checks/run-a/a.png',
  'C:/project/dsh-artifacts/checks/run-a/b.png',
]};
let fetched=0,saved=0,sceneCalls=0;const deferred=[];
const requestRef='a'.repeat(32)+'.'+'b'.repeat(32)
const imageSession=Object.assign(fixtureSession('image-session',{cwd}),{requestHeader:()=>({config:{provider:'active',model:'native'}})})
const exec={agent:{id:'image-session',model:{current:()=>({provider:'active',model:'native'})},options:{provider:'old',model:'wrong'},session:imageSession},callId:'image-call',signal:new AbortController().signal};
const refs=[];
const attachments={imageLimits:{mediaTypes:['image/png'],maxImageBytes:100,maxMessageImageBytes:150},async saveImage({data,name}){saved++;const ref={attachmentId:'image-'+saved,mediaType:'image/png',bytes:data.length,width:1,height:1,name};refs.push(ref);return ref}};
let modalities=['text','image'];
const ctx=await fixtureProjectionContext({on(){},get:n=>n==='attachments'?attachments:n==='llm'?{async resolveModelInfo(p,m){assert.equal(p,'active');assert.equal(m,'native');return {inputModalities:modalities}}}:undefined});
const pendingRoute=await visualCapability({...exec,agent:{...exec.agent,
  model:{current:()=>({provider:'next-step',model:'pending'})}}},ctx);
assert.equal(pendingRoute.status,'available','an in-flight tool uses its recorded request, not a later pending model selection');
const bridge={forRuntime(runtimeId){assert.equal(runtimeId,'a'.repeat(32));return this},async fetchMedia(_p,_signal,cap){fetched++;assert(cap>0);return Buffer.from('image')},async exec(){sceneCalls++;return value},async hipDir(){return cwd},
 async requestStatus(){return {ok:true,stdout:'',stderr:'',requestReceipt:{request_ref:requestRef,runtime_id:'a'.repeat(32),status:'job_submitted',jobId:'abcdef123456'}}},
 async jobStatus(){return {...value,jobId:'abcdef123456',status:'done'}}};
try{
 const result=await attachImages(value,exec,bridge,ctx);
 assert.equal(result.media,undefined);assert.equal(imageBlocks(result).length,2);assert.deepEqual(fs.readdirSync(cwd),[],'no workspace media copy');
 assert.deepEqual(imageBlocks(result).map(b=>b.attachment),refs);
 assert(result.imageAttachments.every(i=>i.semantic_status==='unverified'),'transport is not semantic verification');
 assert(result.imageAttachments.every(i=>i.image?.width===1&&i.image?.height===1&&/re-encode/.test(i.image.preview_policy)&&/1:1/.test(i.image.scope)),
   'attachment facts name stored dimensions and warn that the request preview may be rescaled');
 await attachImages(value,{...exec,parent:{},deferContext:m=>deferred.push(m)},bridge,ctx);
 assert.equal(deferred.length,0,'DSH owns nested image forwarding');
 const defs=new Map();registerHoudiniTools({...ctx,tools:{register:d=>defs.set(d.name,d)}},bridge);
 for(const name of ['houdini_exec','houdini_request']){
  const tool=defs.get(name);const args=name==='houdini_exec'?{code:'render'}:{request_ref:requestRef};
  const output=await tool.execute(args,exec);assert.equal(tool.output.render(args,output).filter(b=>b.type==='image').length,2);
 }
 assert.equal(sceneCalls,1);
 modalities=['text'];const before=fetched;
 const request=defs.get('houdini_request');
 const requestArgs={request_ref:requestRef};
 const blocked=await request.execute(requestArgs,exec);
 assert.equal(blocked.ok,true);assert.equal(fetched,before);assert.equal(imageBlocks(blocked).length,0);
 assert.match(blocked.imageAttachments[0].error,/does not declare image input/);
 const unsupported=await visualCapability(exec,ctx);
 assert.equal(unsupported.status,'unsupported');
 assert.match(unsupported.next_action,/DSH model settings/);
 assert.match(unsupported.next_action,/read existing images with houdini_request/);
 const capability=defs.get('houdini_capabilities');
 assert.equal((await capability.execute({},exec)).result.status,'unsupported');
 modalities=['text','image'];
 assert.equal((await capability.execute({},exec)).result.status,'available',
   'the on-demand capability tool observes same-route settings without cache invalidation');
 assert.equal(fetched,before,'the on-demand capability tool never fetches or renders an image');
 const recovered=await request.execute(requestArgs,exec);
 assert.equal(fetched,before+2);assert.equal(imageBlocks(recovered).length,2);
 assert.equal(sceneCalls,1,'changing the route and retrieving the original receipt never replays the scene operation');
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
