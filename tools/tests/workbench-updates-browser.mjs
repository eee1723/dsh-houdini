import fs from 'node:fs/promises'
import assert from 'node:assert/strict'
import path from 'node:path'

const [port,action,folder,workspace]=process.argv.slice(2)
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))
let page
for(let attempt=0;attempt<400;attempt++){
  try{const pages=await(await fetch('http://127.0.0.1:'+port+'/json')).json();page=pages.find(item=>item.type==='page'&&item.url.startsWith('http://127.0.0.1:'));if(page)break}catch{}
  await pause(100)
}
assert(page,'actual Qt/DSH page did not become available')
const socket=new WebSocket(page.webSocketDebuggerUrl),pending=new Map();let serial=0
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})})
socket.addEventListener('message',event=>{const value=JSON.parse(event.data);pending.get(value.id)?.(value)})
async function call(method,params={}){
  const id=++serial
  const response=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method))},10000);pending.set(id,value=>{clearTimeout(timer);pending.delete(id);resolve(value)});socket.send(JSON.stringify({id,method,params}))})
  assert(!response.error,JSON.stringify(response.error));return response.result
}
async function evaluate(expression){const value=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!value.exceptionDetails,JSON.stringify(value.exceptionDetails));return value.result.value}
async function snapshot(){return evaluate(`({selection:window.__dshHoudiniSelection?.(),update:!!document.querySelector('[data-houdini-update]'),version:document.querySelector('[data-houdini-update]')?.dataset.houdiniUpdateVersion,origin:performance.timeOrigin,marker:window.__updatesDocumentMarker,blocking:[...document.querySelectorAll('[role=dialog]')].some(e=>e.getClientRects().length),draft:[...document.querySelectorAll('[contenteditable=true]')].map(e=>e.textContent).join('|')})`)}
let createdChat=false
async function until(predicate){let value;for(let attempt=0;attempt<250;attempt++){
  await evaluate(`(()=>{const visible=e=>e.getClientRects().length;for(const b of document.querySelectorAll('button'))if(visible(b)&&(['稍后配置','以后再说'].includes(b.textContent.trim())||(document.body?.innerText.includes('预览版说明')&&b.textContent.trim()==='继续')))b.click();for(const d of document.querySelectorAll('[role="dialog"]'))if(visible(d)&&d.textContent.includes('添加 API Key'))d.querySelector('button[aria-label="关闭"]')?.click();return true})()`)
  value=await snapshot();if(predicate(value))return value
  if(action==='hidden'&&!value.selection?.sessionId&&!createdChat)createdChat=await evaluate(`(()=>{const e=[...document.querySelectorAll('button')].find(b=>b.getClientRects().length&&(b.getAttribute('aria-label')==='新会话'||b.textContent.trim().startsWith('新会话')));if(!e)return false;e.click();return true})()`)
  await pause(100)
}throw Error('update UI did not settle: '+JSON.stringify(value))}
try{
  let value=await until(row=>row.selection?.sessionId&&!row.blocking)
  assert.equal(value.selection.agentPreset,'houdini')
  assert.equal(path.resolve(value.selection.cwd).toLowerCase(),path.resolve(workspace).toLowerCase())
  if(action==='hidden'){
    assert.equal(value.update,false,'slow discovery must leave the normal header usable')
    await evaluate(`window.__updatesDocumentMarker='kept-during-version-management';[...document.querySelectorAll('[contenteditable=true]')].find(e=>e.getClientRects().length)?.focus()`)
    await call('Input.insertText',{text:'Unsent update-entry draft'})
    value=await until(row=>row.draft.includes('Unsent update-entry draft'))
    assert(value.draft.includes('Unsent update-entry draft'),'the actual composer must retain the authored draft')
    await fs.writeFile(path.join(folder,'baseline.json'),JSON.stringify(value))
  }else{
    const baseline=JSON.parse(await fs.readFile(path.join(folder,'baseline.json'),'utf8'))
    await evaluate(`document.dispatchEvent(new Event('visibilitychange'))`)
    if(action==='open'||action==='reopen'){
      value=await until(row=>row.update&&row.version==='99.0.0')
      if(action==='open'){
        await pause(250)
        await fs.writeFile(path.join(folder,'available.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'))
      }
      const point=await evaluate(`(()=>{const e=document.querySelector('[data-houdini-update]'),r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`)
      await call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point})
      await call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point})
      await pause(350)
    }else if(action==='offline')value=await until(row=>!row.update)
    else assert.equal(action,'preserved')
    value=await snapshot()
    assert.equal(value.origin,baseline.origin,'version management navigated the document')
    assert.equal(value.marker,baseline.marker)
    assert.equal(value.selection.sessionId,baseline.selection.sessionId)
    assert.equal(value.selection.cwd,baseline.selection.cwd)
    assert(value.draft.includes('Unsent update-entry draft'),'version management discarded the unsent draft')
  }
  await fs.writeFile(path.join(folder,action+'.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'))
  await fs.writeFile(path.join(folder,action+'.json'),JSON.stringify(value))
  console.log('PASS actual update entry: '+action+' session='+value.selection.sessionId)
}catch(error){
  await fs.writeFile(path.join(folder,action+'-failure.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'))
  throw error
}finally{socket.close()}
