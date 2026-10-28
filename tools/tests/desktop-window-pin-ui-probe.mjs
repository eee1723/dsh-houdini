// Real buttons/mode selection against one owned Native renderer. Main's
// read-only Win32 oracle observes OS state independently of plugin RPC replies.
import fs from 'node:fs/promises'
import path from 'node:path'
import assert from 'node:assert/strict'
import {NATIVE_SELECTION} from './browser-selection.mjs'
const config=JSON.parse(await fs.readFile(process.argv[2],'utf8'))
const report={nativePinButtonTested:false,pinRpc:[],screenshots:[]}
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function connect(url){
 const socket=new WebSocket(url),pending=new Map();let id=0
 await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})})
 const events=new Set();socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.id)pending.get(value.id)?.(value);else for(const fn of events)fn(value)})
 return{events,close:()=>socket.close(),async call(method,params={},timeout=15000){const request=++id;const reply=new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(request);reject(Error('CDP timeout '+method))},timeout);pending.set(request,value=>{clearTimeout(timer);pending.delete(request);value.error?reject(Error(JSON.stringify(value.error))):resolve(value.result)})});socket.send(JSON.stringify({id:request,method,params}));return reply}}
}
let page,main,evaluate
async function until(read,label,timeout=45000){const end=Date.now()+timeout;do{const value=typeof read==='string'?await evaluate('(()=>{const value=('+read+');return value instanceof Node?true:value})()'):await read();if(value)return value;await sleep(100)}while(Date.now()<end);throw Error('Not reached: '+label)}
async function click(expression,label){const point=await until(`(()=>{const e=(${expression});if(!e||e.disabled)return null;const folded=e.closest('details:not([open])');if(folded&&folded.firstElementChild!==e)return null;e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();return r.width&&r.height?{x:r.x+r.width/2,y:r.y+r.height/2}:null})()`,label);await page.call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});await page.call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});await sleep(150)}
async function rpc(method,args={}){return evaluate(`(async()=>{const r=await fetch('/api/'+${JSON.stringify(method)},{method:'POST',headers:{'content-type':'application/json'},credentials:'include',body:JSON.stringify({type:'client-request',rpcId:'pin-ui-'+crypto.randomUUID(),method:${JSON.stringify(method)},payload:{args:${JSON.stringify(args)}}})});const b=await r.json();if(!b.result?.ok)throw Error(JSON.stringify(b.result?.error||b));return b.result.value})()`)}
async function oracle(action='read'){
 const body=`(()=>{if(process.pid!==${config.mainPid})throw Error('Foreign Main');const create=process.getBuiltinModule('module').createRequire,r=create(${JSON.stringify(config.pluginPackage)}),e=create(process.resourcesPath+'/app.asar/package.json')('electron'),windows=e.BrowserWindow.getAllWindows().filter(w=>w.webContents.getURL().startsWith('dsh-app://app/'));if(windows.length!==1)throw Error('No unique own Native app window');const w=windows[0];${action==='show'?"const area=e.screen.getPrimaryDisplay().workArea;w.setBounds({x:Math.max(area.x,area.x+area.width-1312),y:area.y+20,width:1296,height:828});w.show();w.focus();":''}${action==='baseline-true'?'w.setAlwaysOnTop(true);':''}${action==='baseline-false'?'w.setAlwaysOnTop(false);':''}const k=r('koffi'),u=k.load('user32.dll'),get=u.func('__stdcall','GetWindowLongW','int32',['void *','int']),h=w.getNativeWindowHandle().readBigUInt64LE();return{pid:process.pid,hwnd:h.toString(),pinned:!!(get(h,-20)&8),bounds:w.getBounds(),visible:w.isVisible()}})()`
 const value=await main.call('Runtime.evaluate',{expression:body,returnByValue:true});assert(!value.exceptionDetails,JSON.stringify(value.exceptionDetails));return value.result.value
}
async function state(expected,label){return until(async()=>{const value=await oracle();return value.pinned===expected?value:null},label)}
async function pin(expected){await until('document.querySelectorAll("[data-houdini-window-pin]").length===1&&!document.querySelector("[data-houdini-window-pin]").disabled','one actionable real pin button');await click('document.querySelector("[data-houdini-window-pin]")','Native pin button');await state(expected,'actual OS topmost='+expected);await until(`document.querySelector('[data-houdini-window-pin]')?.getAttribute('aria-pressed')===${JSON.stringify(String(expected))}`,'UI pin truth')}
async function shot(name){try{const value=await page.call('Page.captureScreenshot',{format:'png'},5000);const file=path.join(path.dirname(config.output),name+'.png');await fs.writeFile(file,Buffer.from(value.data,'base64'));report.screenshots.push(file)}catch(error){report.screenshotError=String(error)}}
async function pinAppearance(expected){
 await until(`(()=>{const e=document.querySelector('[data-houdini-window-pin]');return e&&!e.disabled&&e.getAttribute('aria-pressed')===${JSON.stringify(String(expected))}})()`,'settled pin appearance')
 await page.call('Input.dispatchMouseEvent',{type:'mouseMoved',x:8,y:8})
 const value=await evaluate(`(()=>{const e=document.querySelector('[data-houdini-window-pin]'),s=getComputedStyle(e),r=e.getBoundingClientRect();return {background:s.backgroundColor,color:s.color,width:r.width,height:r.height,fill:getComputedStyle(e.querySelector('path')).fill,clip:{x:Math.max(0,r.x-220),y:Math.max(0,r.y-35),width:Math.min(440,innerWidth-Math.max(0,r.x-220)),height:100,scale:2}}})()`)
 assert.equal(value.background,'rgba(0, 0, 0, 0)','resting pin must not expose a native grey button or selected background')
 assert.equal(value.width,28);assert.equal(value.height,28)
 assert.equal(value.fill,expected?value.color:'none','confirmed topmost state uses filled/outline icon')
 const image=await page.call('Page.captureScreenshot',{format:'png',clip:value.clip})
 const name='pin-'+(expected?'on':'off');await fs.writeFile(path.join(path.dirname(config.output),name+'-detail.png'),Buffer.from(image.data,'base64'))
 delete value.clip;return value
}
async function selectSession(id){const selector='[data-row-key="session:'+id+'"]';for(let n=0;n<12&&!await evaluate('!!document.querySelector('+JSON.stringify(selector)+')');n++){const collapsed=await evaluate('document.querySelector(\'[data-row-key^="workspace:"][aria-expanded="false"]\')?.getAttribute("data-row-key")');if(collapsed)await click('document.querySelector('+JSON.stringify('[data-row-key="'+collapsed+'"]')+')','Native workspace expansion');await sleep(150)}await click('document.querySelector('+JSON.stringify(selector)+')','Native conversation');await until(`(${NATIVE_SELECTION})?.sessionId===${JSON.stringify(id)}`,'selected native conversation '+id)}
async function journal(){try{return JSON.parse(await fs.readFile(config.recordPath,'utf8'))}catch(error){if(error.code==='ENOENT')return null;throw error}}
async function checkpoint(name,value){report[name]=value;await fs.writeFile(config.output,JSON.stringify(report,null,2))}
try {
 main=await connect(config.mainInspector)
 const targets=await(await fetch('http://127.0.0.1:'+config.port+'/json/list')).json(),target=targets.find(row=>row.type==='page'&&row.url.startsWith('dsh-app://app'))
 assert(target,'Owned Native page missing');page=await connect(target.webSocketDebuggerUrl)
 evaluate=async expression=>{const result=await page.call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value}
 await page.call('Runtime.enable');await page.call('Network.enable',{maxPostDataSize:1_000_000})
 page.events.add(event=>{
  let text;if(event.method==='Network.requestWillBeSent')text=event.params.request.postData;
  else if(event.method==='Network.webSocketFrameSent'){const frame=event.params.response;text=frame.opcode===2?Buffer.from(frame.payloadData,'base64').toString('utf8'):frame.payloadData;}
  if(!text)return;
  try{const scan=value=>{if(!value||typeof value!=='object')return;if(value.method==='houdiniFrontend/windowPin'){const input=value.payload?.args?.input??value.args?.input;if(input)report.pinRpc.push(input);return;}Object.values(value).forEach(scan)};scan(JSON.parse(text))}catch{}
 })
 await until(NATIVE_SELECTION,'initial native selection');await oracle('show');await until(NATIVE_SELECTION,'native selection after final fixture window layout')
 if(config.phase==='reopen'){
  await selectSession(config.standardSessionId)
  await until('!document.querySelector("[data-houdini-window-pin],[data-houdini-project-label]")','uninstalled controls absent after real restart')
  const presets=await rpc('agentPresets/list');assert(presets.presets.some(row=>row.id==='standard'&&row.isDefault));assert(!presets.presets.some(row=>row.id==='houdini'))
  const remains=(await rpc('pluginManager/listBundles')).find(row=>row.name==='dsh-houdini');assert(!remains||!remains.installed&&!remains.enabled)
  const projection=await rpc('session/projections',{request:{sessionId:config.standardSessionId}});assert.equal(projection.values.agentPreset,'standard')
  assert.equal((await oracle()).pinned,false)
  await click(`document.querySelector('[data-composer-input][contenteditable=true]')`,'normal Standard composer after uninstall')
  await page.call('Input.insertText',{text:'Owned Standard draft after uninstall'})
  assert(await evaluate('document.querySelector("[data-composer-input]").textContent.includes("Owned Standard draft after uninstall")'))
  report.ok=true;report.reopenedSameProfileWithoutPlugin={standardSelected:true,standardDraftEditable:true,nativeDefaultPreserved:true,pinAbsent:true,osBaseline:false};await shot('reopened-standard-after-uninstall')
 }else{
 const initial=await evaluate(NATIVE_SELECTION);assert.equal(initial.agentPreset,'standard');assert.equal(await evaluate('document.querySelectorAll("[data-houdini-window-pin]").length'),0)
 const baseline=(await oracle()).pinned;assert.equal(baseline,false,'fresh test Native window baseline must be false')
 await click(`document.querySelector('button[title="选择新任务使用的 Agent 预设"],button[title="Choose the agent preset for your new task"]')||document.querySelector('[data-slot="conversation.hero.agentPreset"] button[aria-haspopup=menu]')||[...document.querySelectorAll('button[aria-haspopup=menu]')].find(e=>/标准|Standard/.test(e.textContent))`,'Native mode picker')
 await click(`[...document.querySelectorAll('[role=menuitem]')].find(e=>/Houdini/.test(e.textContent))`,'Native Houdini mode')
 await until('document.querySelector("[data-houdini-project-label]")&&document.querySelector("[data-houdini-window-pin]")','Houdini blank Pin')
 assert.equal(await evaluate('document.querySelectorAll("[data-houdini-window-pin]").length'),1)
 const offAppearance=await pinAppearance(false);await pin(true);const onAppearance=await pinAppearance(true)
 assert.equal(offAppearance.color,onAppearance.color,'pin toggling must not flash a different icon colour')
 await checkpoint('pinAppearance',{off:offAppearance,on:onAppearance});report.nativePinButtonTested=true
 await click('document.querySelector("[data-houdini-project-label]")','Houdini project menu')
 await until('document.querySelector(".dsh-houdini-target-heading")?.textContent==="Houdini 工程"','plain project terminology')
 await shot('project-menu');await click('document.querySelector("[data-houdini-project-label]")','close project menu')
 const blankScope=await journal();assert(blankScope);await checkpoint('blankPin',{sessionId:initial.sessionId,owner:blankScope.owner,os:await oracle()});await shot('pin-blank')
 await rpc('session/selectModel',{request:{sessionId:initial.sessionId,provider:'owned-pin-chat',model:'idle-fixture'}})
 const beforeTransition=report.pinRpc.length
 await click(`document.querySelector('[data-composer-input][contenteditable=true]')`,'Native composer');await page.call('Input.insertText',{text:'请只回复 Owned pin fixture ready，不调用工具。'})
 await page.call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});await page.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13})
 await until('document.querySelector(\'[data-conversation-header-leading]\')?.closest(\'header\')?.querySelector(\'[data-houdini-window-pin]\')','nonblank header pin')
 await until(async()=>{const rows=await rpc('session/list',{_request:{}});return rows.items.find(row=>row.sessionId===initial.sessionId)?.running===false},'owned local Agent idle')
 assert.equal((await journal())?.owner,blankScope.owner);assert.equal(report.pinRpc.slice(beforeTransition).some(row=>row?.action==='release'||row?.action==='reset'),false)
 assert(await evaluate('!!document.querySelector(\'[data-conversation-header-corner] button\')'),'Native single corner remains owned by its original control')
 await state(true,'pin survives blank-to-history');await checkpoint('blankToHistory',{sameOwner:true,os:await oracle()});await shot('pin-header')
 const ownSummary=(await rpc('session/list',{_request:{}})).items.find(row=>row.sessionId===initial.sessionId);assert(ownSummary?.cwd)
 const location=await rpc('workspace/create',{request:{path:ownSummary.cwd}})
 const second=await rpc('session/create',{request:{workspaceId:location.workspace.workspaceId,agentPreset:'houdini'}})
 const standard=await rpc('session/create',{request:{workspaceId:location.workspace.workspaceId,agentPreset:'standard'}})
 const secondId=second.sessionId??second.id,standardId=standard.sessionId??standard.id;assert(secondId&&standardId,JSON.stringify([second,standard]))
 // Native sidebar intentionally omits abandoned empty sessions. Prepare real
 // owned histories through the public API and the same loopback-only model.
 for(const id of [secondId,standardId]){
  await rpc('session/selectModel',{request:{sessionId:id,provider:'owned-pin-chat',model:'idle-fixture'}})
  const admitted=await rpc('session/prompt',{request:{requestId:crypto.randomUUID(),sessionId:id,mode:'queue',content:[{type:'text',text:'Owned Pin lifecycle fixture. Reply only ready; use no tools.'}]}})
  await until(async()=>{const rows=await rpc('session/list',{_request:{}});return rows.items.find(row=>row.sessionId===id)?.running===false&&rows.items.find(row=>row.sessionId===id)?.blank===false},'owned history prepared '+id)
 }

 report.sessions={first:initial.sessionId,second:secondId,standard:standardId};
 const switchAt=report.pinRpc.length;await selectSession(secondId);await until('document.querySelector("[data-houdini-window-pin]")','second H Pin');await state(true,'H-to-H pin remains')
 assert.equal((await journal())?.owner,blankScope.owner);assert(!report.pinRpc.slice(switchAt).some(row=>row?.action==='release'||row?.action==='reset'))
 await checkpoint('houdiniSessionSwitch',{sameOwner:true})
 await selectSession(standardId);await until('!document.querySelector("[data-houdini-window-pin]")','no Standard Pin');await state(false,'Standard baseline restored');assert.equal(await journal(),null);await shot('standard-restored')
 await selectSession(initial.sessionId);await until('document.querySelector("[data-houdini-window-pin]")','H Pin returns');await state(true,'H preference restored');await checkpoint('modePreference',{standardBaselineRestored:true,houdiniPreferenceRestored:true})
 // New page has no in-memory preference; global reset must still reconcile
 // the previous page's live backend owner before acquiring a new scope.
 await page.call('Page.reload');await until(`(${NATIVE_SELECTION})?.sessionId===${JSON.stringify(initial.sessionId)}&&!!document.querySelector('[data-houdini-window-pin]')`,'reloaded native H session');await state(false,'renderer reload restores old baseline');await pin(true)
 await checkpoint('rendererReload',{oldBaselineRestored:true,newScopeActionable:true})
 await selectSession(standardId);await state(false,'baseline before external pre-pin');await oracle('baseline-true')
 await selectSession(initial.sessionId);await until('document.querySelector("[data-houdini-window-pin]")?.getAttribute("aria-pressed")==="true"','pre-pinned H state');await pin(false)
 assert.equal((await journal())?.baseline,true);await selectSession(standardId);await state(true,'pre-existing true baseline restored');await oracle('baseline-false')
 await checkpoint('originalTopmostTrue',{restored:true});await selectSession(initial.sessionId);await pin(true)
 // Public native manager APIs unload the real server/client while its Pin
 // scope is still active; no navigation-induced release can mask disposal.
 const disabled=await rpc('pluginManager/setBundleEnabled',{name:'dsh-houdini',enabled:false});await checkpoint('disableResult',{application:disabled.application,error:disabled.error});assert.equal(disabled.application,'applied',JSON.stringify(disabled));await until('!document.querySelector("[data-houdini-window-pin]")','disabled Pin removed');await state(false,'plugin disable releases OS baseline');assert.equal(await journal(),null)
 const enabled=await rpc('pluginManager/setBundleEnabled',{name:'dsh-houdini',enabled:true});assert.equal(enabled.application,'applied',JSON.stringify(enabled));await until('document.querySelector("[data-houdini-window-pin]")&&!document.querySelector("[data-houdini-window-pin]").disabled','re-enabled Pin')
 await pin(true);const removed=await rpc('pluginManager/removeBundle',{name:'dsh-houdini'});await checkpoint('uninstallResult',{application:removed.application,restartReason:removed.restartReason,exitCode:removed.packageResult?.exitCode,error:removed.error});assert(['applied','restart-required'].includes(removed.application),JSON.stringify(removed));assert.equal(removed.packageResult?.exitCode,0);await until('!document.querySelector("[data-houdini-window-pin]")','uninstalled Pin removed');await state(false,'plugin uninstall restores baseline');assert.equal(await journal(),null);const remains=(await rpc('pluginManager/listBundles')).find(row=>row.name==='dsh-houdini');assert(!remains||!remains.installed&&!remains.enabled,'Native manager must actually remove the dependency and selection')
 await checkpoint('pluginLifecycle',{nativeManagerDisable:true,nativeManagerReEnable:true,nativeManagerDependencyRemoved:true,baselineRestored:true,runtimeRestartRequired:removed.application==='restart-required'})
 report.nativePinButtonTested=true;report.ok=true;await shot('uninstalled-baseline')
 }
}catch(error){report.error=String(error.stack||error);process.exitCode=1;if(evaluate)try{report.failure={pinElements:await evaluate('[...document.querySelectorAll(\'[data-houdini-window-pin]\')].map(e=>({label:e.getAttribute(\'aria-label\'),disabled:e.disabled,inHeader:!!e.closest(\'header\'),pressed:e.getAttribute(\'aria-pressed\')}))'),text:await evaluate('document.body.innerText'),selection:await evaluate(NATIVE_SELECTION),os:await oracle()};await shot('pin-ui-failure')}catch{}}
finally{await fs.writeFile(config.output,JSON.stringify(report,null,2));page?.close();main?.close()}
if(report.ok)console.log('PASS actual Native Pin UI: blank/header, H-to-H, Standard restore/preference, renderer reset, original topmost baseline, disable and uninstall')
