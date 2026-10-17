import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import path from 'node:path'
import {Context} from '@deepseek-ai/cordis'
import {SessionStore} from '@deepseek-ai/dsh-session'
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection'
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
new SessionProjectionRegistry(context)
registerExecutorIdentityProjection(context)
const titles=new SessionTitleService(context,{fallbackMaxWords:12,fallbackMaxBytes:80,maxTitleBytes:160})
const executor='a'.repeat(32),replacement='b'.repeat(32),registration='c'.repeat(32)
const record={workbench:true,executor_id:executor,registration_id:registration,scene_id:'d'.repeat(32),scene_epoch:'e'.repeat(32),
  hip_path:path.resolve('tools/out/test103/untitled.hip'),hip_is_new:false,workspace_path:path.resolve('tools/out/test103')}
const agents=new Map()
context.provide('workspaceRegistry',{list:()=>[],create:async()=>({id:'workspace',title:'test103',sessionIds:[]}),archivedSessionIds:[]})
context.provide('sessionController',{
  create:async({sessionId})=>{
    const session=context.sessions.create(sessionId)
    agents.set(sessionId,{id:sessionId,session,status:'idle',inject:message=>session.append('agent/inbox/spliced',{target:'next-step',start:0,inserted:[message]})})
    return {sessionId}
  },
  resolveAgent:async sessionId=>({agent:agents.get(sessionId)}),
  rename:()=>{throw Error('Opening an engineering file must not impersonate user title choice')},
})
let persisted=true
context.sessions.flush=async()=>persisted
const controller=new ExecutorController(context,{directory:{find:async()=>record},selectInitial:async agent=>{
  await new ExecutorBinding(undefined,(_session,message)=>agent.inject(message)).ensure(agent.session,executor)
}},true)
try {
  const opened=await controller.openWorkspace({executorId:executor,registrationId:registration,expectedHip:record.hip_path,requestId:'f'.repeat(32)},new AbortController().signal)
  const session=agents.get(opened.sessionId).session
  assert.equal(titles.get(session),undefined,'project opening leaves DSH auto-title unpinned')
  assert.equal(foldExecutorState(session.snapshotEvents()).project.hipPath,record.hip_path)
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
assert.match(text(uiContext.HoudiniProjectDetail(props)),/不代表 Houdini 当前在线/)
currentProject={hipPath:'C:/folder/<img src=x>.hip',hipIsNew:false,needsReview:false}
assert.match(text(uiContext.HoudiniProjectLabel(props)),/<img src=x>.hip/,'untrusted filename stays React text, not HTML')
currentProject={hipPath:'C:/untitled.hip',hipIsNew:true,needsReview:false}
assert.match(text(uiContext.HoudiniProjectLabel(props)),/未保存工程/)
currentProject=null
assert.equal(uiContext.HoudiniProjectMark(props),null)
assert.equal(uiContext.HoudiniProjectLabel(props),null)
assert(!fragment.includes('dangerouslySetInnerHTML'))
assert(!fragment.includes('setInterval'),'resident presence polling is banned')
const records={online:{[view.executorId]:{status:'online'}},offline:{[view.executorId]:{status:'offline'}},missing:{}}
assert.equal(uiContext.houdiniEndpointState(view,records.online),'online')
assert.equal(uiContext.houdiniEndpointState(view,records.offline),'offline')
assert.equal(uiContext.houdiniEndpointState(view,records.missing),'unknown','absence is not proof of process exit')
assert.equal(uiContext.houdiniEndpointState(view,{[view.executorId]:{status:'unknown'}}),'unknown')
assert.equal(uiContext.houdiniEndpointState(view,{[view.executorId]:{status:'online',sceneEpoch:'different'}}),'changed','a live window that switched scene is not silently online')
assert.equal(uiContext.houdiniEndpointState(view,null),null)
assert.equal(uiContext.houdiniProjectName({hipIsNew:true,label:'未保存工程 2'}),'未保存工程 2')
React.useSyncExternalStore=(_subscribe,get)=>get()
React.useEffect=callback=>callback()
Object.assign(uiContext,{AbortController,setTimeout,clearTimeout})
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
