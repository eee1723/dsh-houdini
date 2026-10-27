/** Exact official rc3 React/primitives, isolated Edge profile and mock safe RPC.
 * No Native Host, OAuth, clipboard changes, model requests or user data.
 * node packages/dsh-chatgpt-subscription/tests/client-native-browser.mjs <official-runtime-root>
 */
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {spawn} from 'node:child_process'
import {createHash} from 'node:crypto'

const packageRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),root=path.resolve(packageRoot,'../..')
assert(process.argv[2],'Pass the prepared official runtime root')
const runtime=path.resolve(process.argv[2]),dist=path.join(runtime,'node_modules/@deepseek-ai/dsh-web-frontend/dist')
const original=await fs.readFile(path.join(dist,'index.html'),'utf8'),script=original.match(/src="\.\/([^\"]+\.js)"/)[1]
const sdkVersion=JSON.parse(await fs.readFile(path.join(dist,'../package.json'),'utf8')).version
assert.equal(sdkVersion,'0.2.1-rc.3')
const css=[...original.matchAll(/href="\.\/([^\"]+\.css)"/g)].map(match=>match[1])
const themeSource=await fs.readFile(path.join(runtime,'node_modules/@deepseek-ai/dsh-client-ui-theme/lib/client.js'),'utf8')
const theme=['base_css_default','design_platform_css_default'].map(name=>{const literal=themeSource.match(new RegExp('var '+name+' = ("(?:\\\\.|[^"\\\\])*");'))?.[1];assert(literal,name);return JSON.parse(literal)}).join('\n')
const source=await fs.readFile(path.join(packageRoot,'client.js'),'utf8')
const output=await fs.mkdtemp(path.join(root,'tools/out/subscription-native-'))
const fixture=`
const sdk=await window.fixtureSdk,React=sdk.react;
if(!sdk['@deepseek-ai/dsh-client-ui-primitives']?.Modal)throw Error('Official primitives missing');
let component,mode='standard',generation={id:1},listeners=new Set();
const calls=[],copied=[],sections=[];let reopenFailure=false;
let state={provider:'chatgpt-subscription',accounts:[],activeAccountId:null,login:null,models:[],catalogRead:false,protection:'windows-dpapi-user',usageUrl:'https://chatgpt.com/settings/usage',note:'safe'};
Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>copied.push(value)},configurable:true});
const connection={generation:{getSnapshot:()=>generation,subscribe:fn=>{listeners.add(fn);return()=>listeners.delete(fn)}},rpc:{call:async(channel,method,payload)=>{
calls.push({channel,method,input:payload.args.input});const input=payload.args.input;
switch(method.split('/')[1]){
case 'status':return{ok:true,value:structuredClone(state)};
case 'beginLogin':state.login={attemptId:'fixture-attempt',status:'pending',launchUrl:'http://127.0.0.1:48219/launch/'+'a'.repeat(64),message:'请在浏览器完成授权'};return{ok:true,value:structuredClone(state.login)};
case 'loginStatus':return{ok:true,value:structuredClone(state.login)};
case 'cancelLogin':state.login={attemptId:'fixture-attempt',status:'cancelled'};return{ok:true,value:structuredClone(state.login)};
case 'reopenBrowser':return reopenFailure?{ok:false,error:{code:'BROWSER_UNAVAILABLE',message:'夹具：无法打开默认浏览器，请复制临时登录入口。'}}:{ok:true,value:{opened:true}};
case 'acknowledgePlanNotice':state.accounts=state.accounts.map(row=>row.id===input.accountId?{...row,needsPlanNotice:false}:row);return{ok:true,value:structuredClone(state)};
case 'models':state.catalogRead=true;state.models=[{id:'fixture-model-a',name:'目录示例模型甲',supported:true},{id:'fixture-model-b',name:'目录示例模型乙',supported:true},{id:'fixture-unknown-model',name:'目录中的新模型',supported:false,unsupportedReason:'当前客户端尚无可靠的能力定义'}];return{ok:true,value:structuredClone(state.models)};
case 'selectAccount':state.activeAccountId=input.accountId;state.accounts=state.accounts.map(row=>({...row,active:row.id===input.accountId}));state.models=[];state.catalogRead=false;return{ok:true,value:structuredClone(state)};
case 'disconnect':state.accounts=state.accounts.map(row=>row.id===input.accountId?{...row,status:'disconnected',sharing:false}:row);return{ok:true,value:{message:'已在本机断开；远端撤销尚未确认。'}};
default:throw Error('Unexpected mock RPC '+method);
}}}};
window.__ModuleLoader__={load:definition=>definition.factory(name=>{if(!sdk[name])throw Error('Unknown public SDK '+name);return sdk[name]}).apply({get:name=>name==='slots'?slots:undefined,effect:fn=>fn(),inject:(names,fn)=>{if(names.join(',')!=='connection')throw Error('Unexpected dependency');return fn({get:name=>name==='connection'?connection:undefined})}})};
const slots={inject:(name,fn)=>fn(),register:(options,value)=>{sections.push(options);component=value;return()=>{}}};
(new Function(${JSON.stringify(source)}))();
let settingsClosed=0;
function Settings(){const pair=React.useState(true);return React.createElement(sdk['@deepseek-ai/dsh-client-ui-primitives'].Modal,{open:pair[0],title:'设置',closeLabel:'关闭设置',shortcutModal:'settings',className:'fixture-settings',onClose:()=>{settingsClosed++;pair[1](false)}},React.createElement(component));}
sdk['react-dom/client'].createRoot(document.querySelector('#fixture')).render(React.createElement(Settings));
window.fixture={calls,copied,sections,ready:true,settingsClosed:()=>settingsClosed,reopenFailure(value){reopenFailure=value},dark(value){document.body.toggleAttribute('data-ds-dark-theme',value)},
authorize(){state.login={attemptId:'fixture-attempt',status:'authorized'};state.accounts=[{id:'INTERNAL_A',label:'连接 1',identity:{subject:'DO_NOT_DISPLAY_SUBJECT',email:'alice@example.invalid'},status:'connected',sharing:true,active:true,verificationPending:false,needsPlanNotice:true},{id:'INTERNAL_B',label:'连接 2',identity:{subject:'DO_NOT_DISPLAY_SUBJECT_2',email:'bob@example.invalid'},status:'connected',sharing:true,active:false,verificationPending:false,needsPlanNotice:false}];state.activeAccountId='INTERNAL_A'},
reconnect(){generation={id:generation.id+1};listeners.forEach(fn=>fn())}};
`
await fs.writeFile(path.join(output,'fixture.mjs'),fixture)
new (Object.getPrototypeOf(async function(){}).constructor)(fixture)
const html=`<!doctype html><html><meta charset="utf-8">${css.map(file=>'<link rel="stylesheet" href="/sdk/'+file+'">').join('')}<style>${theme}\nbody{margin:0;padding:24px;background:var(--dsw-alias-bg-layer-0);color:var(--dsw-alias-label-primary);font-family:system-ui}*{box-sizing:border-box}.fixture-settings{width:min(960px,calc(100vw - 32px));max-height:calc(100vh - 32px);overflow-y:auto}</style><body><div id="root" hidden></div><main id="fixture"></main><script>window.fixtureSdk=new Promise(resolve=>{window.__ModuleLoader__={create:options=>{resolve(options.staticModules);throw Error('Isolated subscription fixture: application boot stopped')}}})</script><script type="module" src="/sdk/${script}"></script><script type="module">${fixture}</script></html>`
const server=http.createServer(async(request,response)=>{try{const url=new URL(request.url,'http://127.0.0.1');if(url.pathname==='/'){response.setHeader('Content-Type','text/html;charset=utf-8');response.end(html);return}if(!url.pathname.startsWith('/sdk/')){response.writeHead(404);response.end();return}const file=path.resolve(dist,url.pathname.slice(5));assert(file.startsWith(dist+path.sep));response.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'application/octet-stream');response.end(await fs.readFile(file))}catch(error){response.writeHead(404);response.end(String(error))}})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
let executable
for(const candidate of ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe']){try{await fs.access(candidate);executable=candidate;break}catch{}}
assert(executable,'Edge required for this owned fixture')
const profile=path.join(output,'browser'),base='http://127.0.0.1:'+server.address().port
const browser=spawn(executable,['--headless=new','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,base],{windowsHide:true,stdio:'ignore'})
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));let socket,serial=0
const pending=new Map(),errors=[],external=[]
async function call(method,params={}){const id=++serial,result=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('CDP timeout '+method)),10000);pending.set(id,value=>{clearTimeout(timer);pending.delete(id);value.error?reject(Error(JSON.stringify(value.error))):resolve(value.result)})});socket.send(JSON.stringify({id,method,params}));return result}
async function evaluate(expression){const value=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!value.exceptionDetails,JSON.stringify(value.exceptionDetails));return value.result.value}
async function until(expression){for(let n=0;n<120;n++){if(await evaluate('Boolean('+expression+')'))return;await sleep(100)}throw Error('Not settled: '+expression)}
async function click(text,scope='document',tag='button'){const point=await evaluate(`(()=>{const root=${scope};const e=[...root.querySelectorAll(${JSON.stringify(tag)})].find(e=>e.textContent.trim()===${JSON.stringify(text)});if(!e||e.disabled)throw Error('Missing/disabled '+${JSON.stringify(text)});e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);await call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});await call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});await sleep(100)}
async function screenshot(name){await sleep(250);const value=await call('Page.captureScreenshot',{format:'png'});await fs.writeFile(path.join(output,name+'.png'),Buffer.from(value.data,'base64'))}
try{
 let port
 for(let n=0;n<150;n++){try{port=Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break}catch{}await sleep(100)}
 assert(port,'Owned Edge did not start')
 const targets=await(await fetch('http://127.0.0.1:'+port+'/json')).json(),target=targets.find(row=>row.type==='page'&&row.url.startsWith(base));assert(target)
 socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}));socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.id)pending.get(value.id)?.(value);else if(value.method==='Runtime.exceptionThrown'){const text=value.params.exceptionDetails.exception?.description||value.params.exceptionDetails.text;if(!text.includes('Isolated subscription fixture:'))errors.push(text)}else if(value.method==='Network.requestWillBeSent'&&!value.params.request.url.startsWith(base)&&!value.params.request.url.startsWith('data:'))external.push(value.params.request.url)})
 await call('Runtime.enable');await call('Network.enable');await call('Emulation.setDeviceMetricsOverride',{width:1100,height:900,deviceScaleFactor:1,mobile:false})
 await until('window.fixture?.ready&&document.body.innerText.includes("未连接")')
 assert.deepEqual(await evaluate('fixture.sections.map(s=>s.id)'),['chatgpt-subscription'])
 assert.equal(await evaluate('fixture.calls.every(row=>row.method==="chatgptSubscription/status")'),true)
 await screenshot('unconnected-light')
 await click('Continue with ChatGPT');await until('!!document.querySelector(".cgs-modal")')
 await click('复制临时登录入口');await until('document.querySelector(".cgs-modal").innerText.includes("入口已复制")')
 assert.equal(await evaluate('fixture.copied.length'),1)
 await evaluate('fixture.reopenFailure(true)');await click('重新打开浏览器');await until('document.querySelector(".cgs-modal").innerText.includes("无法打开默认浏览器")')
 await screenshot('login-error-visible')
 await click('收起');await until('!document.querySelector(".cgs-modal")')
 assert.equal(await evaluate('fixture.calls.filter(row=>row.method.endsWith("/cancelLogin")).length'),0)
 await click('查看登录进度');await evaluate('fixture.authorize()')
 await until('document.querySelector(".cgs-modal")?.innerText.includes("已允许使用你的 ChatGPT 计划")')
 await screenshot('first-plan-notice');await click('知道了');await until('!document.querySelector(".cgs-modal")')
 await click('刷新模型目录');await until('document.body.innerText.includes("已读取 3 项")')
 await click('查看已读取的模型目录','document','summary');assert(await evaluate('document.body.innerText.includes("当前客户端尚无可靠的能力定义")'))
 assert.equal(await evaluate('document.querySelectorAll("select,input").length'),0,'no parallel model picker or authorization-input form')
 assert.equal(await evaluate('document.body.innerText.includes("INTERNAL_")||document.body.innerText.includes("DO_NOT_DISPLAY_SUBJECT")'),false)
 assert.equal(await evaluate('[...document.querySelectorAll("a")].every(a=>a.href==="https://chatgpt.com/settings/usage")'),true)
 await screenshot('connected-directory-light')
 await click('设为当前账号',`[...document.querySelectorAll('.cgs-row')].find(row=>row.innerText.includes('bob@example.invalid'))`)
 await until('document.querySelector(".cgs-facts").innerText.includes("bob@example.invalid")')
 await click('断开…',`[...document.querySelectorAll('.cgs-row')].find(row=>row.innerText.includes('bob@example.invalid'))`)
 await screenshot('disconnect-confirmation')
 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await until('!document.querySelector(".cgs-modal")')
 assert.equal(await evaluate('fixture.settingsClosed()'),0,'Escape closes only the nested confirmation, not the parent settings')
 assert.equal(await evaluate('fixture.calls.filter(row=>row.method.endsWith("/disconnect")).length'),0)
 await evaluate('fixture.dark(true)');await call('Emulation.setDeviceMetricsOverride',{width:420,height:900,deviceScaleFactor:1,mobile:false})
 await screenshot('connected-narrow-dark')
 assert(await evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'),'narrow settings overflow')
 await evaluate('fixture.reconnect()');await until('document.querySelector(".cgs-facts").innerText.includes("bob@example.invalid")')
 assert.equal(await evaluate('document.querySelectorAll(".cgs-modal").length'),0,'acknowledged plan notice must not repeat on reconnect')
 assert.deepEqual(errors,[]);assert.deepEqual(external,[])
 const result={ok:true,sdkVersion,clientSha256:createHash('sha256').update(source).digest('hex'),sdkEntrySha256:createHash('sha256').update(await fs.readFile(path.join(dist,script))).digest('hex'),scope:'Exact rc3 React and native Button/Modal inside a nested settings Modal; mock RPC only. No Native Host/install, real OAuth/inference, user clipboard or existing profile.',
  output,calls:await evaluate('fixture.calls'),screenshots:['unconnected-light','login-error-visible','first-plan-notice','connected-directory-light','disconnect-confirmation','connected-narrow-dark'],errors,external}
 await fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({ok:true,result:path.join(output,'result.json')}))
}catch(error){if(socket?.readyState===1)try{await screenshot('failure');await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:String(error),text:await evaluate('document.body.innerText'),errors},null,2))}catch{}throw error}
finally{if(socket?.readyState===1){try{await call('Browser.close')}catch{}socket.close()}if(browser.exitCode===null){await Promise.race([new Promise(resolve=>browser.once('exit',resolve)),sleep(3000)]);if(browser.exitCode===null)browser.kill()}await new Promise(resolve=>server.close(resolve))}
