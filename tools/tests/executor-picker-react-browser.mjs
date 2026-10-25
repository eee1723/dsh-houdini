/** Real React + exact DSH Menu component fixture; no Host, account or Houdini.
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
const code=source.slice(source.indexOf('    function useHoudiniProject('),source.indexOf('    function createHoudiniTitleAction('))
const styles=source.slice(source.indexOf('    var shellCss ='),source.indexOf('    var shellCssId ='))
const output=await fs.mkdtemp(path.join(root,'tools/out/target-chip-react-'))
const fixture=`
const sdk=await window.fixtureSdk;
const React=sdk.react, ui=sdk['@deepseek-ai/dsh-client-ui-primitives'];
if(!React?.createElement||!sdk['react-dom/client']?.createRoot||!ui.Menu)throw Error('Exact DSH React/Menu SDK missing');
const style=document.createElement('style');style.textContent=new Function(${JSON.stringify(styles+';return shellCss;')})();document.head.appendChild(style);
const createUi=new Function('React','require',${JSON.stringify(code+';return createWorkbenchUi;')})(React,()=>ui);
let selected=null,session='chat-a',hidden=false,mode='ready',listGate=null,releaseList=null;
const listeners=new Set(),nativeListeners=new Set(),calls=[];
const ids={executor:'a'.repeat(32),runtime:'b'.repeat(32),epoch:'c'.repeat(32),registration:'d'.repeat(32)};
const rows=[{executor_id:ids.executor,runtime_id:ids.runtime,scene_epoch:ids.epoch,registration_id:ids.registration,scene_id:'e'.repeat(32),
hip_path:'C:/项目/旋转船体/船体.hip',hip_is_new:false,workspace_path:'C:/项目/旋转船体',houdini_version:'22.0.368',pid:8234,state:'registered',same_workspace:true,workbench:true},
{executor_id:'f'.repeat(32),runtime_id:'1'.repeat(32),scene_epoch:'2'.repeat(32),registration_id:'3'.repeat(32),scene_id:'4'.repeat(32),
hip_path:'D:/岩石实验/石群.hip',hip_is_new:false,workspace_path:'D:/岩石实验',houdini_version:'21.0.440',pid:5678,state:'registered',same_workspace:false,workbench:true}];
let native=new Map(),projection={byId:{[session]:{id:session,cwd:rows[0].workspace_path,blank:false,projectionValues:{agentPreset:'houdini'}}},projectionsBySession:{}};
function publish(){projection={...projection,projectionsBySession:{[session]:{values:{houdiniExecutorIdentity:selected?{target:selected,executorId:selected.executor_id,runtimeId:selected.runtime_id,sceneEpoch:selected.scene_epoch,hipPath:selected.hip_path,hipIsNew:false}:null}}}};listeners.forEach(fn=>fn());}
function presence(row){return{executorId:row.executor_id,runtimeId:mode==='changed'&&row===rows[0]?'9'.repeat(32):row.runtime_id,sceneEpoch:row.scene_epoch,
status:mode==='offline'?'offline':'online',observedAt:Date.now(),candidate:row,ownerSessionId:row===rows[0]?(mode==='occupied'?'chat-b':session):null,busy:mode==='jobs'&&row===rows[0],activeJobs:mode==='jobs'&&row===rows[0]?1:0,activeRequests:0};}
const connection={generation:{getSnapshot:()=>1,subscribe:()=>()=>{}},rpc:{call:async(_channel,method,payload)=>{calls.push({method,input:payload.args?.input});
if(method==='houdiniFrontend/capabilities')return{ok:true,value:{workbench:true}};
if(method==='houdiniFrontend/windowPin')return{ok:true,value:{pinned:false}};
if(method==='houdiniFrontend/projectPresence'){if(listGate)await listGate;return{ok:true,value:rows.map(presence)};}
if(method==='houdiniTargets/select'){selected=rows.find(row=>row.executor_id===payload.args.input.executorId);return{ok:true,value:{status:'selected',selectedTarget:selected}};}
if(method==='houdiniTargets/clear'){selected=null;return{ok:true,value:{selectedTarget:null}};}
return{ok:true,value:{}};}}};
const owner={sessionStatus:{getSnapshot:()=>native,subscribe:fn=>{nativeListeners.add(fn);return()=>nativeListeners.delete(fn)}},adapter:{current:{getSnapshot:()=>({key:session}),subscribe:()=>()=>{}}}};
const workbench=createUi(connection,owner,{refreshProjections:async()=>publish()});
const props={sessionId:session,useSessions:selector=>React.useSyncExternalStore(fn=>{listeners.add(fn);return()=>listeners.delete(fn)},()=>selector(projection))};
function App(){return React.createElement(React.Fragment,null,React.createElement(workbench.Lifecycle),React.createElement('div',{className:'fixture-toolbar'},React.createElement('span',null,'旋转船体'),React.createElement(workbench.Label,props)));}
sdk['react-dom/client'].createRoot(document.querySelector('#fixture')).render(React.createElement(App));
window.fixture={calls,holdList(){listGate=new Promise(resolve=>releaseList=resolve);},releaseList(){listGate=null;releaseList?.();releaseList=null;},mode(value){mode=value;native=new Map([[session,{running:value==='working'}],['chat-b',{running:value==='occupied'}]]);nativeListeners.forEach(fn=>fn());document.dispatchEvent(new Event('visibilitychange'));},
hidden(value){hidden=value;document.dispatchEvent(new Event('visibilitychange'));},dark(value){document.body.toggleAttribute('data-ds-dark-theme',value);},ready:true};
Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>hidden?'hidden':'visible'});
`
const html=`<!doctype html><html><head><meta charset="utf-8">${css.map(name=>`<link rel="stylesheet" href="/sdk/${name}">`).join('')}
<style>:root{--dsw-alias-label-primary:#25282d;--dsw-alias-label-secondary:#5b626e;--dsw-alias-label-tertiary:#7c8490;--dsw-alias-menu-icon:#717985;--dsw-alias-bg-base:#fff;--dsw-alias-bg-layer-1:#f5f6f8;--dsw-menu-surface-fill:#fff;--dsw-menu-backdrop-filter:none;--dsw-alias-border-l1:#e5e8ec;--dsw-alias-border-l2:#d9dee5;--dsw-alias-border-l3:#e1e5eb;--dsw-alias-interactive-bg-hover:#f1f4f7;--dsw-alias-state-business-primary:#4d82d5;--dsw-radius-lg:12px;--dsw-radius-md:8px;--dsw-radius-sm:6px;--dsw-elevation-prominent:0 8px 30px #17233b26,0 1px 5px #17233b1c}body[data-ds-dark-theme]{--dsw-alias-label-primary:#e8ebef;--dsw-alias-label-secondary:#b1b8c3;--dsw-alias-label-tertiary:#929ca9;--dsw-alias-menu-icon:#b1b8c3;--dsw-alias-bg-base:#24272b;--dsw-alias-bg-layer-1:#1f2226;--dsw-menu-surface-fill:#2a2e34;--dsw-alias-border-l1:#3e444d;--dsw-alias-border-l2:#4c535e;--dsw-alias-border-l3:#3e444d;--dsw-alias-interactive-bg-hover:#363d47}body{margin:0;background:#f5f6f8;color:#25282d;font-family:'Microsoft YaHei UI',sans-serif}body[data-ds-dark-theme]{background:#191c20;color:#e7e9ec}.fixture-surface{margin:60px auto;padding:28px;max-width:800px;min-height:390px;border:1px solid #929ba326;border-radius:16px;background:var(--dsw-alias-bg-base,#fff)}body[data-ds-dark-theme] .fixture-surface{background:#24272b}.fixture-toolbar{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #929ba326;padding-bottom:16px;gap:16px}.fixture-caption{font-size:12px;color:#939aa4;margin-top:240px}.fixture-title{font-size:18px;margin:0 0 26px}</style>
<script>window.fixtureSdk=new Promise(resolve=>{window.__ModuleLoader__={create:options=>{resolve(options.staticModules);throw Error('Isolated component fixture: no Host application boot')}}})</script>
<script type="module" src="/sdk/${script}"></script></head><body><div id="root" hidden></div><main class="fixture-surface"><h1 class="fixture-title">Houdini 工程现场</h1><div id="fixture"></div><p class="fixture-caption">使用配套 DSH 的真实 React 与原生菜单 · 无模型请求</p></main><script type="module">${fixture}</script></body></html>`
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
 await click('[data-houdini-target="'+ 'a'.repeat(32)+'"]');await until('document.querySelector("[data-houdini-project-label]").dataset.state==="ready"&&document.querySelector("[data-houdini-project-label]").getAttribute("aria-expanded")==="false"')
 await evaluate('document.querySelector(".fixture-toolbar").style.cssText=""');await screenshot('ready-wide')
 // New stays usable during a slow list request. Its late response cannot
 // reopen the selector after the native project action has been chosen.
 await evaluate('fixture.holdList()');await click('[data-houdini-project-label]');await until('document.querySelector("[data-houdini-project-action=new]")&&!document.querySelector("[data-houdini-project-action=new]").closest("[role=menuitem]").disabled')
 await click('[data-houdini-project-action=new]');await until('fixture.calls.some(row=>row.method==="houdiniFrontend/projectAction"&&row.input.action==="new")')
 await evaluate('fixture.releaseList()');await sleep(250);assert.equal(await evaluate('document.querySelector("[data-houdini-project-label]").getAttribute("aria-expanded")'),'false','Late list response must not reopen the native project action menu')
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
 const calls=await evaluate('fixture.calls');assert.equal(calls.filter(row=>row.method==='houdiniTargets/select').length,1);assert.equal(calls.filter(row=>row.method==='houdiniTargets/clear').length,1)
 await fs.writeFile(path.join(output,'result.json'),JSON.stringify({ok:true,exactSdk:sdkVersion,nativeMenu:true,realReact:true,stableFixedActions:true,newAvailableWhileLoading:true,candidateActivityIsolation:true,loadingRect,select:1,clear:1,states:['unbound','ready','working','occupied','changed','offline','unknown'],screenshots:(await fs.readdir(output)).filter(name=>name.endsWith('.png'))},null,2))
 console.log('PASS exact DSH SDK React/Menu pointer interaction, explicit selection/clear, states and narrow dark layout: '+output)
} catch(error){if(socket?.readyState===1){try{await screenshot('failure');await fs.writeFile(path.join(output,'failure.txt'),await evaluate('document.body.innerText'))}catch{}}throw error}
finally{if(socket?.readyState===1){try{await call('Browser.close')}catch{}socket.close()}for(let n=0;n<50&&browser.exitCode===null;n++)await sleep(100);if(browser.exitCode===null)browser.kill();server.close()}
