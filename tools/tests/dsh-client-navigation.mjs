// Official DSH browser, native workspace/session navigation and mode scope.
// Owns a fresh browser profile and an authenticated disposable Host fixture.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import {spawn} from 'node:child_process'
import {NATIVE_SELECTION,nativeSessionSelected} from './browser-selection.mjs'
const config=JSON.parse(await fs.readFile(process.argv[2],'utf8'))
const profile=path.join(config.output,'browser-profile'),events=[]
const browser=spawn(config.browser,['--headless=new','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'})
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
let socket,sequence=0;const pending=new Map()
async function call(method,params={}) {
 const id=++sequence,result=new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{pending.delete(id);reject(Error('Browser timeout '+method))},15000)
  pending.set(id,value=>{clearTimeout(timer);pending.delete(id);value.error?reject(Error(JSON.stringify(value.error))):resolve(value.result)})
 });socket.send(JSON.stringify({id,method,params}));return result
}
async function evaluate(expression){const value=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!value.exceptionDetails,JSON.stringify(value.exceptionDetails));return value.result.value}
async function until(expression){for(let n=0;n<200;n++){if(await evaluate('Boolean('+expression+')'))return;await sleep(100)}throw Error('Not ready: '+expression)}
async function click(selector){const position=await evaluate(`(()=>{const element=document.querySelector(${JSON.stringify(selector)});if(!element)throw Error('Missing '+${JSON.stringify(selector)});const box=element.getBoundingClientRect();return{x:box.x+box.width/2,y:box.y+box.height/2}})()`);await call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...position});await call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...position});await sleep(150)}
async function textButton(text){return evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(button=>button.textContent.trim()===${JSON.stringify(text)});if(!button)return false;button.click();return true})()`)}
async function screenshot(name){const result=await call('Page.captureScreenshot',{format:'png'});await fs.writeFile(path.join(config.output,name+'.png'),Buffer.from(result.data,'base64'))}
async function selectSession(id){
 const selector='[data-row-key="session:'+id+'"]'
 for(let attempt=0;attempt<10;attempt++){
  if(await evaluate('!!document.querySelector('+JSON.stringify(selector)+')'))break
  await evaluate(`document.querySelector('[data-row-key^="workspace:"][aria-expanded="false"]')?.click()`)
  await sleep(200)
 }
 await until('document.querySelector('+JSON.stringify(selector)+')');await click(selector)
 await until(nativeSessionSelected(id))
}
try {
 let port
 for(let n=0;n<200;n++){try{port=Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break}catch{}await sleep(100)}
 assert(port,'Owned browser debugging endpoint missing')
 const targets=await(await fetch('http://127.0.0.1:'+port+'/json')).json(),target=targets.find(row=>row.type==='page')
 socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}))
 socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.id)pending.get(value.id)?.(value);else if(value.method==='Runtime.exceptionThrown')events.push(value.params.exceptionDetails)})
 await call('Runtime.enable');await call('Page.enable');await call('Network.enable')
 await call('Network.setCookies',{cookies:config.cookies});await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false})
 await call('Page.navigate',{url:config.base});await until(NATIVE_SELECTION)
 for(let attempt=0;attempt<25;attempt++){
  await textButton('继续');await textButton('稍后配置')
  await evaluate(`document.querySelector('[role="dialog"] button[aria-label="关闭"]')?.click()`)
  await sleep(150)
 }
 await selectSession(config.standardSession)
 assert.equal(await evaluate(NATIVE_SELECTION+'.agentPreset'),'standard')
 assert.equal(await evaluate('!!document.querySelector("[data-houdini-project-label]")'),false)
 assert.equal(await evaluate(`!![...document.querySelectorAll('[role=tab]')].find(tab=>tab.textContent==='执行记录')`),false)
 await screenshot('official-standard-clean')
 await selectSession(config.firstSession);await until('document.querySelector("[data-houdini-project-label]")')
 const firstSelection=await evaluate(NATIVE_SELECTION);assert.equal(firstSelection.agentPreset,'houdini')
 await selectSession(config.secondSession);await until('document.querySelector("[data-houdini-project-label]")')
 const secondSelection=await evaluate(NATIVE_SELECTION);assert.equal(secondSelection.agentPreset,'houdini')
 assert.notEqual(firstSelection.sessionId,secondSelection.sessionId)
 await screenshot('official-houdini-blank')
 await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-action=new]")')
 await screenshot('official-houdini-target-menu')
 await click('[data-houdini-project-action=new]');await until('document.querySelector("[data-houdini-project-dialog]")')
 await screenshot('official-houdini-open-dialog')
 await textButton('取消')
 // Seed receipts into this owned Session without inbox/model/HOM activity.
 await fs.writeFile(config.seedFile,config.secondSession)
 for(let attempt=0;attempt<100;attempt++){try{await fs.access(config.seedFile+'.done');break}catch{}await sleep(100)}
 await call('Page.reload');await until(nativeSessionSelected(config.secondSession))
 await until('document.body.textContent.includes("Isolated UI fixture: inspect Trace and tool documentation.")')
 await until(`!![...document.querySelectorAll('[role=tab]')].find(tab=>tab.textContent==='轨迹')`)
 const composer='[data-composer-input][contenteditable="true"]'
 await until('document.querySelector('+JSON.stringify(composer)+')')
 await evaluate(`(()=>{const editor=document.querySelector(${JSON.stringify(composer)});editor.focus();document.execCommand('insertText',false,'保留这段未发送的草稿')})()`)
 await evaluate(`document.querySelectorAll('[role=tab]').forEach(tab=>{if(tab.textContent==='轨迹')tab.click()})`)
 await until('document.querySelector("[role=tab][aria-selected=true]")?.textContent==="轨迹"')
 await screenshot('official-houdini-trace')
 const traceText=await evaluate('document.body.textContent')
 assert.equal(await evaluate('document.querySelector(".dsh-trace")===null'),true,'native trajectory replaces the duplicate plugin Trace')
 await evaluate(`document.querySelectorAll('[role=tab]').forEach(tab=>{if(tab.textContent==='对话')tab.click()})`)
 await until('document.querySelector("[role=tab][aria-selected=true]")?.textContent==="对话"')
 assert.equal(await evaluate('document.querySelector('+JSON.stringify(composer)+').textContent'),'保留这段未发送的草稿')
 await selectSession(config.standardSession)
 assert.equal(await evaluate(`!![...document.querySelectorAll('[role=tab]')].find(tab=>tab.textContent==='执行记录')`),false,'Trace tab is removed in the real host slot registry')
 assert.equal(await evaluate('!!document.querySelector("[data-houdini-project-label]")'),false)
 assert.equal(await evaluate(`!!document.querySelector('[data-houdini-window-pin],[data-houdini-update]')`),false)
 await screenshot('official-standard-after-houdini')
 await fs.writeFile(path.join(config.output,'browser-review.json'),JSON.stringify({ok:true,firstSelection,secondSelection,traceText,errors:events},null,2))
 assert.deepEqual(events,[],'Official client must load without runtime exceptions')
 console.log('Official rc.3 browser: native workspace/session selection, standard/Houdini mode isolation, target menu/open dialog, Trace and resident draft preservation passed')
} catch(error){if(socket?.readyState===1){try{await screenshot('official-browser-failure');await fs.writeFile(path.join(config.output,'browser-failure.txt'),await evaluate('document.body.innerText'));await fs.writeFile(path.join(config.output,'browser-failure.json'),JSON.stringify(await evaluate(`({selection:${NATIVE_SELECTION},rows:[...document.querySelectorAll('[data-row-key]')].map(row=>({key:row.dataset.rowKey,expanded:row.getAttribute('aria-expanded'),text:row.textContent})),errors:${JSON.stringify(events)}})`),null,2))}catch{}}throw error}
finally{if(socket?.readyState===1){try{await call('Browser.close')}catch{}socket.close()}for(let n=0;n<50&&browser.exitCode===null;n++)await sleep(100);if(browser.exitCode===null)browser.kill()}
