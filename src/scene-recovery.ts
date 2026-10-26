/** Selected-task recovery, using DSH persistence and the task's actual Bridge. */
import type {Context} from '@deepseek-ai/cordis'
import type {Agent} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-user-questions'
import {randomUUID} from 'node:crypto'
import path from 'node:path'
import type {} from '@deepseek-ai/dsh-workspace'
import {HoudiniBridge} from './bridge.js'
import {projectedExecutorState,projectedExecutionFacts,executorIdentityProjection,executorBindingState,type ExecutorIdentityState,type RecoveryBinding} from './executor-identity-projection.js'
import {houdiniSnapshot,recordHoudiniContext} from './dsh-adapter.js'
import {executionStateFromFacts} from './execution-state.js'
import type {HoudiniConnection} from './tool-runtime.js'
import {literalData} from './prompt-data.js'

export interface SceneRecoveryService {
  beforeWrite(agent:Agent,signal:AbortSignal):Promise<void>
  followDirectory(agent:Agent,signal:AbortSignal,probe?:boolean):Promise<void>
  inspect(agent:Agent,signal:AbortSignal):Promise<any>
  assess(agent:Agent,signal:AbortSignal,target?:string):Promise<unknown>
  restore(agent:Agent,assessmentId:string,signal:AbortSignal,target?:string):Promise<unknown>
  ensure(agent:Agent,signal?:AbortSignal):Promise<void>
}
declare module '@deepseek-ai/cordis' {interface Context {houdiniRecovery:SceneRecoveryService}}

export function recoveryMessage(value:RecoveryBinding) {
  return houdiniSnapshot({name:'dsh-houdini:executor-binding',text:
    'Verified saved provenance for the original task nodes has been recorded in the explicitly selected scene. Matching Bridge activation must succeed before those nodes become writable. Historical results are not current scene state. '
    +'Inspect the actual scene and external outputs before repeating interrupted operations. Retrieve each request or job only at its recorded original runtime. '
    +'Unrestored nodes remain foreign. No user confirmation of technical success is needed. '
    +'Load warnings must be checked against affected nodes and dependencies; reconnection does not certify cross-version compatibility. '
    +(value.load_warning_details?'Warning previews may omit the middle. If stored, read the original using houdini_resource(kind="result", ref=load_warning_details.sha256, pointer="/result/load_warnings"). If unavailable, missing detail remains unverified. ':'')+'\n'
    +literalData(JSON.stringify(value))})
}

export async function observeSavedProject(ctx:Context,agent:Agent,directory:string,hipPath:string,signal:AbortSignal,hipIsNew=false,scene?:{scene_id?:unknown;scene_epoch?:unknown}) {
  const current=agent.session.header.cwd
  const normalize=(value:string)=>process.platform==='win32'?path.resolve(value).toLowerCase():path.resolve(value)
  const observed=projectedExecutorState(ctx,agent.session).project
  signal.throwIfAborted()
  // SessionHeader.cwd identifies the native creation project. A HIP Save As
  // changes neither that identity nor the sandbox grant. Only use native cd
  // within the original project; an external HIP remains an explicit path.
  const relative=current?path.relative(normalize(current),normalize(directory)):undefined
  const inside=relative!==undefined&&!relative.startsWith('..'+path.sep)&&relative!=='..'&&!path.isAbsolute(relative)
  const working=ctx.get('workingDirectory') as {get(session:any):string;set(agent:any,directory:string,signal:AbortSignal):Promise<string>}|undefined
  if(inside&&working&&normalize(working.get(agent.session))!==normalize(directory))await working.set(agent,directory,signal)
  if(observed?.hipPath&&normalize(observed.hipPath)===normalize(hipPath))return
  const sceneIdentity=scene&&typeof scene.scene_id==='string'?{scene_id:scene.scene_id}:{}
  const epoch=scene&&typeof scene.scene_epoch==='string'?{scene_epoch:scene.scene_epoch}:{}
  recordHoudiniContext(agent,houdiniSnapshot({name:'dsh-houdini:workspace-directory',text:
    'The selected Houdini scene was saved at the observed HIP path. Native session project and file permissions remain unchanged. Use the actual HIP paths for project outputs; paths outside the original workspace require the native file permission flow. Earlier paths remain historical references.\n'
    +literalData(JSON.stringify({previous_directory:current,directory:working?.get(agent.session)??current,hip_path:hipPath,
      executor_id:projectedExecutorState(ctx,agent.session).identity,hip_is_new:hipIsNew,...sceneIdentity,...epoch}))}))
  if(await ctx.sessions.flush(agent.session)!==true)throw new Error('工程保存观察尚未可靠记录。')
}

