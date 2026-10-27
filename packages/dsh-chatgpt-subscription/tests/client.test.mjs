import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

const source=fs.readFileSync(new URL('../client.js',import.meta.url),'utf8')
const requests=[],copied=[],registered=[],timers=new Map()
let hooks=[],effects=[],cursor=0,serial=0,generation={id:1},definition,component,delayStatus=null,delayBegin=null,loseBegin=false,commitWinsCancel=false
const clone=value=>structuredClone(value)
const a={id:'INTERNAL_ACCOUNT_A',label:'测试甲',status:'connected',sharing:true,active:true,verificationPending:false,needsPlanNotice:false}
const b={...a,id:'INTERNAL_ACCOUNT_B',label:'测试乙',active:false}
let state={provider:'chatgpt-subscription',accounts:[],activeAccountId:null,login:null,models:[],catalogRead:false,
  protection:'windows-dpapi',usageUrl:'https://chatgpt.com/settings/usage',note:'safe'}
const launch='http://127.0.0.1:48219/launch/'+'a'.repeat(64)
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return{promise,resolve}}
const React={Fragment:'fragment',
  createElement:(tag,props,...children)=>typeof tag==='function'?tag({...props,children:children.flat(Infinity)}):({tag,props:props??{},children:children.flat(Infinity)}),
  useState(value){const index=cursor++;if(!(index in hooks))hooks[index]=value;return[hooks[index],next=>{hooks[index]=typeof next==='function'?next(hooks[index]):next}]},
  useRef(value){const index=cursor++;return hooks[index]??(hooks[index]={current:value})},
  useSyncExternalStore:(_subscribe,get)=>get(),
  useEffect(callback,deps){const index=cursor++;if(!hooks[index]||deps.some((value,key)=>!Object.is(value,hooks[index].deps[key]))){
    hooks[index]?.dispose?.();hooks[index]={deps};effects.push(()=>hooks[index].dispose=callback())}}
}
const ui={Button:props=>React.createElement('button',props,props.children),Modal:props=>props.open?React.createElement('dialog',{'aria-label':props.title},
  React.createElement('button',{'aria-label':props.closeLabel,onClick:props.onClose},'modal-close'),props.children,props.footer):null}
const connection={generation:{getSnapshot:()=>generation,subscribe:()=>()=>{}},rpc:{call:async(channel,method,payload,signal)=>{
  requests.push({channel,method,payload,signal});const input=payload.args.input
  assert.equal(channel,'/api');assert(method.startsWith('chatgptSubscription/'))
  switch(method.split('/')[1]){
    case 'status': {assert.deepEqual(Object.keys(payload.args),[]);if(delayStatus){const delayed=delayStatus;delayStatus=null;return delayed.promise}return{ok:true,value:clone(state)}}
    case 'beginLogin': {
      assert(!('answer' in input));state.login={attemptId:'ATTEMPT_INTERNAL',status:'pending',launchUrl:launch,message:'请在浏览器完成授权'}
      if(delayBegin){const delayed=delayBegin;delayBegin=null;return delayed.promise}
      if(loseBegin){loseBegin=false;throw Error('Fixture: admission response lost')}
      return{ok:true,value:clone(state.login)}
    }
    case 'loginStatus':assert.equal(input.attemptId,state.login.attemptId);return{ok:true,value:clone(state.login)}
    case 'cancelLogin':assert.equal(input.attemptId,state.login.attemptId);state.login={...state.login,status:commitWinsCancel?'authorized':'cancelled'};delete state.login.launchUrl;return{ok:true,value:clone(state.login)}
    case 'reopenBrowser':assert.equal(input.attemptId,state.login.attemptId);return{ok:true,value:{opened:true}}
    case 'models':state.catalogRead=true;state.models=[];return{ok:true,value:[]}
    case 'selectAccount':state.activeAccountId=input.accountId;state.accounts=state.accounts.map(row=>({...row,active:row.id===input.accountId}));state.models=[];state.catalogRead=false;return{ok:true,value:clone(state)}
    case 'disconnect':state.accounts=state.accounts.map(row=>row.id===input.accountId?{...row,status:'disconnected',sharing:false}:row);return{ok:true,value:{disconnected:true,remoteRevocationConfirmed:false,message:'已在本机断开，远端撤销尚未确认。'}}
    case 'acknowledgePlanNotice':state.accounts=state.accounts.map(row=>row.id===input.accountId?{...row,needsPlanNotice:false}:row);return{ok:true,value:clone(state)}
    default:throw Error('Unexpected RPC '+method)
  }
}}}
const context={window:{__ModuleLoader__:{load(value){definition=value}}},URL,AbortController,
  navigator:{clipboard:{writeText:async value=>copied.push(value)}},
  setTimeout(fn,ms){const id=++serial;timers.set(id,{fn,ms});return id},clearTimeout(id){timers.delete(id)}}
