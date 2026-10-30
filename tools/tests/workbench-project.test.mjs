import {foldExecutorBinding} from '../../lib/executor-identity-projection.js'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import path from 'node:path'
import {executorIdentityProjection,foldExecutorState,registerExecutorIdentityProjection} from '../../lib/executor-identity-projection.js'
import {houdiniSnapshot,workspaceOpeningMessage} from '../../lib/dsh-adapter.js'
import {recoveryMessage} from '../../lib/scene-recovery.js'

const executor='a'.repeat(32),replacement='b'.repeat(32)
const record={workbench:true,executor_id:executor,registration_id:'c'.repeat(32),runtime_id:'9'.repeat(32),scene_id:'d'.repeat(32),scene_epoch:'e'.repeat(32),
  hip_path:path.resolve('tools/out/test103/untitled.hip'),hip_is_new:false,workspace_path:path.resolve('tools/out/test103')}
let state=executorIdentityProjection.init(),sequence=0
const apply=(type,data,time=1000)=>{state=executorIdentityProjection.apply(state,{type,data,seq:++sequence,time});return state}
const bind=houdiniSnapshot({name:'dsh-houdini:executor-binding',text:'binding\n'+JSON.stringify({schema:1,kind:'executor_binding',executor_id:executor})})
apply('user/message',bind)
const opening=workspaceOpeningMessage({...record,hip_is_new:true})
apply('agent/inbox/spliced',{inserted:[opening]},2000)
assert.equal(state.project.hipIsNew,true)
function result(callId,hipPath,observedAt,target=executor,nested=false) {
  apply(nested?'tool/ptc-dispatch-start':'tool/call',nested?{subCallId:callId,name:'houdini_exec'}:{callId,name:'houdini_exec'})
  const value={execution:{executor_id:target,hip_path:hipPath,hip_is_new:false,observed_at:observedAt,sequence}}
  apply(nested?'tool/ptc-dispatch':'tool/result',nested?{subCallId:callId,name:'houdini_exec',content:[{type:'text',text:JSON.stringify({kind:'dsh-houdini/execution-v1',callId,tool:'houdini_exec',value})}]}:
    {message:{source:{callId}},meta:{canonical:value}})
}
result('save','C:/test104/rock.hip',4)
assert.equal(state.project.hipPath,'C:/test104/rock.hip')
apply('user/message',opening,6000)
assert.equal(state.project.hipPath,'C:/test104/rock.hip','consuming old queued context cannot revert Save As')
result('late','C:/test103/rock.hip',3)
assert.equal(state.project.hipPath,'C:/test104/rock.hip','older execution observation must not replace the new path')
result('nested','C:/test104/岩石<draft>.hip',5,executor,true)
assert.equal(state.project.hipPath,'C:/test104/岩石<draft>.hip')
apply('tool/call',{callId:'old-pending',name:'houdini_exec'})
apply('user/message',recoveryMessage({schema:2,kind:'executor_recovery',previous_executor:executor,executor_id:replacement,
  operation_id:'1'.repeat(32),checkpoint_id:'2'.repeat(32),scene_id:'3'.repeat(32),scene_epoch:'4'.repeat(32),runtime_id:'5'.repeat(32),
  hip_path:'C:/reopened/rock.hip',restored_nodes:1}),7000)
apply('tool/result',{message:{source:{callId:'old-pending'}},meta:{canonical:{execution:{executor_id:executor,hip_path:'C:/wrong/old.hip',observed_at:8}}}},8000)
assert.equal(state.project.hipPath,'C:/reopened/rock.hip','a late old-executor result cannot relabel a recovered task')
const view=executorIdentityProjection.wire.view(state)
assert.deepEqual(Object.keys(view).sort(),['executorId','hipIsNew','hipPath','label','needsReview','sceneEpoch','sceneId'])
assert.equal(executorIdentityProjection.wire.view(executorIdentityProjection.init()),null,'an unbound task has no project mark')
assert.equal(executorIdentityProjection.wire.view({...state,conflict:true}).needsReview,true)