async function followSavedDirectory(ctx:Context,agent:Agent,signal:AbortSignal) {
  let state:ExecutorIdentityState
  try {state=projectedExecutorState(ctx,agent.session)}
  catch {return} // Unverified historical identity cannot authorize a cwd change.
  const history=projectedExecutionFacts(ctx,agent.session),execution=history.anchor?.execution
  // A scene-wide last-save marker also appears in other conversations' reads.
  // Only this conversation's successful Save As is authority to move its files.
  const producer=history.saveAs?.execution.owner_session===agent.id?history.saveAs:undefined
  const value=execution?.scene_recovery,saved=value?.successful_save
  const produced=producer?.execution?.scene_recovery
  if(!producer||producer.execution.executor_id!==state.identity||!produced
    ||produced.scene_id!==value?.scene_id||produced.scene_epoch!==value?.scene_epoch
    ||produced.checkpoint_id!==value?.checkpoint_id||produced.hip_path!==value?.hip_path)return
  if(!state.identity||execution?.executor_id!==state.identity||!value||!saved
    ||saved.checkpoint_id!==value.checkpoint_id||typeof saved.hip_path!=='string'
    ||typeof value.hip_path!=='string'||!path.isAbsolute(value.hip_path))return
  if(state.selectedTarget&&state.selectedTarget.scene_id!==value.scene_id)return
  const normalize=(value:string)=>process.platform==='win32'?path.resolve(value).toLowerCase():path.resolve(value)
  if(normalize(saved.hip_path)!==normalize(value.hip_path))return
  await observeSavedProject(ctx,agent,path.dirname(value.hip_path),value.hip_path,signal,false,value)
}

export function installSceneRecovery(ctx:Context,connection:HoudiniConnection):void {
  // Consume this session's current Save As receipt without moving native
  // history or changing permissions. There is no endpoint lookup or recovery.
  ctx.on?.('agent/pre-step',async({agent,signal},next)=>{
    await followSavedDirectory(ctx,agent,signal)
    return next()
  })
  if(!(connection instanceof HoudiniBridge)) {
    const services=new WeakMap<Agent,{bridge:HoudiniBridge;key:string;service:SceneRecoveryService}>()
    const serviceFor=async(agent:Agent,signal:AbortSignal,write=false)=>{
      // Selection belongs to the target service. Recovery never searches other
      // windows, opens a project, or substitutes a historical endpoint.
      const target=await connection.resolve({agent,signal},{write})
      const key=JSON.stringify(projectedExecutorState(ctx,agent.session).selectedTarget)
      let entry=services.get(agent)
      if(!entry||entry.key!==key||entry.bridge.targetExecutorId!==target.targetExecutorId||entry.bridge.baseUrl!==target.baseUrl) {
        entry={bridge:target,key,service:createSceneRecovery(ctx,target)}
        services.set(agent,entry)
      }
      return entry.service
    }
    ctx.provide('houdiniRecovery',{
      beforeWrite:async(agent,signal)=>(await serviceFor(agent,signal)).beforeWrite(agent,signal),
      followDirectory:async(agent,signal)=>followSavedDirectory(ctx,agent,signal),
      ensure:async(agent,signal)=>(await serviceFor(agent,signal??new AbortController().signal,true)).ensure(agent,signal),
      inspect:async(agent,signal)=>(await serviceFor(agent,signal)).inspect(agent,signal),
      assess:async(agent,signal)=>(await serviceFor(agent,signal)).assess(agent,signal),
      restore:async(agent,id,signal)=>(await serviceFor(agent,signal,true)).restore(agent,id,signal),
    })
    return
  }
  ctx.provide('houdiniRecovery',createSceneRecovery(ctx,connection))
}

