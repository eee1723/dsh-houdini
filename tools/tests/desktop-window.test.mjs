import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {DesktopWindowController,DesktopWindowUnavailableError} from '../../lib/desktop-window.js'

const A='a'.repeat(32),B='b'.repeat(32)
const identity={pid:123,started:'134375000000000000',executable:path.resolve('fixture/DeepSeek Harness.exe'),hwnd:'456'}
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return{promise,resolve}}
const roots=[]
async function fixture({baseline=false,parentPid=identity.pid,root:provided}={}) {
 const root=provided??await fs.mkdtemp(path.join(os.tmpdir(),'dsh-window-pin-'));if(!provided)roots.push(root)
 const scopedIdentity={...identity,pid:parentPid}
 const events=[];let window={...scopedIdentity,pinned:baseline},gate=null,unavailable=false,fail=false
 const boundary={parentPid,
  async current(){if(unavailable)throw new DesktopWindowUnavailableError('Ambiguous main windows');return{...window}},
  async set(expected,value,commit){
   const record=JSON.parse(await fs.readFile(controller.recordPath,'utf8'))
   assert.equal(record.baseline,baseline,'the original baseline is durable before the first native mutation')
   assert.equal('pinned' in record.window,false,'persist only identity plus its single baseline')
   if(gate)await gate.promise
   commit?.();assert.deepEqual(expected,scopedIdentity)
   events.push(['set',value]);window.pinned=value
   if(fail)throw Error('Fixture: failed after OS commit')
  },
  async restore(expected,value){
   events.push(['restore',value])
   if(expected.pid===window.pid&&expected.started===window.started&&expected.hwnd===window.hwnd)window.pinned=value
  },
 }
 const controller=new DesktopWindowController({root,os:boundary,platform:'win32'})
 return{root,boundary,controller,events,state:()=>window,gate:value=>gate=value,unavailable:value=>unavailable=value,fail:value=>fail=value,
  replace:value=>window={...window,...value},exists:()=>fs.stat(controller.recordPath).then(()=>true,error=>{if(error.code==='ENOENT')return false;throw error})}
}
try {
 {
  const f=await fixture();f.unavailable(true)
  await f.controller.start();assert.equal(await f.exists(),false,'fresh startup never needs a window or writes a journal')
  assert.deepEqual(await f.controller.read(),{available:false,reason:'Ambiguous main windows'})
  f.unavailable(false);assert.equal((await f.controller.activate(A)).pinned,false)
  assert.equal(await f.exists(),false,'activation alone does not persist a lease')
  await f.controller.set(A,false);assert.equal(await f.exists(),false,'a no-op does not persist a lease')
  await f.controller.set(A,true);assert.equal(await f.exists(),true)
  await f.controller.release(A);assert.equal(f.state().pinned,false);assert.equal(await f.exists(),false)
  await f.controller.dispose()
 }
 {
  const f=await fixture({baseline:true});await f.controller.activate(A);await f.controller.set(A,false)
  await f.controller.release(A);assert.equal(f.state().pinned,true,'release restores a pre-existing pin instead of forcing unpinned')
  await f.controller.dispose()
 }
 {
  const f=await fixture();await f.controller.activate(A);await f.controller.set(A,true)
  await f.controller.reset();assert.equal(f.state().pinned,false,'renderer reload into Standard restores the previous page baseline')
  assert.equal(await f.exists(),false);await assert.rejects(f.controller.set(A,true),/已结束/)
  await f.controller.activate(B);await f.controller.set(B,true);await f.controller.release(B)
  assert.equal(f.state().pinned,false,'reset keeps the native adapter usable for the new page')
  await f.controller.dispose()
 }
 {
  const f=await fixture();await f.controller.activate(A);await f.controller.set(A,true)
  await f.controller.activate(B);assert.equal(f.state().pinned,false,'a new owner begins after the old baseline is restored')
  await f.controller.set(B,true);const count=f.events.length
  await f.controller.release(A);assert.equal(f.events.length,count,'late old release cannot restore the new owner’s window')
  await assert.rejects(f.controller.activate(A),/已结束/);await assert.rejects(f.controller.set(A,false),/已结束/)
  await f.controller.release(B);assert.equal(f.state().pinned,false);await f.controller.dispose()
 }
 {
  const f=await fixture(),activation=f.controller.activate(A),released=f.controller.release(A)
  await assert.rejects(activation,/已结束/);await released;assert.equal(f.events.length,0,'release before admission permanently retires the old scope')
  await f.controller.dispose()
 }
 {
  const f=await fixture();await f.controller.activate(A);const gate=deferred();f.gate(gate)
  const setting=f.controller.set(A,true)
  for(let n=0;n<100&&!await f.exists();n++)await new Promise(resolve=>setTimeout(resolve,2))
  assert.equal(await f.exists(),true);const released=f.controller.release(A),next=f.controller.activate(B)
  gate.resolve();await assert.rejects(setting,/已结束/);await released;await next
  assert.equal(f.events.some(event=>event[0]==='set'),false,'the native commit fence rejects a mode exit during asynchronous preparation')
  assert.equal(f.state().pinned,false);assert.equal(await f.exists(),false);await f.controller.dispose()
 }
 {
  const f=await fixture();await f.controller.activate(A);await f.controller.set(A,true)
  // The old object is abandoned, exactly as after a Host crash.
  const restarted=new DesktopWindowController({root:f.root,os:f.boundary,platform:'win32'})
  await restarted.start();assert.equal(f.state().pinned,false,'root startup restores its saved baseline before any Houdini mode request')
  assert.equal(await f.exists(),false);await restarted.dispose()
 }
 {
  const f=await fixture();await f.controller.activate(A);f.fail(true)
  await assert.rejects(f.controller.set(A,true),/failed after OS commit/)
  assert.equal(await f.exists(),true,'unknown/failed post-commit results preserve recovery')
  await f.controller.release(A);assert.equal(f.state().pinned,false);assert.equal(await f.exists(),false);await f.controller.dispose()
 }
 {
  const f=await fixture();await f.controller.activate(A);f.replace({hwnd:'789'})
  await assert.rejects(f.controller.set(A,true),/窗口已变化/)
  assert.equal(f.events.length,0);assert.equal(await f.exists(),false,'a replaced window cannot be pinned by the old scope')
  await f.controller.dispose()
 }
 {
  const f=await fixture();const text='{"schema":999,"preserve":"unknown"}'
  await fs.mkdir(path.dirname(f.controller.recordPath),{recursive:true});await fs.writeFile(f.controller.recordPath,text)
  await assert.rejects(f.controller.start(),/记录无效/)
  assert.equal(await fs.readFile(f.controller.recordPath,'utf8'),text);assert.equal(f.events.length,0)
  await f.controller.dispose()
 }
 {
  const first=await fixture(),second=await fixture({root:first.root,parentPid:789})
  await first.controller.activate(A);await first.controller.set(A,true)
  const original=await fs.readFile(first.controller.recordPath,'utf8')
  await second.controller.start();assert.notEqual(first.controller.recordPath,second.controller.recordPath)
  assert.equal(await fs.readFile(first.controller.recordPath,'utf8'),original,'a second Native Main cannot consume or remove the first Main recovery record')
  await second.controller.activate(B);await second.controller.set(B,true);await second.controller.release(B)
  assert.equal(first.state().pinned,true);assert.equal(await first.exists(),true)
  await first.controller.release(A);await first.controller.dispose();await second.controller.dispose()
 }
 console.log('Desktop window pin: actual baseline, change-only journal, startup recovery, owner retirement/commit fence, late release, replaced window and error recovery passed')
} finally {
 const parent=(await fs.realpath(os.tmpdir())).toLowerCase()
 for(const root of roots){const actual=await fs.realpath(root);assert.equal(path.dirname(actual).toLowerCase(),parent);assert(path.basename(actual).startsWith('dsh-window-pin-'));await fs.rm(actual,{recursive:true,force:true})}
}