const source=fs.readFileSync('client.js','utf8')
const fragment=source.slice(source.indexOf('    function Button('),source.indexOf('    // >>> houdini-node-delivery'))
const React={createElement:(tag,props,...children)=>typeof tag==='function'?tag({...props,children}):({tag,props:props??{},children})}
const uiContext={React,require:()=>({Tooltip:props=>React.createElement('tooltip',props,props.children)})}
vm.createContext(uiContext)
vm.runInContext(fragment,uiContext)
let currentProject=view
const props={sessionId:'a',useSessions:select=>select({projectionsBySession:{a:{values:{houdiniExecutorIdentity:currentProject}}}})}
const text=element=>typeof element==='string'?element:Array.isArray(element)?element.map(text).join(''):element?.children?.map(text).join('')??''
assert.equal(uiContext.HoudiniProjectMark(props).props['data-houdini-project-mark'],true)
assert.match(text(uiContext.HoudiniProjectLabel(props)),/rock.hip/)
assert.match(text(uiContext.HoudiniProjectDetail(props)),/C:\/reopened\/rock.hip/)
assert.match(text(uiContext.HoudiniProjectDetail(props)),/连接|确认/)
currentProject={executorId:executor,hipPath:'C:/folder/<img src=x>.hip',hipIsNew:false,needsReview:false}
assert.match(text(uiContext.HoudiniProjectLabel(props)),/<img src=x>.hip/,'untrusted filename stays React text, not HTML')
currentProject={executorId:executor,hipPath:'C:/untitled.hip',hipIsNew:true,needsReview:false}
assert.match(text(uiContext.HoudiniProjectLabel(props)),/未保存工程/)
currentProject=null
assert.equal(uiContext.HoudiniProjectMark(props),null)
assert.match(text(uiContext.HoudiniProjectLabel(props)),/未绑定工程/)
assert(!fragment.includes('dangerouslySetInnerHTML'))
const liveView={...view,runtimeId:'8'.repeat(32),target:{executor_id:view.executorId,runtime_id:'8'.repeat(32),scene_epoch:view.sceneEpoch,hip_path:view.hipPath,hip_is_new:false}}
const live={available:true,observedAt:Date.now(),records:{[view.executorId]:{status:'online',runtimeId:'8'.repeat(32),sceneEpoch:view.sceneEpoch,observedAt:Date.now()}}}
assert.equal(uiContext.houdiniPresence(liveView,live).status,'online')
assert.equal(uiContext.houdiniPresence(liveView,{...live,observedAt:Date.now()-13000}).status,'unknown','expired green must not persist')
assert.equal(uiContext.houdiniPresence(liveView,{...live,records:{}}).status,'unknown','absence is not proof of process exit')
assert.equal(uiContext.houdiniPresence(liveView,{...live,records:{[view.executorId]:{status:'online',runtimeId:'8'.repeat(32),sceneEpoch:'different',observedAt:Date.now()}}}).status,'changed')
assert.equal(uiContext.houdiniPresence(liveView,{...live,records:{[view.executorId]:{status:'offline',observedAt:Date.now()}}}).status,'offline')
assert.equal(uiContext.houdiniPresence(liveView,{...live,records:{[view.executorId]:{status:'online',runtimeId:'8'.repeat(32),sceneEpoch:view.sceneEpoch,observedAt:Date.now()-13000}}}).status,'unknown','a fresh batch response does not freshen an old individual observation')
const mismatch=uiContext.houdiniPresence(liveView,{...live,records:{[view.executorId]:{status:'online',runtimeId:'8'.repeat(32),sceneEpoch:view.sceneEpoch,observedAt:Date.now(),contractMismatch:true}}})
assert.equal(mismatch.status,'unknown','a contract mismatch is not painted as live')
assert.equal(mismatch.label,'需要检查组件')
assert.match(mismatch.detail,/先安装或更新组件/,'unknown installed state must not promise that reopening alone fixes the mismatch')
const componentSnapshot=patch=>({...live,records:{[view.executorId]:{...live.records[view.executorId],...patch}}})
const toInstall=uiContext.houdiniPresence(liveView,componentSnapshot({contractMismatch:true,componentUpdate:{state:'install'}}))
assert.equal(toInstall.label,'需要更新组件')
assert.match(toInstall.detail,/先更新 Houdini 组件/)
const toRestart=uiContext.houdiniPresence(liveView,componentSnapshot({contractMismatch:true,componentUpdate:{state:'restart'}}))
assert.equal(toRestart.label,'更新待生效')
assert.match(toRestart.detail,/组件已安装/)
const compatibleRestart=uiContext.houdiniPresence(liveView,componentSnapshot({componentUpdate:{state:'restart'}}))
assert.equal(compatibleRestart.status,'online','an optional helper build update does not disable a compatible running scene')
assert.match(compatibleRestart.detail,/可以继续使用/)
assert.equal(uiContext.houdiniPresence(liveView,componentSnapshot({contractMismatch:true,runtimeId:'different',componentUpdate:{state:'restart'}})).state,'changed',
  'a replaced scene is reselected before any component advice')
