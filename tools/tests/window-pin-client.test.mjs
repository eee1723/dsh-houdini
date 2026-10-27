import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import vm from 'node:vm'
import {DesktopWindowController} from '../../lib/desktop-window.js'

const text=await fs.readFile(new URL('../../client.js',import.meta.url),'utf8')
const code=text.slice(text.indexOf('    function createWindowPinUi('),text.indexOf('    function createHoudiniDesktopUi('))
const box={AbortSignal,setTimeout,clearTimeout};vm.runInNewContext(code+';this.make=createWindowPinUi',box)
function store(value){const listeners=new Set();return {getSnapshot:()=>value,subscribe:f=>{listeners.add(f);return()=>listeners.delete(f)},
  set(next){value=next;for(const f of [...listeners])f()},listeners}}
async function until(read){for(let n=0;n<200;n++){if(await read())return;await new Promise(r=>setTimeout(r,5))}throw Error('pin UI fixture did not settle')}
const root=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-pin-client-'))
let pinned=false,number=0,failRelease=false,changes=0
const identity={pid:process.ppid,started:'123',executable:process.execPath,hwnd:'42'}
const backend=new DesktopWindowController({root,platform:'win32',os:{parentPid:process.ppid,
  current:async()=>({...identity,pinned}),set:async(_window,next,commit)=>{commit?.();pinned=next},restore:async(_window,next)=>{pinned=next}}})
const generation=store(1),calls=[],errors=[]
const connection={generation,rpc:{call:async(_channel,method,payload)=>{
  assert.equal(method,'houdiniFrontend/windowPin');const v=payload.args.input;calls.push(v.action)
  if(v.action==='release'&&failRelease){failRelease=false;return {ok:false,error:{message:'owned transport failure'}}}
  try {return {ok:true,value:await (v.action==='set'?backend.set(v.owner,v.pinned):v.action==='read'||v.action==='reset'?backend[v.action]():backend[v.action](v.owner))}}
  catch(error){return {ok:false,error:{message:String(error.message)}}}
}}}
const make=enabled=>box.make(connection,()=>changes++,message=>errors.push(message),{enabled,owner:()=> (++number).toString(16).padStart(32,'0')})
let ui
try {
  await backend.start();ui=make(true)
  await ui.enter();assert.equal(ui.snapshot().pinned,false)
  await ui.toggle();assert.equal(pinned,true);assert.equal(ui.snapshot().pinned,true)
  failRelease=true;ui.leave()
  await until(async()=>!pinned&&!await fs.stat(backend.recordPath).then(()=>true,()=>false))
  assert.equal(errors.length,0,'background cleanup failure retries without a domain toast in Standard mode')
  assert.equal(await fs.stat(backend.recordPath).then(()=>true,()=>false),false)
  await ui.enter();assert.equal(pinned,true,'returning to Houdini restores the explicit preference while this client lives')
  generation.set(0);ui.leave();generation.set(2)
  await until(()=>!pinned)
  assert.equal(pinned,false,'a reconnected client in Standard mode reconciles its old window change')
  await ui.enter();assert.equal(pinned,true)
  ui.dispose();ui=undefined
  const replacement=make(true);ui=replacement
  await until(()=>!pinned)
  await ui.enter();assert.equal(pinned,false,'a replacement renderer reads the restored OS baseline')
  await ui.toggle();ui.leave();await until(()=>!pinned)
  const count=calls.length,web=make(false)
  await web.enter();await web.toggle();web.leave();web.dispose()
  assert.equal(calls.length,count,'a browser client never calls the native window control')
  assert.ok(changes>0);assert.equal(errors.length,0)
  console.log('Native pin UI: explicit choices, mode baseline restore, release retry, reconnect/reload cleanup and browser isolation passed')
} finally {ui?.dispose();await backend.dispose();await fs.rm(root,{recursive:true,force:true})}