vm.createContext(context);vm.runInContext(source,context)
const client=definition.factory(name=>name==='react'?React:name==='@deepseek-ai/dsh-client-ui-primitives'?ui:assert.fail('Unknown public SDK '+name))
const slots={inject(name,callback){assert.equal(name,'settings.section');return callback()},register(options,render){registered.push(options);component=render;return()=>{}}}
client.apply({get:name=>name==='slots'?slots:undefined,effect:callback=>callback(),inject(names,callback){assert.deepEqual([...names],['connection']);return callback({get:name=>name==='connection'?connection:undefined})}})
assert.equal(registered.length,1);assert.equal(registered[0].id,'chatgpt-subscription')
assert(!source.includes('agentDefaultModel')&&!source.includes('session/prompt')&&!source.includes('localStorage'))
function render(){cursor=0;const result=component();while(effects.length)effects.shift()();return result}
function nodes(tree){return tree&&typeof tree==='object'?[tree,...tree.children.flatMap(nodes)]:[]}
function text(tree){return typeof tree==='string'?tree:tree&&typeof tree==='object'?tree.children.map(text).join(' '):''}
function button(label,within=render()){const found=nodes(within).find(node=>node.tag==='button'&&text(node).trim()===label);assert(found,'Missing button '+label);return found}
function click(label,within){const element=button(label,within);assert(!element.props.disabled,label+' unexpectedly disabled');return element.props.onClick()}
const flush=async()=>{await Promise.resolve();await Promise.resolve();await Promise.resolve();render();await Promise.resolve()}
function row(name){const value=nodes(render()).find(node=>node.props.className==='cgs-row'&&text(node).includes(name));assert(value);return value}
function count(method){return requests.filter(request=>request.method==='chatgptSubscription/'+method).length}
function unmount(){hooks.forEach(value=>value?.dispose?.());hooks=[];effects=[];cursor=0}

render();await flush()
assert.equal(requests.length,1,'opening settings only reads local safe status')
assert(text(render()).includes('未连接'));assert.equal(count('models'),0)
const initialConnect=button('Continue with ChatGPT')
let pending=initialConnect.props.onClick();initialConnect.props.onClick();assert.equal(count('beginLogin'),1)
await pending;await flush()
assert(nodes(render()).some(node=>node.tag==='dialog'&&node.props['aria-label']==='在浏览器中完成 ChatGPT 授权'))
assert(!text(render()).includes('ATTEMPT_INTERNAL')&&!text(render()).includes(launch))
await click('复制临时登录入口');assert.deepEqual(copied,[launch])
await click('重新打开浏览器');await flush();assert.equal(count('reopenBrowser'),1)
await click('取消登录');await flush();assert.equal(count('cancelLogin'),1)
assert(!nodes(render()).some(node=>node.tag==='dialog'))
await click('Continue with ChatGPT');await flush();commitWinsCancel=true
await click('取消登录');await flush();commitWinsCancel=false
assert(text(render()).includes('授权已在取消前完成')&&!text(render()).includes('登录已取消'),'cancellation must consume the native commit outcome')

