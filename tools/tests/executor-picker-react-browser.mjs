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
const root=path.resolve('.'),runtime=path.resolve(process.argv[2]??'')
assert(process.argv[2],'Pass the exact prepared runtime root')
const dist=path.join(runtime,'node_modules/@deepseek-ai/dsh-web-frontend/dist')
const sdkVersion=JSON.parse(await fs.readFile(path.join(dist,'../package.json'),'utf8')).version
const original=await fs.readFile(path.join(dist,'index.html'),'utf8')
const script=original.match(/src="\.\/([^\"]+\.js)"/)[1]
const css=[...original.matchAll(/href="\.\/([^\"]+\.css)"/g)].map(match=>match[1])
const source=await fs.readFile(path.join(root,'client.js'),'utf8')
const code=source.slice(source.indexOf('    function Button('),source.indexOf('    // >>> houdini-node-delivery'))
const videoCode=source.slice(source.indexOf('    function createVideoSettings('),source.indexOf('    function createSupportReporter('))
const styles=source.slice(source.indexOf('    var shellCss ='),source.indexOf('    var shellCssId ='))
const output=await fs.mkdtemp(path.join(root,'tools/out/target-chip-react-'))
const fixture=`
const sdk=await window.fixtureSdk;
const React=sdk.react;
if(!React?.createElement||!sdk['react-dom/client']?.createRoot)throw Error('Exact DSH React SDK missing');
const style=document.createElement('style');style.textContent=new Function(${JSON.stringify(styles+';return shellCss;')})();document.head.appendChild(style);
const factories=new Function('React','require',${JSON.stringify(code+videoCode+';return {createHoudiniDesktopUi,createVideoSettings};')})(React,name=>{if(!sdk[name])throw Error('Unsupported public SDK '+name);return sdk[name]});
const createUi=factories.createHoudiniDesktopUi;
let selected=null,session='chat-a',hidden=false,mode='ready',listGate=null,releaseList=null,launchGate=null,releaseLaunch=null;
let generation={id:1},launchPhase='ready',loseActionReply=false,lastLaunch=null;
const tickets=new Map(),listeners=new Set(),nativeListeners=new Set(),generationListeners=new Set(),calls=[];
const viewListeners=new Set(),formListeners=new Set(),credentialEvents=new Set(),opened=[];
let view='project',videoRevision={revision:1,status:'ready',writable:true},rejectKey=false,losePrompt=false,secretOnly=true;
let videoFacts={revision:1,selected:{model:'fixture-asr',protocol:'openai-transcriptions'},defaults:{concurrency:2,requestsPerSecond:1},diagnostics:[],
service:{displayName:'本机转录',model:'fixture-asr',protocol:'openai-transcriptions',endpoint:'http://127.0.0.1:9876/v1/audio/transcriptions',
authentication:'bearer',credentialRef:'DSH_HOUDINI_ASR_FIXTURE_API_KEY',credential:{configured:false,writable:true},dataLocation:'loopback',support:'unverified'},
adapters:[{id:'openai-transcriptions',label:'OpenAI 兼容文件转录'}]};
function notifyView(){viewListeners.forEach(fn=>fn());}
function closeVideo(){view='project';notifyView();}
function updateVideo(patch){videoFacts={...videoFacts,service:{...videoFacts.service,...patch}};videoRevision={...videoRevision,revision:videoRevision.revision+1};videoFacts.revision=videoRevision.revision;formListeners.forEach(fn=>fn());}
const ids={executor:'a'.repeat(32),runtime:'b'.repeat(32),epoch:'c'.repeat(32),registration:'d'.repeat(32)};
const rows=[{executor_id:ids.executor,runtime_id:ids.runtime,scene_epoch:ids.epoch,registration_id:ids.registration,scene_id:'e'.repeat(32),
hip_path:'C:/项目/旋转船体/船体.hip',hip_is_new:false,workspace_path:'C:/项目/旋转船体',houdini_version:'22.0.368',pid:8234,state:'registered',same_workspace:true,workbench:true},
{executor_id:'f'.repeat(32),runtime_id:'1'.repeat(32),scene_epoch:'2'.repeat(32),registration_id:'3'.repeat(32),scene_id:'4'.repeat(32),
hip_path:'D:/岩石实验/石群.hip',hip_is_new:false,workspace_path:'D:/岩石实验',houdini_version:'21.0.440',pid:5678,state:'registered',same_workspace:false,workbench:true}];
let native=new Map(),projection={byId:{[session]:{id:session,cwd:rows[0].workspace_path,blank:false,projectionValues:{agentPreset:'houdini'}}},projectionsBySession:{}};
function publish(){projection={...projection,projectionsBySession:{[session]:{values:{houdiniExecutorIdentity:selected?{target:selected,executorId:selected.executor_id,runtimeId:selected.runtime_id,sceneEpoch:selected.scene_epoch,hipPath:selected.hip_path,hipIsNew:false}:null}}}};listeners.forEach(fn=>fn());}
function presence(row){return{executorId:row.executor_id,runtimeId:mode==='changed'&&row===rows[0]?'9'.repeat(32):row.runtime_id,sceneEpoch:row.scene_epoch,
status:mode==='offline'?'offline':'online',observedAt:Date.now(),candidate:row,ownerSessionId:row===rows[0]?(mode==='occupied'?'chat-b':session):null,busy:mode==='jobs'&&row===rows[0],activeJobs:mode==='jobs'&&row===rows[0]?1:0,activeRequests:0};}
const connection={generation:{getSnapshot:()=>generation,subscribe:fn=>{generationListeners.add(fn);return()=>generationListeners.delete(fn)}},rpc:{call:async(_channel,method,payload)=>{calls.push({method,input:payload.args?.input,request:payload.args?.request,keyRef:payload.args?.ref});
if(method==='houdiniFrontend/videoSettings')return{ok:true,value:structuredClone(videoFacts)};
if(method==='houdiniFrontend/videoDiagnostics')return{ok:true,value:{dependencies:[],note:'仅检查夹具依赖'}};
if(method==='credentials/set'){
 secretOnly=secretOnly&&Object.keys(payload.args).sort().join(',')==='ref,value'&&payload.args.value==='fixture-only-private-key';
 if(rejectKey)return{ok:false,error:{message:'Native credentials: reference is read-only'}};
 videoFacts.service.credential.configured=true;credentialEvents.forEach(fn=>fn());return{ok:true};
}
if(method==='session/prompt'){if(losePrompt){losePrompt=false;throw Error('Fixture: prompt receipt lost')}return{ok:true,value:{accepted:true}};}
if(method==='houdiniFrontend/capabilities')return{ok:true,value:{desktop:true}};
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
if(method==='houdiniFrontend/prepareBridge')return{ok:true,value:{message:'夹具：Houdini 组件已准备；已有窗口未重启。'}};
if(method==='houdiniFrontend/projectPresence'){if(listGate)await listGate;return{ok:true,value:rows.map(presence)};}
if(method==='houdiniTargets/select'){selected=rows.find(row=>row.executor_id===payload.args.input.executorId);return{ok:true,value:{status:'selected',selectedTarget:selected}};}
if(method==='houdiniTargets/clear'){selected=null;return{ok:true,value:{selectedTarget:null}};}
return{ok:true,value:{}};}}};
const selection={key:session};
const owner={sessionStatus:{getSnapshot:()=>native,subscribe:fn=>{nativeListeners.add(fn);return()=>nativeListeners.delete(fn)}},adapter:{current:{getSnapshot:()=>selection,subscribe:()=>()=>{}}}};
const workbench=createUi(connection,owner,{refreshProjections:async()=>publish(),list:{getSnapshot:()=>projection,subscribe:fn=>{listeners.add(fn);return()=>listeners.delete(fn)}}});
const video=factories.createVideoSettings(connection,{get:()=>({getSnapshot:()=>videoRevision,subscribe:fn=>{formListeners.add(fn);return()=>formListeners.delete(fn)}})},owner,
{list:{getSnapshot:()=>projection,subscribe:fn=>{listeners.add(fn);return()=>listeners.delete(fn)}}},
{openSession:id=>{opened.push(id);closeVideo();}},{$on:(name,fn)=>{if(name!=='credentials/reference-updated')throw Error(name);credentialEvents.add(fn);return()=>credentialEvents.delete(fn);}});
const props={sessionId:session,useSessions:selector=>React.useSyncExternalStore(fn=>{listeners.add(fn);return()=>listeners.delete(fn)},()=>selector(projection))};
function App(){const preset=props.useSessions(state=>state.byId[session].projectionValues.agentPreset);const active=React.useSyncExternalStore(fn=>{viewListeners.add(fn);return()=>viewListeners.delete(fn)},()=>view);return React.createElement(React.Fragment,null,preset==='houdini'&&React.createElement(workbench.Lifecycle),React.createElement('div',{className:'fixture-toolbar'},React.createElement('span',null,'旋转船体'),React.createElement(workbench.Label,props)),preset==='houdini'&&active==='video'&&React.createElement(sdk['@deepseek-ai/dsh-client-ui-primitives'].Modal,{open:true,onClose:closeVideo,title:'设置',closeLabel:'关闭设置',shortcutModal:'settings',className:'fixture-settings-modal'},React.createElement(video,{close:closeVideo})));}
sdk['react-dom/client'].createRoot(document.querySelector('#fixture')).render(React.createElement(App));
window.fixture={calls,videoOpen(){view='video';notifyView();},videoClose:closeVideo,videoUpdate:updateVideo,rejectKey(value){rejectKey=value;},losePrompt(){losePrompt=true;},secretOnly:()=>secretOnly,opened,
holdList(){listGate=new Promise(resolve=>releaseList=resolve);},releaseList(){listGate=null;releaseList?.();releaseList=null;},holdLaunch(){launchGate=new Promise(resolve=>releaseLaunch=resolve);},releaseLaunch(){launchGate=null;releaseLaunch?.();releaseLaunch=null;},launchPhase(value){launchPhase=value;},loseActionReply(){loseActionReply=true;},lastLaunch(){return lastLaunch;},ticket(value){Object.assign(tickets.get(lastLaunch),value);},connection(value){generation=value?{id:value}:null;generationListeners.forEach(fn=>fn());},mode(value){mode=value;native=new Map([[session,{running:value==='working'}],['chat-b',{running:value==='occupied'}]]);nativeListeners.forEach(fn=>fn());document.dispatchEvent(new Event('visibilitychange'));},
hidden(value){hidden=value;document.dispatchEvent(new Event('visibilitychange'));},preset(value){projection={...projection,byId:{[session]:{...projection.byId[session],projectionValues:{agentPreset:value}}}};publish();},dark(value){document.body.toggleAttribute('data-ds-dark-theme',value);},ready:true};
Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>hidden?'hidden':'visible'});
`
const html=`<!doctype html><html><head><meta charset="utf-8">${css.map(name=>`<link rel="stylesheet" href="/sdk/${name}">`).join('')}
<style>:root{--dsw-alias-label-primary:#25282d;--dsw-alias-label-secondary:#5b626e;--dsw-alias-label-tertiary:#7c8490;--dsw-alias-menu-icon:#717985;--dsw-alias-bg-base:#fff;--dsw-alias-bg-layer-1:#f5f6f8;--dsw-alias-bg-layer-2:#fff;--dsw-alias-brand-primary:#416fca;--dsw-alias-button-primary-fill:#416fca;--dsw-alias-button-primary-hover:#3158a2;--dsw-alias-label-primary-foreground:#fff;--dsw-alias-label-on-brand:#fff;--dsw-focus-ring-color:#416fca;--dsw-menu-surface-fill:#fff;--dsw-menu-backdrop-filter:none;--dsw-alias-border-l1:#e5e8ec;--dsw-alias-border-l2:#d9dee5;--dsw-alias-border-l3:#e1e5eb;--dsw-alias-interactive-bg-hover:#f1f4f7;--dsw-alias-state-business-primary:#4d82d5;--dsw-radius-lg:12px;--dsw-radius-md:8px;--dsw-radius-sm:6px;--dsw-elevation-prominent:0 8px 30px #17233b26,0 1px 5px #17233b1c}body[data-ds-dark-theme]{--dsw-alias-label-primary:#e8ebef;--dsw-alias-label-secondary:#b1b8c3;--dsw-alias-label-tertiary:#929ca9;--dsw-alias-menu-icon:#b1b8c3;--dsw-alias-bg-base:#24272b;--dsw-alias-bg-layer-1:#1f2226;--dsw-alias-bg-layer-2:#282c32;--dsw-alias-brand-primary:#fff;--dsw-alias-button-primary-fill:#fff;--dsw-alias-button-primary-hover:#e5e5e5;--dsw-alias-label-primary-foreground:#141414;--dsw-menu-surface-fill:#2a2e34;--dsw-alias-border-l1:#3e444d;--dsw-alias-border-l2:#4c535e;--dsw-alias-border-l3:#3e444d;--dsw-alias-interactive-bg-hover:#363d47}body{margin:0;background:#f5f6f8;color:#25282d;font-family:'Microsoft YaHei UI',sans-serif}body[data-ds-dark-theme]{background:#191c20;color:#e7e9ec}.fixture-surface{margin:60px auto;padding:28px;max-width:800px;min-height:390px;border:1px solid #929ba326;border-radius:16px;background:var(--dsw-alias-bg-base,#fff)}body[data-ds-dark-theme] .fixture-surface{background:#24272b}.fixture-toolbar{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #929ba326;padding-bottom:16px;gap:16px}.fixture-caption{font-size:12px;color:#939aa4;margin-top:240px}.fixture-title{font-size:18px;margin:0 0 26px}.fixture-settings-modal{width:min(760px,calc(100vw - 32px))}</style>
<script>window.fixtureSdk=new Promise(resolve=>{window.__ModuleLoader__={create:options=>{resolve(options.staticModules);throw Error('Isolated component fixture: no Host application boot')}}})</script>
<script type="module" src="/sdk/${script}"></script></head><body><div id="root" hidden></div><main class="fixture-surface"><h1 class="fixture-title">Houdini 工程现场</h1><div id="fixture"></div><p class="fixture-caption">使用配套 DSH 的真实 React 与插件自有控件 · 无模型请求</p></main><script type="module">${fixture}</script></body></html>`
const server=http.createServer(async(request,response)=>{try{const url=new URL(request.url,'http://127.0.0.1');if(url.pathname==='/'){response.setHeader('Content-Type','text/html;charset=utf-8');response.end(html);return}if(!url.pathname.startsWith('/sdk/')){response.writeHead(404);response.end();return}const file=path.resolve(dist,url.pathname.slice(5));if(!file.startsWith(dist+path.sep))throw Error('invalid path');response.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.woff2')?'font/woff2':'application/octet-stream');response.end(await fs.readFile(file))}catch(error){response.writeHead(404);response.end(String(error))}})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
let executable
for(const file of ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe']){try{await fs.access(file);executable=file;break}catch{}}
assert(executable,'Microsoft Edge is required for this owned browser fixture')
const userData=path.join(output,'browser'),browser=spawn(executable,['--headless=new','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+userData,'http://127.0.0.1:'+server.address().port],{windowsHide:true,stdio:'ignore'})
let socket,sequence=0;const pending=new Map()
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function call(method,params={}){const id=++sequence;const result=new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method))},10000);pending.set(id,data=>{clearTimeout(timer);pending.delete(id);data.error?reject(Error(JSON.stringify(data.error))):resolve(data.result)})});socket.send(JSON.stringify({id,method,params}));return result}
async function evaluate(expression){const value=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!value.exceptionDetails,JSON.stringify(value.exceptionDetails));return value.result.value}
async function until(expression){for(let n=0;n<150;n++){if(await evaluate('Boolean('+expression+')'))return;await sleep(100)}throw Error('Not settled: '+expression)}
async function click(selector){const box=await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e)throw Error('Missing '+${JSON.stringify(selector)});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);await call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...box});await call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...box});await sleep(120)}
async function screenshot(name){const shot=await call('Page.captureScreenshot',{format:'png'});await fs.writeFile(path.join(output,name+'.png'),Buffer.from(shot.data,'base64'))}
const primaryColors={}
async function primaryContrast(selector,label){
 const color=await evaluate(`(()=>{const s=getComputedStyle(document.querySelector(${JSON.stringify(selector)}));const lum=c=>{const v=c.match(/[0-9.]+/g).slice(0,3).map(Number).map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722};const a=lum(s.color),b=lum(s.backgroundColor);return{color:s.color,background:s.backgroundColor,contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)}})()`)
 assert(color.contrast>=4.5,label+' primary text must remain readable: '+JSON.stringify(color));primaryColors[label]=color
}
try{
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
 await screenshot('choose-wide')
 assert.equal(await evaluate('document.querySelector("[data-houdini-target]").dataset.houdiniTarget'),'a'.repeat(32))
 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Home',code:'Home',windowsVirtualKeyCode:36});await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Home',code:'Home',windowsVirtualKeyCode:36})
 for(let n=0;n<3;n++){
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40})
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40})
 }
 await sleep(100)
 assert.equal(await evaluate('document.activeElement.querySelector("[data-houdini-target]").dataset.houdiniTarget'),'a'.repeat(32),'keyboard reaches the actual candidate')
 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13})
 await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13})
 await sleep(100)
 assert.equal(await evaluate('fixture.calls.filter(row=>row.method==="houdiniTargets/select").length'),1,'Enter invokes selection: '+JSON.stringify(await evaluate('fixture.calls')))
 await until('document.querySelector("[data-houdini-project-label]").dataset.state==="ready"&&document.querySelector("[data-houdini-project-label]").getAttribute("aria-expanded")==="false"')
 await evaluate('document.querySelector(".fixture-toolbar").style.cssText=""');await screenshot('ready-wide')
 // New stays usable during a slow list request. Its late response cannot
 // reopen the selector after the native project action has been chosen.
 await evaluate('fixture.holdList()');await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-action=new]")&&!document.querySelector("[data-houdini-project-action=new]").closest("[role=menuitem]").disabled')
 await click('[data-houdini-project-action=new]');await until('document.querySelector("[data-houdini-project-dialog]")&&document.querySelector("[aria-label=\\"Houdini 版本\\"]")?.value')
 await screenshot('new-scene-dialog')
 await evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(e=>e.textContent==='打开并绑定');if(!button||button.disabled)throw Error('Launch action unavailable');button.click()})()`)
 await until('fixture.calls.some(row=>row.method==="houdiniFrontend/projectAction"&&row.input.action==="new")')
 await evaluate('fixture.releaseList()');await sleep(250);assert.equal(await evaluate('document.querySelector("[data-houdini-project-label]").getAttribute("aria-expanded")'),'false','Late list response must not reopen the native project action menu')
 // Closing before the launch ticket response arrives must still detach that
 // exact ticket when it returns. The accepted process launch is not killed.
 await evaluate('fixture.launchPhase("preparing");fixture.holdLaunch()');await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-action=new]")')
 await click('[data-houdini-project-action=new]');await until('document.querySelector("[data-houdini-project-dialog]")&&document.querySelector("[aria-label=\\"Houdini 版本\\"]")?.value')
 await evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(e=>e.textContent==='打开并绑定');button.click()})()`)
 await until('fixture.calls.filter(row=>row.method==="houdiniFrontend/projectAction").length===2')
 await evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(e=>e.textContent==='停止等待');if(!button)throw Error('Stop observation unavailable');button.dataset.fixtureStop='true'})()`)
 await click('[data-fixture-stop]');await until('!document.querySelector("[data-houdini-project-dialog]")')
 await evaluate('fixture.releaseLaunch()');await until('fixture.calls.some(row=>row.method==="houdiniFrontend/projectLaunchDetach"&&row.input.id===fixture.lastLaunch())')
 // Initial admission can be lost, while its exact request already exists on
 // the Host. Reconnect observes that ticket and never submits another launch.
 await evaluate('fixture.launchPhase("preparing");fixture.loseActionReply()');await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-action=new]")')
 await click('[data-houdini-project-action=new]');await until('document.querySelector("[data-houdini-project-dialog]")&&document.querySelector("[aria-label=\\"Houdini 版本\\"]")?.value')
 await evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(e=>e.textContent==='打开并绑定');button.click()})()`)
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
 await click('[data-fixture-clear]');await until('document.querySelector("[data-houdini-project-label]").dataset.state==="unbound"')
 await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-action=prepareBridge]")')
 await click('[data-houdini-project-action=prepareBridge]');await until('document.querySelector(".dsh-houdini-target-menu")?.textContent.includes("夹具：Houdini 组件已准备")')
 assert.equal(await evaluate('fixture.calls.find(row=>row.method==="houdiniFrontend/prepareBridge")?.input.sessionId'),'chat-a','first setup remains scoped to the selected Houdini session')
 await screenshot('bridge-setup-in-menu')
 await evaluate('fixture.preset("standard")');await until('!document.querySelector("[data-houdini-project-label]")&&!document.querySelector("[data-houdini-project-dialog]")')
 await screenshot('standard-mode-clean')
 await evaluate('fixture.preset("houdini")');await until('document.querySelector("[data-houdini-project-label]")')
 // Real public SDK modal layers: configuration is a status page and secret
 // drafts stay inside the nested password control until credentials/set.
 await call('Emulation.setDeviceMetricsOverride',{width:1080,height:900,deviceScaleFactor:1,mobile:false})
 await evaluate('fixture.dark(false);fixture.videoOpen()');await until('document.querySelector("[data-houdini-video-status]")?.textContent.includes("等待安全录入")')
 await primaryContrast('[data-houdini-video-guide]','light-guide')
 assert.equal(await evaluate('document.querySelectorAll("[data-houdini-video-settings] input,[data-houdini-video-settings] select").length'),0)
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
 await until('!document.querySelector("[data-houdini-video-credential]")&&document.querySelector("[data-houdini-video-status]")?.textContent.includes("服务配置已保存")')
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
 await evaluate('fixture.losePrompt()');await click('[data-houdini-video-guide]')
 await until('document.querySelector("[data-houdini-video-guide]")?.textContent.includes("重试引导请求")')
 const firstPrompt=await evaluate('fixture.calls.find(row=>row.method==="session/prompt").request')
 assert.equal(firstPrompt.sessionId,'chat-a');assert.equal(firstPrompt.mode,'queue')
 await click('[data-houdini-video-guide]');await until('!document.querySelector("[data-houdini-video-settings]")&&fixture.opened.length===1')
 assert.deepEqual(await evaluate('fixture.calls.filter(row=>row.method==="session/prompt").map(row=>row.request.requestId)'),[firstPrompt.requestId,firstPrompt.requestId])
 assert.deepEqual(await evaluate('fixture.opened'),['chat-a'])
 await evaluate('fixture.videoOpen()');await until('document.querySelector("[data-houdini-video-settings]")')
 await evaluate('fixture.preset("standard")');await until('!document.querySelector("[data-houdini-video-settings]")')
 await evaluate('fixture.videoClose();fixture.preset("houdini")');await until('document.querySelector("[data-houdini-project-label]")')
 const calls=await evaluate('fixture.calls');assert.equal(calls.filter(row=>row.method==='houdiniTargets/select').length,1);assert.equal(calls.filter(row=>row.method==='houdiniTargets/clear').length,1)
 await fs.writeFile(path.join(output,'result.json'),JSON.stringify({ok:true,exactSdk:sdkVersion,pluginControls:true,realReact:true,stableFixedActions:true,newAvailableWhileLoading:true,candidateActivityIsolation:true,lateLaunchTicketDetached:true,modeIsolation:true,tutorial:{statusOnly:true,nativePrompt:true,sameRequestRetry:true,nativeCredentialModal:true,secretOnlyInCredentials:true,nestedEscape:true,storedKeyNeverRead:true,changedServiceClosesOldDraft:true,primaryColors},loadingRect,select:1,clear:1,states:['unbound','ready','working','occupied','changed','offline','unknown'],screenshots:(await fs.readdir(output)).filter(name=>name.endsWith('.png'))},null,2))
 console.log('PASS exact DSH React + plugin controls: selection/clear, states and narrow dark layout: '+output)
} catch(error){if(socket?.readyState===1){try{await screenshot('failure');await fs.writeFile(path.join(output,'failure.txt'),await evaluate('document.body.innerText'))}catch{}}throw error}
finally{if(socket?.readyState===1){try{await call('Browser.close')}catch{}socket.close()}for(let n=0;n<50&&browser.exitCode===null;n++)await sleep(100);if(browser.exitCode===null)browser.kill();server.close()}
