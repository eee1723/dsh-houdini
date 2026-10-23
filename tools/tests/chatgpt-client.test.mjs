import fs from 'node:fs'
import vm from 'node:vm'
import assert from 'node:assert/strict'

const source=fs.readFileSync('client.js','utf8')
const fragment=source.slice(source.indexOf('    function createChatGptSettings('),source.indexOf('    // Tutorial preferences'))
const hooks=[],effects=[],requests=[],popups=[],intervals=new Map()
let cursor=0,generation={id:1},timerId=0
const React={createElement:(tag,props,...children)=>({tag,props:props??{},children:children.flat(Infinity)}),
  useRef(value){const i=cursor++;return hooks[i]??(hooks[i]={current:value})},
  useState(value){const i=cursor++;if(!(i in hooks))hooks[i]=value;return[hooks[i],next=>{hooks[i]=typeof next==='function'?next(hooks[i]):next}]},
  useSyncExternalStore:(_subscribe,get)=>get(),
  useEffect(callback,deps){const i=cursor++;if(!hooks[i]||deps.some((value,k)=>value!==hooks[i].deps[k])){
    hooks[i]?.dispose?.();hooks[i]={deps};effects.push(()=>hooks[i].dispose=callback())
  }}}
const context={React,URL,AbortController,console,
  require:name=>{assert.equal(name,'@deepseek-ai/dsh-client-ui-primitives');return{Button:'button'}},
  setTimeout:()=>++timerId,clearTimeout(){},
  setInterval(fn){const id=++timerId;intervals.set(id,fn);return id},clearInterval:id=>intervals.delete(id),
  window:{open(){const popup={location:{href:''},closed:false,close(){this.closed=true}};popups.push(popup);return popup}}}
vm.createContext(context);vm.runInContext(fragment+'\nthis.factory=createChatGptSettings;',context)
const component=context.factory({generation:{subscribe:()=>()=>{},getSnapshot:()=>generation},rpc:{call:async(channel,method,payload,signal)=>{
  return new Promise(resolve=>requests.push({channel,method,payload,signal,resolve}))
}}})
function render(runEffects=true){cursor=0;const tree=component();if(runEffects)while(effects.length)effects.shift()();return tree}
function nodes(tree){return tree&&typeof tree==='object'?[tree,...tree.children.flatMap(nodes)]:[]}
function allText(tree){return tree&&typeof tree==='object'?tree.children.map(allText).join(' '):String(tree??'')}
function text(){return allText(render())}
function button(label,tree=render()){return nodes(tree).find(n=>n.tag==='button'&&n.children.includes(label))}
function field(label){return nodes(render()).find(n=>n.props['aria-label']===label)}
const settle=async(value,request=requests.at(-1))=>{request.resolve({ok:true,value});await new Promise(resolve=>setImmediate(resolve));render();render()}
const base={nativeFlowAvailable:true,credential:{stored:false,kind:null,writable:true},route:{configured:false,registered:false,writable:true,conflicts:[]},models:[],defaultSelection:null,login:null}
render();assert.equal(requests[0].method,'houdiniFrontend/chatgptStatus')
await settle(base);assert.equal(intervals.size,0,'closed login does not poll')
let promise=button('使用 ChatGPT 登录').props.onClick()
assert.equal(popups.length,1,'browser opens during explicit click')
assert.equal(requests.at(-1).method,'houdiniFrontend/chatgptStart')
const pending={...base,login:{attemptId:'attempt-1',status:'pending',notice:{url:'https://auth.openai.com/api/accounts/authorize?state=ephemeral',message:'continue'},
  prompt:{id:'prompt-1',kind:'text',message:'manual',placeholder:'http://localhost/callback'}}}
