import {foldExecutorBinding} from '../../lib/executor-identity-projection.js'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import path from 'node:path'
import {Context} from '@deepseek-ai/cordis'
import {SessionStore} from '@deepseek-ai/dsh-session'
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection'
import {agentPresetProjectionDefinition} from '@deepseek-ai/dsh-agent-preset-registry'
import {SessionTitleService} from '@deepseek-ai/dsh-session-title'
import {createUserMessage} from '@deepseek-ai/dsh-llm'
import {ExecutorController} from '../../lib/executor-controller.js'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {HoudiniFrontend} from '../../lib/frontend-host.js'
import {executorIdentityProjection,foldExecutorState,registerExecutorIdentityProjection} from '../../lib/executor-identity-projection.js'
import {houdiniSnapshot,workspaceOpeningMessage} from '../../lib/dsh-adapter.js'
import {recoveryMessage} from '../../lib/scene-recovery.js'

const context=new Context()
new SessionStore(context)
new SessionProjectionRegistry(context).register(agentPresetProjectionDefinition)
registerExecutorIdentityProjection(context)
const titles=new SessionTitleService(context,{fallbackMaxWords:12,fallbackMaxBytes:80,maxTitleBytes:160})
const executor='a'.repeat(32),replacement='b'.repeat(32),registration='c'.repeat(32)
const record={workbench:true,executor_id:executor,registration_id:registration,runtime_id:'9'.repeat(32),scene_id:'d'.repeat(32),scene_epoch:'e'.repeat(32),
  hip_path:path.resolve('tools/out/test103/untitled.hip'),hip_is_new:false,workspace_path:path.resolve('tools/out/test103')}
