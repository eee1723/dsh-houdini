// Real official browser: an already open project menu receives new ordinary
// Houdini registrations, and selection changes only its original native Session.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import {spawn} from 'node:child_process'
import {NATIVE_SELECTION,nativeSessionSelected} from './browser-selection.mjs'

const config=JSON.parse(await fs.readFile(process.argv[2],'utf8'))
const profile=path.join(config.output,'startup-browser-profile')
const browser=spawn(config.browser,['--headless=new','--no-first-run','--no-default-browser-check',
  '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'})
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)),pending=new Map(),errors=[]
let socket,sequence=0
async function call(method,params={}){
  const id=++sequence,result=new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('Browser timeout '+method))},15000)
    pending.set(id,value=>{clearTimeout(timer);pending.delete(id);value.error?reject(Error(JSON.stringify(value.error))):resolve(value.result)})
  });socket.send(JSON.stringify({id,method,params}));return result
}
async function evaluate(expression){
  const value=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true})
  assert(!value.exceptionDetails,JSON.stringify(value.exceptionDetails));return value.result.value
}
async function until(expression,label,timeout=45000){
  const end=Date.now()+timeout
  while(Date.now()<end){const value=typeof expression==='function'?await expression():await evaluate(expression);if(value)return value;await sleep(100)}
  throw Error('Not ready: '+label)
}
async function click(selector){
  const point=await until(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e)return null;
    const b=e.closest('button')||e;if(b.disabled||b.getAttribute('aria-disabled')==='true')return null;
    b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;
    const hit=document.elementFromPoint(x,y);return r.width&&r.height&&hit&&(b===hit||b.contains(hit))?{x,y}:null})()`,selector)
  await call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point})
  await call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});await sleep(150)
}
async function rpc(method,args){
  return evaluate(`(async()=>{const r=await fetch('/api/'+${JSON.stringify(method)},{method:'POST',headers:{'content-type':'application/json'},
    credentials:'include',body:JSON.stringify({type:'client-request',rpcId:crypto.randomUUID(),method:${JSON.stringify(method)},payload:{args:${JSON.stringify(args)}}})});
    const b=await r.json();if(!b.result?.ok)throw Error(JSON.stringify(b.result?.error||b));return b.result.value})()`)
}
async function signal(name,value){
  const file=path.join(config.output,name),temporary=file+'.tmp';await fs.writeFile(temporary,JSON.stringify(value));await fs.rename(temporary,file)
}
async function shot(name){const image=await call('Page.captureScreenshot',{format:'png'});await fs.writeFile(path.join(config.output,name+'.png'),Buffer.from(image.data,'base64'))}
try{
  let port
  for(let n=0;n<200;n++){try{port=Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break}catch{}await sleep(100)}
  assert(port,'Owned browser endpoint missing')
  const targets=await(await fetch('http://127.0.0.1:'+port+'/json')).json(),target=targets.find(row=>row.type==='page')
  socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}))
  socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.id)pending.get(value.id)?.(value);else if(value.method==='Runtime.exceptionThrown')errors.push(value.params.exceptionDetails)})
  await call('Runtime.enable');await call('Page.enable');await call('Network.enable')
  await call('Network.setCookies',{cookies:config.cookies})
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false})
  // Restore the official browser preference from before the original window
  // exited. The native restoreBlank path retains this Session's Houdini preset;
  // creating another blank draft here would exercise the standard-mode entry.
  await call('Page.addScriptToEvaluateOnNewDocument',{source:`if(location.origin===${JSON.stringify(new URL(config.base).origin)})localStorage.setItem('dsh.sessions.current',JSON.stringify({sessionId:${JSON.stringify(config.sessionId)}}))`})
  await call('Page.navigate',{url:config.base})
  await until('Boolean('+NATIVE_SELECTION+')','native initial selection')
  for(let n=0;n<12;n++){
    await evaluate(`[...document.querySelectorAll('button')].find(e=>['继续','稍后配置'].includes(e.textContent.trim()))?.click()`)
    await evaluate(`document.querySelector('[role="dialog"] button[aria-label="关闭"]')?.click()`);await sleep(100)
  }
  const sessionSelector='[data-row-key="session:'+config.sessionId+'"]'
  for(let n=0;n<12;n++){
    if(await evaluate('Boolean(document.querySelector('+JSON.stringify(sessionSelector)+'))'))break
    await evaluate(`document.querySelector('[data-row-key^="workspace:"][aria-expanded="false"]')?.click()`);await sleep(100)
  }
  await click(sessionSelector);await until(nativeSessionSelected(config.sessionId),'original native conversation selected')
  const original=await rpc('session/projections',{request:{sessionId:config.sessionId}})
  assert.equal(original?.values?.agentPreset,'houdini','Native restoration must retain the recorded Houdini preset')
  await until('Boolean(document.querySelector("[data-houdini-project-label]"))','native Houdini project header')
  await click('[data-houdini-project-label]')
  await click('[data-houdini-target="'+config.executorA+'"]')
  await until(async()=>(await rpc('houdiniTargets/list',{input:{sessionId:config.sessionId}})).selectedTarget?.executor_id===config.executorA,'A actually selected')
  await click('[data-houdini-project-label]');await until('Boolean(document.querySelector("[data-houdini-project-action=new]"))','menu kept open before A exits')
  await shot('startup-original-A-selected')
  await signal('startup-A-selected.json',{selection:await evaluate(NATIVE_SELECTION),menuOpen:true})
  let second
  const startupDeadline=Date.now()+config.nativeStartupTimeoutMs+35000
  while(Date.now()<startupDeadline){try{second=JSON.parse(await fs.readFile(path.join(config.output,'startup-B-ready.json'),'utf8'));break}catch{}await sleep(100)}
  assert(second,'Ordinary B registration signal missing')
  // No refresh/reopen action after this point: the existing menu must receive B.
  const selector='[data-houdini-target="'+second.executorId+'"]'
  await until('Boolean(document.querySelector('+JSON.stringify(selector)+'))','B automatically appears in the already open menu')
  assert.equal((await evaluate(NATIVE_SELECTION)).sessionId,config.sessionId)
  const title=await evaluate('document.querySelector('+JSON.stringify(selector)+').title')
  assert(title.includes(String(second.pid)),'The candidate presents the actual new process')
  await shot('startup-new-B-visible-without-refresh')
  await click(selector)
  const final=await until(async()=>{const value=await rpc('houdiniTargets/list',{input:{sessionId:config.sessionId}});return value.selectedTarget?.executor_id===second.executorId?value:null},'B selected by the original conversation')
  const selection=await evaluate(NATIVE_SELECTION);assert.equal(selection.sessionId,config.sessionId)
  assert.deepEqual(errors,[])
  await shot('startup-original-session-now-B')
  const report={ok:true,selection,selectedTarget:final.selectedTarget,newWindowVisibleWithoutRefresh:true,
    restoredNativeSelection:{sessionId:config.sessionId,agentPreset:original.values.agentPreset},errors}
  await signal('startup-B-selected.json',report);await signal('startup-browser-result.json',report)
  console.log('PASS real official browser selected B in the original conversation without refresh, menu reopen or new Session')
}catch(error){
  if(socket?.readyState===1)try{await shot('startup-browser-failure');await fs.writeFile(path.join(config.output,'startup-browser-failure.txt'),await evaluate('document.body.innerText'))}catch{}
  throw error
}finally{
  if(socket?.readyState===1){try{await call('Browser.close')}catch{}socket.close()}
  for(let n=0;n<50&&browser.exitCode===null;n++)await sleep(100)
  if(browser.exitCode===null)browser.kill()
}