function createSceneRecovery(ctx:Context,connection:HoudiniBridge):SceneRecoveryService {
  const plans=new WeakMap<Agent,{id:string;state:string;facts:any;previous:string;sources:string[]}>()
  const running=new WeakSet<Agent>()
  const writePhase=new WeakSet<Agent>()
  const attempted=new WeakMap<Agent,string>()
  const bridge=()=>connection
  const persisted=async(agent:Agent)=>{
    if(await ctx.sessions.flush(agent.session)!==true)
      throw new Error('权限恢复记录尚未可靠保存，本轮未继续激活原节点权限。现场选择和内容保留，可以继续查看或讨论后再试。')
  }
  const key=(agent:Agent)=>{
    const state=projectedExecutorState(ctx,agent.session)
    return JSON.stringify([state.identity,state.selectionRevision,state.recovery,anchor(agent)])
  }
  const anchor=(agent:Agent)=>{
    const state=projectedExecutorState(ctx,agent.session),selected=state.selectedTarget
    const execution=state.execution
    if(!selected)return execution.current.anchor?.execution
    // An observation in the newly selected runtime cannot prove that old
    // checkpoint nodes are already owned. Retain the latest original receipt
    // for this exact scene, excluding status retrievals and this current epoch.
    const rows=Object.values(execution.checkpoints[selected.scene_id??'']??{}).filter(row=>row.execution.owner_session===agent.id
      &&row.execution.scene_recovery?.scene_id===selected.scene_id
      &&typeof row.execution.scene_recovery?.checkpoint_id==='string'
      &&(row.execution.executor_id!==selected.executor_id||row.execution.scene_recovery.scene_epoch!==selected.scene_epoch))
    return rows.reduce<(typeof rows)[number]|undefined>((last,row)=>!last
      ||row.execution.observed_at>last.execution.observed_at
      ||row.execution.observed_at===last.execution.observed_at&&row.execution.sequence>last.execution.sequence?row:last,undefined)?.execution
  }
  const recordedScene=(agent:Agent)=>anchor(agent)?.scene_recovery?.scene_id
    ??projectedExecutorState(ctx,agent.session).selectedTarget?.scene_id
    ??projectedExecutorState(ctx,agent.session).project?.sceneId
  const service:SceneRecoveryService={
    async followDirectory(agent,signal) {await followSavedDirectory(ctx,agent,signal)},
    async beforeWrite(agent,signal) {
      const state=projectedExecutorState(ctx,agent.session),selected=state.selectedTarget
      const previous=anchor(agent),saved=previous?.scene_recovery
      // A fresh explicitly selected project is writable without proving the
      // conversation's former project. Only exact same-scene saved provenance
      // is a candidate for restoring this task's own old nodes.
      if(!selected||selected.executor_id!==connection.targetExecutorId||!saved?.checkpoint_id
        ||saved.scene_id!==selected.scene_id||typeof previous?.executor_id!=='string')return
      if(previous.executor_id===selected.executor_id&&saved.scene_epoch===selected.scene_epoch)return
      if(state.recovery?.executor_id===selected.executor_id&&state.recovery.scene_id===selected.scene_id
        &&state.recovery.runtime_id===selected.runtime_id
        &&state.recovery.scene_epoch===selected.scene_epoch
        &&state.recovery.checkpoint_id===saved.checkpoint_id) {
        await service.ensure(agent,signal)
        return
      }
      const attempt=JSON.stringify([selected.executor_id,selected.runtime_id,selected.scene_epoch,saved.checkpoint_id])
      if(attempted.get(agent)===attempt)return
      writePhase.add(agent)
      try {
        const assessment=await service.assess(agent,signal) as any
        // Pending checkpoint workers, transport and durability failures may
        // settle without a new scene epoch. Do not permanently cache them.
        if(assessment.status!=='ready')return
        if(assessment.requires_reload===true) {attempted.set(agent,attempt);return}
        if(!Number.isInteger(assessment.owned_nodes)||assessment.owned_nodes<0
          ||typeof assessment.checkpoint_id!=='string'||typeof assessment.scene_id!=='string'
          ||typeof assessment.scene_epoch!=='string')return
        if(assessment.owned_nodes===0||assessment.checkpoint_id!==saved.checkpoint_id
          ||assessment.scene_id!==selected.scene_id||assessment.scene_epoch!==selected.scene_epoch) {
          attempted.set(agent,attempt)
          return
        }
        await service.restore(agent,assessment.assessment_id,signal)
        attempted.set(agent,attempt)
      } catch(error) {
        signal.throwIfAborted()
        recordHoudiniContext(agent,houdiniSnapshot({name:'dsh-houdini:ownership-recovery',text:
          'The selected scene remains available. Restoration of its previous node ownership was not confirmed; ordinary ownership checks still apply. '
          +'No file was opened and no operation was replayed.\n'+literalData(error instanceof Error?error.message:String(error))}))
      } finally {writePhase.delete(agent)}
    },
    async ensure(agent,signal) {
      const state=projectedExecutorState(ctx,agent.session)
      if(!state.recovery)return
      const target=bridge(),operation=state.recovery
      if(state.identity!==target.targetExecutorId)throw new Error('恢复目标已经改变，本轮未激活原节点权限。')
      const current=()=>{
        const value=projectedExecutorState(ctx,agent.session)
        return value.identity===state.identity&&value.selectionRevision===state.selectionRevision
          &&value.recovery?.operation_id===operation.operation_id
      }
      await persisted(agent)
      if(!current())throw new Error('保存恢复记录期间现场选择已变化，本轮未激活原节点权限。')
      const result=await target.recover('activate',{session_id:agent.id,operation_id:operation.operation_id},signal)
      if(!current())throw new Error('现场选择已变化，未将旧现场的恢复回执当作当前结果。')
      if(result.status!=='active'||result.operation_id!==operation.operation_id
        ||result.executor_id!==state.identity||result.checkpoint_id!==operation.checkpoint_id)
        throw new Error('恢复激活回执不匹配，未确认原节点权限。')
    },
    async inspect(agent,signal) {
      const target=bridge(),state=projectedExecutorState(ctx,agent.session)
      if(!state.identity||(state.identity===target.targetExecutorId&&!state.recovery
        &&!anchor(agent))) {
        await target.inspectExecutor(signal)
        return {status:'new_task',executor_id:target.targetExecutorId,message:'尚未执行过 Houdini 操作。'}
      }
      const before=key(agent),previous=anchor(agent)
      const recordedHip=executionStateFromFacts(projectedExecutionFacts(ctx,agent.session))?.hip_path??state.recovery?.hip_path
      const sceneId=recordedScene(agent)
      let value:any
      try {value=await target.recover('assess',{session_id:agent.id,previous_executor:previous?.executor_id??state.recovery?.previous_executor??state.identity,
        source_executors:state.executors,...(typeof sceneId==='string'?{expected:{scene_id:sceneId,
          ...(previous?.scene_recovery?.scene_epoch?{scene_epoch:previous.scene_recovery.scene_epoch}:{})}}:{})},signal)
        if(value.executor_id!==target.targetExecutorId)throw new Error('连接回执来自另一个 Houdini，尚未确认当前工程连接。')
        if(value.status==='connected'&&state.identity!==target.targetExecutorId)
          throw new Error('原对话仍记录着另一个 Houdini，当前连接尚未完成接续。')
      }
      catch(error) {
        signal.throwIfAborted()
        return {status:'unavailable',executor_id:target.targetExecutorId,recorded_hip:recordedHip,message:error instanceof Error?error.message:String(error)}
      }
      value={...value,recorded_hip:recordedHip}
      if(key(agent)!==before)throw new Error('任务在检查期间发生变化，请重新检查。')
      if(sceneId&&value.scene_id!==sceneId)return {...value,status:'different_scene',
        message:'当前工程与原对话记录的工程不同。请在对话中明确要继续哪份工程；系统没有切换或修改内容。'}
      return value
    },
    async assess(agent,signal) {
      if(running.has(agent))throw new Error('工程恢复正在进行，请等待结果。')
      const target=bridge(),state=projectedExecutorState(ctx,agent.session),before=key(agent)
      const value=await service.inspect(agent,signal)
      if(key(agent)!==before)throw new Error('任务在检查期间发生变化，请重新检查。')
      if(value.status!=='ready')return value
      if(!state.identity)throw new Error('当前任务没有可核对的原连接身份。')
      const retained=state.recovery&&state.recovery.executor_id===target.targetExecutorId
        &&state.recovery.checkpoint_id===value.checkpoint_id&&state.recovery.scene_epoch===value.scene_epoch
        ?state.recovery:undefined
      const id=retained?.operation_id??randomUUID().replaceAll('-','')
      plans.set(agent,{id,state:before,facts:value,previous:anchor(agent)?.executor_id??state.recovery?.previous_executor??state.identity,sources:state.executors})
      return {...value,assessment_id:id,message:'已找到此任务的可信保存点。恢复后请先核对当前工程；未保存的进度和外部副作用不会自动重放。'}
    },
    async restore(agent,assessmentId,signal) {
      if((agent.status!=='idle'&&!writePhase.has(agent))||running.has(agent))throw new Error('工程接续只能在当前任务的模型步骤边界进行。')
      const target=bridge(),state=projectedExecutorState(ctx,agent.session)
      // An acknowledged commit may have lost its activation response. Retrying
      // the same displayed operation must flush again, then activate it once.
      if(state.recovery?.operation_id===assessmentId&&state.identity===target.targetExecutorId) {
        await service.ensure(agent,signal)
        return {status:'active',message:'当前工程的原节点归属已恢复，本轮继续核对实际现场。'}
      }
      const plan=plans.get(agent)
      if(!plan||plan.id!==assessmentId||plan.state!==key(agent))throw new Error('检查结果已过期，请重新检查工程。')
      if(plan.facts.requires_reload)throw new Error('当前节点没有可验证的加载基线。请先保留未保存内容，手动重新打开要恢复的工程后再检查；系统没有加载或替换文件。')
      running.add(agent)
      try {
        const prepared=await target.recover('prepare',{session_id:agent.id,previous_executor:plan.previous,
          source_executors:plan.sources,operation_id:plan.id,expected:plan.facts,
          reload_saved:false},signal)
        if(prepared.executor_id!==target.targetExecutorId||prepared.operation_id!==plan.id
          ||prepared.checkpoint_id!==plan.facts.checkpoint_id||prepared.scene_id!==plan.facts.scene_id
          ||!['prepared','active'].includes(prepared.status))
          throw new Error('恢复返回的工程或连接身份不匹配，未提交新绑定。')
        signal.throwIfAborted()
        if((agent.status!=='idle'&&!writePhase.has(agent))||plan.state!==key(agent))throw new Error('任务在恢复期间发生变化，未提交新绑定。')
        const value:RecoveryBinding={schema:2,kind:'executor_recovery',previous_executor:plan.previous,
          executor_id:prepared.executor_id,operation_id:plan.id,checkpoint_id:prepared.checkpoint_id,
          scene_id:prepared.scene_id,scene_epoch:prepared.scene_epoch,runtime_id:prepared.runtime_id,
          hip_path:plan.facts.hip_path,restored_nodes:prepared.restored_nodes,
          unrestored_nodes:prepared.unrestored_nodes??[],
          load_warnings:prepared.load_warnings??[],
          ...(prepared.load_warning_details?{load_warning_details:prepared.load_warning_details}:{}),
          ...(plan.facts.user_choice?{user_choice:plan.facts.user_choice}:{}),
          ...(!state.selectionRecorded?{previous_work:executionStateFromFacts(projectedExecutionFacts(ctx,agent.session))}:{})}
        const message=recoveryMessage(value)
        // Same-target ownership facts are native queued context. They must not
        // insert a user body between an assistant tool call and its result or
        // retire that current request. Legacy fixed-target explicit idle
        // recovery retains the committed transition required by its old schema.
        const event=state.selectionRecorded
          ?{type:'agent/inbox/spliced',data:{target:'next-step',start:0,removedCount:0,inserted:[message]}}
          :{type:'user/message',data:message}
        executorBindingState(executorIdentityProjection.apply(state,event))
        if(state.selectionRecorded)recordHoudiniContext(agent,message)
        else agent.session.append('user/message',message,{surfaceOp:'append'})
        if(projectedExecutorState(ctx,agent.session).recovery?.operation_id!==value.operation_id)
          throw new Error('权限恢复事实尚未进入 DSH 持久记录，本轮未激活原节点权限。')
        await service.ensure(agent,signal)
        plans.delete(agent)
        return {status:'active',restored_nodes:value.restored_nodes,
          message:'当前工程的原节点归属已恢复，恢复 '+value.restored_nodes+' 个节点的修改归属；本轮继续核对实际现场。'}
      } finally {running.delete(agent)}
    },
  }
  return service
}