const agents=new Map()
context.provide('workspaceRegistry',{list:()=>[],create:async()=>({id:'workspace',title:'test103',sessionIds:[]}),archivedSessionIds:[]})
context.provide('sessionController',{
  create:async({sessionId})=>{
    const session=context.sessions.create(sessionId,{meta:{agentPreset:'houdini',cwd:record.workspace_path}})
    agents.set(sessionId,{id:sessionId,session,status:'idle',inject:message=>session.append('agent/inbox/spliced',{target:'next-step',start:0,inserted:[message]})})
    return {sessionId}
  },
  resolveAgent:async sessionId=>({agent:agents.get(sessionId)}),
  rename:()=>{throw Error('Opening an engineering file must not impersonate user title choice')},
})
let persisted=true
context.sessions.flush=async()=>persisted
const controller=new ExecutorController(context,{directory:{find:async()=>record},selectTarget:async agent=>{
  const target={executor_id:record.executor_id,runtime_id:record.runtime_id,registration_id:record.registration_id,scene_id:record.scene_id,scene_epoch:record.scene_epoch,hip_path:record.hip_path,hip_is_new:record.hip_is_new,workspace_path:record.workspace_path}
  await new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents()),(_session,message)=>agent.inject(message)).select(agent.session,target)
  return target
}},true)
try {
  const opened=await controller.openWorkspace({executorId:executor,registrationId:registration,expectedHip:record.hip_path,requestId:'f'.repeat(32)},new AbortController().signal)
  const session=agents.get(opened.sessionId).session
  assert.equal(titles.get(session),undefined,'project opening leaves DSH auto-title unpinned')
  assert.equal(foldExecutorState(session.snapshotEvents()).project.hipPath,record.hip_path)
  assert.equal(executorIdentityProjection.wire.view(foldExecutorState(session.snapshotEvents())).target.executor_id,executor)
  assert.equal(foldExecutorState(session.snapshotEvents()).project.hipIsNew,false,'a real saved untitled.hip is not inferred to be unsaved')
  const human=text=>createUserMessage({source:{kind:'user'},content:[{type:'text',text}]})
  session.append('user/message',human('制作一组可调节的岩石'),{surfaceOp:'append'})
  await new Promise(resolve=>setImmediate(resolve))
  assert.equal(titles.get(session)?.title,'制作一组可调节的岩石')
  assert.equal(titles.get(session)?.source.kind,'fallback')
  titles.rename(session,'我手动保留的标题')
  session.append('user/message',human('调整岩石的风化程度'),{surfaceOp:'append'})
  await new Promise(resolve=>setImmediate(resolve))
  assert.equal(titles.get(session)?.title,'我手动保留的标题')
  const frontend=new HoudiniFrontend(context,{})
  const refreshed=await frontend.refreshTitle({sessionId:session.id},new AbortController().signal)
  assert.equal(refreshed.title,'制作一组可调节的岩石')
  assert.equal(titles.get(session)?.source.kind,'fallback','only explicit refresh unpins an old/manual title')
  await assert.rejects(frontend.refreshTitle({sessionId:session.id,extra:true},new AbortController().signal),/请选择/)
  persisted=false
  await assert.rejects(frontend.refreshTitle({sessionId:session.id},new AbortController().signal),/尚未可靠保存/)
  persisted=true
} finally {await context.fiber.dispose()}

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
const fragment=source.slice(source.indexOf('    function useHoudiniProject('),source.indexOf('    // >>> houdini-node-delivery'))
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
assert.match(text(uiContext.HoudiniProjectLabel(props)),/未绑定现场/)
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
assert.match(mismatch.detail,/版本不一致/,'the user gets an actionable reload reason')
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
assert.match(liveLabel.props.label,/已就绪/,'the tooltip explains the live state without opening the menu')
assert.match(source,/\[data-houdini-presence="online"\][^{]*\{color:/,'online has a visible color rule')
assert.match(source,/\[data-houdini-presence="changed"\]/,'changed is visually distinct')
assert.match(source,/\[data-houdini-presence="offline"\][^{]*\{color:/,'offline has a visible color rule')
assert.equal(uiContext.houdiniProjectName({hipIsNew:true,label:'未保存工程 2'}),'未保存工程 2')
React.useSyncExternalStore=(_subscribe,get)=>get()
React.useEffect=callback=>callback()
Object.assign(uiContext,{AbortController,AbortSignal,setTimeout,clearTimeout})
const presenceCalls=[]
let intervalCallback=null
const lifecycleUi=uiContext.createWorkbenchUi({
  generation:{getSnapshot:()=>1,subscribe:()=>()=>{}},
  rpc:{call:async(_channel,method)=>{
    presenceCalls.push(method)
    if(method==='houdiniFrontend/capabilities')return {ok:true,value:{workbench:true}}
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
const boundedUi=uiContext.createWorkbenchUi({
  generation:{getSnapshot:()=>1,subscribe:()=>()=>{}},
  rpc:{call:async(_channel,method,_payload,signal)=>{
    if(method==='houdiniFrontend/capabilities')return {ok:true,value:{workbench:true}}
    if(method==='houdiniFrontend/windowPin')return {ok:true,value:{pinned:false}}
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
let pinned=false,pinFailure=false
const pinWrites=[]
const pinUi=uiContext.createWorkbenchUi({
  generation:{getSnapshot:()=>1,subscribe:()=>()=>{}},
  rpc:{call:async(_channel,method,payload)=>{
    if(method==='houdiniFrontend/capabilities')return {ok:true,value:{workbench:true}}
    if(method==='houdiniFrontend/projectPresence')return {ok:true,value:[]}
    assert.equal(method,'houdiniFrontend/windowPin')
    if('pinned' in payload.args.input){
      pinWrites.push(payload.args.input.pinned)
      if(pinFailure)return {ok:false,error:{message:'fixture pin failure'}}
      pinned=payload.args.input.pinned
    }
    return {ok:true,value:{pinned}}
  }},
},{adapter:{current:{subscribe:()=>()=>{},getSnapshot:()=>null}}})
pinUi.Lifecycle()
await new Promise(resolve=>setTimeout(resolve,0))
const pinButton=()=>findNode(pinUi.Pin(),node=>node.props['data-houdini-window-pin'])
assert.equal(pinButton().props.style.height,28,'pin reuses the compact existing header')
assert.equal(pinButton().props['aria-pressed'],false)
assert.deepEqual(pinWrites,[],'mount only reads the native state')
pinButton().props.onClick();pinButton().props.onClick()
await new Promise(resolve=>setTimeout(resolve,0))
assert.deepEqual(pinWrites,[true],'rapid clicks cannot duplicate a pending change')
assert.equal(pinButton().props['aria-pressed'],true)
pinFailure=true;pinButton().props.onClick()
await new Promise(resolve=>setTimeout(resolve,0))
assert.equal(pinButton().props['aria-pressed'],true,'failed native change cannot paint a false success')
pinFailure=false;pinButton().props.onClick()
await new Promise(resolve=>setTimeout(resolve,0))
assert.equal(pinButton().props['aria-pressed'],false)
// Update discovery stays on the desktop's cached source; the client only shows
// a confirmed available update and opens the existing version manager.
const updateRequests=[],updateGenerations=new Set(),updateVisibility=new Set()
let updateGeneration={id:1},updatePoll=null,updateCleanup=null
uiContext.setInterval=(callback,delay)=>{assert.equal(delay,60000);updatePoll=callback;return 9}
uiContext.document={visibilityState:'visible',addEventListener:(name,listener)=>{
  assert.equal(name,'visibilitychange');updateVisibility.add(listener)
},removeEventListener:(_name,listener)=>updateVisibility.delete(listener)}
React.useEffect=callback=>{updateCleanup=callback()}
const updatesUi=uiContext.createWorkbenchUpdates({generation:{getSnapshot:()=>updateGeneration,subscribe:listener=>{
  updateGenerations.add(listener);return ()=>updateGenerations.delete(listener)
}},rpc:{call:(_channel,method,payload,signal)=>new Promise((resolve,reject)=>{
  updateRequests.push({method,payload,signal,resolve})
  signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true})
})}})
const updateButton=()=>findNode(updatesUi.Button(),node=>node.props['data-houdini-update'])
assert.equal(updatesUi.Button(),null,'unknown update state leaves the normal header untouched')
assert.equal(updatesUi.Lifecycle(),null)
React.useEffect=()=>{}
assert.equal(updateRequests[0].method,'houdiniFrontend/updateStatus')
updateRequests[0].resolve({ok:true,value:{available:false,version:'99.0'}})
await new Promise(resolve=>setTimeout(resolve,0))
assert.equal(updatesUi.Button(),null,'version text alone cannot claim that an update is available')
updatePoll()
updateRequests[1].resolve({ok:true,value:{available:true,version:'0.0.13'}})
await new Promise(resolve=>setTimeout(resolve,0))
assert.equal(text(updateButton()),'有更新','the header uses a compact action instead of an update panel')
assert.match(updateButton().props['aria-label'],/0\.0\.13.*版本与更新/)
const openingUpdates=updateButton().props.onClick()
updateButton().props.onClick()
assert.equal(updateButton().props.disabled,true)
assert.equal(updateRequests.length,3,'rapid clicks open the native manager once')
assert.equal(updateRequests[2].method,'houdiniFrontend/openUpdates')
assert.deepEqual(Object.keys(updateRequests[2].payload.args),[],'opening the manager cannot request installation')
updateRequests[2].resolve({ok:false,error:{message:'fixture updates unavailable'}})
await openingUpdates
assert.equal(updatesUi.Lifecycle().props.text,'fixture updates unavailable','only an explicit open failure produces feedback')
updatesUi.Lifecycle().props.onDone()
assert.equal(updatesUi.Lifecycle(),null)
const reopeningUpdates=updateButton().props.onClick()
updateRequests[3].resolve({ok:true,value:{opened:true}})
await reopeningUpdates
assert.equal(updatesUi.Lifecycle(),null,'opening the manager needs no success toast')
updatePoll()
updateRequests[4].resolve({ok:false,error:{message:'background discovery failed'}})
await new Promise(resolve=>setTimeout(resolve,0))
assert.equal(updatesUi.Button(),null,'failed status reads silently hide the update action')
assert.equal(updatesUi.Lifecycle(),null)
uiContext.document.visibilityState='hidden'
updateVisibility.forEach(listener=>listener());updatePoll()
assert.equal(updateRequests.length,5,'hidden pages do not poll update state')
uiContext.document.visibilityState='visible'
updateVisibility.forEach(listener=>listener())
assert.equal(updateRequests.length,6,'returning to the page reads the shared status again')
updateGeneration={id:2};updateGenerations.forEach(listener=>listener())
assert.equal(updateRequests[5].signal.aborted,true)
updateRequests[5].resolve({ok:true,value:{available:true,version:'stale'}})
updateRequests[6].resolve({ok:true,value:{available:true,version:'0.0.14'}})
await new Promise(resolve=>setTimeout(resolve,0))
assert.equal(updateButton().props['data-houdini-update-version'],'0.0.14','old-generation replies cannot restore a stale notice')
updatePoll();updateCleanup()
assert.equal(updateRequests[7].signal.aborted,true)
assert.equal(updateVisibility.size,0)
assert.equal(updateGenerations.size,0)
assert.match(source,/name: "conversation\.session\.header\.controls", id: "houdini-update", order: 10/)
React.useEffect=callback=>callback()
uiContext.require=()=>({MenuItemButton:'menuitem',Toast:'toast'})
const generationListeners=new Set(),requests=[]
let generation={id:1},menuClosed=false
const actions=uiContext.createHoudiniTitleAction({generation:{getSnapshot:()=>generation,subscribe:listener=>{
  generationListeners.add(listener);return ()=>generationListeners.delete(listener)
}},rpc:{call:(_channel,_method,payload,signal)=>new Promise(resolve=>requests.push({payload,signal,resolve}))}})
currentProject=view
const menuProps={...props,useMenuOpenState:()=>[true,value=>{menuClosed=!value}]}
actions.Feedback()
const action=actions.Menu(menuProps)
const naming=action.props.onSelect()
assert(menuClosed,'native menu closes immediately; its unmount must not cancel the accepted naming action')
await action.props.onSelect()
assert.equal(requests.length,1,'rapid clicks do not duplicate a title-generation request')
assert.equal(requests[0].payload.args.input.sessionId,'a')
assert.equal(requests[0].signal.aborted,false)
requests[0].resolve({ok:true,value:{title:'新标题'}})
await naming
assert.equal(actions.Feedback().props.text,'对话标题已更新。')
const stale=actions.Menu(menuProps).props.onSelect()
generation={id:2};generationListeners.forEach(listener=>listener())
assert(requests[1].signal.aborted)
requests[1].resolve({ok:true,value:{title:'过期标题'}})
await stale
assert.equal(actions.Feedback(),null,'old-generation replies do not publish a success notice')
const leaving=actions.Menu(menuProps).props.onSelect()
actions.dispose()
assert(requests[2].signal.aborted)
requests[2].resolve({ok:true,value:{title:'卸载后的标题'}})
await leaving
assert.equal(actions.Feedback(),null)
console.log('workbench project: native automatic/manual title, explicit refresh, single-source labels, saved untitled, Save As, nested and stale recovery facts, escaped filenames, no unbound/online claim')