// Even a faulty DTO cannot turn the clipboard button into an OAuth-secret export.
state.login={attemptId:'ATTEMPT_INTERNAL',status:'pending',launchUrl:'https://auth.openai.com/oauth?code=PRIVATE&id_token_hint=PRIVATE'}
await click('刷新状态');await flush();click('查看登录进度')
assert(button('复制临时登录入口').props.disabled);assert(!text(render()).includes('id_token_hint'))
await click('取消登录');await flush()
state={...state,accounts:[clone(a),clone(b)],activeAccountId:a.id,login:null}
await click('刷新状态');await flush()
assert(text(render()).includes('尚未读取此账号的目录'))
await click('刷新模型目录');await flush()
assert(text(render()).includes('已读取 0 项')&&text(render()).includes('服务返回的目录为空'))
assert(text(render()).includes('不代表真实请求已成功'))
assert(!text(render()).includes(a.id)&&!text(render()).includes(b.id),'internal account IDs never become visible labels')
state.models=[{id:'unknown-server-model',name:'服务端新模型',supported:false,unsupportedReason:'当前客户端尚无可靠的能力定义'}]
await click('刷新状态');await flush();assert(text(render()).includes('当前客户端尚无可靠的能力定义'))
state.accounts[0]={...state.accounts[0],sharing:false};await click('刷新状态');await flush()
assert(button('刷新模型目录').props.disabled&&button('授权计划额度',row('测试甲')),'connected without plan scope still has a repair action')
state.accounts[0]={...state.accounts[0],sharing:true};await click('刷新状态');await flush()

// A late pre-switch read cannot overwrite the explicitly selected account.
const oldRead=deferred();delayStatus=oldRead
const refreshing=click('刷新状态'),before=clone(state)
await click('设为当前账号',row('测试乙'));await flush()
oldRead.resolve({ok:true,value:before});await refreshing;await flush()
assert.match(text(render()),/测试乙\s+· 当前/)
click('断开…',row('测试乙'));let dialog=nodes(render()).find(node=>node.tag==='dialog')
click('取消',dialog);assert.equal(count('disconnect'),0)
click('断开…',row('测试乙'));dialog=nodes(render()).find(node=>node.tag==='dialog')
await click('断开账号',dialog);await flush()
assert.equal(count('disconnect'),1);assert(text(render()).includes('远端撤销尚未确认'))

// First-plan notice consumes the persistent backend flag, never a local account ledger.
state.accounts=[{...a,needsPlanNotice:true}];state.activeAccountId=a.id
await click('刷新状态');await flush()
assert(nodes(render()).some(node=>node.tag==='dialog'&&node.props['aria-label']==='已允许使用你的 ChatGPT 计划'))
await click('知道了');await flush();assert.equal(count('acknowledgePlanNotice'),1)
unmount();render();await flush();assert(!nodes(render()).some(node=>node.tag==='dialog'))

// Lost admission responses only trigger a safe status read, never a second OAuth flow.
loseBegin=true;const started=count('beginLogin');await click('Continue with ChatGPT');await flush()
assert.equal(count('beginLogin'),started+1);assert(text(render()).includes('请在浏览器完成授权'))
state.login={attemptId:state.login.attemptId,status:'authorized'}
const poll=[...timers].find(([,value])=>value.ms===1000);assert(poll)
timers.delete(poll[0]);await poll[1].fn();await flush()
assert.equal(count('beginLogin'),started+1);assert(!nodes(render()).some(node=>node.tag==='dialog'))

// Reconnect cancels the old observer and ignores a late mutation response.
const oldBegin=deferred();delayBegin=oldBegin
pending=click('Continue with ChatGPT');const signal=requests.at(-1).signal
generation={id:2};state.login=null;render();await flush();assert(signal.aborted)
oldBegin.resolve({ok:true,value:{attemptId:'OLD_ATTEMPT',status:'pending',launchUrl:launch}});await pending;await flush()
assert(!text(render()).includes('OLD_ATTEMPT')&&!nodes(render()).some(node=>node.tag==='dialog'))
// A timeout followed by a non-cooperative late response may not leave a loading page forever.
const timedRead=deferred();delayStatus=timedRead;generation={id:3};render()
const timeout=[...timers].find(([,value])=>value.ms===30000);assert(timeout);timeout[1].fn()
timedRead.resolve({ok:true,value:clone(state)});await flush()
assert(text(render()).includes('请求已超时')&&text(render()).includes('暂时无法读取账号状态'))
await click('刷新状态');await flush();await click('Continue with ChatGPT');await flush()
assert(state.login.status==='pending')
const beforeClose=count('cancelLogin');unmount();assert.equal(count('cancelLogin'),beforeClose,'closing settings does not cancel browser authorization')
assert(requests.every(request=>Object.keys(request.payload.args).every(key=>key==='input')))
assert.equal(count('models'),1,'mount, status refresh and reconnect never issue model requests')
console.log('subscription settings: all-mode registration, native controls, safe login/copy/cancel, status layers, empty catalog, account switch/disconnect, persistent notice, lost responses and stale reconnect passed')
