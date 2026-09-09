import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {attachImages,imageBlocks} from '../../lib/image-output.js';
import {registerHoudiniTools} from '../../lib/tools.js';
const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-native-images-'));
const value={ok:true,stdout:'',stderr:'',images:['C:/project/a.png','C:/project/b.png']};
let fetched=0,saved=0,sceneCalls=0;const deferred=[];
const exec={agent:{options:{provider:'old',model:'wrong'},session:{header:{cwd},requestHeader:()=>({config:{provider:'active',model:'native'}})}},signal:new AbortController().signal};
const refs=[];
const attachments={imageLimits:{mediaTypes:['image/png'],maxImageBytes:100,maxMessageImageBytes:150},async saveImage({data,name}){saved++;const ref={attachmentId:'image-'+saved,mediaType:'image/png',bytes:data.length,width:1,height:1,name};refs.push(ref);return ref}};
let modalities=['text','image'];
const ctx={get:n=>n==='attachments'?attachments:n==='llm'?{async resolveModelInfo(p,m){assert.equal(p,'active');assert.equal(m,'native');return {inputModalities:modalities}}}:undefined};
const bridge={async fetchMedia(_p,_signal,cap){fetched++;assert(cap>0);return Buffer.from('image')},async exec(){sceneCalls++;return value},async hipDir(){return cwd},async jobStatus(){return {...value,jobId:'job',status:'done'}}};
try{
 const result=await attachImages(value,exec,bridge,ctx);
 assert.equal(result.media,undefined);assert.equal(imageBlocks(result).length,2);assert.deepEqual(fs.readdirSync(cwd),[],'no workspace media copy');
 assert.deepEqual(imageBlocks(result).map(b=>b.attachment),refs);
 assert(result.imageAttachments.every(i=>i.semantic_status==='unverified'),'transport is not semantic verification');
 await attachImages(value,{...exec,parent:{},deferContext:m=>deferred.push(m)},bridge,ctx);
 assert.equal(deferred.length,1);assert.equal(deferred[0].content.filter(b=>b.type==='image').length,2);
 const defs=new Map();registerHoudiniTools({...ctx,tools:{register:d=>defs.set(d.name,d)}},bridge);
 for(const name of ['houdini_exec','houdini_job_status']){
  const tool=defs.get(name);const args=name==='houdini_exec'?{code:'render'}:{jobId:'job'};
  const output=await tool.execute(args,exec);assert.equal(tool.output.render(args,output).filter(b=>b.type==='image').length,2);
 }
 assert.equal(sceneCalls,1);
 modalities=['text'];const before=fetched;
 const refused=await attachImages(value,exec,bridge,ctx);assert.equal(fetched,before);assert.equal(imageBlocks(refused).length,0);assert.match(refused.imageAttachments[0].error,/does not declare image input/);
 const missing=await attachImages(value,exec,bridge,{});assert.match(missing.imageAttachments[0].error,/unavailable/);
 modalities=['image'];const failed=await attachImages(value,exec,{fetchMedia:async()=>{throw Error('transport unavailable')}},ctx);
 assert.equal(failed.ok,true,'image failure must not cause scene replay');assert.equal(imageBlocks(failed).length,0);
 const exr=await attachImages({...value,images:['C:/project/a.exr']},exec,bridge,ctx);assert.match(exr.imageAttachments[0].error,/format unsupported/);
 const abort=new AbortController();const pending=attachImages(value,{...exec,signal:abort.signal},{}, {get:n=>n==='attachments'?attachments:{resolveModelInfo:()=>new Promise(()=>{})}});abort.abort();assert.equal(imageBlocks(await pending).length,0);
 assert.deepEqual(fs.readdirSync(cwd),[]);
}finally{assert.equal(path.dirname(cwd),path.resolve(os.tmpdir()));fs.rmdirSync(cwd)}
console.log('native image attachments: current route, nested context, job output, failures, no media files');
