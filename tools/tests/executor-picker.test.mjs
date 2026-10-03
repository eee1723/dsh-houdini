import fs from 'node:fs/promises'
import vm from 'node:vm'
import assert from 'node:assert/strict'
import {Context} from '@deepseek-ai/cordis'
import Registry from '@deepseek-ai/dsh-typert-registry'
import Gateway from '@deepseek-ai/dsh-api-gateway'
import * as frontendHost from '../../lib/frontend-host.js'

const host=new Context()
new Registry(host)
const gateway=new Gateway(host,{websocketHeartbeatIntervalMs:2000})
await host.plugin(frontendHost)

const source=await fs.readFile(new URL('../../client.js',import.meta.url),'utf8')
const fragment=source.slice(source.indexOf('    function createExecutorPicker('),source.indexOf('    function apply(ctx) {'))
const hooks=[],effects=[];let cursor=0,task='task-a',preset='houdini',requests=[],response,hostGeneration,capabilityResponse
const React={
  createElement:(tag,props,...children)=>({tag,props:props||{},children:children.flat(Infinity)}),
  useRef:value=>{let i=cursor++;return hooks[i]||(hooks[i]={current:value})},
  useState:value=>{let i=cursor++;if(!(i in hooks))hooks[i]=value;return [hooks[i],next=>hooks[i]=typeof next==='function'?next(hooks[i]):next]},
  useSyncExternalStore:(subscribe,getSnapshot)=>getSnapshot(),
  useEffect:(fn,deps)=>{let i=cursor++;if(!hooks[i]||deps.some((dep,j)=>!Object.is(hooks[i].deps[j],dep))){
    hooks[i]?.dispose?.();hooks[i]={deps};effects.push(()=>hooks[i].dispose=fn())}},
}
const context={React,AbortController,setTimeout,clearTimeout}
vm.createContext(context);vm.runInContext(fragment+'\nthis.factory=createExecutorPicker;',context)
const component=context.factory({generation:{getSnapshot:()=>hostGeneration,subscribe:()=>()=>{}},rpc:{call:async(channel,endpoint,payload,signal)=>{
  requests.push({channel,endpoint,payload,signal})
  if(endpoint==='houdiniFrontend/capabilities'){
    if(capabilityResponse)return capabilityResponse()
    // Browser arguments cross a JSON wire before entering the Host realm.
    return {ok:true,value:await gateway.invoke({namespace:'houdiniFrontend',method:'capabilities',args:JSON.parse(JSON.stringify(payload.args)),signal})}
  }
  return typeof response==='function'?response():response
}}})
function render(){cursor=0;let tree=component({sessionId:task,useSessions:fn=>fn({byId:{[task]:{projectionValues:{agentPreset:preset}}}})});while(effects.length)effects.shift()();return tree}
function nodes(tree){return tree&&typeof tree==='object'?[tree,...tree.children.flatMap(nodes)]:[]}
function button(tree,label){return nodes(tree).find(n=>n.tag==='button'&&n.children.includes(label))}
const settle=()=>new Promise(resolve=>setImmediate(resolve))
const targetRequests=()=>requests.filter(r=>r.endpoint.startsWith('houdiniTargets/'))
const record={executor_id:'a'.repeat(32),registration_id:'b'.repeat(32),houdini_version:'22.0.368',
  hip_path:'C:/fixture/test.hip',task_id:null,state:'registered'}
let tree=render()
assert.equal(tree,null,'no picker before a Host generation is ready')
assert.equal(requests.length,0,'mount must not query a disconnected Host')
hostGeneration={id:1};assert.equal(render(),null);await settle()
assert.equal(render(),null,'ordinary Open Workspace must not show a shared executor picker')
assert.equal(requests[0].endpoint,'houdiniFrontend/capabilities')
assert.equal(targetRequests().length,0,'capability discovery must not list or select Houdini targets')
const shared=await host.plugin({apply(ctx){ctx.provide('houdiniTargets',{})}})
hostGeneration={id:2};assert.equal(render(),null);await settle();tree=render()
assert(button(tree,'Houdini 执行端'),'mounted shared Host service enables the picker')
assert.equal(targetRequests().length,0,'enabling the picker does not silently query/select a target')
response={ok:true,value:{candidates:[record],recovery:{status:'unbound',message:'本任务尚未绑定Houdini。'}}}
button(tree,'Houdini 执行端').props.onClick();await settle();tree=render()
assert.equal(targetRequests()[0].endpoint,'houdiniTargets/list')
assert.equal(targetRequests()[0].payload.args.input.sessionId,'task-a')
assert(nodes(tree).some(n=>n.children.some(c=>typeof c==='string'&&c.includes('本任务尚未绑定'))))
assert(button(tree,'选择并绑定'))
response={ok:true,value:{status:'bound'}}
button(tree,'选择并绑定').props.onClick();await settle();tree=render()
assert.equal(targetRequests().length,2,'one explicit choice submits exactly one selection')
assert.equal(targetRequests()[1].channel,'/api')
assert.equal(targetRequests()[1].payload.args.input.sessionId,'task-a')
assert.equal(targetRequests()[1].payload.args.input.expectedHip,record.hip_path)
assert(nodes(tree).some(n=>n.children.some(c=>typeof c==='string'&&c.includes('本任务已绑定'))))
let resolve
response=()=>new Promise(r=>resolve=r)
button(tree,'刷新执行端').props.onClick();await settle()
const staleSignal=requests.at(-1).signal
task='task-b';render();assert(staleSignal.aborted)
resolve({ok:true,value:{candidates:[record]}});await settle();tree=render()
assert.equal(button(tree,'选择并绑定'),undefined,'late response must not populate another task')
response={ok:true,value:{candidates:[{...record,task_id:'task-a'}],recovery:{status:'bound_disconnected',message:'原Houdini执行端已断开。'}}}
button(tree,'Houdini 执行端').props.onClick();await settle();tree=render()
assert.equal(button(tree,'选择并绑定').props.disabled,true,'other author reservation is not selectable')
response=()=>new Promise(r=>resolve=r)
button(tree,'刷新执行端').props.onClick();await settle()
const disconnectedSignal=requests.at(-1).signal
hostGeneration=undefined;assert.equal(render(),null,'connection loss immediately removes the picker')
assert(disconnectedSignal.aborted,'connection loss aborts an in-flight target request')
resolve({ok:true,value:{candidates:[record]}});await settle()
await shared.dispose()
hostGeneration={id:3};assert.equal(render(),null);await settle()
assert.equal(render(),null,'reconnection must not reuse capabilities from a previous Host')
capabilityResponse=()=>new Promise(r=>resolve=r)
hostGeneration={id:4};render();const staleCapability=requests.at(-1).signal
hostGeneration=undefined;render();assert(staleCapability.aborted)
resolve({ok:true,value:{sharedExecutors:true}});await settle()
assert.equal(render(),null,'late capabilities cannot revive a disconnected picker')
capabilityResponse=async()=>{throw new Error('capability transport unavailable')}
hostGeneration={id:5};render();await settle()
assert.equal(render(),null,'failed capability lookup leaves optional UI hidden')
const beforePreset=requests.length
preset='standard';render();hostGeneration={id:6};render();await settle()
assert.equal(requests.length,beforePreset,'other presets do not query Houdini capabilities')
assert(targetRequests().every(r=>['houdiniTargets/list','houdiniTargets/select'].includes(r.endpoint)))
console.log('executor picker: real Host capability RPC, local/shared visibility, reconnect isolation, explicit selection, captured HIP and author exclusion passed')
