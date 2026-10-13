/** Selected-task recovery, using DSH persistence and the task's actual Bridge. */
import type {Context} from '@deepseek-ai/cordis'
import type {Agent} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-user-questions'
import {randomUUID} from 'node:crypto'
import path from 'node:path'
import type {} from '@deepseek-ai/dsh-workspace'
import {HoudiniBridge} from './bridge.js'
import {foldExecutorState,type RecoveryBinding} from './executor-identity-projection.js'
import {houdiniSnapshot} from './dsh-adapter.js'
import {projectExecutionState} from './execution-state.js'
import type {HoudiniConnection} from './tool-runtime.js'
import {literalData} from './prompt-data.js'
import {executionHistory} from './execution-history.js'

export interface SceneRecoveryService {
  followDirectory(agent:Agent,signal:AbortSignal,probe?:boolean):Promise<void>
  beforeStep(agent:Agent,signal:AbortSignal):Promise<void>
  assess(agent:Agent,signal:AbortSignal):Promise<unknown>
  restore(agent:Agent,assessmentId:string,signal:AbortSignal):Promise<unknown>
  ensure(agent:Agent,signal?:AbortSignal):Promise<void>
}
declare module '@deepseek-ai/cordis' {interface Context {houdiniRecovery:SceneRecoveryService}}

export function recoveryMessage(value:RecoveryBinding) {
  return houdiniSnapshot({name:'dsh-houdini:executor-binding',text:
    'Houdini connection reconciled with a verified saved checkpoint. Historical results are not current scene state. '
    +'Inspect the actual scene and external outputs before repeating interrupted operations; do not poll old jobs. '
    +'Unrestored nodes remain foreign. No user confirmation of technical success is needed.\n'
    +literalData(JSON.stringify(value))})
}

