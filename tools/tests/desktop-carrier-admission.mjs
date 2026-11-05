// Admit only an owned, naturally unpackaged official Electron carrier before
// any DSH application code runs. No Electron API or official code is replaced.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {pathToFileURL} from 'node:url'

const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'))
assert.equal(path.basename(config.executable).toLowerCase(),'electron.exe')
assert(new URL(config.main).hostname==='127.0.0.1')
const mainUrl=pathToFileURL(path.join(path.dirname(config.appPackage),'lib/main.js')).href.toLowerCase()
const ws=new WebSocket(config.main),pending=new Map(),pauses=[],scripts=new Map()
let serial=0
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
ws.onmessage=event=>{
  const row=JSON.parse(event.data)
  if(row.id)pending.get(row.id)?.(row)
  else if(row.method==='Debugger.paused')pauses.push(row.params)
  else if(row.method==='Debugger.scriptParsed')scripts.set(row.params.scriptId,row.params.url)
}
async function call(method,params={}){
  const id=++serial,promise=new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('Carrier admission timeout: '+method))},15000)
    pending.set(id,row=>{clearTimeout(timer);pending.delete(id);row.error?reject(Error(JSON.stringify(row.error))):resolve(row.result)})
  })
  ws.send(JSON.stringify({id,method,params}));return promise
}
async function nativeState(){
  const result=await call('Runtime.evaluate',{expression:`(()=>{const {app}=process._linkedBinding('electron_browser_app');return {pid:process.pid,packaged:app.isPackaged,executable:process.execPath,forcePackaged:'ELECTRON_FORCE_IS_PACKAGED' in process.env,registerDevelopment:process.env.DSH_DESKTOP_DEV_APP==='1'}})()`,returnByValue:true})
  assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails))
  const state=result.result.value
  assert.equal(state.packaged,false);assert.equal(state.forcePackaged,false);assert.equal(state.registerDevelopment,false)
  return state
}
try{
  await call('Runtime.enable')
  const bootstrap=await nativeState()
  await call('Debugger.enable')
  const breakpoint=await call('Debugger.setBreakpointByUrl',{lineNumber:0,urlRegex:'[/\\\\]lib[/\\\\]main\\.js$'})
  await call('Runtime.runIfWaitingForDebugger')
  let reached=false
  for(let count=0;count<64;count++){
    const deadline=Date.now()+15000
    while(pauses.length===0&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,20))
    const paused=pauses.shift();assert(paused,'Official main entry did not pause')
    const url=paused.callFrames[0].url||scripts.get(paused.callFrames[0].location.scriptId)||''
    if(url.toLowerCase()===mainUrl){reached=true;break}
    await call('Debugger.resume')
  }
  assert(reached,'Never admit an unobserved application entry')
  const application=await nativeState()
  assert.equal(application.pid,config.pid)
  assert.equal(application.executable.toLowerCase(),config.executable.toLowerCase())
  fs.writeFileSync(config.output,JSON.stringify({bootstrap,application,officialMain:mainUrl},null,2))
  await call('Debugger.removeBreakpoint',{breakpointId:breakpoint.breakpointId})
  await call('Debugger.resume');await call('Debugger.disable')
}finally{ws.close()}
