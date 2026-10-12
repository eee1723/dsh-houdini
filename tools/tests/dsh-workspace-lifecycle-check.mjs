import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const cache=path.resolve(process.argv[2]);
const require=createRequire(path.join(cache,'node_modules/@deepseek-ai/dsh/lib/bin.js'));
const {AclSandbox,AclWriteGrant,workspaceWriteSid}=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-sandbox-windows-acl')));
const root=fs.mkdtempSync('E:/tmp/dsh-workspace-lifecycle-');
const work=path.join(root,'work'),outside=path.join(root,'outside'),deep=path.join(work,'pre/deep');
fs.mkdirSync(deep,{recursive:true});fs.mkdirSync(outside);
const original=path.join(outside,'keep.txt');fs.writeFileSync(original,'keep');
fs.writeFileSync(path.join(deep,'old.txt'),'old');fs.linkSync(original,path.join(work,'hard.txt'));fs.symlinkSync(outside,path.join(work,'junction'),'junction');
const acl=p=>{const r=spawnSync('icacls.exe',[p],{encoding:'utf8'});assert.equal(r.status,0,r.stderr);return r.stdout};
const protectedDir=path.join(work,'protected');fs.mkdirSync(protectedDir);fs.writeFileSync(path.join(protectedDir,'keep.txt'),'protected');
assert.equal(spawnSync('icacls.exe',[protectedDir,'/inheritance:r','/grant',`${process.env.USERNAME}:(OI)(CI)(F)`],{encoding:'utf8'}).status,0);
const protectedBefore=acl(protectedDir);
const outsideBefore=acl(original),dirBefore=acl(outside);
const box=new AclSandbox({writableDirs:[work],tempDir:null,writeSid:workspaceWriteSid(fs.realpathSync.native(work)),mode:'workspace-write'});
try {
 const started=performance.now();await box.init();const provisionMs=performance.now()-started;
 assert.equal(acl(original),outsideBefore,'hard-linked outside security must not change');assert.equal(acl(outside),dirBefore);
 const code=`const fs=require('fs');const results={};
 for(const [name,fn] of Object.entries({
   lifecycle:()=>{fs.writeFileSync('pre/deep/old.txt','updated');fs.renameSync('pre/deep/old.txt','pre/deep/renamed.txt');fs.unlinkSync('pre/deep/renamed.txt');fs.writeFileSync('pre/deep/new.txt','ok')},
   hardlink:()=>fs.writeFileSync('hard.txt','BAD'),junction:()=>fs.writeFileSync('junction/keep.txt','BAD'),
   protected:()=>fs.writeFileSync('protected/keep.txt','BAD')
 }))try{fn();results[name]='OK'}catch(e){results[name]=e.code}console.log(JSON.stringify(results));`;
 const r=await box.spawn({command:process.execPath,args:['-e',code],cwd:work}).wait();assert.equal(r.exitCode,0,r.stderr.toString());
 const results=JSON.parse(r.stdout.toString());assert.equal(results.lifecycle,'OK');assert.notEqual(results.hardlink,'OK');assert.notEqual(results.junction,'OK');
 assert.notEqual(results.protected,'OK');assert.equal(acl(protectedDir),protectedBefore);
 assert.equal(fs.readFileSync(original,'utf8'),'keep');assert.equal(acl(original),outsideBefore);assert.equal(acl(outside),dirBefore);
 console.log(JSON.stringify({root,provisionMs,results}));
}finally{box.dispose()}
const revocable=path.join(root,'revocable');fs.mkdirSync(path.join(revocable,'deep'),{recursive:true});fs.writeFileSync(path.join(revocable,'deep/a.txt'),'a');
const sid='S-1-4-98211-441';const g=AclWriteGrant.create(sid);g.add(revocable);g.dispose();
for(const p of [revocable,path.join(revocable,'deep'),path.join(revocable,'deep/a.txt')]){assert(!acl(p).includes(sid),'revocation must remove descendant grants: '+p);assert(!acl(p).includes('Low Mandatory Level'));}
const denied=path.join(root,'denied');fs.mkdirSync(denied);const deniedSid='S-1-15-2-337311-22111';
assert.equal(spawnSync('icacls.exe',[denied,'/deny',`*${deniedSid}:(W)`],{encoding:'utf8'}).status,0);
const deniedBefore=acl(denied),deniedGrant=AclWriteGrant.create(deniedSid);
try{assert.throws(()=>deniedGrant.add(denied,true),/explicitly denied/)}finally{deniedGrant.dispose()}
assert.equal(acl(denied),deniedBefore);
const readonly=new AclSandbox({writableDirs:[],tempDir:null,mode:'read-only'});
try{await readonly.init();const r=await readonly.spawn({command:process.execPath,args:['-e',"require('fs').writeFileSync('pre/deep/new.txt','BAD')"],cwd:work}).wait();assert.notEqual(r.exitCode,0)}finally{readonly.dispose()}
assert.equal(fs.readFileSync(path.join(deep,'new.txt'),'utf8'),'ok');
const repeated=AclWriteGrant.create(workspaceWriteSid(fs.realpathSync.native(work)));const beforeRepeat=acl(deep);repeated.add(work,true);repeated.dispose();assert.equal(acl(deep),beforeRepeat);
const moved=path.join(root,'replace'),held=path.join(root,'held');fs.mkdirSync(moved);const replaced=AclWriteGrant.create('S-1-4-821321-33');replaced.add(moved);fs.renameSync(moved,held);fs.symlinkSync(outside,moved,'junction');
assert.throws(()=>replaced.dispose(),e=>e instanceof AggregateError&&e.errors.some(cause=>/reparse point/.test(cause.message)));assert.equal(acl(outside),dirBefore);assert.equal(acl(original),outsideBefore);
const many=path.join(root,'many');fs.mkdirSync(many);for(let i=0;i<200;i++)fs.writeFileSync(path.join(many,`${i}.txt`),'x');
const manyGrant=AclWriteGrant.create('S-1-4-734101-91');const start=performance.now();manyGrant.add(many);const elapsed=performance.now()-start;manyGrant.dispose();console.log('200 existing files provision ms:',elapsed);
console.log('PASS existing workspace lifecycle, outside link isolation and descendant revocation');
// Optional installed baseline reproduces the exact upgrade path without touching a user workspace.
if(process.argv[3]){
 const legacy=path.resolve(process.argv[3]),oldRequire=createRequire(path.join(legacy,'node_modules/@deepseek-ai/dsh/lib/bin.js'));
 const upgrade=path.join(root,'upgrade');fs.mkdirSync(path.join(upgrade,'existing'),{recursive:true});fs.writeFileSync(path.join(upgrade,'existing/old.txt'),'old');
 const script=`const {AclSandbox,workspaceWriteSid}=await import(${JSON.stringify(pathToFileURL(oldRequire.resolve('@deepseek-ai/dsh-sandbox-windows-acl')).href)});const fs=await import('node:fs');const box=new AclSandbox({writableDirs:[${JSON.stringify(upgrade)}],tempDir:null,writeSid:workspaceWriteSid(fs.realpathSync.native(${JSON.stringify(upgrade)})),mode:'workspace-write'});try{await box.init();const r=await box.spawn({command:process.execPath,args:['-e',"require('fs').renameSync('existing/old.txt','existing/renamed.txt')"],cwd:${JSON.stringify(upgrade)}}).wait();console.log(JSON.stringify({exitCode:r.exitCode,stderr:r.stderr.toString()}))}finally{box.dispose()}`;
 const old=spawnSync(process.execPath,['--input-type=module','-e',script],{encoding:'utf8'});assert.equal(old.status,0,old.stderr);const before=JSON.parse(old.stdout);assert.notEqual(before.exitCode,0);assert.match(before.stderr,/EPERM|EACCES/);
 const updated=new AclSandbox({writableDirs:[upgrade],tempDir:null,writeSid:workspaceWriteSid(fs.realpathSync.native(upgrade)),mode:'workspace-write'});
 try{await updated.init();const r=await updated.spawn({command:process.execPath,args:['-e',"const fs=require('fs');fs.renameSync('existing/old.txt','existing/renamed.txt');fs.unlinkSync('existing/renamed.txt')"],cwd:upgrade}).wait();assert.equal(r.exitCode,0,r.stderr.toString());assert.deepEqual(fs.readdirSync(path.join(upgrade,'existing')),[])}finally{updated.dispose()}
 console.log('PASS baseline fails existing rename; new runtime provisions that same workspace and rename/delete succeed');
}