assert.equal(uiContext.houdiniComponentNotice({componentUpdate:{state:'unknown'}}),null,'unknown helper identity alone is not evidence of a required update')
const liveProps={...props,usePresence:()=>live}
currentProject=liveView
const liveMark=uiContext.HoudiniProjectMark(liveProps)
assert.equal(liveMark.props['data-houdini-presence'],'online','the closed-state project mark paints live presence')
assert.match(liveMark.props['aria-label'],/已就绪/)
const findNode=(node,predicate)=>{
  if(!node||typeof node==='string')return null
  if(Array.isArray(node)){for(const child of node){const found=findNode(child,predicate);if(found)return found}return null}
  if(predicate(node))return node
  for(const child of node.children??[]){const found=findNode(child,predicate);if(found)return found}
  return null
}
const liveLabel=uiContext.HoudiniProjectLabel(liveProps)
const liveLabelNode=findNode(liveLabel,node=>node.props?.['data-houdini-project-label']===true)
assert(liveLabelNode,'the project label renders')
assert.equal(liveLabelNode.props['data-houdini-presence'],'online','a closed project menu still exposes live presence')
assert.match(liveLabel.props.title,/已就绪/,'the native tooltip explains the live state without opening the menu')
assert.match(source,/\[data-houdini-presence="online"\][^{]*\{color:/,'online has a visible color rule')
assert.match(source,/\[data-houdini-presence="changed"\]/,'changed is visually distinct')
assert.match(source,/\[data-houdini-presence="offline"\][^{]*\{color:/,'offline has a visible color rule')
assert.equal(uiContext.houdiniProjectName({hipIsNew:true,label:'未保存工程 2'}),'未保存工程 2')
React.useSyncExternalStore=(_subscribe,get)=>get()
React.useEffect=callback=>callback()
Object.assign(uiContext,{AbortController,AbortSignal,setTimeout,clearTimeout})
const presenceCalls=[]
let intervalCallback=null
const lifecycleUi=uiContext.createHoudiniDesktopUi({
  generation:{getSnapshot:()=>1,subscribe:()=>()=>{}},
  rpc:{call:async(_channel,method)=>{
    presenceCalls.push(method)
    if(method==='houdiniFrontend/capabilities')return {ok:true,value:{desktop:true}}
    if(method==='houdiniFrontend/projectPresence')return {ok:true,value:[{executorId:view.executorId,runtimeId:'8'.repeat(32),status:'online',sceneEpoch:view.sceneEpoch,observedAt:Date.now()}]}
    throw Error('unexpected '+method)
  }},
},{adapter:{current:{subscribe:()=>()=>{},getSnapshot:()=>null}}})
uiContext.setInterval=callback=>{intervalCallback=callback;return 7}
uiContext.clearInterval=()=>{}
uiContext.document={visibilityState:'visible',addEventListener:()=>{},removeEventListener:()=>{}}
lifecycleUi.Lifecycle()
await new Promise(resolve=>setTimeout(resolve,20))
assert(presenceCalls.includes('houdiniFrontend/projectPresence'),'the page lifecycle reads live presence without opening a menu')
assert.equal(typeof intervalCallback,'function','a resident presence refresh is scheduled')
React.useSyncExternalStore=(_subscribe,get)=>get()
// A stalled poll must expire the displayed observation and allow later polls.
let stalled=false,deadlineCallback=null,pollCount=0
uiContext.setTimeout=callback=>{deadlineCallback=callback;return 1}
uiContext.clearTimeout=()=>{}
const boundedUi=uiContext.createHoudiniDesktopUi({
  generation:{getSnapshot:()=>1,subscribe:()=>()=>{}},
  rpc:{call:async(_channel,method,_payload,signal)=>{
    if(method==='houdiniFrontend/capabilities')return {ok:true,value:{desktop:true}}
    if(method==='houdiniFrontend/windowPin')return {ok:true,value:{pinned:false}}
    if(method==='houdiniFrontend/pluginUpdates')return {ok:true,value:{state:'current',title:'当前版本可以继续使用',message:'没有适用更新。'}}
    pollCount++
    if(stalled)return new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true}))
    return {ok:true,value:[{executorId:view.executorId,runtimeId:'8'.repeat(32),status:'online',sceneEpoch:view.sceneEpoch,observedAt:Date.now()}]}
  }},
},{adapter:{current:{subscribe:()=>()=>{},getSnapshot:()=>null}}})
boundedUi.Lifecycle()
await new Promise(resolve=>setTimeout(resolve,0))
assert.equal(boundedUi.Mark(props).props['data-houdini-presence'],'online')
stalled=true;intervalCallback();deadlineCallback()
await new Promise(resolve=>setTimeout(resolve,0))
assert.equal(boundedUi.Mark(props).props['data-houdini-presence'],'unknown','timed-out polling cannot leave a green stale mark')
stalled=false;intervalCallback()
await new Promise(resolve=>setTimeout(resolve,0))
assert.equal(pollCount,3)
assert.equal(boundedUi.Mark(props).props['data-houdini-presence'],'online')
Object.assign(uiContext,{setTimeout,clearTimeout})
uiContext.require=()=>({Tooltip:'tooltip',Button:'button',Toast:'toast'})
console.log('Houdini project: single-source labels, saved untitled, Save As, nested/stale recovery, escaped filenames and bounded live presence passed')
