// Real consumer of an explicitly owned Native Desktop renderer/main inspector.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import {createHash} from 'node:crypto'
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
 const point=await until(`(()=>{const e=(${expression});if(!e||e.disabled)return null;e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();const x=r.x+r.width/2,y=r.y+r.height/2;const hit=document.elementFromPoint(x,y);return r.width&&r.height&&hit&&e.contains(hit)?{x,y}:null})()`,label)
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
async function runtimeIdentity(expectedVersion,expectedHashes){
 const facts={expectedVersion,verified:false}
 try{
  const descriptor=JSON.parse(await fs.readFile(config.runtimeDescriptor,'utf8'))
  facts.pluginRoot=descriptor.pluginRoot;facts.generation=descriptor.generation;facts.pid=descriptor.pid
  facts.installedRoot=await fs.realpath(config.installedPackageRoot)
  facts.runtimeRoot=await fs.realpath(descriptor.pluginRoot)
  facts.runtimeVersion=JSON.parse(await fs.readFile(path.join(facts.runtimeRoot,'package.json'),'utf8')).version
  facts.entrySha256={}
  for(const name of Object.keys(expectedHashes))facts.entrySha256[name]=createHash('sha256').update(await fs.readFile(path.join(facts.runtimeRoot,name))).digest('hex')
  facts.verified=path.normalize(facts.runtimeRoot).toLowerCase()===path.normalize(facts.installedRoot).toLowerCase()
   &&facts.runtimeVersion===expectedVersion&&Object.entries(expectedHashes).every(([name,hash])=>facts.entrySha256[name]===hash)
 }catch(error){facts.error=String(error)}
 return facts
}
async function verifyRuntime(label,version,hashes){
 return until(async()=>{const facts=await runtimeIdentity(version,hashes);report[label]=facts;return facts.verified?facts:null},
  'actual loaded plugin root and frozen runtime entries '+version,30000)
}
async function directSourceUpdateEligibility(installed,label){
 assert.equal(installed.updatable,false,'A tarball dependency must not inherit registry update eligibility')
 const before=await bundle()
 await plugins()
 await click(`document.querySelector('[data-plugin-package="dsh-houdini"] button[aria-label]')`,'Native tarball package details')
 await until('document.querySelector("[data-plugin-detail=dsh-houdini]")','Native direct-source detail page')
 assert.equal(await evaluate('!!document.querySelector("[data-plugin-versions]")'),false)
 const listing=await rpc('pluginManager/listVersions',{name:'dsh-houdini'})
 assert.equal(listing.status,'refused');assert.equal(listing.problem,'not-updatable')
 const duplicate=await rpc('pluginManager/inspect',{spec:'dsh-houdini'})
 assert.equal(duplicate.status,'refused');assert.equal(duplicate.problem,'already-installed')
 const unchanged=await bundle()
 assert.deepEqual([unchanged.version,unchanged.source,unchanged.enabled],[before.version,before.source,before.enabled])
 report.directSourceUpdate={source:installed.source,updatable:false,nativeVersionSectionAbsent:true,
  listingRefusal:listing.problem,duplicatePackageNameRefusal:duplicate.problem}
 await shot(label+'-no-registry-update');await plugins()
}
async function nativeHistory(sessionId){
 const projection=await rpc('session/projections',{request:{sessionId}})
 assert(projection&&Number.isSafeInteger(projection.asOfSeq),'Native current projection must supply its exact event cut')
 const history=await rpc('session/page',{request:{address:{kind:'session',sessionId},throughSeq:projection.asOfSeq,maxMessages:100}})
 const failed=history.records.find(row=>row.event.type==='tool/result'&&row.event.data.message?.isError||row.event.type==='tool/ptc-dispatch'&&row.event.data.isError)
 if(failed)throw Error('Actual Native tool failed: '+JSON.stringify(failed.event.data))
 return history
}
async function nativeState(check=false,kind='migration'){
 const stateFile=kind==='update'?config.updateState:config.migrationState
 const workspace=kind==='update'?config.updateWorkspace:config.migrationWorkspace
 if(!check){
  const agentPreset=kind==='update'&&config.seedEnabled?'houdini':'standard'
  const created=await rpc('session/create',{request:{sessionId:crypto.randomUUID(),cwd:workspace,agentPreset}})
  const sessionId=created.sessionId
  const selected=await rpc('session/selectModel',{request:{sessionId,provider:'owned-distribution-chat',model:'scripted-chat'}})
  const text='Owned '+kind+': preserve this native conversation, model selection and original result across plugin replacement and update.'
  await rpc('session/prompt',{request:{sessionId,requestId:crypto.randomUUID(),mode:'queue',content:[{type:'text',text}]}})
  const history=await until(async()=>{const page=await nativeHistory(sessionId);return JSON.stringify(page.records).includes(text)&&page.records.some(row=>row.event.type==='turn/end')?page:null},'owned Native conversation actually settled before '+kind)
  assert.equal(history.hasMore,false)
  const projection=await rpc('session/projections',{request:{sessionId}})
  const throughSeq=history.records.at(-1)?.event.seq
  assert(Number.isSafeInteger(throughSeq),'The preservation baseline needs the exact last original event')
  const state={sessionId,agentPreset,records:history.records,throughSeq,modelSelection:projection.values.modelSelection,
   modes:(await rpc('agentPresets/list')).presets.map(row=>({id:row.id,isDefault:row.isDefault})),
   modelCatalog:await rpc('session/modelCatalog')}
  assert.deepEqual(state.modelSelection.lastUsed,selected.selected)
  assert.deepEqual(state.modelSelection.next,selected.selected)
  await fs.writeFile(stateFile,JSON.stringify(state,null,2))
  report[kind+'StateCreated']={sessionId,agentPreset,throughSeq:state.throughSeq,modelSelection:state.modelSelection,settledNativeHistory:true}
  return state
 }
 const state=JSON.parse(await fs.readFile(stateFile,'utf8'))
 const page=await rpc('session/page',{request:{address:{kind:'session',sessionId:state.sessionId},throughSeq:state.throughSeq,maxMessages:100}})
 assert.deepEqual(page.records,state.records,'Source migration/update changed the original native conversation records')
 const projection=await rpc('session/projections',{request:{sessionId:state.sessionId}})
 assert.deepEqual(projection.values.modelSelection,state.modelSelection,'Source migration/update changed the recorded model selection')
 assert.equal(projection.values.agentPreset,state.agentPreset??'standard')
 assert.deepEqual(await rpc('session/modelCatalog'),state.modelCatalog,'Owned model settings did not survive source migration/update')
 const roster=await rpc('agentPresets/list')
 for(const mode of state.modes)assert(roster.presets.some(row=>row.id===mode.id&&row.isDefault===mode.isDefault),'Existing Native mode changed: '+mode.id)
 report[kind+'StatePreserved']=true
 report[kind+'StateObservation']={sessionId:state.sessionId,throughSeq:state.throughSeq,modelSelection:projection.values.modelSelection,
  originalRecordsUnchanged:true,modelCatalogUnchanged:true,originalModesUnchanged:true}
 return state
}
async function directMigrationLatest(before){
 const migrated=await bundle()
 assert.equal(migrated.source,'dsh-houdini@'+config.expectedVersion)
 assert.equal(migrated.version,config.expectedVersion);assert.equal(migrated.enabled,false);assert.equal(migrated.updatable,true)
 await nativeState(true)
 report.migrationRegistrySource={version:migrated.version,source:migrated.source,enabled:migrated.enabled,updatable:migrated.updatable}
 const updatesBefore=report.uiMethods['pluginManager/updateBundle']??0
 await plugins()
 await click(`document.querySelector('[data-plugin-package="dsh-houdini"] button[aria-label]')`,'Native migrated current-release details')
 await until('document.querySelector("[data-plugin-versions]")','Native migrated registry Versions section')
 await until('/已是最新版本|Up to date/.test(document.querySelector("[data-plugin-versions]")?.innerText||"")','Native registry Versions actually reports up to date')
 const listing=await rpc('pluginManager/listVersions',{name:'dsh-houdini',options:{registry:config.expectedRegistry}})
 assert.equal(listing.status,'listed');assert.equal(listing.installed,config.expectedVersion);assert.equal(listing.versions.length,0)
 assert.equal(new URL(listing.registry).href,new URL(config.expectedRegistry).href)
 assert.equal(report.uiMethods['pluginManager/updateBundle']??0,updatesBefore,'Direct CLI upgrade must not be counted as a Native button update')
 report.nativeVersionsUiLatest=true
 report.nativeVersionsObservation={text:await evaluate('document.querySelector("[data-plugin-versions]").innerText'),registry:listing.registry,installed:listing.installed,newerVersions:listing.versions.length}
 report.migratedByOfficialCli=true;report.updatedByNativeUi=false;report.updatedByNativeApi=false
 await shot('migration-direct-native-up-to-date')
 await plugins();await click(enableSwitch(),'Native enable after direct CLI migration and upgrade')
 await until(async()=>(await rpc('agentPresets/list')).presets.some(row=>row.id==='houdini'&&!row.broken),'Directly migrated package actually supplies Houdini')
 await until(switchState(true),'Directly migrated switch reflects explicit enablement')
 await preservedRoster(before,true);await nativeState(true)
 const current=await bundle()
 report.migrationFinalSource={version:current.version,source:current.source,enabled:current.enabled,updatable:current.updatable}
 report.otherModesAndDefaultPreserved=true
}
async function plugins(){await click(button('/^(插件|Plugins)$/'),'Native Plugins navigation')}
async function install(spec,label,enable){
 await plugins()
 await click(button('/^(添加插件|Add plugin)$/'),'Native Add plugin')
 await click(`document.querySelector('input[aria-label="包名或地址"],input[aria-label="Package name or address"]')`,'Native package spec input')
 await cdp.call('Input.insertText',{text:spec})
 await shot(label+'-spec')
 await click(button('/^(安装|Install)$/',`[...document.querySelectorAll('[role=dialog]')].at(-1)`),'Native install submit')
 await shot(label+'-submitted')
 await until(async()=>{
  const failed=await evaluate('/插件安装失败|Plugin installation failed/i.test(document.body.innerText)')
  if(failed){
   const details=button('/^(查看安装详情|View installation details)$/')
   if(await evaluate(`!!(${details})`)){await click(details,'Native actual installation failure details');await sleep(150)}
   throw Error('Native installation failed: '+await evaluate('document.body.innerText.slice(-16000)'))
  }
  const current=await bundle()
  if(!current?.installed||current.version!==config.expectedVersion)return false
  return evaluate(`(()=>{
   const ready=(${button('/^(立即启用|Enable now)$/')});if(ready&&!ready.disabled&&ready.getBoundingClientRect().width)return true;
   const dialog=[...document.querySelectorAll('[role=dialog]')].some(e=>e.getBoundingClientRect().width);
   const toggle=(${enableSwitch()});return !dialog&&!!toggle&&!toggle.disabled&&toggle.getBoundingClientRect().width>0;
  })()`)
 },label+' completed Native dialog')
 const installed=await until(async()=>{const row=await bundle();return row?.installed&&typeof row.version==='string'?row:null},label+' actual installed bundle')
 assert.equal(installed.version,config.expectedVersion,'Native UI installed another release version')
 if(config.npmSpec)assert(['','^','~'].some(prefix=>installed.source==='dsh-houdini@'+prefix+config.expectedVersion),
  'Native dependency must use the registry package name: '+installed.source)
 assert.equal(installed.enabled,false,'Native custom installation must remain disabled until the person enables it')
 report[label]={installed:true,enabledBeforeExplicitAction:installed.enabled,version:installed.version,source:installed.source}
 await shot(label+'-installed-disabled')
 if(enable){
  const immediate=await evaluate(`!!(${button('/^(立即启用|Enable now)$/')})`)
  await click(immediate?button('/^(立即启用|Enable now)$/'):enableSwitch(),'Native explicit enable')
  report[label].enableEntry=immediate?'installation-result':'installed-plugin-switch'
  await until(async()=>{const row=await bundle();return row?.enabled},label+' enabled bundle')
  await until(async()=>{const roster=await rpc('agentPresets/list');return roster.presets.some(row=>row.id==='houdini'&&!row.broken)},'actual Houdini preset after Native enable')
  await until(switchState(true),'native installed switch reflects enabled state')
  report[label].enabledByUi=true
 }else{
  const close=`[...document.querySelectorAll('[role=dialog]')].at(-1)?.querySelector('button[aria-label="关闭"],button[aria-label="Close"]')`
  if(await evaluate(`!!(${close})`))await click(close,'Native completed install close')
 }
 return installed
}
function enableSwitch(){return `[...document.querySelectorAll('[role=switch]')].find(e=>/^(启用 |Enable )/.test(e.getAttribute('aria-label')||'')&&/Houdini|dsh-houdini/i.test(e.getAttribute('aria-label')||''))`}
function switchState(checked){return `(()=>{const e=(${enableSwitch()});return !!e&&!e.disabled&&e.getAttribute('aria-checked')===${JSON.stringify(String(checked))}})()`}
async function preservedRoster(before,withHoudini){
 const roster=await rpc('agentPresets/list')
 assert(roster.presets.some(row=>row.id==='standard'&&row.isDefault))
 for(const row of before.presets)if(row.id!=='houdini')assert(roster.presets.some(next=>next.id===row.id),'An existing Native mode disappeared: '+row.id)
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
 for(const method of ['pluginManager/inspect','pluginManager/registries','pluginManager/installBundle','pluginManager/updateBundle','pluginManager/setBundleEnabled','pluginManager/removeBundle','session/prompt','credentials/set']){
  if(outgoing&&text.includes('"'+method+'"'))report.uiMethods[method]=(report.uiMethods[method]||0)+1
 }
 if(outgoing&&text.includes('pluginManager/setBundleEnabled'))try{
  const message=JSON.parse(text)
  if(message.method==='pluginManager/setBundleEnabled'){
   report.toggleActions??=[];report.toggleActions.push(message.payload?.args)
   writeProgress()
  }
 }catch{}
 if(outgoing&&text.includes('pluginManager/updateBundle'))try{
  const message=JSON.parse(text)
  if(message.method==='pluginManager/updateBundle'){
   const args=message.payload?.args
   report.updateActions??=[]
   report.updateActions.push({name:args?.name,version:args?.version,registry:args?.options?.registry??null})
   writeProgress()
  }
 }catch{}
}
function writeProgress(){fs.writeFile(path.join(path.dirname(config.output),'ui-progress.json'),JSON.stringify(report,null,2)).catch(()=>{})}
try{
 const targets=await(await fetch('http://127.0.0.1:'+config.port+'/json/list')).json()
 const target=targets.find(row=>row.type==='page'&&row.url.startsWith('dsh-app://app/'))
 assert(target,'Owned Native renderer not found');report.nativeUrl=target.url
 cdp=await connect(target.webSocketDebuggerUrl)
 evaluate=async expression=>{const result=await cdp.call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value}
 main=await connect(config.mainInspector)
 const shown=await main.call('Runtime.evaluate',{expression:`(()=>{if(process.pid!==${config.expectedPid})throw Error('Foreign Native carrier');const e=process.getBuiltinModule('module').createRequire(${JSON.stringify(config.appPackage)})('electron');if(e.app.isPackaged!==${JSON.stringify(config.expectedPackaged)})throw Error('Unexpected official carrier mode');const w=e.BrowserWindow.getAllWindows().filter(w=>w.webContents.getURL().startsWith('dsh-app://app/'));if(w.length!==1)throw Error('Nonunique owned window');w[0].show();w[0].focus();return process.pid})()`,returnByValue:true})
 assert.equal(shown.result.value,config.expectedPid)
 cdp.on(event=>{
  if(event.method==='Runtime.exceptionThrown'){
   report.runtimeErrors??=[]
   report.runtimeErrors.push(String(event.params.exceptionDetails.exception?.description??event.params.exceptionDetails.text).replaceAll(config.sentinel,'[redacted]'))
  }
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
 if(config.expectedRegistry){
  const registries=await rpc('pluginManager/registries',{})
  assert.equal(new URL(registries.registry).href,new URL(config.expectedRegistry).href)
  assert.equal(new URL(registries.resolved).href,new URL(config.expectedRegistry).href)
  assert.deepEqual(registries.fallbackRegistries,[],'A selected-registry check must not pass through another source')
  report.registry=registries
 }
 if(config.resumeVerificationOnly){
  const state=JSON.parse(await fs.readFile(config.updateState,'utf8'))
  await rpc('session/selectModel',{request:{sessionId:state.sessionId,...state.modelSelection.next}})
  await nativeState(true,'update')
  await verifyRuntime('runtimeAfterColdReopen',config.expectedVersion,config.candidateRuntimeHashes)
  const current=await bundle()
  assert.equal(current.version,config.expectedVersion);assert.equal(current.enabled,true)
  assert((await rpc('agentPresets/list')).presets.some(row=>row.id==='houdini'&&!row.broken))
  report.coldReopenVerified=true;report.modelInferencePerformed=false
 }else{
 const before=await rpc('agentPresets/list');assert(before.presets.some(row=>row.id==='standard'&&row.isDefault))
 assert.equal(before.presets.some(row=>row.id==='houdini'),config.seedEnabled===true)
 if(config.seedEnabled)await verifyRuntime('runtimeBeforeUpdate',config.updateFromVersion,config.seedRuntimeHashes)
 if(config.migrationPhase==='before'){
  const source=await bundle()
  assert.equal(source.version,config.migrationVersion);assert.equal(source.enabled,false)
  if(config.migrationSource==='file')assert(source.source.startsWith('file:'))
  else assert.equal(source.source,config.migrationSourceSpec)
  await directSourceUpdateEligibility(source,'migration-original-'+config.migrationSource)
  await nativeState()
  report.migrationOriginalSource={version:source.version,source:source.source,enabled:source.enabled,updatable:source.updatable}
 }else if(config.migrationPhase==='after'&&config.migrationDirect){
  await directMigrationLatest(before)
 }else{
 if(config.migrationPhase==='after'){
  const migrated=await bundle()
  assert.equal(migrated.source,'dsh-houdini@'+config.migrationVersion)
  assert.equal(migrated.version,config.migrationVersion);assert.equal(migrated.enabled,false);assert.equal(migrated.updatable,true)
  await nativeState(true)
  report.migrationRegistrySource={version:migrated.version,source:migrated.source,enabled:migrated.enabled,updatable:migrated.updatable}
 }
 if(config.updateFromVersion){
  const previous=await bundle()
  assert.equal(previous.version,config.updateFromVersion);assert.equal(previous.enabled,config.seedEnabled===true)
  assert(previous.source.startsWith('dsh-houdini@'),'the previous official CLI must seed a registry dependency')
  assert.equal(previous.updatable,true,'An older registry bundle must remain eligible for a compatible update')
  report.previousOfficialCli={version:previous.version,enabled:previous.enabled,source:previous.source}
  if(!config.migrationPhase)await nativeState(false,'update')
  await plugins()
  const listing=await rpc('pluginManager/listVersions',{name:'dsh-houdini',options:{registry:config.updateRegistry}})
  assert.equal(listing.status,'listed',JSON.stringify(listing))
  assert(listing.versions.some(row=>row.version===config.expectedVersion&&!row.incompatible))
  await click(`document.querySelector('[data-plugin-package="dsh-houdini"] button[aria-label]')`,'Native old registry package details')
  await until('document.querySelector("[data-plugin-versions]")','Native registry versions section')
  const updateButton=`[...document.querySelectorAll('button')].find(e=>e.textContent.trim()===${JSON.stringify('更新到 '+config.expectedVersion)}||e.textContent.trim()===${JSON.stringify('Update to '+config.expectedVersion)})`
  await until(updateButton,'Native compatible update button')
  await shot('registry-compatible-update-button')
  const updateCallsBefore=report.uiMethods['pluginManager/updateBundle']||0
  const updateActionsBefore=report.updateActions?.length??0
  await click(updateButton,'Native update to compatible release')
  await until('document.querySelector("[data-plugin-update=confirm]")','Native update confirmation')
  await click(button('/^(更新|Update)$/',`[...document.querySelectorAll('[role=dialog]')].at(-1)`),'Native confirm compatible update')
  await until('document.querySelector("[data-plugin-update=done]")','Native update result')
  await until(async()=>{const current=await bundle();return current.version===config.expectedVersion&&current.enabled===previous.enabled},'native registry update preserves the original enabled selection')
  assert((report.uiMethods['pluginManager/updateBundle']||0)>updateCallsBefore,'The actual Native button must submit the update')
  const observedRequest=report.updateActions?.slice(updateActionsBefore).find(row=>row.name==='dsh-houdini'&&row.version===config.expectedVersion)
  if(config.expectedRegistry){
   assert(observedRequest,'The actual Native update request was not observed')
   assert.equal(new URL(observedRequest.registry).href,new URL(config.expectedRegistry).href,'The Native button selected a different registry')
  }
  const update={via:'native-update-button',from:previous.version,to:config.expectedVersion,
   outcome:await evaluate('document.querySelector("[data-plugin-update=done]").innerText'),enabledSelectionPreserved:true,previousEnabled:previous.enabled,
   ...(observedRequest?{observedRequest}:{})}
  await shot('registry-native-update-result')
  await click(`document.querySelector('[role=dialog] button[aria-label="关闭"], [role=dialog] button[aria-label="Close"]')`,'Native completed update close')
  await until(`document.querySelector('[data-plugin-detail="dsh-houdini"]')?.textContent.includes(${JSON.stringify(config.expectedVersion)})`,'actual native details display the candidate version')
  await shot('registry-updated-details');await plugins()
  if(!previous.enabled)await click(enableSwitch(),'Native enable after host/plugin upgrade')
  await until(async()=>(await rpc('agentPresets/list')).presets.some(row=>row.id==='houdini'&&!row.broken),'updated candidate actually enabled')
  await until(switchState(true),'native updated switch reflects enabled state')
  await preservedRoster(before,true);await shot('registry-updated-candidate')
  if(config.seedEnabled){
   const loaded=await verifyRuntime('runtimeAfterUpdate',config.expectedVersion,config.candidateRuntimeHashes)
   assert.notEqual(loaded.generation,report.runtimeBeforeUpdate.generation,'The active plugin service must have a new generation after update')
  }
  report.nativeRegistryUpdate={update,targetVersion:config.expectedVersion}
  report.updatedByNativeUi=true
  if(!config.migrationPhase){await nativeState(true,'update');report.updateHistoryVerifiedBeforeFault=true}
  let failed
  if(config.brokenVersion){
  failed=await rpc('pluginManager/updateBundle',{name:'dsh-houdini',version:config.brokenVersion,
   options:{registry:config.updateRegistry,requestId:'owned-failed-update-fixture'}})
  report.failedFixtureObservation={fixture:config.failureFixture,receipt:failed,bundle:await bundle(),
   entries:(await rpc('pluginManager/listPlugins')).filter(row=>/dsh-houdini|owned-update/.test(JSON.stringify(row))),
   presets:(await rpc('agentPresets/list')).presets.map(row=>({id:row.id,broken:row.broken}))}
  if(failed.result.application!=='failed'){
   assert(config.diagnoseLoadFailure,'Expected native update failure and automatic restoration: '+JSON.stringify(failed))
   report.automaticFailureRecoveryVerified=false
   const removed=await rpc('pluginManager/removeBundle',{name:'dsh-houdini'})
   assert(!['failed','cancelled'].includes(removed.application),JSON.stringify(removed))
   const repaired=await rpc('pluginManager/installBundle',{spec:'dsh-houdini@'+config.expectedVersion,
    options:{registry:config.updateRegistry,saveExact:true,enabled:true}})
   assert(!['failed','cancelled'].includes(repaired.application),JSON.stringify(repaired))
   report.explicitFailureRecovery={removed,repaired,via:'native-manager-remove-and-install',publicUiPathTested:false}
  }else{
   assert(failed.restore,JSON.stringify(failed))
   assert(!['failed','cancelled'].includes(failed.restore.application),JSON.stringify(failed))
   report.automaticFailureRecoveryVerified=true
  }
  await until(async()=>{const current=await bundle();return current.version===config.expectedVersion&&current.enabled},'native failed update restores the enabled frozen candidate')
  await until(async()=>(await rpc('agentPresets/list')).presets.some(row=>row.id==='houdini'&&!row.broken),'restored candidate actually supplies Houdini')
  await until(switchState(true),'native restored switch reflects enabled state')
  await preservedRoster(before,true);await shot('registry-failed-fixture-restored')
  if(config.diagnoseLoadFailure&&!report.automaticFailureRecoveryVerified)report.explicitFailureRecoveryVerified=true
  report.updatedByNativeApi=true
  }
  report.nativeRegistryUpdate={...report.nativeRegistryUpdate,...(failed?{failedFixture:failed,restoredEnabled:true}:{})}
  if(config.migrationPhase==='after'){
   const current=await bundle()
   assert.equal(current.source,'dsh-houdini@'+config.expectedVersion)
   assert.equal(current.updatable,true)
   await nativeState(true)
   report.migrationFinalSource={version:current.version,source:current.source,enabled:current.enabled,updatable:current.updatable}
  }
  if(!config.migrationPhase){await nativeState(true,'update');report.updateHistoryVerifiedAfterFault=true}
 }else{
  assert(!(await bundle()),'Fixture must begin without the product installed')
  report.initialNativeProfileWithoutPlugin=true
  const installed=await install(config.remoteOnly?config.remoteInstallSpec:config.artifact,config.npmSpec?'npmPackage':config.remoteOnly?'remoteTarball':'localTarball',true)
  if(!config.npmSpec)await directSourceUpdateEligibility(installed,config.remoteOnly?'remoteTarball':'localTarball')
  report.installedByNativeUi=true
 }
 if(!config.remoteOnly){
 // Return to the exact existing native blank, then use its real mode menu.
 assert(initial?.sessionId)
 await click(`document.querySelector('[data-row-key="session:${initial.sessionId}"]')`,'Native existing conversation')
 const modeMenu=`document.querySelector('button[title="选择新任务使用的 Agent 预设"],button[title="Choose the agent preset for your new task"]')||document.querySelector('[data-slot="conversation.hero.agentPreset"] button[aria-haspopup=menu]')||[...document.querySelectorAll('button[aria-haspopup=menu]')].find(e=>/标准|Standard/.test(e.textContent))`
 // The native seat closes its menu when the newly enabled preset roster arrives.
 // Reopen only when that observable transition closed it; a missing preset still fails.
 await until(async()=>{
  if(await evaluate(`[...document.querySelectorAll('[role=menuitem]')].some(e=>/Houdini/.test(e.textContent))`))return true
  if(await evaluate(`(${modeMenu})?.getAttribute('aria-expanded')!=='true'`))await click(modeMenu,'Native agent mode menu')
  return false
 },'Native Houdini mode menu after enabled roster arrives')
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
  await until(switchState(false),'native switch actually reflects disabled state before another click')
  await preservedRoster(before,false)
  assert.equal(await evaluate('!!document.querySelector("[data-houdini-project-label],[data-houdini-video-settings]")'),false)
  await shot('remote-disabled-native')
  await click(enableSwitch(),'Native re-enable owned plugin switch')
  await until(async()=>{const row=await bundle();return row?.enabled},'actual package re-enabled')
  await until(async()=>(await rpc('agentPresets/list')).presets.some(row=>row.id==='houdini'),'Houdini mode restored after Native re-enable')
  await until(switchState(true),'native switch actually reflects re-enabled state')
  await preservedRoster(before,true)
  if(!config.updateFromVersion){
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
  }else{
   assert(JSON.stringify(await rpc('session/modelCatalog')).includes('scripted-chat'))
   await click(`document.querySelector('[data-row-key="session:${initial.sessionId}"]')`,'Native original blank after update and restoration')
   const remained=await until(NATIVE_SELECTION,'original default conversation after update and restoration')
   assert.equal(remained.sessionId,initial.sessionId);assert.equal(remained.agentPreset,'standard')
   report.nativeLifecycle={disabled:true,houdiniRemoved:true,reEnabled:true,uninstalled:false,retainedForFrozenByteVerification:true,
    originalDefaultSessionPreserved:true,nativeModelSettingsPreserved:true}
  }
 }
 const finalRoster=await rpc('agentPresets/list');assert(finalRoster.presets.some(row=>row.id==='standard'&&row.isDefault))
 assert.equal(finalRoster.presets.some(row=>row.id==='houdini'&&!row.isDefault),!config.remoteOnly||!!config.updateFromVersion)
 report.otherModesAndDefaultPreserved=true
 await sleep(300)
 if(!config.remoteOnly){
  assert(report.secretTransport>0,'Native credential RPC must actually be observed, not inferred from a fixture')
  assert(!report.secretReturned&&!report.secretWrongChannel&&!report.secretInConsole,'secret crossed an unexpected Native channel')
  assert((report.uiMethods['credentials/set']||0)>=1&&(report.uiMethods['session/prompt']||0)===0,'direct configuration and credential presence must not invoke an Agent')
 }
 assert((report.uiMethods[config.updateFromVersion?'pluginManager/updateBundle':'pluginManager/installBundle']||0)>=(config.updateFromVersion?(config.brokenVersion?2:1):1)
  &&(report.uiMethods['pluginManager/setBundleEnabled']||0)>=1)
 }
 }
 report.ok=true
 const quit=await main.call('Runtime.evaluate',{expression:`(()=>{if(process.pid!==${config.expectedPid})throw Error('Foreign Native carrier');const e=process.getBuiltinModule('module').createRequire(${JSON.stringify(config.appPackage)})('electron');setTimeout(()=>e.app.quit(),100);return true})()`,returnByValue:true})
 assert.equal(quit.result.value,true);report.normalOwnedQuitRequested=true
}catch(error){
 report.error=String(error.stack||error).replaceAll(config.sentinel,'[fixture-secret-redacted]');process.exitCode=1
 if(evaluate)try{report.nativeFailure=String(await evaluate('document.body.innerText')).replaceAll(config.sentinel,'[fixture-secret-redacted]');await shot('native-ui-failure')}catch{}
}finally{cdp?.close();main?.close();await fs.writeFile(config.output,JSON.stringify(report,null,2))}
