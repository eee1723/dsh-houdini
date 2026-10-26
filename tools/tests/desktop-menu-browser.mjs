// Actual official client consumes a session-less menu intent to an Ungrouped Session.
import fs from 'node:fs/promises'
import path from 'node:path'
import assert from 'node:assert/strict'
import {spawn} from 'node:child_process'
import {NATIVE_SELECTION} from './browser-selection.mjs'
const config=JSON.parse(await fs.readFile(process.argv[2],'utf8')),profile=path.join(config.output,'browser-profile')
const browser=spawn(config.browser,['--headless=new','--no-first-run','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore',windowsHide:true})
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));let socket,serial=0;const pending=new Map(),errors=[]
async function call(method,params={}){const id=++serial,result=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('CDP timeout '+method)),15000);pending.set(id,value=>{clearTimeout(timer);pending.delete(id);value.error?reject(Error(JSON.stringify(value.error))):resolve(value.result)})});socket.send(JSON.stringify({id,method,params}));return result}
async function evaluate(expression){const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value}
try{
 let port;for(let n=0;n<200;n++){try{port=Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break}catch{}await sleep(100)}assert(port)
 const targets=await(await fetch('http://127.0.0.1:'+port+'/json')).json();socket=new WebSocket(targets.find(row=>row.type==='page').webSocketDebuggerUrl)
 await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}));socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.id)pending.get(value.id)?.(value);else if(value.method==='Runtime.exceptionThrown')errors.push(value.params.exceptionDetails.exception?.description)})
 await call('Network.enable');await call('Runtime.enable');await call('Network.setCookies',{cookies:config.cookies})
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false})
 await call('Page.navigate',{url:config.base})
 let selected
 for(let n=0;n<300;n++){
  await evaluate(`document.querySelectorAll('button').forEach(button=>{if(['继续','稍后配置'].includes(button.textContent.trim()))button.click()});document.querySelector('[role="dialog"] button[aria-label="关闭"]')?.click()`)
  await evaluate(`[...document.querySelectorAll('[data-row-key^="workspace:"][aria-expanded="false"]')].find(row=>row.textContent.includes('未分组'))?.click()`)
  selected=await evaluate(NATIVE_SELECTION)
  if(selected?.sessionId===config.expectedSessionId&&await evaluate('!!document.querySelector("[data-houdini-project-label]")'))break
  await sleep(100)
 }
 assert.equal(selected?.sessionId,config.expectedSessionId,'native selected conversation must be the exact Ungrouped writer')
 assert.equal(selected.agentPreset,'houdini');assert.deepEqual(errors,[])
 const screenshot=await call('Page.captureScreenshot',{format:'png'});await fs.writeFile(path.join(config.output,'ungrouped-menu-selected.png'),Buffer.from(screenshot.data,'base64'))
 await fs.writeFile(path.join(config.output,'browser-done.json'),JSON.stringify({ok:true,selected,errors},null,2))
 console.log('PASS actual official browser: menu selects exact Ungrouped writer, without a workspace membership')
}catch(error){
 if(socket?.readyState===1)try{
  const shot=await call('Page.captureScreenshot',{format:'png'});await fs.writeFile(path.join(config.output,'browser-failure.png'),Buffer.from(shot.data,'base64'))
  const evidence=await evaluate(`({selected:${NATIVE_SELECTION},text:document.body.innerText,rows:[...document.querySelectorAll('[data-row-key]')].map(row=>({key:row.dataset.rowKey,selected:row.getAttribute('aria-selected'),expanded:row.getAttribute('aria-expanded'),text:row.textContent})),errors:${JSON.stringify(errors)}})`)
  await fs.writeFile(path.join(config.output,'browser-failure.json'),JSON.stringify(evidence,null,2))
 }catch{}
 throw error
}finally{if(socket?.readyState===1){try{await call('Browser.close')}catch{}socket.close()}for(let n=0;n<50&&browser.exitCode===null;n++)await sleep(100);if(browser.exitCode===null)browser.kill()}
