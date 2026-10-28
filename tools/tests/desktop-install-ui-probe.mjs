// Real consumer of an explicitly owned Native Desktop renderer/main inspector.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import {NATIVE_SELECTION} from './browser-selection.mjs'

const config=JSON.parse(await fs.readFile(process.argv[2],'utf8'))
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
const report={nativeElectronWindowTested:false,cliPluginInstallUsed:false,screenshots:[],uiMethods:{},secretTransport:0,secretReturned:false}
let cdp,main,evaluate
async function connect(url){
 const ws=new WebSocket(url),pending=new Map();let serial=0
 await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true})})
 const listeners=new Set()
 ws.addEventListener('message',event=>{const row=JSON.parse(event.data);if(row.id)pending.get(row.id)?.(row);else for(const fn of listeners)fn(row)})
 return {on:fn=>listeners.add(fn),close:()=>ws.close(),async call(method,params={},timeout=20000){
  const id=++serial,answer=new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method))},timeout)
   pending.set(id,row=>{clearTimeout(timer);pending.delete(id);row.error?reject(Error(JSON.stringify(row.error))):resolve(row.result)})})
  ws.send(JSON.stringify({id,method,params}));return answer
 }}
}
async function until(read,label,timeout=config.timeoutMs){
 const end=Date.now()+timeout
 while(Date.now()<end){const result=typeof read==='string'?await evaluate(`(()=>{const value=(${read});return value instanceof Node?true:value})()`):await read();if(result)return result;await sleep(150)}
 throw Error('Not reached: '+label)
}
async function click(expression,label){
 const point=await until(`(()=>{const e=(${expression});if(!e||e.disabled)return null;e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return r.width&&r.height?{x:r.x+r.width/2,y:r.y+r.height/2}:null})()`,label)
 await cdp.call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point})
 await cdp.call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});await sleep(200)
}
const button=(pattern,scope='document')=>`[...${scope}.querySelectorAll('button')].find(e=>${pattern}.test(e.textContent.trim())&&e.getBoundingClientRect().width)`
async function key(key,code,vk,modifiers=0){
 await cdp.call('Input.dispatchKeyEvent',{type:'keyDown',key,code,windowsVirtualKeyCode:vk,modifiers})
 await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode:vk,modifiers})
}
async function primaryColor(selector){
 const value=await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});const s=getComputedStyle(e);const luminance=color=>{const rgb=color.match(/[0-9.]+/g).slice(0,3).map(Number).map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722};const a=luminance(s.color),b=luminance(s.backgroundColor);return{color:s.color,background:s.backgroundColor,contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)}})()`)
 assert(value.contrast>=4.5,'Native primary button is unreadable: '+JSON.stringify(value));return value
}
async function shot(name){
 try{await cdp.call('Page.bringToFront',{},5000);const image=await cdp.call('Page.captureScreenshot',{format:'png'},5000)
  const file=path.join(path.dirname(config.output),name+'.png');await fs.writeFile(file,Buffer.from(image.data,'base64'));report.screenshots.push(file)
 }catch(error){report.screenshotError=String(error)}
}
async function rpc(method,args={}){
 return evaluate(`(async()=>{const r=await fetch('/api/'+${JSON.stringify(method)},{method:'POST',headers:{'content-type':'application/json'},credentials:'include',body:JSON.stringify({type:'client-request',rpcId:'fixture-'+crypto.randomUUID(),method:${JSON.stringify(method)},payload:{args:${JSON.stringify(args)}}})});const b=await r.json();if(!b.result?.ok)throw Error(JSON.stringify(b.result?.error||b));return b.result.value})()`)
}
async function bundle(){return (await rpc('pluginManager/listBundles')).find(row=>row.name==='dsh-houdini')}
async function nativeHistory(sessionId){
 const projection=await rpc('session/projections',{request:{sessionId}})
 assert(projection&&Number.isSafeInteger(projection.asOfSeq),'Native current projection must supply its exact event cut')
 const history=await rpc('session/page',{request:{address:{kind:'session',sessionId},throughSeq:projection.asOfSeq,maxMessages:100}})
 const failed=history.records.find(row=>row.event.type==='tool/result'&&row.event.data.message?.isError||row.event.type==='tool/ptc-dispatch'&&row.event.data.isError)
 if(failed)throw Error('Actual Native tool failed: '+JSON.stringify(failed.event.data))
 return history
}
async function plugins(){await click(button('/^(插件|Plugins)$/'),'Native Plugins navigation')}
async function install(spec,label,enable){
 await plugins()
 await click(button('/^(添加插件|Add plugin)$/'),'Native Add plugin')
 await click(`document.querySelector('input[aria-label="包名或地址"],input[aria-label="Package name or address"]')`,'Native package spec input')
 await cdp.call('Input.insertText',{text:spec})
 await shot(label+'-spec')
 await click(button('/^(安装|Install)$/',`[...document.querySelectorAll('[role=dialog]')].at(-1)`),'Native install submit')
 const installed=await until(async()=>{const row=await bundle();return row?.installed?row:null},label+' actual installed bundle')
 assert.equal(installed.enabled,false,'Native custom installation must remain disabled until the person enables it')
 report[label]={installed:true,enabledBeforeExplicitAction:installed.enabled,version:installed.version,source:installed.source}
 await until(button('/^(立即启用|Enable now)$/'),label+' completed Native dialog')
 await shot(label+'-installed-disabled')
 if(enable){
  await click(button('/^(立即启用|Enable now)$/'),'Native explicit enable')
  await until(async()=>{const row=await bundle();return row?.enabled},label+' enabled bundle')
  await until(async()=>{const roster=await rpc('agentPresets/list');return roster.presets.some(row=>row.id==='houdini'&&!row.broken)},'actual Houdini preset after Native enable')
  report[label].enabledByUi=true
 }else{
  const close=`[...document.querySelectorAll('[role=dialog]')].at(-1)?.querySelector('button[aria-label="关闭"],button[aria-label="Close"]')`
  await click(close,'Native completed install close')
 }
 return installed
}
function enableSwitch(){return `[...document.querySelectorAll('[role=switch]')].find(e=>/^(启用 |Enable )/.test(e.getAttribute('aria-label')||'')&&/Houdini|dsh-houdini/i.test(e.getAttribute('aria-label')||''))`}
async function preservedRoster(before,withHoudini){
 const roster=await rpc('agentPresets/list')
 assert(roster.presets.some(row=>row.id==='standard'&&row.isDefault))
 for(const row of before.presets)assert(roster.presets.some(next=>next.id===row.id),'An existing Native mode disappeared: '+row.id)
 assert.equal(roster.presets.some(row=>row.id==='houdini'),withHoudini)
 return roster
}
async function tutorial(){
 await click(`document.querySelector('button[data-signed-out][aria-haspopup=menu]')`,'Native account/More menu')
 await click(`[...document.querySelectorAll('[role=menuitem]')].find(e=>/^(设置|Settings)/.test(e.textContent.trim()))`,'Native visible Settings action')
 await until('document.querySelector("[data-shortcut-modal=settings]")','Native settings modal')
 await click(button('/^教程视频$/',`document.querySelector('[data-shortcut-modal=settings]')`),'Houdini tutorial section')
 await until('document.querySelector("[data-houdini-video-settings]")','actual plugin tutorial status')
}
function wire(text,outgoing){
 if(!text)return
 if(text.includes(config.sentinel)){
  if(!outgoing){report.secretReturned=true;return}
  if(!text.includes('credentials/set')){report.secretWrongChannel=true;return}
  report.secretTransport++
 }
 for(const method of ['pluginManager/installBundle','pluginManager/setBundleEnabled','pluginManager/removeBundle','session/prompt','credentials/set']){
  if(outgoing&&text.includes('"'+method+'"'))report.uiMethods[method]=(report.uiMethods[method]||0)+1
 }
}
try{
 const targets=await(await fetch('http://127.0.0.1:'+config.port+'/json/list')).json()
 const target=targets.find(row=>row.type==='page'&&row.url.startsWith('dsh-app://app/'))
 assert(target,'Owned Native renderer not found');report.nativeUrl=target.url
 cdp=await connect(target.webSocketDebuggerUrl)
 evaluate=async expression=>{const result=await cdp.call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value}
 main=await connect(config.mainInspector)
 const shown=await main.call('Runtime.evaluate',{expression:`(()=>{if(process.pid!==${config.expectedPid})throw Error('Foreign Native carrier');const e=process.getBuiltinModule('module').createRequire(process.resourcesPath+'/app.asar/package.json')('electron');const w=e.BrowserWindow.getAllWindows().filter(w=>w.webContents.getURL().startsWith('dsh-app://app/'));if(w.length!==1)throw Error('Nonunique owned window');w[0].show();w[0].focus();return process.pid})()`,returnByValue:true})
 assert.equal(shown.result.value,config.expectedPid)
 cdp.on(event=>{
  if(event.method==='Network.webSocketFrameSent'||event.method==='Network.webSocketFrameReceived'){
   const frame=event.params.response,text=frame.opcode===2?Buffer.from(frame.payloadData,'base64').toString('utf8'):frame.payloadData
   wire(text,event.method==='Network.webSocketFrameSent')
  }
  if(event.method==='Network.requestWillBeSent')wire(event.params.request.postData,true)
  if(event.method==='Runtime.consoleAPICalled'&&JSON.stringify(event.params.args).includes(config.sentinel))report.secretInConsole=true
 })
 await cdp.call('Runtime.enable');await cdp.call('Page.enable');await cdp.call('Network.enable',{maxPostDataSize:1_000_000})
 const initial=await until(NATIVE_SELECTION,'Native initial selected blank',45000)
 report.nativeElectronWindowTested=true
 assert(!(await bundle()),'Fixture must begin without the product installed')
 const before=await rpc('agentPresets/list');assert(before.presets.some(row=>row.id==='standard'&&row.isDefault));assert(!before.presets.some(row=>row.id==='houdini'))
 report.initialNativeProfileWithoutPlugin=true
 await install(config.remoteOnly?config.remoteTarball:config.artifact,config.remoteOnly?'ownedHttpTarball':'localTarball',true)
 report.installedByNativeUi=true
 if(!config.remoteOnly){
 // Return to the exact existing native blank, then use its real mode menu.
 assert(initial?.sessionId)
 await click(`document.querySelector('[data-row-key="session:${initial.sessionId}"]')`,'Native existing conversation')
 await click(`document.querySelector('button[title="选择新任务使用的 Agent 预设"],button[title="Choose the agent preset for your new task"]')||document.querySelector('[data-slot="conversation.hero.agentPreset"] button[aria-haspopup=menu]')||[...document.querySelectorAll('button[aria-haspopup=menu]')].find(e=>/标准|Standard/.test(e.textContent))`,'Native agent mode menu')
 await click(`[...document.querySelectorAll('[role=menuitem]')].find(e=>/Houdini/.test(e.textContent))`,'Native Houdini mode item')
 await until('document.querySelector("[data-houdini-project-label]")','Houdini mode selected by Native picker')
 const selected=await evaluate(NATIVE_SELECTION);assert.equal(selected.sessionId,initial.sessionId)
 report.houdiniModeSelectedByNativeUi=true;report.sessionId=selected.sessionId
 await rpc('session/selectModel',{request:{sessionId:selected.sessionId,provider:'owned-distribution-chat',model:'scripted-chat'}})
 await tutorial();await shot('tutorial-before-configuration')
 report.primaryColors={saveConfig:await primaryColor('[data-houdini-video-save-config]')}
 await click('document.querySelector("[data-houdini-video-endpoint]")','Native transcription endpoint input')
 await key('a','KeyA',65,2);await cdp.call('Input.insertText',{text:config.asrEndpoint})
 await click('document.querySelector("[data-houdini-video-model]")','Native transcription model input')
 await key('a','KeyA',65,2);await cdp.call('Input.insertText',{text:'owned-asr-id'})
 await click('document.querySelector("[data-houdini-video-save-config]")','Direct native configuration save')
 const configured=await until(async()=>{const status=await rpc('houdiniFrontend/videoSettings');return status.service?.endpoint===config.asrEndpoint?status:null},'direct native configuration committed')
 assert.equal(configured.service.model,'owned-asr-id');assert.equal(configured.defaults.concurrency,2);assert.equal(configured.defaults.requestsPerSecond,1)
 assert.equal(configured.service.credential.configured,false)
 assert.equal(report.uiMethods['session/prompt']??0,0,'deterministic settings must not invoke an Agent')
 await shot('tutorial-real-loopback-config')
 assert.equal(await evaluate('document.querySelector("[data-houdini-video-endpoint]").value'),config.asrEndpoint)
 assert.equal(await evaluate('document.querySelector("[data-houdini-video-model]").value'),'owned-asr-id')
 await click('document.querySelector("[data-houdini-video-key]")','Native secure credential action')
 await until('document.querySelector("[data-houdini-video-credential] input")===document.activeElement','actual password focus')
 assert.equal(await evaluate('document.activeElement.type'),'password')
 await cdp.call('Input.insertText',{text:config.sentinel})
 report.primaryColors.save=await primaryColor('[data-houdini-video-save-key]')
 assert.equal(await evaluate(`document.body.innerText.includes(${JSON.stringify(config.sentinel)})`),false)
 await shot('tutorial-masked-password')
 await click('document.querySelector("[data-houdini-video-save-key]")','Native write-only credential submit')
 const saved=await until(async()=>{const status=await rpc('houdiniFrontend/videoSettings');return status.service?.credential.configured?status:null},'actual DSH credential presence')
 await until('!document.querySelector("[data-houdini-video-credential]")','secret draft disposal')
 assert.equal(JSON.stringify(saved).includes(config.sentinel),false)
 const credentialView=await rpc('credentials/describe',{refs:[saved.service.credentialRef]})
 assert.equal(credentialView[saved.service.credentialRef].configured,true)
 assert(!Object.hasOwn(credentialView[saved.service.credentialRef],'value'))
 const modelCatalogue=await rpc('session/modelCatalog')
 assert(JSON.stringify(modelCatalogue).includes('scripted-chat'))
 assert(!JSON.stringify(modelCatalogue).includes('owned-asr-id'),'ASR configuration must not create a fake chat model')
 await click('document.querySelector("[data-houdini-video-key]")','reopen native credential field')
 await until('document.querySelector("[data-houdini-video-credential] input")===document.activeElement','reopened password focus')
 assert.equal(await evaluate('document.activeElement.value'),'','stored key must never be read back')
 await key('Escape','Escape',27)
 await until('!document.querySelector("[data-houdini-video-credential]")&&document.querySelector("[data-houdini-video-settings]")','nested Escape keeps status page')
 await shot('tutorial-real-configured')
 const history=await nativeHistory(selected.sessionId)
 assert.equal(history.hasMore,false);assert(!JSON.stringify(history).includes(config.sentinel),'native history must never contain the key')
 assert.equal(report.uiMethods['session/prompt']??0,0,'configuration and credential presence checks must not invoke an Agent')
 report.tutorial={directNativeConfiguration:true,actualNativeCredentialConfigured:true,storedKeyNeverReadBack:true,
  configurationWithoutAgent:true,nativeHistorySecretFree:true,chatModelSeparateFromAsr:true}
 }
 if(config.remoteOnly){
  await click(`document.querySelector('[data-row-key="session:${initial.sessionId}"]')`,'Native original default blank')
  const standard=await until(NATIVE_SELECTION,'Native default conversation remains selected')
  assert.equal(standard.sessionId,initial.sessionId);assert.equal(standard.agentPreset,'standard')
  await plugins();await click(enableSwitch(),'Native disable owned plugin switch')
  await until(async()=>{const row=await bundle();return row&&row.enabled===false},'actual package disabled')
  await until(async()=>!(await rpc('agentPresets/list')).presets.some(row=>row.id==='houdini'),'Houdini mode removed after Native disable')
  await preservedRoster(before,false)
  assert.equal(await evaluate('!!document.querySelector("[data-houdini-project-label],[data-houdini-video-settings]")'),false)
  await shot('remote-disabled-native')
  await click(enableSwitch(),'Native re-enable owned plugin switch')
  await until(async()=>{const row=await bundle();return row?.enabled},'actual package re-enabled')
  await until(async()=>(await rpc('agentPresets/list')).presets.some(row=>row.id==='houdini'),'Houdini mode restored after Native re-enable')
  await preservedRoster(before,true)
  await click(`document.querySelector('[data-plugin-package="dsh-houdini"] button[aria-label]')`,'Native installed package details')
  await until('document.querySelector("[data-plugin-detail=dsh-houdini]")','Native plugin detail page')
  await click(`[...document.querySelectorAll('button[aria-label]')].find(e=>/^(卸载 |Uninstall )/.test(e.getAttribute('aria-label'))&&/Houdini|dsh-houdini/i.test(e.getAttribute('aria-label')))`,'Native uninstall only owned plugin')
  await click(button('/^(卸载|Uninstall)$/',`[...document.querySelectorAll('[role=dialog]')].at(-1)`),'Native uninstall confirmation')
  await until(async()=>!(await bundle()),'owned plugin actually uninstalled by Native UI')
  await preservedRoster(before,false)
  const nativeSettings=await rpc('settings/describe')
  assert(nativeSettings.namespaces.some(row=>row.ns==='llm-pi-ai'))
  const catalogue=await rpc('session/modelCatalog');assert(JSON.stringify(catalogue).includes('scripted-chat'))
  await click(`document.querySelector('[data-row-key="session:${initial.sessionId}"]')`,'Native original blank after uninstall')
  const remained=await until(NATIVE_SELECTION,'default blank after uninstall')
  assert.equal(remained.sessionId,initial.sessionId);assert.equal(remained.agentPreset,'standard')
  await shot('remote-uninstalled-default-native')
  report.nativeLifecycle={disabled:true,houdiniRemoved:true,reEnabled:true,uninstalled:true,originalDefaultSessionPreserved:true,nativeModelSettingsPreserved:true}
 }
 const finalRoster=await rpc('agentPresets/list');assert(finalRoster.presets.some(row=>row.id==='standard'&&row.isDefault))
 assert.equal(finalRoster.presets.some(row=>row.id==='houdini'&&!row.isDefault),!config.remoteOnly)
 report.otherModesAndDefaultPreserved=true
 await sleep(300)
 if(!config.remoteOnly){
  assert(report.secretTransport>0,'Native credential RPC must actually be observed, not inferred from a fixture')
  assert(!report.secretReturned&&!report.secretWrongChannel&&!report.secretInConsole,'secret crossed an unexpected Native channel')
  assert((report.uiMethods['credentials/set']||0)>=1&&(report.uiMethods['session/prompt']||0)===0,'direct configuration and credential presence must not invoke an Agent')
 }
 assert((report.uiMethods['pluginManager/installBundle']||0)>=1&&(report.uiMethods['pluginManager/setBundleEnabled']||0)>=1)
 report.ok=true
 const quit=await main.call('Runtime.evaluate',{expression:`(()=>{if(process.pid!==${config.expectedPid})throw Error('Foreign Native carrier');const e=process.getBuiltinModule('module').createRequire(process.resourcesPath+'/app.asar/package.json')('electron');setTimeout(()=>e.app.quit(),100);return true})()`,returnByValue:true})
 assert.equal(quit.result.value,true);report.normalOwnedQuitRequested=true
}catch(error){
 report.error=String(error.stack||error).replaceAll(config.sentinel,'[fixture-secret-redacted]');process.exitCode=1
 if(evaluate)try{report.nativeFailure=String(await evaluate('document.body.innerText')).replaceAll(config.sentinel,'[fixture-secret-redacted]');await shot('native-ui-failure')}catch{}
}finally{cdp?.close();main?.close();await fs.writeFile(config.output,JSON.stringify(report,null,2))}