await settle(pending);await promise;render()
assert.match(popups[0].location.href,/^https:\/\/auth\.openai\.com\//)
assert.equal(intervals.size,1)
assert.equal(nodes(render()).find(n=>n.tag==='input').props.type,'password','callback data is masked')
nodes(render()).find(n=>n.tag==='input').props.onChange({target:{value:'private-callback'}})
promise=button('提交返回信息').props.onClick()
assert.deepEqual(JSON.parse(JSON.stringify(requests.at(-1).payload.args.input)),{attemptId:'attempt-1',promptId:'prompt-1',value:'private-callback'})
await settle({...pending,login:{...pending.login,prompt:undefined,notice:{url:'https://evil.example/authorize'}}});await promise
assert.equal(nodes(render()).filter(n=>n.tag==='a').some(n=>/evil/.test(n.props.href)),false,'untrusted authorization destinations are not surfaced')
assert.equal(nodes(render()).some(n=>n.tag==='input'),false,'withdrawn callback prompt is removed')
promise=button('取消登录').props.onClick()
assert.equal(requests.at(-1).payload.args.input.attemptId,'attempt-1')
await settle({...base,login:{attemptId:'attempt-1',status:'cancelled'}});await promise
assert.equal(intervals.size,0)

const connected={...base,credential:{stored:true,kind:'grant',writable:true},route:{configured:true,registered:true,writable:true,conflicts:[]},
  models:[{id:'exact-model',name:'Exact Model',inputModalities:['text','image'],contextWindow:100000,
    reasoning:{efforts:[{id:'high',name:'High'}]}}],defaultSelection:{provider:'openai',model:'exact-model'}}
button('刷新状态').props.onClick();await settle(connected)
assert.equal(field('ChatGPT 模型').props.value,'exact-model')
assert.equal(requests.filter(r=>r.method.endsWith('Probe')).length,0,'status and catalog never spend model quota')
assert.equal(button('设为新对话默认').props.disabled,false)
field('ChatGPT 思考程度').props.onChange({target:{value:'high'}})
promise=button('设为新对话默认').props.onClick()
assert.deepEqual(JSON.parse(JSON.stringify(requests.at(-1).payload.args.input)),{model:'exact-model',reasoningEffort:'high'})
await settle(connected);await promise
assert.match(text(),/已有对话可在输入框旁/)
promise=button('测试模型连接').props.onClick()
await settle({ok:true,code:'OK',message:'请求完成',model:'exact-model',elapsedMs:12});await promise
assert.match(text(),/这次模型请求成功/)
field('ChatGPT 思考程度').props.onChange({target:{value:''}})
assert(!text().includes('这次模型请求成功'),'changing a tested selection drops its receipt')
button('断开连接').props.onClick();promise=button('确认断开本机授权').props.onClick()
await settle({...base,signout:{revocation:'unconfirmed',localCleared:true}});await promise
assert.match(text(),/服务端撤销尚未确认/)
button('刷新状态').props.onClick();await settle(connected)
button('断开连接').props.onClick();promise=button('确认断开本机授权').props.onClick()
await settle({...connected,signout:{revocation:'confirmed',localCleared:false}});await promise
assert.match(text(),/当前授权仍保留/)
assert(button('断开连接'),'a concurrent replacement remains connected')

button('刷新状态').props.onClick();await settle({...connected,route:{...connected.route,conflicts:[{field:'apiKeyEnv',message:'使用API凭据'}]}})
assert.equal(button('设为新对话默认').props.disabled,true)
assert.equal(button('测试模型连接').props.disabled,true)
assert.match(text(),/不会覆盖/)
button('刷新状态').props.onClick();const stale=requests.at(-1)
generation={id:2}
const immediate=render(false)
assert.equal(button('断开连接',immediate),undefined,'old host credential state disappears before cleanup effects')
render();assert(stale.signal.aborted)
await settle(connected,stale)
assert.equal(button('断开连接'),undefined,'late old-host response cannot restore its account actions')
const newest=requests.at(-1)
await settle({...base,credential:{stored:null,kind:null,writable:false,error:{code:'UNAVAILABLE',message:'凭据状态读取失败'}}},newest)
assert.match(text(),/状态暂不可用/)
assert.equal(button('使用 ChatGPT 登录').props.disabled,true)
assert.equal(intervals.size,0)
assert(!fragment.includes('localStorage')&&!fragment.includes('sessionStorage'),'credential flow does not create browser persistence')
console.log('ChatGPT UI: explicit auth/probe, exact attempt and model, masked callback, conflicts, unknown state and stale host isolation passed')
