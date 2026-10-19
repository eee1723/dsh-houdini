import fs from 'node:fs/promises'
import assert from 'node:assert/strict'
const [port,action,output,expectedState,expectedSession,executor]=process.argv.slice(2)
const pages=await(await fetch('http://127.0.0.1:'+port+'/json')).json()
const page=pages.find(item=>item.type==='page'&&item.url.startsWith('http://127.0.0.1:'))
assert(page,'Actual workbench Qt page must exist')
const socket=new WebSocket(page.webSocketDebuggerUrl),pending=new Map();let serial=0
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})})
socket.addEventListener('message',event=>{const value=JSON.parse(event.data);pending.get(value.id)?.(value)})
async function call(method,params={}){const id=++serial;const result=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('Browser test timed out: '+method))},10000);pending.set(id,value=>{pending.delete(id);clearTimeout(timer);resolve(value)});socket.send(JSON.stringify({id,method,params}))});assert(!result.error,JSON.stringify(result.error));return result.result}
async function evaluate(expression){const value=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!value.exceptionDetails,JSON.stringify(value.exceptionDetails));return value.result.value}
const takeScreenshots=process.env.DSH_GUI_CAPTURE_SCREENSHOTS==='1'
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function dismiss(){await evaluate(`(()=>{const visible=e=>e.getClientRects().length;for(const b of document.querySelectorAll('button'))if(visible(b)&&(['稍后配置','以后再说'].includes(b.textContent.trim())||(document.body?.innerText.includes('预览版说明')&&b.textContent.trim()==='继续')))b.click();for(const d of document.querySelectorAll('[role="dialog"]'))if(visible(d)&&d.textContent.includes('添加 API Key'))d.querySelector('button[aria-label="关闭"]')?.click();return true})()`)}
async function capture(){return evaluate(`(async()=>{const chip=document.querySelector('[data-houdini-project-label]'),selection=window.__dshHoudiniSelection?.();let targets=null;if(selection?.sessionId){const method='houdiniTargets/list';const r=await fetch('/api/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:'launch-ui-'+crypto.randomUUID(),method,payload:{args:{input:{sessionId:selection.sessionId}}}})});const body=await r.json();if(body.result?.ok)targets=body.result.value;}return{selection,label:document.querySelector('[data-houdini-project-name]')?.textContent,state:chip?.dataset.state,status:chip?.dataset.houdiniPresence,entry:!!document.querySelector('[aria-label="打开或新建 Houdini 工程"]'),menuOpen:chip?.getAttribute('aria-expanded')==='true',selectedTarget:targets?.selectedTarget??null,targetState:targets?.state?.status,text:document.body?.innerText??''}})()`)}
async function until(check){let value;for(let n=0;n<200;n++){await dismiss();value=await capture();if(check(value))return value;await sleep(100)}throw Error('UI did not settle: '+JSON.stringify(value))}
async function click(expression){const point=await evaluate(`(()=>{const e=${expression};if(!e||e.disabled)return null;const r=e.getBoundingClientRect();return r.width&&r.height?{x:r.x+r.width/2,y:r.y+r.height/2}:null})()`);if(!point)return false;await call('Input.dispatchMouseEvent',{type:'mouseMoved',...point});await sleep(120);const onTarget=await evaluate(`(()=>{const e=${expression},hit=document.elementFromPoint(${point.x},${point.y});return !!e&&(e===hit||e.contains(hit))})()`);if(!onTarget)return false;await call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});await call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});return true}
async function openMenu(){if(!await evaluate(`document.querySelector('[data-houdini-project-label]')?.getAttribute('aria-expanded')==='true'`))assert(await click(`document.querySelector('[data-houdini-project-label]')||document.querySelector('[aria-label="打开或新建 Houdini 工程"]')`),'Native project entry must be clickable');await until(row=>row.menuOpen&&!row.text.includes('正在查看已打开的 Houdini…'));await sleep(250)}
try{
 let value=await until(row=>(row.label||row.entry)&&(!(action==='snapshot'&&expectedSession)||row.selection?.sessionId===expectedSession))
 if(action==='state')value=await until(row=>row.state===expectedState&&(!expectedSession||row.selection?.sessionId===expectedSession)&&(!executor||row.selectedTarget?.executor_id===executor))
 else if(action==='new-target')value=await until(row=>row.state===expectedState&&row.selection?.sessionId!==expectedSession&&row.selectedTarget?.executor_id===executor)
 else if(action==='new-chat'){
   const before=value.selection?.sessionId,wasBound=!!value.selectedTarget
   let chosen=false
   for(let n=0;n<60;n++){
     await dismiss();value=await capture()
     // The native workspace launch can finish selecting its first blank
     // conversation while the preview dialog appears. Reuse that real row.
     if(!wasBound&&value.selection?.sessionId&&!value.selectedTarget){chosen=true;break}
     if(await click(`[...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')==='新会话'||b.textContent.trim().startsWith('新会话'))`)){chosen=true;break}
     await sleep(100)
   }
   assert(chosen,'Native New Session button or its actual unbound conversation must be available')
   value=await until(row=>row.selection?.sessionId&&(!wasBound||row.selection.sessionId!==before))
 }else if(action==='select-target'||action==='clear-target'){
   const cwd=value.selection?.cwd
   await openMenu()
   let clicked=false
   for(let n=0;n<60;n++){
     clicked=await click(action==='select-target'?`document.querySelector('[data-houdini-target="${executor}"]')?.closest('[role="menuitem"]')`:`[...document.querySelectorAll('[role="menuitem"]')].find(b=>b.textContent.trim()==='取消此对话的绑定')`)
     if(clicked)break;await sleep(100)
   }
   assert(clicked,'An explicit available target/clear entry must be clickable')
   value=await until(row=>!row.menuOpen&&(action==='clear-target'?row.state==='unbound'&&row.targetState==='unbound':row.state==='ready'&&row.selectedTarget?.executor_id===executor))
   assert.equal(value.selection.cwd,cwd,'Choosing or clearing an operation target must preserve the native conversation cwd')
 }else if(action!=='snapshot'){
   await openMenu();const label={open:'打开 Houdini 工程…',new:'新建 Houdini 工程…',reopen:'打开关联工程'}[action];assert(label,'Known native project action required')
   let clicked=false
   for(let n=0;n<60;n++){clicked=await click(`[...document.querySelectorAll('[role="menuitem"]')].find(b=>b.textContent.trim()===${JSON.stringify(label)})`);if(clicked)break;await sleep(100)}
   assert(clicked,'The compact project menu must start the requested native action');await sleep(600);value.afterText=await evaluate('document.body.innerText')
 }
 await fs.writeFile(output+'.json',JSON.stringify(value));console.log('UI ready: '+action+' session='+value.selection?.sessionId+' state='+value.state);if(takeScreenshots&&action!=='snapshot'){await sleep(250);await fs.writeFile(output+'.png',Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'))}
}catch(error){console.error(error);try{await fs.writeFile(output+'-failure.json',JSON.stringify(await capture()));if(takeScreenshots)await fs.writeFile(output+'-failure.png',Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'))}catch(captureError){console.error('Failure diagnostic: '+captureError)}throw error}
finally{socket.close()}
