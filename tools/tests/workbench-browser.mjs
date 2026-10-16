import fs from 'node:fs/promises'
import assert from 'node:assert/strict'
import path from 'node:path'

const [port,sessionId,output,expectedDirectory,expectedHip,action]=process.argv.slice(2)
const pages=await (await fetch('http://127.0.0.1:'+port+'/json')).json()
const page=pages.find(item=>item.type==='page'&&item.url.startsWith('http://127.0.0.1:'))
assert(page,'test desktop page must exist')
const socket=new WebSocket(page.webSocketDebuggerUrl)
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})})
const pending=new Map();let serial=0
socket.addEventListener('message',event=>{const value=JSON.parse(event.data);const callback=pending.get(value.id);if(callback){pending.delete(value.id);callback(value)}})
async function call(method,params={}) {
  const id=++serial
  const result=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP test timeout'))},10000)
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
  let selection
  for(let attempt=0;attempt<120;attempt++) {
    await evaluate(`(()=>{for(const button of document.querySelectorAll('button')){if(['稍后配置','以后再说'].includes(button.textContent.trim())||(document.body.innerText.includes('预览版说明')&&button.textContent.trim()==='继续'))button.click()}return true})()`)
    selection=await evaluate('window.__dshHoudiniSelection?.()')
    if(selection?.sessionId===sessionId)break
    await new Promise(resolve=>setTimeout(resolve,100))
  }
  assert.equal(selection?.sessionId,sessionId,'actual selected DSH task must match menu activation')
  assert.equal(selection.agentPreset,'houdini')
  if(expectedDirectory)assert.equal(path.resolve(selection.cwd).toLowerCase(),path.resolve(expectedDirectory).toLowerCase(),
    'actual browser workspace must follow the selected project')
  assert(await evaluate(`!document.querySelector('[data-houdini-connection]')&&!Array.from(document.querySelectorAll('button')).some(button=>['检查连接','Houdini 执行端'].includes(button.textContent.trim()))`))
  if(action==='refresh-title') {
    await evaluate(`document.querySelector('[data-row-key="session:${sessionId}"] button').click()`)
    let ready=false
    for(let attempt=0;attempt<40;attempt++) {
      ready=await evaluate(`(()=>{const item=Array.from(document.querySelectorAll('[role="menuitem"]')).find(item=>item.textContent.includes('按对话内容重新命名'));if(!item)return false;item.click();return true})()`)
      if(ready)break
      await new Promise(resolve=>setTimeout(resolve,100))
    }
    assert(ready,'native conversation menu must expose explicit title regeneration')
    let changed=false
    for(let attempt=0;attempt<150;attempt++) {
      changed=await evaluate(`!document.querySelector('[data-row-key="session:${sessionId}"]').textContent.includes('旧工程标题.hip')`)
      if(changed)break
      await new Promise(resolve=>setTimeout(resolve,100))
    }
    assert(changed,'explicit menu action must update the real DSH conversation title')
  }
  if(expectedHip) {
    let label
    for(let attempt=0;attempt<80;attempt++) {
      label=await evaluate(`document.querySelector('[data-houdini-project-label]')?.textContent`)
      if(label===path.basename(expectedHip))break
      await new Promise(resolve=>setTimeout(resolve,100))
    }
    assert.equal(label,path.basename(expectedHip),'real DSH projection must render the selected project independently of the conversation title')
    const bounds=await evaluate(`(()=>{const rectangle=document.querySelector('[data-houdini-project-label]').getBoundingClientRect();return {x:rectangle.x+rectangle.width/2,y:rectangle.y+rectangle.height/2}})()`)
    await call('Input.dispatchMouseEvent',{type:'mouseMoved',...bounds})
    let detail
    const containsPath=value=>typeof value==='string'&&value.replace(/\\/g,'/').includes(expectedHip.replace(/\\/g,'/'))
    for(let attempt=0;attempt<30;attempt++) {
      detail=await evaluate(`document.querySelector('[role="tooltip"]')?.textContent`)
      if(containsPath(detail))break
      await new Promise(resolve=>setTimeout(resolve,100))
    }
    assert(containsPath(detail),'native hover detail must expose the exact recorded HIP path')
  }
  const screenshot=await call('Page.captureScreenshot',{format:'png'})
  await fs.writeFile(output,Buffer.from(screenshot.data,'base64'))
  console.log('PASS actual Qt/DSH selected task and no connection/picker panel')
}catch(error) {
  const screenshot=await call('Page.captureScreenshot',{format:'png'})
  await fs.writeFile(output,Buffer.from(screenshot.data,'base64'))
  throw error
}finally {socket.close()}
