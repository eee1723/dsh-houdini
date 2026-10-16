import fs from 'node:fs/promises'
import assert from 'node:assert/strict'

const [port,action,output,expectedStatus,expectedSession]=process.argv.slice(2)
const pages=await (await fetch('http://127.0.0.1:'+port+'/json')).json()
const page=pages.find(item=>item.type==='page'&&item.url.startsWith('http://127.0.0.1:'))
assert(page)
const socket=new WebSocket(page.webSocketDebuggerUrl),pending=new Map()
let serial=0
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})})
socket.addEventListener('message',event=>{const value=JSON.parse(event.data),callback=pending.get(value.id);if(callback){pending.delete(value.id);callback(value)}})
async function call(method,params={}) {
  const id=++serial
  const result=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('Browser test timed out')),10000)
    pending.set(id,value=>{clearTimeout(timer);resolve(value)})
    socket.send(JSON.stringify({id,method,params}))
  })
  if(result.error)throw Error(JSON.stringify(result.error))
  return result.result
}
async function evaluate(expression) {
  const result=await call('Runtime.evaluate',{expression,returnByValue:true})
  if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
try {
  let value
  for(let attempt=0;attempt<150;attempt++) {
    await evaluate(`(()=>{for(const button of document.querySelectorAll('button')){if(['稍后配置','以后再说'].includes(button.textContent.trim())||(document.body.innerText.includes('预览版说明')&&button.textContent.trim()==='继续'))button.click()}return true})()`)
    value=await evaluate(`(()=>{const label=document.querySelector('[data-houdini-project-label]');return {selection:window.__dshHoudiniSelection?.(),label:label?.textContent,status:label?.dataset.houdiniPresence,entry:!!document.querySelector('[aria-label="打开或新建 Houdini 工程"]'),text:document.body?.innerText??''}})()`)
    if(action==='state'?(value.status===expectedStatus&&(!expectedSession||value.selection?.sessionId===expectedSession)):(value.label||value.entry))break
    await new Promise(resolve=>setTimeout(resolve,100))
  }
  if(action==='state') {
    assert.equal(value.status,expectedStatus)
    if(expectedSession)assert.equal(value.selection?.sessionId,expectedSession)
  } else if(action==='new-chat') {
    const previousSession=value.selection?.sessionId
    const wasBound=!!value.label
    assert(await evaluate(`(()=>{const button=Array.from(document.querySelectorAll('button')).find(button=>button.getAttribute('aria-label')==='新会话'||button.textContent.trim().startsWith('新会话'));if(!button)return false;button.click();return true})()`))
    for(let attempt=0;attempt<100;attempt++) {
      value.selection=await evaluate('window.__dshHoudiniSelection?.()')
      if(value.selection?.sessionId&&(!wasBound||value.selection.sessionId!==previousSession))break
      await new Promise(resolve=>setTimeout(resolve,100))
    }
    assert(value.selection?.sessionId)
    if(wasBound)assert.notEqual(value.selection.sessionId,previousSession)
  } else if(action!=='snapshot') {
    await evaluate(`(document.querySelector('[data-houdini-project-label]')||document.querySelector('[aria-label="打开或新建 Houdini 工程"]')).click()`)
    const label={open:'打开 Houdini 工程…',new:'新建 Houdini 工程…',reopen:'打开关联工程'}[action]
    let clicked=false
    for(let attempt=0;attempt<30;attempt++) {
      clicked=await evaluate(`(()=>{const button=Array.from(document.querySelectorAll('[role="menuitem"]')).find(button=>button.textContent.trim()===${JSON.stringify(label)});if(!button)return false;button.click();return true})()`)
      if(clicked)break
      await new Promise(resolve=>setTimeout(resolve,100))
    }
    assert(clicked,'the existing compact project menu must start the requested action')
    await new Promise(resolve=>setTimeout(resolve,700))
    value.afterText=await evaluate('document.body.innerText')
  }
  await fs.writeFile(output+'.json',JSON.stringify(value))
  await fs.writeFile(output+'.png',Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'))
}finally {socket.close()}