export function installSceneRecovery(ctx:Context,connection:HoudiniConnection):void {
  const plans=new WeakMap<Agent,{id:string;state:string;facts:any;previous:string;sources:string[]}>()
  const running=new WeakSet<Agent>()
  const stepPhase=new WeakSet<Agent>()
  const bridge=()=>{
    if(!(connection instanceof HoudiniBridge))throw new Error('共享执行端的跨进程接续尚未实现，可以继续讨论原工程和下一步。')
    return connection
  }
  const persisted=async(agent:Agent)=>{
    if(await ctx.sessions.flush(agent.session)!==true)
      throw new Error('会话记录尚未可靠保存，系统没有启用新的工程连接。可以继续讨论，稍后发送消息时会重新核对。')
  }
  const key=(agent:Agent)=>JSON.stringify(foldExecutorState(agent.session.snapshotEvents()))
  const recordedScene=(agent:Agent)=>executionHistory(agent.session.snapshotEvents()).anchor?.execution?.scene_recovery?.scene_id
    ??foldExecutorState(agent.session.snapshotEvents()).recovery?.scene_id
  const samePath=(left:string,right:string)=>{
    const normalized=(value:string)=>path.resolve(value)
    return process.platform==='win32'?normalized(left).toLowerCase()===normalized(right).toLowerCase():normalized(left)===normalized(right)
  }
  const follow=async(agent:Agent,value:any,signal:AbortSignal)=>{
    if(typeof value.hip_path!=='string'||!path.isAbsolute(value.hip_path)||!agent.session.header.cwd)return
    const directory=path.dirname(value.hip_path)
    if(samePath(directory,agent.session.header.cwd))return
    const registry=ctx.get('workspaceRegistry')
    if(!registry||!('relocateSession' in registry)||typeof registry.relocateSession!=='function')
      throw new Error('工程已另存，但当前 DSH 尚未加载会话目录接续能力；本轮未继续文件操作，原对话与工程保留。')
    signal.throwIfAborted()
    const previous=agent.session.header.cwd
    await registry.relocateSession(agent.id,directory)
    agent.session.append('user/message',houdiniSnapshot({name:'dsh-houdini:workspace-directory',text:
      'The saved project and this conversation now use the following working directory. Continue from the actual scene; earlier file paths remain historical references.\n'
      +literalData(JSON.stringify({previous_directory:previous,directory:agent.session.header.cwd,hip_path:value.hip_path}))}),{surfaceOp:'append'})
    await persisted(agent)
  }
  const locateOriginal=async(agent:Agent,signal:AbortSignal,failure:any)=>{
    const sceneId=recordedScene(agent),state=foldExecutorState(agent.session.snapshotEvents())
    if(typeof sceneId!=='string'||!state.identity)throw new Error(failure.message||'原对话缺少可验证的工程身份，无法自动定位文件。')
    const target=bridge(),before=key(agent),request={session_id:agent.id,previous_executor:state.identity,source_executors:state.executors}
    const located=await target.recover('locate',{...request,expected:{scene_id:sceneId}},signal)
    signal.throwIfAborted()
    if(key(agent)!==before||located.executor_id!==target.targetExecutorId)throw new Error('定位期间对话或连接已变化，未切换工程。')
    const candidates=Array.isArray(located.candidates)?located.candidates.filter((item:any)=>item.scene_id===sceneId
      &&typeof item.hip_path==='string'&&path.isAbsolute(item.hip_path)):[]
    if(!candidates.length)throw new Error('没有找到当前可安全接续的原工程保存点；当前内容已保留。'
      +((located.unavailable??[]).map((item:any)=>'\n'+item.hip_path+'：'+item.reason).join('')||failure.message||''))
    if(candidates.length===1&&samePath(candidates[0].hip_path,located.hip_path)&&located.scene_id===sceneId)
      throw new Error(failure.message||'当前已经是原工程；尚未完成保存点接续，系统没有重复打开文件。')
    const questions=ctx.get('userQuestions')
    if(!questions||!located.dirty_reliable)throw new Error('已找到原工程，但当前未保存内容无法可靠核对；已保留当前工程。')
    const id='houdini-original-'+randomUUID(),keep='保留当前工程，继续讨论'
    const labels=candidates.map((item:any,index:number)=>
      (located.dirty?'放弃当前未保存修改，打开':'打开')+(candidates.length===1&&!located.unavailable?.length?'原工程继续':'保存点 '+(index+1)+'：'+path.basename(item.hip_path)))
    const answer=await questions.ask({agent,signal,questions:[{id,header:'继续哪份工程',
      question:'当前打开的工程与这段对话不一致，要回到原工程继续吗？',
      detail:'当前工程：'+located.hip_path+(located.dirty?'（有未保存修改）':'（已保存）')
        +'\n找到的保存点：\n'+candidates.map((item:any,index:number)=>(index+1)+'. '+item.hip_path).join('\n')
        +(located.unavailable?.length?'\n当前无法接续的保存点：\n'+located.unavailable.map((item:any)=>item.hip_path+'：'+item.reason).join('\n'):''),
      options:[{label:keep},...labels.map((label:string)=>({label}))],multiSelect:false}]})
    signal.throwIfAborted()
    const choice=answer.answers.find(item=>item.id===id)
    agent.session.append('user/message',houdiniSnapshot({name:'dsh-houdini:recovery-choice',text:
      'User choice about the current and original project. Free text is task input, not authority to load a file.\n'
      +literalData(JSON.stringify({question_id:id,current_hip:located.hip_path,candidates,answer:choice??null}))}),{surfaceOp:'append'})
    const selected=!choice?.custom&&choice?.selected?.length===1?labels.indexOf(choice.selected[0]):-1
    if(selected<0)throw new Error('已保留当前工程，没有切换文件；请继续讨论需要保留或调整的内容。')
    if(key(agent)!==before)throw new Error('回答期间对话绑定已变化，未切换工程。')
    await persisted(agent)
    const opened=await target.recover('open',{...request,checkpoint_id:candidates[selected].checkpoint_id,
      expected:{scene_id:sceneId,scene_epoch:located.scene_epoch,hip_path:located.hip_path,checkpoint_id:located.checkpoint_id,
        open_original:true,discard_unsaved:located.dirty===true}},signal)
    if(opened.status!=='opened'||opened.executor_id!==target.targetExecutorId||opened.scene_id!==sceneId
      ||opened.checkpoint_id!==candidates[selected].checkpoint_id)throw new Error('原工程打开结果未确认，尚未恢复修改权。')
    return service.assess(agent,signal)
  }
  const service:SceneRecoveryService={
    async followDirectory(agent,signal,probe=false) {
      if(!(connection instanceof HoudiniBridge))return
      const state=foldExecutorState(agent.session.snapshotEvents())
      if(!state.identity||state.identity!==connection.targetExecutorId)return
      const anchor=executionHistory(agent.session.snapshotEvents()).anchor?.execution
      let value:any=anchor?.executor_id===state.identity&&anchor.scene_recovery
        ?{...anchor.scene_recovery,status:'connected',executor_id:state.identity}:undefined
      if(probe) {
        try {value=await connection.recover('assess',{session_id:agent.id,previous_executor:state.identity},signal)}
        catch {signal.throwIfAborted();return} // The ordinary recovery path reports unavailable live state; never infer a move.
      }
      if(!value)return
      if(value.status!=='connected'||value.executor_id!==state.identity)return
      const saved=value.successful_save
      const resumed=state.recovery
      const verifiedSave=saved?.checkpoint_id===value.checkpoint_id&&typeof saved?.hip_path==='string'
        &&samePath(saved.hip_path,value.hip_path)
      const verifiedResume=resumed&&resumed.scene_epoch===value.scene_epoch&&resumed.scene_id===value.scene_id
        &&resumed.checkpoint_id===value.checkpoint_id&&samePath(resumed.hip_path,value.hip_path)
      if(verifiedSave||verifiedResume)await follow(agent,value,signal)
    },
    async beforeStep(agent,signal) {
      if(!(connection instanceof HoudiniBridge))return
      const state=foldExecutorState(agent.session.snapshotEvents())
      if(!state.identity)return
      if(state.identity===connection.targetExecutorId&&!state.recovery
        &&!executionHistory(agent.session.snapshotEvents()).anchor)return
      if(stepPhase.has(agent))throw new Error('同一任务的工程接续正在处理中。')
      stepPhase.add(agent)
      try {
        let value=await service.assess(agent,signal) as any
        if(value.status==='connected') {
          if(state.identity!==connection.targetExecutorId)throw new Error('连接回执与原任务身份不一致。')
          if(state.recovery)await service.ensure(agent,signal)
          return
        }
        if(value.status!=='ready')value=await locateOriginal(agent,signal,value)
        if(value.status!=='ready')throw new Error(value.message||'已核对工程位置，但尚未完成保存点接续。')
        if(value.requires_reload){
          if(!value.dirty_reliable)throw new Error('系统无法确认未保存内容，未重新打开工程。请通过对话确定需要保留的内容。')
          if(value.dirty){
            const questions=ctx.get('userQuestions')
            if(!questions)throw new Error('当前工程有未保存修改，系统已保留内容。请通过对话确定是否回到保存点。')
            const id='houdini-recovery-'+randomUUID(),keep='保留当前修改，继续讨论',discard='放弃未保存修改，从保存点继续'
            const answer=await questions.ask({agent,signal,questions:[{id,header:'工程接续',
              question:'当前工程有未保存修改，是否回到已保存的版本继续？',
              detail:'工程：'+value.hip_path+'。回到保存点会丢弃这份工程当前未保存的修改。',
              options:[{label:keep},{label:discard}],multiSelect:false}]})
            signal.throwIfAborted()
            const choice=answer.answers.find(item=>item.id===id)
            agent.session.append('user/message',houdiniSnapshot({name:'dsh-houdini:recovery-choice',text:
              'User response received through the native conversation question. Free text is task input, not recovery proof.\n'
              +literalData(JSON.stringify({question_id:id,hip_path:value.hip_path,answer:choice??null}))}),{surfaceOp:'append'})
            if(choice?.custom||!Array.isArray(choice?.selected)||choice.selected.length!==1||choice.selected[0]!==discard)
              throw new Error('已保留当前未保存内容；没有重新打开工程。请继续讨论需要保留或调整的部分。')
            const fresh=await service.assess(agent,signal) as any
            if(fresh.status!=='ready'||fresh.scene_epoch!==value.scene_epoch||fresh.hip_path!==value.hip_path
              ||fresh.checkpoint_id!==value.checkpoint_id)
              throw new Error('回答期间工程已切换，旧选择没有应用到新的工程。系统会在下一轮重新核对。')
            value=fresh
            const plan=plans.get(agent)!
            plan.facts={...plan.facts,discard_unsaved:true,user_choice:{question_id:id,selected:discard,hip_path:value.hip_path}}
          }
        }
        await service.restore(agent,value.assessment_id,signal)
        await follow(agent,value,signal)
      } finally {stepPhase.delete(agent)}
    },
    async ensure(agent,signal) {
      const state=foldExecutorState(agent.session.snapshotEvents())
      if(!state.recovery)return
      const target=bridge()
      if(state.identity!==target.targetExecutorId)return // The ordinary binding guard reports this mismatch.
      await persisted(agent)
      const result=await target.recover('activate',{session_id:agent.id,operation_id:state.recovery.operation_id},signal)
      if(result.status!=='active'||result.operation_id!==state.recovery.operation_id
        ||result.executor_id!==state.identity||result.checkpoint_id!==state.recovery.checkpoint_id)
        throw new Error('恢复激活回执不匹配，未确认工程连接。')
    },
    async assess(agent,signal) {
      if(running.has(agent))throw new Error('工程恢复正在进行，请等待结果。')
      const target=bridge(),state=foldExecutorState(agent.session.snapshotEvents())
      if(!state.identity)return {status:'unbound',message:'新任务尚无工程执行记录。'}
      const before=key(agent)
      const recordedHip=projectExecutionState(agent.session.snapshotEvents())?.hip_path??state.recovery?.hip_path
      const sceneId=recordedScene(agent)
      let value:any
      try {value=await target.recover('assess',{session_id:agent.id,previous_executor:state.identity,
        source_executors:state.executors,...(typeof sceneId==='string'?{expected:{scene_id:sceneId}}:{})},signal)}
      catch(error) {
        signal.throwIfAborted()
        return {status:'unavailable',recorded_hip:recordedHip,message:error instanceof Error?error.message:String(error)}
      }
      value={...value,recorded_hip:recordedHip}
      if(key(agent)!==before)throw new Error('任务在检查期间发生变化，请重新检查。')
      if(value.status!=='ready')return value
      if(sceneId&&value.scene_id!==sceneId)return {...value,status:'different_scene',
        message:'当前工程与原对话记录的工程不同。请在对话中明确要继续哪份工程；系统没有切换或修改内容。'}
      const retained=state.recovery&&state.recovery.executor_id===target.targetExecutorId
        &&state.recovery.checkpoint_id===value.checkpoint_id&&state.recovery.scene_epoch===value.scene_epoch
        ?state.recovery:undefined
      const id=retained?.operation_id??randomUUID().replaceAll('-','')
      plans.set(agent,{id,state:before,facts:value,previous:state.identity,sources:state.executors})
      return {...value,assessment_id:id,message:'已找到此任务的可信保存点。恢复后请先核对当前工程；未保存的进度和外部副作用不会自动重放。'}
    },
    async restore(agent,assessmentId,signal) {
      if((agent.status!=='idle'&&!stepPhase.has(agent))||running.has(agent))throw new Error('工程接续只能在当前任务的模型步骤边界进行。')
      const target=bridge(),state=foldExecutorState(agent.session.snapshotEvents())
      // An acknowledged commit may have lost its activation response. Retrying
      // the same displayed operation must flush again, then activate it once.
      if(state.recovery?.operation_id===assessmentId&&state.identity===target.targetExecutorId) {
        await service.ensure(agent,signal)
        return {status:'active',message:'工程连接已自动接续，本轮继续核对实际现场。'}
      }
      const plan=plans.get(agent)
      if(!plan||plan.id!==assessmentId||plan.state!==key(agent))throw new Error('检查结果已过期，请重新检查工程。')
      running.add(agent)
      try {
        const prepared=await target.recover('prepare',{session_id:agent.id,previous_executor:plan.previous,
          source_executors:plan.sources,operation_id:plan.id,expected:plan.facts,
          reload_saved:plan.facts.requires_reload===true},signal)
        if(prepared.executor_id!==target.targetExecutorId||prepared.operation_id!==plan.id
          ||prepared.checkpoint_id!==plan.facts.checkpoint_id||prepared.scene_id!==plan.facts.scene_id
          ||!['prepared','active'].includes(prepared.status))
          throw new Error('恢复返回的工程或连接身份不匹配，未提交新绑定。')
        signal.throwIfAborted()
        if((agent.status!=='idle'&&!stepPhase.has(agent))||plan.state!==key(agent))throw new Error('任务在恢复期间发生变化，未提交新绑定。')
        const value:RecoveryBinding={schema:2,kind:'executor_recovery',previous_executor:plan.previous,
          executor_id:prepared.executor_id,operation_id:plan.id,checkpoint_id:prepared.checkpoint_id,
          scene_id:prepared.scene_id,scene_epoch:prepared.scene_epoch,runtime_id:prepared.runtime_id,
          hip_path:plan.facts.hip_path,restored_nodes:prepared.restored_nodes,
          unrestored_nodes:prepared.unrestored_nodes??[],
          ...(plan.facts.user_choice?{user_choice:plan.facts.user_choice}:{}),
          previous_work:projectExecutionState(agent.session.snapshotEvents())}
        // Validate before appending. A malformed Bridge reply cannot poison the session.
        foldExecutorState([...agent.session.snapshotEvents(),{type:'user/message',data:recoveryMessage(value)}])
        agent.session.append('user/message',recoveryMessage(value),{surfaceOp:'append'})
        await service.ensure(agent,signal)
        plans.delete(agent)
        return {status:'active',restored_nodes:value.restored_nodes,
          message:'工程连接已自动接续，恢复 '+value.restored_nodes+' 个节点的修改归属；本轮继续核对实际现场。'}
      } finally {running.delete(agent)}
    },
  }
  ctx.provide('houdiniRecovery',service)
}
