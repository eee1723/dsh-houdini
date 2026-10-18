import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
const [port,sessionId,cwd,png,resultFile]=process.argv.slice(2)
const pages=await (await fetch('http://127.0.0.1:'+port+'/json')).json()
const page=pages.find(p=>p.type==='page'&&p.url.startsWith('http://127.0.0.1:'))
assert(page,'Actual Qt page must exist')
const socket=new WebSocket(page.webSocketDebuggerUrl)
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})})
let serial=0;const pending=new Map()
socket.addEventListener('message',event=>{const data=JSON.parse(event.data);pending.get(data.id)?.(data)})
async function call(method,params={}) {
  const id=++serial
  const response=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method))},10000)
    pending.set(id,data=>{pending.delete(id);clearTimeout(timer);resolve(data)})
    socket.send(JSON.stringify({id,method,params}))
  })
  assert(!response.error,JSON.stringify(response.error))
  return response.result
}
async function evaluate(expression) {
  const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true})
  assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails))
  return result.result.value
}
try {
  let selected
  for(let attempt=0;attempt<150;attempt++) {
    await evaluate(`(()=>{for(const b of document.querySelectorAll('button'))if(['稍后配置','以后再说'].includes(b.textContent.trim())||(document.body.innerText.includes('预览版说明')&&b.textContent.trim()==='继续'))b.click();return true})()`)
    selected=await evaluate('window.__dshHoudiniSelection?.()')
    if(selected?.sessionId===sessionId)break
    await new Promise(resolve=>setTimeout(resolve,200))
  }
  assert.equal(selected.sessionId,sessionId)
  assert.equal(selected.agentPreset,'houdini')
  assert.equal(path.resolve(selected.cwd).toLowerCase(),path.resolve(cwd).toLowerCase())
  const rpc=await evaluate(`fetch('/api/session/list',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:'release-standalone',method:'session/list',payload:{args:{_request:{}}}})}).then(async r=>({status:r.status,value:await r.json()}))`)
  assert.equal(rpc.status,200)
  assert.equal(rpc.value.result.ok,true)
  assert(rpc.value.result.value.items.some(item=>item.sessionId===sessionId))
  const initial=await evaluate(`(()=>{const p=document.querySelector('[data-houdini-window-pin]');if(!p||p.disabled)throw Error('Window pin unavailable');window.__releaseDocumentMarker='retained';return{pinned:p.getAttribute('aria-pressed')==='true',origin:performance.timeOrigin,width:innerWidth,height:innerHeight}})()`)
  for(const pinned of [!initial.pinned,initial.pinned]) {
    await evaluate(`document.querySelector('[data-houdini-window-pin]').click()`)
    let settled=false
    for(let attempt=0;attempt<40;attempt++) {
      settled=await evaluate(`(()=>{const p=document.querySelector('[data-houdini-window-pin]');return p&&!p.disabled&&p.getAttribute('aria-pressed')===${JSON.stringify(String(pinned))}})()`)
      if(settled)break
      await new Promise(resolve=>setTimeout(resolve,100))
    }
    assert(settled,'Native window pin must settle')
    assert.deepEqual(await evaluate(`({marker:window.__releaseDocumentMarker,origin:performance.timeOrigin,width:innerWidth,height:innerHeight})`),{marker:'retained',origin:initial.origin,width:initial.width,height:initial.height})
  }
  assert.equal(await evaluate(`new URL(location.href).searchParams.has('token')`),false)
  const shot=await call('Page.captureScreenshot',{format:'png'})
  fs.writeFileSync(png,Buffer.from(shot.data,'base64'))
  fs.writeFileSync(resultFile,JSON.stringify({selected,webRpc:true,pinRestored:true,sameDocument:true,screenshot:png}))
  console.log('Actual standalone Qt selection, authenticated RPC, pin/restore and document continuity passed')
} finally {socket.close()}
