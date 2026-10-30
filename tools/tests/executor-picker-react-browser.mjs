/** Real React + plugin-owned controls; no Host, account or Houdini.
 * The immutable web bundle publishes its real static SDK into a fixture-only
 * bootstrap seam. Its application boot is stopped before any Host requests.
 * node tools/tests/executor-picker-react-browser.mjs <prepared-runtime-root>
 */
import fs from 'node:fs/promises'
import path from 'node:path'
import http from 'node:http'
import {spawn} from 'node:child_process'
import assert from 'node:assert/strict'
import {createRun} from '../output-artifacts.mjs'
const root=path.resolve('.'),runtime=path.resolve(process.argv[2]??'')
assert(process.argv[2],'Pass the exact prepared runtime root')
const dist=path.join(runtime,'node_modules/@deepseek-ai/dsh-web-frontend/dist')
const sdkVersion=JSON.parse(await fs.readFile(path.join(dist,'../package.json'),'utf8')).version
const original=await fs.readFile(path.join(dist,'index.html'),'utf8')
const script=original.match(/src="\.\/([^\"]+\.js)"/)[1]
const css=[...original.matchAll(/href="\.\/([^\"]+\.css)"/g)].map(match=>match[1])
const source=await fs.readFile(path.join(root,'client.js'),'utf8')
// Use the exact official palette instead of a fixture palette that accidentally
// made the translucent native menu-material token fully opaque.
const themeSource=await fs.readFile(path.join(runtime,'node_modules/@deepseek-ai/dsh-client-ui-theme/lib/client.js'),'utf8')
const nativeThemeCss=['base_css_default','design_platform_css_default'].map(name=>{
 const literal=themeSource.match(new RegExp('var '+name+' = (\"(?:\\\\.|[^\"\\\\])*\");'))?.[1]
 assert(literal,'Official theme CSS export missing: '+name)
 return JSON.parse(literal)
}).join('\n')
const code=source.slice(source.indexOf('    function Button('),source.indexOf('    // >>> houdini-node-delivery'))
const videoCode=source.slice(source.indexOf('    function createVideoSettings('),source.indexOf('    function createSupportReporter('))
const styles=source.slice(source.indexOf('    var shellCss ='),source.indexOf('    var shellCssId ='))
const evidence=await createRun({label:'target-chip-react',kind:'evidence',isolation:'isolated'})
const output=evidence.directory
const scratch=await createRun({label:'target-chip-react-browser',kind:'tmp',isolation:'isolated'})
const fixture=`
const sdk=await window.fixtureSdk;
const React=sdk.react;
if(!React?.createElement||!sdk['react-dom/client']?.createRoot)throw Error('Exact DSH React SDK missing');
const style=document.createElement('style');style.textContent=new Function(${JSON.stringify(styles+';return shellCss;')})();document.head.appendChild(style);
const factories=new Function('React','require',${JSON.stringify(code+videoCode+';return {createHoudiniDesktopUi,createVideoSettings};')})(React,name=>{if(!sdk[name])throw Error('Unsupported public SDK '+name);return sdk[name]});
const createUi=factories.createHoudiniDesktopUi;
let selected=null,session='chat-a',hidden=false,mode='ready',listGate=null,releaseList=null,launchGate=null,releaseLaunch=null;
let onlyCurrent=false,prepareFailure=false,prepareGate=null,releasePrepare=null,reverseRows=false;
let generation={id:1},launchPhase='ready',loseActionReply=false,lastLaunch=null;
let pluginUpdateState='available';
window.fixturePluginUpdate=value=>{pluginUpdateState=value;};
const tickets=new Map(),listeners=new Set(),nativeListeners=new Set(),generationListeners=new Set(),calls=[];
const viewListeners=new Set(),formListeners=new Set(),credentialEvents=new Set(),opened=[];
let view='project',videoRevision={revision:1,status:'ready',writable:true},rejectKey=false,losePrompt=false,secretOnly=true;
let videoFacts={revision:1,selected:{provider:'',model:'fixture-asr',protocol:'openai-transcriptions',endpoint:'http://127.0.0.1:9876/v1/audio/transcriptions',authentication:'bearer',concurrency:2,requestsPerSecond:1},defaults:{concurrency:2,requestsPerSecond:1},diagnostics:[],writable:true,
service:{displayName:'本机转录',model:'fixture-asr',protocol:'openai-transcriptions',endpoint:'http://127.0.0.1:9876/v1/audio/transcriptions',
authentication:'bearer',credentialRef:'DSH_HOUDINI_ASR_FIXTURE_API_KEY',credential:{configured:false,writable:true},dataLocation:'loopback',support:'unverified'},
adapters:[{id:'openai-transcriptions',label:'OpenAI 兼容文件转录'}]};
function notifyView(){viewListeners.forEach(fn=>fn());}
function closeVideo(){view='project';notifyView();}
function updateVideo(patch){videoFacts={...videoFacts,selected:{...videoFacts.selected,...patch.endpoint?{endpoint:patch.endpoint}:{}},service:{...videoFacts.service,...patch}};videoRevision={...videoRevision,revision:videoRevision.revision+1};videoFacts.revision=videoRevision.revision;formListeners.forEach(fn=>fn());}
const ids={executor:'a'.repeat(32),runtime:'b'.repeat(32),epoch:'c'.repeat(32),registration:'d'.repeat(32)};
const rows=[{executor_id:ids.executor,runtime_id:ids.runtime,scene_epoch:ids.epoch,registration_id:ids.registration,scene_id:'e'.repeat(32),
hip_path:'C:/项目/旋转船体/船体.hip',hip_is_new:false,workspace_path:'C:/项目/旋转船体',houdini_version:'22.0.368',pid:8234,state:'registered',same_workspace:true,workbench:true},
{executor_id:'f'.repeat(32),runtime_id:'1'.repeat(32),scene_epoch:'2'.repeat(32),registration_id:'3'.repeat(32),scene_id:'4'.repeat(32),
hip_path:'D:/岩石实验/石群.hip',hip_is_new:false,workspace_path:'D:/岩石实验',houdini_version:'21.0.440',pid:5678,state:'registered',same_workspace:false,workbench:true}];
let native=new Map(),projection={byId:{[session]:{id:session,cwd:rows[0].workspace_path,blank:false,projectionValues:{agentPreset:'houdini'}}},projectionsBySession:{}};
function publish(){projection={...projection,projectionsBySession:{[session]:{values:{houdiniExecutorIdentity:selected?{target:selected,executorId:selected.executor_id,runtimeId:selected.runtime_id,sceneEpoch:selected.scene_epoch,hipPath:selected.hip_path,hipIsNew:selected.hip_is_new}:null}}}};listeners.forEach(fn=>fn());}
function presence(row){return{executorId:row.executor_id,runtimeId:mode==='changed'&&row===rows[0]?'9'.repeat(32):row.runtime_id,sceneEpoch:row.scene_epoch,
status:mode==='offline'?'offline':'online',observedAt:Date.now(),candidate:row,ownerSessionId:row===rows[0]?(mode==='occupied'?'chat-b':session):null,busy:mode==='jobs'&&row===rows[0],activeJobs:mode==='jobs'&&row===rows[0]?1:0,activeRequests:0};}
const connection={generation:{getSnapshot:()=>generation,subscribe:fn=>{generationListeners.add(fn);return()=>generationListeners.delete(fn)}},rpc:{call:async(_channel,method,payload)=>{calls.push({method,input:payload.args?.input,request:payload.args?.request,keyRef:payload.args?.ref});
if(method==='houdiniFrontend/videoSettings')return{ok:true,value:structuredClone(videoFacts)};
if(method==='houdiniFrontend/videoDiagnostics')return{ok:true,value:{dependencies:[],note:'仅检查夹具依赖'}};
if(method==='houdiniFrontend/videoConfigure'){
 const input=payload.args.input;Object.assign(videoFacts.selected,{provider:input.provider,endpoint:input.endpoint,protocol:input.protocol,model:input.model,authentication:input.authentication,concurrency:input.concurrency,requestsPerSecond:input.requests_per_second});
 Object.assign(videoFacts.service,{provider:input.provider||null,model:input.model,protocol:input.protocol,endpoint:input.endpoint,authentication:input.authentication});
 videoFacts.revision=++videoRevision.revision;return{ok:true,value:structuredClone(videoFacts)};
}
if(method==='credentials/set'){
 secretOnly=secretOnly&&Object.keys(payload.args).sort().join(',')==='ref,value'&&payload.args.value==='fixture-only-private-key';
 if(rejectKey)return{ok:false,error:{message:'Native credentials: reference is read-only'}};
 videoFacts.service.credential.configured=true;credentialEvents.forEach(fn=>fn());return{ok:true};
}
if(method==='session/prompt'){if(losePrompt){losePrompt=false;throw Error('Fixture: prompt receipt lost')}return{ok:true,value:{accepted:true}};}
if(method==='houdiniFrontend/capabilities')return{ok:true,value:{desktop:true}};
if(method==='houdiniFrontend/pluginUpdates')return{ok:true,value:pluginUpdateState==='available'?{state:'available',title:'有可选更新',message:'当前版本可以继续使用，可在方便时更新。',currentVersion:'0.1.3',hostVersion:'0.2.1-rc.5',canIgnore:true,ignoredVersion:'',checkedAt:Date.now(),update:{version:'0.1.4',url:'https://github.com/eee1723/dsh-houdini/releases/tag/v0.1.4',summary:'改善更新提醒和工程选择。',urgency:'optional'}}:{state:'unknown',title:'暂时无法检查更新',message:'请稍后再试。当前工程可以继续使用。',checkedAt:Date.now()}};
if(method==='houdiniFrontend/projectInstallations')return{ok:true,value:[{hfs:'C:/Program Files/Side Effects Software/Houdini 22.0.368',version:'22.0.368',series:'22.0'}]};
if(method==='houdiniFrontend/projectAction'){
 const input=payload.args.input;if(!/^[a-f0-9]{32}$/.test(input.requestId))throw Error('Stable request identity missing');lastLaunch=input.requestId;
 if(!tickets.has(lastLaunch))tickets.set(lastLaunch,{id:lastLaunch,phase:launchPhase,stage:'launching',message:'Host: 已记录启动请求',elapsedMs:100});
 if(launchGate)await launchGate;if(loseActionReply){loseActionReply=false;throw Error('Fixture: initial admission reply lost')}
 return{ok:true,value:structuredClone(tickets.get(input.requestId))};
}
if(method==='houdiniFrontend/projectLaunchStatus')return{ok:true,value:structuredClone(tickets.get(payload.args.input.id))};
if(method==='houdiniFrontend/projectLaunchDetach'){
 const ticket=tickets.get(payload.args.input.id);if(ticket&&ticket.phase!=='ready')ticket.phase='detached';return{ok:true,value:structuredClone(ticket||{id:payload.args.input.id,phase:'detached'})};
}
if(method==='houdiniFrontend/projectLaunchResume'){
 const ticket=tickets.get(payload.args.input.id);Object.assign(ticket,{phase:'waiting',stage:'binding',message:'Host: 正在复核原启动回执'});return{ok:true,value:structuredClone(ticket)};
}
if(method==='houdiniFrontend/prepareBridge'){if(prepareGate)await prepareGate;if(prepareFailure)return{ok:false,error:{message:'Command failed: powershell.exe install.ps1\\nFixture: access denied while updating components.'}};return{ok:true,value:{message:'夹具：Houdini 组件已准备；已有窗口未重启。'}};}
if(method==='houdiniFrontend/projectPresence'){if(listGate)await listGate;return{ok:true,value:(reverseRows?[...rows].reverse():rows).filter(row=>!onlyCurrent||row===rows[0]).map(presence)};}
if(method==='houdiniTargets/select'){const input=payload.args.input,row=rows.find(row=>row.executor_id===input.executorId);if(!row||row.scene_epoch!==input.sceneEpoch||row.hip_path!==input.expectedHip)return{ok:false,error:{message:'Fixture: scene changed; choose the window again.'}};selected=row;return{ok:true,value:{status:'selected',selectedTarget:selected}};}
if(method==='houdiniTargets/clear'){selected=null;return{ok:true,value:{selectedTarget:null}};}
return{ok:true,value:{}};}}};
const selection={key:session};
const owner={sessionStatus:{getSnapshot:()=>native,subscribe:fn=>{nativeListeners.add(fn);return()=>nativeListeners.delete(fn)}},adapter:{current:{getSnapshot:()=>selection,subscribe:()=>()=>{}}}};
const workbench=createUi(connection,owner,{refreshProjections:async()=>publish(),list:{getSnapshot:()=>projection,subscribe:fn=>{listeners.add(fn);return()=>listeners.delete(fn)}}});
const video=factories.createVideoSettings(connection,{get:()=>({getSnapshot:()=>videoRevision,subscribe:fn=>{formListeners.add(fn);return()=>formListeners.delete(fn)}})},
{$on:(name,fn)=>{if(name!=='credentials/reference-updated')throw Error(name);credentialEvents.add(fn);return()=>credentialEvents.delete(fn);}});
const props={sessionId:session,useSessions:selector=>React.useSyncExternalStore(fn=>{listeners.add(fn);return()=>listeners.delete(fn)},()=>selector(projection))};
function App(){const preset=props.useSessions(state=>state.byId[session].projectionValues.agentPreset);const active=React.useSyncExternalStore(fn=>{viewListeners.add(fn);return()=>viewListeners.delete(fn)},()=>view);return React.createElement(React.Fragment,null,preset==='houdini'&&React.createElement(workbench.Lifecycle),React.createElement('div',{className:'fixture-toolbar'},React.createElement('span',null,'旋转船体'),React.createElement(workbench.Label,props)),active==='video'&&React.createElement(sdk['@deepseek-ai/dsh-client-ui-primitives'].Modal,{open:true,onClose:closeVideo,title:'设置',closeLabel:'关闭设置',shortcutModal:'settings',className:'fixture-settings-modal'},React.createElement(video,{close:closeVideo})));}
sdk['react-dom/client'].createRoot(document.querySelector('#fixture')).render(React.createElement(App));
const initialRow={...rows[0]},initialOther={...rows[1]};
window.fixture={calls,onlyCurrent(value){onlyCurrent=value;document.dispatchEvent(new Event('visibilitychange'));},reverse(value){reverseRows=value;document.dispatchEvent(new Event('visibilitychange'));},otherScene(){rows[1]={...rows[1],hip_path:'D:/岩石实验/changed.hip',scene_epoch:'5'.repeat(32)};document.dispatchEvent(new Event('visibilitychange'));},restoreOther(){rows[1]={...initialOther};document.dispatchEvent(new Event('visibilitychange'));},failPrepare(value){prepareFailure=value;},holdPrepare(){prepareGate=new Promise(resolve=>releasePrepare=resolve);},releasePrepare(){prepareGate=null;releasePrepare?.();releasePrepare=null;},selection:()=>({hip:selected?.hip_path,isNew:selected?.hip_is_new,cwd:projection.byId[session].cwd}),
unsaved(){rows[0]={...initialRow,hip_path:'C:/项目/旋转船体/untitled.hip',hip_is_new:true,label:'未保存工程'};selected={...rows[0]};publish();document.dispatchEvent(new Event('visibilitychange'));},
saveAs(){rows[0]={...rows[0],hip_path:'D:/交付/船体完成.hip',hip_is_new:false,workspace_path:'D:/交付'};document.dispatchEvent(new Event('visibilitychange'));},
restoreScene(){rows[0]={...initialRow};selected=rows[0];publish();document.dispatchEvent(new Event('visibilitychange'));},videoOpen(){view='video';notifyView();},videoClose:closeVideo,videoUpdate:updateVideo,rejectKey(value){rejectKey=value;},losePrompt(){losePrompt=true;},secretOnly:()=>secretOnly,opened,
holdList(){listGate=new Promise(resolve=>releaseList=resolve);},releaseList(){listGate=null;releaseList?.();releaseList=null;},holdLaunch(){launchGate=new Promise(resolve=>releaseLaunch=resolve);},releaseLaunch(){launchGate=null;releaseLaunch?.();releaseLaunch=null;},launchPhase(value){launchPhase=value;},loseActionReply(){loseActionReply=true;},lastLaunch(){return lastLaunch;},ticket(value){Object.assign(tickets.get(lastLaunch),value);},connection(value){generation=value?{id:value}:null;generationListeners.forEach(fn=>fn());},mode(value){mode=value;native=new Map([[session,{running:value==='working'}],['chat-b',{running:value==='occupied'}]]);nativeListeners.forEach(fn=>fn());document.dispatchEvent(new Event('visibilitychange'));},
hidden(value){hidden=value;document.dispatchEvent(new Event('visibilitychange'));},preset(value){projection={...projection,byId:{[session]:{...projection.byId[session],projectionValues:{agentPreset:value}}}};publish();},dark(value){document.body.toggleAttribute('data-ds-dark-theme',value);},ready:true};
Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>hidden?'hidden':'visible'});
`
const html=`<!doctype html><html><head><meta charset="utf-8">${css.map(name=>`<link rel="stylesheet" href="/sdk/${name}">`).join('')}
<style>${nativeThemeCss}</style>\n<style>body{margin:0;background:#f5f6f8;color:#25282d;font-family:'Microsoft YaHei UI',sans-serif}body[data-ds-dark-theme]{background:#191c20;color:#e7e9ec}.fixture-surface{margin:60px auto;padding:28px;max-width:800px;min-height:390px;border:1px solid #929ba326;border-radius:16px;background:var(--dsw-alias-bg-base,#fff)}body[data-ds-dark-theme] .fixture-surface{background:#24272b}.fixture-toolbar{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #929ba326;padding-bottom:16px;gap:16px}.fixture-caption{font-size:12px;color:#939aa4;margin-top:240px}.fixture-title{font-size:18px;margin:0 0 26px}.fixture-settings-modal{width:min(760px,calc(100vw - 32px))}</style>
<script>window.fixtureSdk=new Promise(resolve=>{window.__ModuleLoader__={create:options=>{resolve(options.staticModules);throw Error('Isolated component fixture: no Host application boot')}}})</script>
<script type="module" src="/sdk/${script}"></script></head><body><div id="root" hidden></div><main class="fixture-surface"><h1 class="fixture-title">Houdini 工程</h1><div id="fixture"></div><p class="fixture-caption">使用配套 DSH 的真实 React 与插件自有控件 · 无模型请求</p></main><script type="module">${fixture}</script></body></html>`
const server=http.createServer(async(request,response)=>{try{const url=new URL(request.url,'http://127.0.0.1');if(url.pathname==='/'){response.setHeader('Content-Type','text/html;charset=utf-8');response.end(html);return}if(!url.pathname.startsWith('/sdk/')){response.writeHead(404);response.end();return}const file=path.resolve(dist,url.pathname.slice(5));if(!file.startsWith(dist+path.sep))throw Error('invalid path');response.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.woff2')?'font/woff2':'application/octet-stream');response.end(await fs.readFile(file))}catch(error){response.writeHead(404);response.end(String(error))}})
const userData=path.join(scratch.directory,'browser')
let browser,browserClosed,browserDidClose=false,socket,sequence=0;const pending=new Map()
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function call(method,params={}){const id=++sequence;const result=new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method))},10000);pending.set(id,data=>{clearTimeout(timer);pending.delete(id);data.error?reject(Error(JSON.stringify(data.error))):resolve(data.result)})});socket.send(JSON.stringify({id,method,params}));return result}
async function evaluate(expression){const value=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!value.exceptionDetails,JSON.stringify(value.exceptionDetails));return value.result.value}
async function until(expression){for(let n=0;n<150;n++){if(await evaluate('Boolean('+expression+')'))return;await sleep(100)}throw Error('Not settled: '+expression)}
async function click(selector){const box=await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e)throw Error('Missing '+${JSON.stringify(selector)});if(!e.getClientRects().length)throw Error('Hidden '+${JSON.stringify(selector)});e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);await call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...box});await call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...box});await sleep(120)}
async function section(name){const selector='[data-houdini-menu-section="'+name+'"]';if(!await evaluate('document.querySelector('+JSON.stringify(selector)+').open'))await click('[data-houdini-menu-toggle="'+name+'"]');await until('document.querySelector('+JSON.stringify(selector)+').open')}
async function projectAction(name){await section(['clear','prepareBridge'].includes(name)?'management':'project');await click('[data-houdini-project-action="'+name+'"]')}
async function key(key,code,virtual){await call('Input.dispatchKeyEvent',{type:'keyDown',key,code,windowsVirtualKeyCode:virtual,...(key==='Enter'?{text:'\r'}:key===' '?{text:' '}:{} )});await call('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode:virtual});await sleep(80)}
async function screenshot(name){const shot=await call('Page.captureScreenshot',{format:'png'});await fs.writeFile(path.join(output,name+'.png'),Buffer.from(shot.data,'base64'))}
const primaryColors={}
let succeeded=false
async function primaryContrast(selector,label){
 const color=await evaluate(`(()=>{const s=getComputedStyle(document.querySelector(${JSON.stringify(selector)}));const lum=c=>{const v=c.match(/[0-9.]+/g).slice(0,3).map(Number).map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722};const a=lum(s.color),b=lum(s.backgroundColor);return{color:s.color,background:s.backgroundColor,contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)}})()`)
 assert(color.contrast>=4.5,label+' primary text must remain readable: '+JSON.stringify(color));primaryColors[label]=color
}
try{
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve)})
 let executable
 for(const file of ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe']){try{await fs.access(file);executable=file;break}catch{}}
 assert(executable,'Microsoft Edge is required for this owned browser fixture')
 browser=spawn(executable,['--headless=new','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+userData,'http://127.0.0.1:'+server.address().port],{windowsHide:true,stdio:'ignore'})
 browserClosed=new Promise(resolve=>browser.once('close',()=>{browserDidClose=true;resolve()}))
 await new Promise((resolve,reject)=>{browser.once('spawn',resolve);browser.once('error',reject)})
 let port
 for(let n=0;n<200;n++){try{port=Number((await fs.readFile(path.join(userData,'DevToolsActivePort'),'utf8')).split('\n')[0]);break}catch{await sleep(100)}}
 assert(port,'Owned Edge did not create a debugging endpoint')
 let target
 for(let n=0;n<100;n++){const targets=await(await fetch('http://127.0.0.1:'+port+'/json')).json();target=targets.find(item=>item.type==='page'&&item.url.startsWith('http://127.0.0.1:'));if(target)break;await sleep(100)}
 assert(target,'Owned fixture tab missing');socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}));socket.addEventListener('message',event=>{const value=JSON.parse(event.data);pending.get(value.id)?.(value)})
 await call('Emulation.setDeviceMetricsOverride',{width:1080,height:720,deviceScaleFactor:1,mobile:false});await until('window.fixture?.ready&&document.querySelector("[data-houdini-project-label]")')
 await until('document.querySelector("[data-houdini-project-label]").dataset.state==="unbound"');await screenshot('unbound-wide')
 // A bottom composer anchor makes the native menu flip upward. Loading must
 // not move its fixed project actions, including in that worst-case placement.
 await evaluate('fixture.holdList();document.querySelector(".fixture-toolbar").style.cssText="position:fixed;bottom:24px;left:40px;right:40px"')
 await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-action=new]")&&!document.querySelector("[data-houdini-project-action=new]").closest("[role=menuitem]").disabled')
 const actionRect=()=>evaluate(`(()=>{const e=document.querySelector('[data-houdini-project-action=new]').closest('[role=menuitem]'),r=e.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height,disabled:e.disabled}})()`)
 await sleep(200);const loadingRect=await actionRect();await screenshot('loading-fixed-actions')
 await evaluate('fixture.releaseList()');await until('document.querySelectorAll("[data-houdini-target]").length===2');await sleep(200)
 assert.deepEqual(await actionRect(),loadingRect,'Async candidate insertion must preserve New action position and availability')
 const menuColors=[]
 for(const dark of [false,true]){
  await evaluate('fixture.dark('+dark+')')
  const material=await evaluate(`(()=>{const e=document.querySelector('.dsh-houdini-menu-surface');const c=getComputedStyle(e);const probe=document.createElement('div');probe.style.background='var(--dsw-alias-bg-layer-2)';document.body.appendChild(probe);const expected=getComputedStyle(probe).backgroundColor;probe.remove();return{background:c.backgroundColor,opacity:c.opacity,expected,material:getComputedStyle(document.body).getPropertyValue('--dsw-menu-surface-fill').trim()}})()`)
  assert.equal(material.background,material.expected,'menu uses the official opaque surface, not its translucent menu material')
  assert.equal(material.opacity,'1')
  assert(!material.background.startsWith('rgba('),'popup backing is fully opaque')
  assert.match(material.material,/^#[0-9a-f]{8}$/i,'fixture consumes the actual alpha-valued official menu material')
  menuColors.push({dark,...material});await screenshot('choose-'+(dark?'dark':'light')+'-opaque')
 }
 await evaluate('fixture.dark(false)')
 await fs.writeFile(path.join(output,'popup-colors.json'),JSON.stringify({sdkVersion,menuColors},null,2))
 await screenshot('choose-wide')
 assert.equal(await evaluate('document.querySelector("[data-houdini-target]").dataset.houdiniTarget'),'a'.repeat(32))
 await key('Home','Home',36)
 assert.equal(await evaluate('document.activeElement.querySelector("[data-houdini-project-action]").dataset.houdiniProjectAction'),'pluginUpdates','an available update has a visible keyboard-reachable entry')
 await key('ArrowDown','ArrowDown',40)
 assert.equal(await evaluate('document.activeElement.dataset.houdiniMenuToggle'),'project')
 await key('Enter','Enter',13);await until('!document.querySelector("[data-houdini-menu-section=project]").open')
 await key(' ','Space',32);await until('document.querySelector("[data-houdini-menu-section=project]").open')
 await key('Enter','Enter',13);await until('!document.querySelector("[data-houdini-menu-section=project]").open')
 await key('ArrowDown','ArrowDown',40);assert.equal(await evaluate('document.activeElement.dataset.houdiniMenuToggle'),'management','closed project actions are skipped')
 await key('ArrowDown','ArrowDown',40)
 assert.equal(await evaluate('document.activeElement.querySelector("[data-houdini-target]").dataset.houdiniTarget'),'a'.repeat(32),'keyboard reaches the visible candidate, never a folded action')
 await key('Enter','Enter',13)
 await sleep(100)
 assert.equal(await evaluate('fixture.calls.filter(row=>row.method==="houdiniTargets/select").length'),1,'Enter invokes selection: '+JSON.stringify(await evaluate('fixture.calls')))
 await until('document.querySelector("[data-houdini-project-label]").dataset.state==="ready"&&document.querySelector("[data-houdini-project-label]").getAttribute("aria-expanded")==="false"')
 await evaluate('document.querySelector(".fixture-toolbar").style.cssText=""');await screenshot('ready-wide')
 await evaluate('fixture.unsaved()');await until('document.querySelector("[data-houdini-project-name]").textContent==="未保存工程"')
 const selectedBeforeSave=await evaluate('fixture.selection()')
 await evaluate('fixture.saveAs()');await until('document.querySelector("[data-houdini-project-name]").textContent==="船体完成.hip"')
 await click('[data-houdini-project-label]');await until('document.querySelector(".dsh-houdini-target-current")?.textContent.includes("船体完成.hip")')
 assert.equal(await evaluate('document.querySelector("[data-houdini-project-info=hip]").textContent.includes("D:/交付/船体完成.hip")'),true)
 assert.deepEqual(await evaluate('[...document.querySelectorAll(".dsh-houdini-target-group")].map(e=>e.textContent)'),['其他工程'])
 assert.equal(await evaluate('document.querySelector("[data-houdini-target]").dataset.houdiniTarget'),'a'.repeat(32))
 assert.deepEqual(await evaluate('fixture.selection()'),selectedBeforeSave,'Save As presentation leaves native selection and cwd unchanged')
 assert.equal(await evaluate(`document.querySelectorAll('[data-houdini-target="${'a'.repeat(32)}"]').length`),1,'current scene appears once')
 await screenshot('save-as-current-scene')
 await section('project');assert.equal(await evaluate('document.querySelector("[data-houdini-project-info=cwd]").textContent'),'C:/项目/旋转船体')
 await screenshot('project-details-expanded')
 await projectAction('reopen');await until('document.querySelector("[aria-label=\\"Houdini 工程路径\\"]")?.value==="D:/交付/船体完成.hip"')
 await screenshot('reopen-current-saved-path')
 await click('[aria-label="关闭打开工程对话框"]');await until('!document.querySelector("[data-houdini-project-dialog]")')
 await evaluate('fixture.restoreScene()');await until('document.querySelector("[data-houdini-project-name]").textContent==="船体.hip"')
 // One current window needs no duplicate row or fixed-height empty list.
 await evaluate('fixture.onlyCurrent(true)');await click('[data-houdini-project-label]');await until('document.querySelectorAll("[data-houdini-target]").length===1')
 assert.equal(await evaluate('document.querySelector(".dsh-houdini-target-choices").getBoundingClientRect().height'),0)
 assert(await evaluate('document.querySelector(".dsh-houdini-target-menu").getBoundingClientRect().height<240'))
 const sectionRect=()=>evaluate('(()=>{const r=document.querySelector("[data-houdini-menu-toggle=project]").getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height}})()')
 const pinned=await sectionRect();await screenshot('compact-single-current')
 await evaluate('fixture.onlyCurrent(false)');await until('document.querySelectorAll("[data-houdini-target]").length===2')
 assert.deepEqual(await sectionRect(),pinned,'a new candidate cannot move the project disclosure')
 assert.equal(await evaluate('document.querySelector("[data-houdini-menu-section=project]").open'),false)
 await evaluate('fixture.reverse(true)');await sleep(150)
 assert.equal(await evaluate('document.querySelector("[data-houdini-menu-section=project]").open'),false,'refresh does not open a user-collapsed section')
 await evaluate('fixture.reverse(false)')
 // Pointer-down owns the expected scene. A refresh before release must not
 // silently select the new HIP/epoch now rendered in that same window row.
 const other='[data-houdini-target="'+ 'f'.repeat(32)+'"]'
 const press=await evaluate('(()=>{const r=document.querySelector('+JSON.stringify(other)+').getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()')
 await call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...press})
 await evaluate('fixture.otherScene()');await until('document.querySelector('+JSON.stringify(other)+').textContent.includes("changed.hip")')
 await call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...press})
 await sleep(250)
 const pressCalls=await evaluate('fixture.calls.filter(row=>row.method==="houdiniTargets/select")')
 assert([1,2].includes(pressCalls.length),'a changed row admits at most one original click')
 if(pressCalls.length===2){
  const pressedSelection=pressCalls.at(-1).input
  assert.equal(pressedSelection.expectedHip,'D:/岩石实验/石群.hip');assert.equal(pressedSelection.sceneEpoch,'2'.repeat(32))
  await until('document.querySelector(".dsh-houdini-target-message")?.textContent.includes("scene changed")')
 }
 assert.equal(await evaluate('fixture.selection().hip'),'C:/项目/旋转船体/船体.hip','either native cancellation or the old expected identity must reject retargeting')
 await screenshot('pressed-scene-change-rejected')
 await evaluate('fixture.restoreOther()');await key('Escape','Escape',27)
 await until('!document.querySelector(".dsh-houdini-target-menu")')
 assert.equal(await evaluate('document.activeElement.hasAttribute("data-houdini-project-label")'),true,'Escape returns focus to the anchor')


 // New stays usable during a slow list request. Its late response cannot
 // reopen the selector after the native project action has been chosen.
 await evaluate('fixture.holdList()');await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-action=new]")&&!document.querySelector("[data-houdini-project-action=new]").closest("[role=menuitem]").disabled')
 await projectAction('new');await until('document.querySelector("[data-houdini-project-dialog]")&&document.querySelector("[aria-label=\\"Houdini 版本\\"]")?.value')
 await screenshot('new-scene-dialog')
 await evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(e=>(/^(打开|新建)并绑定$/).test(e.textContent));if(!button||button.disabled)throw Error('Launch action unavailable');button.click()})()`)
 await until('fixture.calls.some(row=>row.method==="houdiniFrontend/projectAction"&&row.input.action==="new")')
 await evaluate('fixture.releaseList()');await sleep(250);assert.equal(await evaluate('document.querySelector("[data-houdini-project-label]").getAttribute("aria-expanded")'),'false','Late list response must not reopen the native project action menu')
 // Closing before the launch ticket response arrives must still detach that
 // exact ticket when it returns. The accepted process launch is not killed.
 await evaluate('fixture.launchPhase("preparing");fixture.holdLaunch()');await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-action=new]")')
 await projectAction('new');await until('document.querySelector("[data-houdini-project-dialog]")&&document.querySelector("[aria-label=\\"Houdini 版本\\"]")?.value')
 await evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(e=>(/^(打开|新建)并绑定$/).test(e.textContent));button.click()})()`)
 await until('fixture.calls.filter(row=>row.method==="houdiniFrontend/projectAction").length===2')
 await evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(e=>e.textContent==='停止等待');if(!button)throw Error('Stop observation unavailable');button.dataset.fixtureStop='true'})()`)
 await click('[data-fixture-stop]');await until('!document.querySelector("[data-houdini-project-dialog]")')
 await evaluate('fixture.releaseLaunch()');await until('fixture.calls.some(row=>row.method==="houdiniFrontend/projectLaunchDetach"&&row.input.id===fixture.lastLaunch())')
 // Initial admission can be lost, while its exact request already exists on
 // the Host. Reconnect observes that ticket and never submits another launch.
 await evaluate('fixture.launchPhase("preparing");fixture.loseActionReply()');await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-action=new]")')
 await projectAction('new');await until('document.querySelector("[data-houdini-project-dialog]")&&document.querySelector("[aria-label=\\"Houdini 版本\\"]")?.value')
 await evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(e=>(/^(打开|新建)并绑定$/).test(e.textContent));button.click()})()`)
 await until('document.querySelector("[data-houdini-launch-stage]")?.textContent.includes("Host: 已记录启动请求")')
 const observedLaunch=await evaluate('fixture.lastLaunch()'),actionCount=await evaluate('fixture.calls.filter(row=>row.method==="houdiniFrontend/projectAction").length')
 await evaluate('fixture.ticket({phase:"waiting",stage:"capturing",message:"Host: 已读取实际启动场景",elapsedMs:42000})')
 await until('document.querySelector("[data-houdini-launch-stage=capturing]")?.textContent.includes("Host: 已读取实际启动场景")')
 assert.equal(await evaluate('document.querySelector("[data-houdini-project-dialog]").textContent.includes("已等待 42 秒")'),true)
 await screenshot('launch-real-stage')
 await evaluate('fixture.connection(0)');await until('document.querySelector("[data-houdini-project-dialog]")?.textContent.includes("连接已中断")')
 await evaluate('fixture.connection(2)');await until('document.querySelector("[data-houdini-launch-stage=capturing]")?.textContent.includes("Host: 已读取实际启动场景")')
 assert.equal(await evaluate('fixture.calls.filter(row=>row.method==="houdiniFrontend/projectAction").length'),actionCount,'reconnect does not spawn again')
 assert.equal(await evaluate(`fixture.calls.some(row=>row.method==='houdiniFrontend/projectLaunchDetach'&&row.input.id===${JSON.stringify(observedLaunch)})`),false,'connection cleanup is not a user detach')
 await evaluate('fixture.ticket({phase:"detached",message:"Host: 已停止自动连接"})')
 await until('[...document.querySelectorAll("button")].some(button=>button.textContent==="继续连接原窗口")')
 assert.equal(await evaluate('fixture.calls.filter(row=>row.method==="houdiniFrontend/projectLaunchResume").length'),0)
 await evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(e=>e.textContent==='继续连接原窗口');button.click()})()`)
 await until('fixture.calls.some(row=>row.method==="houdiniFrontend/projectLaunchResume")&&document.querySelector("[data-houdini-launch-stage=binding]")')
 await evaluate('fixture.ticket({phase:"ready",message:"",result:{sessionId:"chat-a",executorId:"fixture"}})');await until('!document.querySelector("[data-houdini-project-dialog]")')
 assert.equal(await evaluate('fixture.calls.filter(row=>row.method==="houdiniFrontend/projectAction").length'),actionCount)
 for(const [mode,state] of [['working','working'],['occupied','occupied'],['changed','changed'],['offline','offline']]){
   await evaluate(`fixture.mode(${JSON.stringify(mode)})`);await until(`document.querySelector('[data-houdini-project-label]').dataset.state===${JSON.stringify(state)}`);await screenshot(state+'-wide')
   if(mode==='working'){
     await click('[data-houdini-project-label]');await until('document.querySelectorAll("[data-houdini-target]").length===2')
     assert.equal(await evaluate(`document.querySelector('[data-houdini-target="${'a'.repeat(32)}"]').dataset.state`),'working')
     assert.equal(await evaluate(`document.querySelector('[data-houdini-target="${'f'.repeat(32)}"]').dataset.state`),'ready','A working on its selected target cannot label an unrelated idle B candidate as its work')
     await screenshot('working-candidates-wide');await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-label]").getAttribute("aria-expanded")==="false"')
   }
 }
 await evaluate('fixture.mode("ready");fixture.hidden(true)');await until('document.querySelector("[data-houdini-project-label]").dataset.state==="unknown"');await screenshot('hidden-unknown')
 await evaluate('fixture.hidden(false);fixture.dark(true)');await until('document.querySelector("[data-houdini-project-label]").dataset.state==="ready"')
 await call('Emulation.setDeviceMetricsOverride',{width:420,height:720,deviceScaleFactor:1,mobile:false});await click('[data-houdini-project-label]');await until('document.querySelectorAll("[data-houdini-target]").length===2');await screenshot('choose-narrow-dark')
 const clear=await evaluate(`(()=>{const e=[...document.querySelectorAll('[role="menuitem"]')].find(e=>e.textContent.includes('取消此对话'));if(!e)throw Error('clear item missing');e.dataset.fixtureClear='true';return true})()`);assert(clear)
 await section('management');await click('[data-fixture-clear]');await until('document.querySelector("[data-houdini-project-label]").dataset.state==="unbound"')
 await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-action=prepareBridge]")')
 await evaluate('fixture.failPrepare(true);fixture.holdPrepare()');await projectAction('prepareBridge')
 await click('[data-houdini-menu-toggle=management]');await until('!document.querySelector("[data-houdini-menu-section=management]").open')
 assert.equal(await evaluate('document.querySelector(".dsh-houdini-target-message").innerText.includes("正在安装或更新")'),true,'progress remains visible outside the management disclosure')
 await evaluate('fixture.releasePrepare()');await until('document.querySelector(".dsh-houdini-target-message")?.innerText.includes("未能确认")')
 assert.equal(await evaluate('document.body.innerText.includes("Command failed:")'),false,'technical installation failure is folded by default')
 await click('.dsh-houdini-target-error>summary');assert.equal(await evaluate('document.querySelector(".dsh-houdini-target-error").innerText.includes("access denied")'),true)
 await screenshot('installation-error-folded-control')
 await evaluate('fixture.failPrepare(false)');await projectAction('prepareBridge');await until('document.querySelector(".dsh-houdini-target-menu")?.textContent.includes("夹具：Houdini 组件已准备")')
 assert.equal(await evaluate('fixture.calls.find(row=>row.method==="houdiniFrontend/prepareBridge")?.input.sessionId'),'chat-a','first setup remains scoped to the selected Houdini session')
 await screenshot('bridge-setup-in-menu')
 await evaluate('document.querySelectorAll(".dsh-houdini-toast button").forEach(button=>button.click())')
 await section('management');await click('[data-houdini-project-action=pluginUpdates]')
 await until('document.querySelector("[data-houdini-plugin-updates=available]")')
 assert.equal(await evaluate('document.body.innerText.includes("可以继续使用")'),true)
 assert.equal(await evaluate('document.querySelector("[data-houdini-update-notes]").textContent'),'查看更新方法与说明')
 assert.equal(await evaluate('document.body.innerText.includes("0.2.1-rc.5")'),false,'version details stay folded for ordinary users')
 await primaryContrast('[data-houdini-update-notes]','dark-update-notes')
 await screenshot('plugin-update-optional-narrow-dark')
 await call('Emulation.setDeviceMetricsOverride',{width:1080,height:720,deviceScaleFactor:1,mobile:false});await evaluate('fixture.dark(false)')
 await primaryContrast('[data-houdini-update-notes]','light-update-notes')
 await screenshot('plugin-update-optional-wide-light')
 await evaluate('fixturePluginUpdate("unknown");[...document.querySelectorAll("button")].find(e=>e.textContent==="重新检查").click()')
 await until('document.querySelector("[data-houdini-plugin-updates=unknown]")')
 assert.equal(await evaluate('document.querySelector("[data-houdini-update-notes]")===null'),true,'failed update lookup has no installation action')
 await screenshot('plugin-update-unavailable-network')
 await key('Escape','Escape',27);await until('!document.querySelector("[data-houdini-plugin-updates]")')
 await evaluate('fixture.preset("standard")');await until('!document.querySelector("[data-houdini-project-label]")&&!document.querySelector("[data-houdini-project-dialog]")')
 await screenshot('standard-mode-clean')
 await evaluate('fixture.preset("houdini")');await until('document.querySelector("[data-houdini-project-label]")')
 // Real public SDK modal layers: deterministic configuration and write-only secrets.
 await call('Emulation.setDeviceMetricsOverride',{width:1080,height:900,deviceScaleFactor:1,mobile:false})
 await evaluate('fixture.dark(false);fixture.videoOpen()');await until('document.querySelector("[data-houdini-video-status]")?.textContent.includes("等待安全录入")')
 await primaryContrast('[data-houdini-video-save-config]','light-save-config')
 assert(await evaluate('document.querySelectorAll("[data-houdini-video-settings] input,[data-houdini-video-settings] select").length>0'))
 assert.equal(await evaluate('document.querySelector("[data-houdini-video-guide]")===null'),true)
 await screenshot('tutorial-status')
 await click('[data-houdini-video-key]');await until('document.querySelector("[data-houdini-video-credential] input")===document.activeElement')
 assert.equal(await evaluate('document.activeElement.type'), 'password')
 assert.equal(await evaluate('document.activeElement.autocomplete'), 'new-password')
 await call('Input.insertText',{text:'fixture-only-private-key'});await screenshot('tutorial-secret-native-modal')
 await primaryContrast('[data-houdini-video-save-key]','light-save')
 const savePoint=await evaluate('(()=>{const r=document.querySelector("[data-houdini-video-save-key]").getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()')
 await call('Input.dispatchMouseEvent',{type:'mouseMoved',...savePoint});await sleep(100)
 await primaryContrast('[data-houdini-video-save-key]','light-save-hover')
 await evaluate('fixture.dark(true)');await primaryContrast('[data-houdini-video-save-key]','dark-save-hover')
 await call('Input.dispatchMouseEvent',{type:'mouseMoved',x:10,y:10});await sleep(100)
 await primaryContrast('[data-houdini-video-save-key]','dark-save')
 await screenshot('tutorial-secret-native-modal-dark')
 await evaluate('fixture.dark(false)')
 assert.equal(await evaluate('document.body.innerText.includes("fixture-only-private-key")'),false)
 await evaluate('fixture.rejectKey(true)');await click('[data-houdini-video-save-key]')
 await until('document.querySelector("[data-houdini-video-credential]")?.textContent.includes("Native credentials: reference is read-only")')
 assert.equal(await evaluate('document.querySelector("[data-houdini-video-credential] input").value'),'')
 assert.equal(await evaluate('fixture.calls.filter(row=>row.method==="session/prompt").length'),0)
 await evaluate('fixture.rejectKey(false);document.querySelector("[data-houdini-video-credential] input").focus()')
 await call('Input.insertText',{text:'fixture-only-private-key'});await click('[data-houdini-video-save-key]')
 await until('!document.querySelector("[data-houdini-video-credential]")&&document.querySelector("[data-houdini-video-status]")?.textContent.includes("配置已保存，实际效果以试转录为准")')
 assert.equal(await evaluate('fixture.secretOnly()'),true,'only write-only native credentials receive the fake secret')
 assert.equal(await evaluate('JSON.stringify(fixture.calls).includes("fixture-only-private-key")'),false)
 await screenshot('tutorial-key-configured')
 await click('[data-houdini-video-key]');await until('document.querySelector("[data-houdini-video-credential] input")===document.activeElement')
 assert.equal(await evaluate('document.activeElement.value'),'','stored credentials never reappear in the field')
 await call('Input.insertText',{text:'fixture-only-private-key'})
 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27})
 await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27})
 await until('!document.querySelector("[data-houdini-video-credential]")&&document.querySelector("[data-houdini-video-settings]")')
 await click('[data-houdini-video-key]');await until('document.querySelector("[data-houdini-video-credential] input")===document.activeElement')
 assert.equal(await evaluate('document.activeElement.value'),'','cancelled secret drafts are discarded')
 await evaluate('fixture.videoUpdate({endpoint:"http://127.0.0.1:9877/v1/audio/transcriptions",credentialRef:"DSH_HOUDINI_ASR_NEW_API_KEY"})')
 await until('!document.querySelector("[data-houdini-video-credential]")&&document.querySelector("[data-houdini-video-settings]").textContent.includes("9877")')
 await click('[data-houdini-video-model]')
 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:2});await call('Input.dispatchKeyEvent',{type:'keyUp',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:2})
 await call('Input.insertText',{text:'direct-asr'});await click('[data-houdini-video-save-config]')
 await until('document.querySelector("[data-houdini-video-settings]").textContent.includes("配置已保存")')
 const direct=await evaluate('fixture.calls.find(row=>row.method==="houdiniFrontend/videoConfigure").input')
 assert.equal(direct.model,'direct-asr');assert.equal(direct.expected_revision,2)
 assert.equal(await evaluate('fixture.calls.filter(row=>row.method==="session/prompt").length'),0,'direct settings never invoke an Agent')
 await evaluate('fixture.preset("standard")');await until('document.querySelector("[data-houdini-video-settings]")')
 await evaluate('fixture.videoClose();fixture.preset("houdini")');await until('document.querySelector("[data-houdini-project-label]")')
 const calls=await evaluate('fixture.calls');assert.equal(calls.filter(row=>row.method==='houdiniTargets/select').length,pressCalls.length);assert.equal(calls.filter(row=>row.method==='houdiniTargets/clear').length,1)
 await fs.writeFile(path.join(output,'result.json'),JSON.stringify({ok:true,exactSdk:sdkVersion,pluginControls:true,realReact:true,stableFixedActions:true,newAvailableWhileLoading:true,candidateActivityIsolation:true,lateLaunchTicketDetached:true,modeIsolation:true,tutorial:{directConfiguration:true,nativeCredentialModal:true,secretOnlyInCredentials:true,nestedEscape:true,storedKeyNeverRead:true,changedServiceClosesOldDraft:true,allModeSettings:true,primaryColors},loadingRect,compactDisclosures:true,hiddenActionsSkipped:true,oneCurrentScene:true,sceneChangeCannotRetarget:true,nativeChangedRowClickDispatched:pressCalls.length===2,select:pressCalls.length,clear:1,states:['unbound','ready','working','occupied','changed','offline','unknown'],screenshots:(await fs.readdir(output)).filter(name=>name.endsWith('.png'))},null,2))
 console.log('PASS exact DSH React + plugin controls: selection/clear, states and narrow dark layout: '+output)
 succeeded=true
} catch(error){if(socket?.readyState===1){try{await screenshot('failure');await fs.writeFile(path.join(output,'failure.txt'),await evaluate('document.body.innerText'))}catch{}}throw error}
finally{
 if(socket?.readyState===1){try{await call('Browser.close')}catch{}socket.close()}
 if(browser){for(let n=0;n<50&&!browserDidClose;n++)await sleep(100);if(!browserDidClose)browser.kill();await browserClosed}
 if(server.listening)await new Promise(resolve=>server.close(resolve))
 try{await scratch.finish(succeeded?'success':'failed')}finally{await evidence.finish(succeeded?'success':'failed')}
}
