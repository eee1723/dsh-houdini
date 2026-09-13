import fs from 'node:fs/promises'
import vm from 'node:vm'
import assert from 'node:assert/strict'

const source=await fs.readFile(new URL('../../client.js',import.meta.url),'utf8')
const fragment=source.slice(source.indexOf('    function createExecutorPicker('),source.indexOf('    function apply(ctx) {'))
const hooks=[],effects=[];let cursor=0,confirm=false,task='task-a',requests=[],response
const React={
  createElement:(tag,props,...children)=>({tag,props:props||{},children:children.flat(Infinity)}),
  useRef:value=>{let i=cursor++;return hooks[i]||(hooks[i]={current:value})},
  useState:value=>{let i=cursor++;if(!(i in hooks))hooks[i]=value;return [hooks[i],next=>hooks[i]=typeof next==='function'?next(hooks[i]):next]},
  useEffect:(fn,deps)=>{let i=cursor++;if(!hooks[i]||hooks[i].deps[0]!==deps[0]){
    hooks[i]?.dispose?.();hooks[i]={deps};effects.push(()=>hooks[i].dispose=fn())}},
}
const context={React,AbortController,setTimeout,clearTimeout,window:{confirm:()=>confirm}}
vm.createContext(context);vm.runInContext(fragment+'\nthis.factory=createExecutorPicker;',context)
const component=context.factory({rpc:{call:async(channel,endpoint,payload,signal)=>{
  requests.push({channel,endpoint,payload,signal});return typeof response==='function'?response():response
}}})
function render(){cursor=0;let tree=component({sessionId:task,useSessions:fn=>fn({byId:{[task]:{projectionValues:{agentPreset:'houdini'}}}})});while(effects.length)effects.shift()();return tree}
function nodes(tree){return tree&&typeof tree==='object'?[tree,...tree.children.flatMap(nodes)]:[]}
function button(tree,label){return nodes(tree).find(n=>n.tag==='button'&&n.children.includes(label))}
const settle=async()=>{for(let i=0;i<8;i++)await Promise.resolve()}
const record={executor_id:'a'.repeat(32),registration_id:'b'.repeat(32),houdini_version:'22.0.368',
  hip_path:'C:/fixture/test.hip',task_id:null,state:'registered'}
let tree=render()
assert.equal(requests.length,0,'mount must not silently query/select a target')
response={ok:true,value:{candidates:[record]}}
button(tree,'Houdini 执行端').props.onClick();await settle();tree=render()
assert.equal(requests[0].endpoint,'houdiniTargets/list')
assert(button(tree,'选择并绑定'))
button(tree,'选择并绑定').props.onClick();assert.equal(requests.length,1,'cancelled confirmation must not select')
confirm=true;response={ok:true,value:{status:'bound'}}
button(tree,'选择并绑定').props.onClick();await settle();tree=render()
assert.equal(requests[1].channel,'/api')
assert.equal(requests[1].payload.args.input.sessionId,'task-a')
assert.equal(requests[1].payload.args.input.expectedHip,record.hip_path)
assert(nodes(tree).some(n=>n.children.some(c=>typeof c==='string'&&c.includes('本任务已绑定'))))
let resolve
response=()=>new Promise(r=>resolve=r)
button(tree,'刷新执行端').props.onClick();await settle()
const staleSignal=requests.at(-1).signal
task='task-b';render();assert(staleSignal.aborted)
resolve({ok:true,value:{candidates:[record]}});await settle();tree=render()
assert.equal(button(tree,'选择并绑定'),undefined,'late response must not populate another task')
response={ok:true,value:{candidates:[{...record,task_id:'task-a'}]}}
button(tree,'Houdini 执行端').props.onClick();await settle();tree=render()
assert.equal(button(tree,'选择并绑定').props.disabled,true,'other author reservation is not selectable')
console.log('executor picker: explicit consent, native RPC, captured HIP, stale response and author exclusion passed')
