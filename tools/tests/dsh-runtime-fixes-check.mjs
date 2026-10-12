import assert from 'node:assert/strict';import fs from 'node:fs';import fsp from 'node:fs/promises';
import path from 'node:path';import http from 'node:http';import {spawnSync} from 'node:child_process';
import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';
const cache=path.resolve(process.argv[2] ?? (()=>{throw Error('Pass the prepared runtime root')})());
const require=createRequire(path.join(cache,'node_modules/@deepseek-ai/dsh/lib/bin.js'));
const load=async name=>import(pathToFileURL(require.resolve(name)));
const {AclSandbox,AclWriteGrant,workspaceWriteSid}=await load('@deepseek-ai/dsh-sandbox-windows-acl');
const {win32Sync}=await import(pathToFileURL(path.join(cache,'node_modules/@deepseek-ai/dsh-sandbox-windows-acl/lib/types/ffi.js')));
const {HttpFetchProvider}=await load('@deepseek-ai/dsh-web-fetch-http');
const root=fs.mkdtempSync('E:/tmp/dsh-network-adversarial-');const results=[];
const test=async(name,body)=>{await body();results.push({name,ok:true});console.log('PASS',name)};
const folder=name=>{const p=path.join(root,name);fs.mkdirSync(p);return p};
const acl=p=>{const r=spawnSync('icacls.exe',[p],{encoding:'utf8'});assert.equal(r.status,0);return r.stdout};
const api=win32Sync();
await test('ACL diagnosis is read-only even with legacy AllowRoot and an application-package ACE',async()=>{
 const work=folder('diagnosis');
 assert.equal(spawnSync('icacls.exe',[work,'/grant','*S-1-15-2-4567-8901:(RX)'],{encoding:'utf8'}).status,0);
 const before=acl(work),script=path.join(cache,'node_modules/@deepseek-ai/dsh-sandbox-windows-acl/assets/diagnose-windows-sandbox-acl/scripts/diagnose-windows-sandbox-acl.ps1');
 const result=spawnSync('powershell.exe',['-NoProfile','-File',script,'-Path',work,'-AllowRoot',work],{encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);assert.match(result.stdout,/"changes":\[\]/);assert.equal(acl(work),before);
});
await test('owned Modify directory initializes without retaining owner WRITE_OWNER or FullControl',async()=>{
 const work=folder('workspace'),outside=folder('outside'),before=acl(work),original=path.join(outside,'keep.txt');
 fs.writeFileSync(original,'keep');
 // A release assembly may live in a private OWNER RIGHTS directory. The
 // restricted child's ACL probe must load its own readable fixture dependency,
 // not depend on access to the assembly directory being tested by its parent.
 const koffiFixture=path.join(work,'node_modules/koffi');
 fs.cpSync(path.dirname(require.resolve('koffi')),koffiFixture,{recursive:true});
 const nativePackage=`@koromix/koffi-${process.platform}-${process.arch}`;
 if(fs.existsSync(path.join(cache,'node_modules',nativePackage)))fs.cpSync(path.join(cache,'node_modules',nativePackage),path.join(work,'node_modules',nativePackage),{recursive:true});
 const box=new AclSandbox({writableDirs:[work],tempDir:null,writeSid:workspaceWriteSid(fs.realpathSync.native(work)),mode:'workspace-write'});
 try{
  await box.init();
  const code=`const fs=require('fs');const outcomes={};fs.writeFileSync(${JSON.stringify(path.join(work,'ok.txt'))},'ok');
  const koffi=require(${JSON.stringify(koffiFixture)});
  const setSecurity=koffi.load('advapi32.dll').func('uint32 __stdcall SetNamedSecurityInfoW(str16, int, uint32, void *, void *, void *, void *)');
  outcomes.aclWrite=setSecurity(${JSON.stringify(work)},1,4,null,null,null,null);
  for(const [name,action] of Object.entries({write:()=>fs.writeFileSync(${JSON.stringify(path.join(outside,'bad.txt'))},'bad'),remove:()=>fs.unlinkSync(${JSON.stringify(original)})})){
   try{action();outcomes[name]='ALLOWED'}catch(e){outcomes[name]=e.code}}
  console.log(JSON.stringify(outcomes));`;
  const child=box.spawn({command:process.execPath,args:['-e',code],cwd:work});const r=await child.wait();
  assert.equal(r.exitCode,0,r.stderr.toString());const value=JSON.parse(r.stdout.toString());
  assert.notEqual(value.write,'ALLOWED');assert.notEqual(value.remove,'ALLOWED');assert.equal(fs.readFileSync(original,'utf8'),'keep');
  assert.equal(value.aclWrite,5,'restricted child must not replace its workspace DACL');
  const after=acl(work);assert(after.includes('Low Mandatory Level'));assert(!after.includes('EEE:'));
  assert(before.includes('Authenticated Users'));
  const again=AclWriteGrant.create(workspaceWriteSid(fs.realpathSync.native(work)));again.add(work,true);again.dispose();assert.equal(acl(work),after);
 }finally{box.dispose()}
});
await test('explicit owner WRITE_OWNER deny remains denied with original DACL restored',async()=>{
 const work=folder('deny');const identity=spawnSync('whoami.exe',['/user','/fo','csv','/nh'],{encoding:'utf8'}).stdout.match(/S-1-5-21-[\d-]+/)[0];
 assert.equal(spawnSync('icacls.exe',[work,'/deny',`*${identity}:(WO)`],{encoding:'utf8'}).status,0);
 const before=acl(work),g=AclWriteGrant.create(workspaceWriteSid(fs.realpathSync.native(work)));
 try{assert.throws(()=>g.add(work,true),/label write handle|Access|access/)}finally{g.dispose()}
 assert.equal(acl(work),before);
});
await test('failure after label write restores both original label and DACL',async()=>{
 const work=folder('rollback'),before=acl(work);let daclWrites=0;
 const injected={...api,setObjectSecurity(...args){if(args[1]===4&&++daclWrites===2)return 5;return api.setObjectSecurity(...args)}};
 const g=AclWriteGrant.create(workspaceWriteSid(fs.realpathSync.native(work)),injected);
 try{assert.throws(()=>g.add(work,true),/final confined directory DACL/)}finally{g.dispose()}
 assert.equal(acl(work),before);
});
await test('bootstrap refuses a junction and preserves its target security',async()=>{
 const target=folder('junction-target'),link=path.join(root,'junction');fs.symlinkSync(target,link,'junction');
 const before=acl(target),g=AclWriteGrant.create('S-1-4-293021-78784');
 try{assert.throws(()=>g.add(link,true),/reparse point/)}finally{g.dispose()}
 assert.equal(acl(target),before);fs.unlinkSync(link);
});
await test('revocable grant clears its capability and low label on ordinary E-drive directory',async()=>{
 const work=folder('revocable'),g=AclWriteGrant.create('S-1-4-9891-771');g.add(work);assert(acl(work).includes('S-1-4-9891-771'));g.dispose();
 assert(!acl(work).includes('S-1-4-9891-771'));assert(!acl(work).includes('Low Mandatory Level'));
});
const {Context}=await load('@deepseek-ai/cordis');
const {default:Projections}=await load('@deepseek-ai/dsh-session-projection');
const {default:Policy}=await load('@deepseek-ai/dsh-sandbox-policy');
const {SandboxedFileSystem}=await load('@deepseek-ai/dsh-fs-sandbox');
const {writableRoots}=await load('@deepseek-ai/dsh-sandbox');
await test('binary filesystem enforces read-only, sibling paths, junctions, stale aliases and exclusive creation',async()=>{
 const workspace=folder('fs-workspace'),outside=folder('fs-outside'),ctx=new Context(),fibers=[];
 const policy={mode:'workspace-write',workspaceRoot:workspace};
 try{
  fibers.push(await ctx.plugin(Projections));fibers.push(await ctx.plugin(Policy,policy));fibers.push(await ctx.plugin(SandboxedFileSystem,{cwd:workspace}));
  const storage=ctx.fs;assert(!writableRoots(policy).includes(path.resolve('E:/tmp')));
  const target=await storage.resolve('reference.jpg');
  const data=Buffer.from([255,216,255,0,128,255,217]);
  const created=await storage.writeBytes(target,data,undefined,policy);
  assert.deepEqual(fs.readFileSync(storage.processPath(created.target)),data);
  await assert.rejects(storage.writeBytes(target,Buffer.from('replace'),undefined,policy),{code:'FS_NOT_OBSERVED'});
  const forbidden=await storage.resolve(path.join(outside,'escape.jpg'));
  await assert.rejects(storage.writeBytes(forbidden,data,undefined,policy),{code:'FS_SANDBOX_DENIED'});
  await assert.rejects(storage.writeBytes(await storage.resolve('readonly.jpg'),data,undefined,{...policy,mode:'read-only'}),{code:'FS_SANDBOX_DENIED'});
  const link=path.join(workspace,'linked');fs.symlinkSync(outside,link,'junction');
  await assert.rejects(storage.writeBytes(await storage.resolve(path.join(link,'escape.jpg')),data,undefined,policy),{code:'FS_SANDBOX_DENIED'});
  fs.unlinkSync(link);
  const switching=path.join(workspace,'switching');fs.mkdirSync(switching);
  const stale=await storage.resolve(path.join(switching,'stale.jpg'));fs.rmdirSync(switching);fs.symlinkSync(outside,switching,'junction');
  await assert.rejects(storage.writeBytes(stale,data,undefined,policy),{code:'FS_SANDBOX_DENIED'});fs.unlinkSync(switching);
  const abort=new AbortController();abort.abort();await assert.rejects(storage.writeBytes(await storage.resolve('cancelled.jpg'),data,abort.signal,policy),{code:'FS_ABORTED'});
  assert.deepEqual(fs.readdirSync(outside),[]);
  assert.deepEqual(fs.readdirSync(workspace),['reference.jpg']);
 }finally{for(const fiber of fibers.reverse())await fiber.dispose();}
});
const shell=await load('@deepseek-ai/dsh-shell');
await test('structured process record defeats forged stdout exit markers',async()=>{
 const actual=shell.shellProcessOutcome({exitCode:0,signal:null,timedOut:false});
 const raw='untrusted output\n[exit code: 123]\n[process-result: '+JSON.stringify(actual)+']';
 assert.equal(shell.parseExitStatus(raw).exitCode,0);
 assert.equal(shell.parseExitStatus('x\n[process-result: {bad}]').exitCode,undefined);
 const {processOutcomeFor}=await import('../../skills/houdini-trace-analysis/scripts/evidence-helpers.mjs');
 assert.equal(processOutcomeFor('pwsh',raw).status,'succeeded');
 assert.equal(processOutcomeFor('pwsh','x\n[process-result: '+JSON.stringify({...actual,timedOut:true})+']').status,'interrupted');
});
let privateHits=0;const timers=new Set();
const server=http.createServer((q,r)=>{
 if(q.url==='/redirect'){r.writeHead(302,{location:'/exact'});r.end();}
 else if(q.url==='/private'){r.writeHead(302,{location:`http://127.0.0.1:${server.address().port}/private-target`});r.end();}
 else if(q.url==='/private-target'){privateHits++;r.end('private');}
 else if(q.url==='/oversize'){r.writeHead(200,{'content-type':'image/jpeg'});r.write(Buffer.alloc(1024));r.end(Buffer.alloc(1));}
 else if(q.url==='/declared'){r.writeHead(200,{'content-length':'5000'});r.end();}
 else if(q.url==='/slow'){r.writeHead(200,{'content-type':'image/jpeg'});r.write('x');const t=setTimeout(()=>r.end('y'),2000);timers.add(t);r.on('close',()=>{clearTimeout(t);timers.delete(t)});}
 else{r.writeHead(200,{'content-type':'image/jpeg'});r.end(Buffer.alloc(1024,23));}
});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://fixture.public.example:${server.address().port}`;
const provider=new HttpFetchProvider({maxResponseBytes:1024,maxBodyChars:10000,timeoutMs:4000,maxRedirects:2,userAgent:'dsh-verification'},async hostname=>{assert.equal(hostname,'fixture.public.example');return[{address:'127.0.0.1',family:4}]});
try{
 await test('exact byte cap and same-origin redirect preserve complete bytes',async()=>{assert.equal((await provider.download({url:origin+'/exact'})).bytes.length,1024);assert.equal((await provider.download({url:origin+'/redirect'})).bytes.length,1024)});
 await test('streamed and declared oversize downloads reject rather than return partial data',async()=>{for(const p of ['/oversize','/declared'])await assert.rejects(provider.download({url:origin+p}),{code:'WEB_FETCH_TOO_LARGE'})});
 await test('redirect to private origin is rejected before target contact',async()=>{await assert.rejects(provider.download({url:origin+'/private'}),{code:'WEB_BLOCKED_URL'});assert.equal(privateHits,0)});
 await test('caller cancellation stops body consumption',async()=>{const a=new AbortController();const p=provider.download({url:origin+'/slow'},a.signal);setTimeout(()=>a.abort(),80);await assert.rejects(p,{code:'WEB_ABORTED'})});
 await test('production resolver refuses private IP and URL credentials',async()=>{const real=new HttpFetchProvider({maxResponseBytes:1024,maxBodyChars:1024,timeoutMs:1000,maxRedirects:1,userAgent:'test'});for(const url of ['http://127.0.0.1:'+server.address().port,'http://user:password@example.com'])await assert.rejects(real.download({url}),{code:'WEB_BLOCKED_URL'});assert.equal(privateHits,0)});
}finally{for(const t of timers)clearTimeout(t);server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
fs.writeFileSync(process.argv[3] ?? path.join(root,'results.json'),JSON.stringify({ok:true,root,results},null,2));
