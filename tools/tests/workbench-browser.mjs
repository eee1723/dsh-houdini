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
    await evaluate(`(()=>{for(const button of document.querySelectorAll('button')){if(['稍后配置','以后再说'].includes(button.textContent.trim())||(document.body.innerText.includes('预览版说明')&&button.textContent.trim()==='继续'))button.click()}for(const dialog of document.querySelectorAll('[role=dialog]'))if(dialog.getClientRects().length&&dialog.textContent.includes('添加 API Key'))dialog.querySelector('button[aria-label="关闭"]')?.click();return true})()`)
    selection=await evaluate('window.__dshHoudiniSelection?.()')
    if(selection?.sessionId===sessionId&&!await evaluate(`[...document.querySelectorAll('[role=dialog]')].some(e=>e.getClientRects().length)`))break
    await new Promise(resolve=>setTimeout(resolve,100))
  }
  assert.equal(selection?.sessionId,sessionId,'actual selected DSH task must match menu activation')
  assert.equal(selection.agentPreset,'houdini')
  if(action==='maintenance-draft') {
    await evaluate(`(()=>{const input=[...document.querySelectorAll('[contenteditable=true]')].find(e=>e.getClientRects().length);if(!input)throw Error('composer unavailable');input.focus()})()`)
    await call('Input.insertText',{text:'Unsent maintenance draft 中文'})
  }
  if(action==='maintenance-draft'||action==='maintenance-restored') {
    let draft=''
    for(let attempt=0;attempt<80;attempt++) {
      draft=await evaluate(`[...document.querySelectorAll('[contenteditable=true]')].map(e=>e.textContent).join('|')`)
      if(draft.includes('Unsent maintenance draft 中文'))break
      await new Promise(resolve=>setTimeout(resolve,100))
    }
    assert(draft.includes('Unsent maintenance draft 中文'),'native DSH draft did not survive ordinary desktop restart')
  }
  if(expectedDirectory)assert.equal(path.resolve(selection.cwd).toLowerCase(),path.resolve(expectedDirectory).toLowerCase(),
    'actual browser workspace must follow the selected project')
  assert(await evaluate(`!document.querySelector('[data-houdini-connection]')&&!Array.from(document.querySelectorAll('button')).some(button=>['检查连接','Houdini 执行端'].includes(button.textContent.trim()))`))
  // Exercise the visible header button through real DSH -> desktop -> Win32.
  for(let attempt=0;attempt<60;attempt++) {
    if(await evaluate(`(()=>{const pin=document.querySelector('[data-houdini-window-pin]');return pin&&!pin.disabled&&pin.hasAttribute('aria-pressed')})()`))break
    await new Promise(resolve=>setTimeout(resolve,100))
  }
  const pinBefore=await evaluate(`(()=>{const pin=document.querySelector('[data-houdini-window-pin]');
    if(!pin||pin.disabled)throw Error('header pin unavailable');
    const r=pin.getBoundingClientRect();if(r.width>32||r.height>32)throw Error('pin is not compact');
    if(!pin.closest('[data-conversation-header-corner]'))throw Error('pin must reuse the existing header');
    window.__pinDocumentMarker='same-document';return {pinned:pin.getAttribute('aria-pressed')==='true',origin:performance.timeOrigin,width:innerWidth,height:innerHeight}})()`)
  for(const enabled of [!pinBefore.pinned,pinBefore.pinned]) {
    await evaluate(`document.querySelector('[data-houdini-window-pin]').click()`)
    let settled=false
    for(let attempt=0;attempt<60;attempt++) {
      settled=await evaluate(`(()=>{const pin=document.querySelector('[data-houdini-window-pin]');return pin&&!pin.disabled&&pin.getAttribute('aria-pressed')===${JSON.stringify(String(enabled))}})()`)
      if(settled)break
      await new Promise(resolve=>setTimeout(resolve,100))
    }
    assert(settled,'the header must show the confirmed native pin state')
    assert.deepEqual(await evaluate(`({marker:window.__pinDocumentMarker,origin:performance.timeOrigin,width:innerWidth,height:innerHeight})`),
      {marker:'same-document',origin:pinBefore.origin,width:pinBefore.width,height:pinBefore.height},'pin must not reload or resize the document')
  }
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
      label=await evaluate(`document.querySelector('[data-houdini-project-name]')?.textContent`)
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
