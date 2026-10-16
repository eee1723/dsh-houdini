/** Selected-task recovery, using DSH persistence and the task's actual Bridge. */
import type {Context} from '@deepseek-ai/cordis'
import type {Agent} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-user-questions'
import {randomUUID} from 'node:crypto'
import path from 'node:path'
import type {} from '@deepseek-ai/dsh-workspace'
import {HoudiniBridge} from './bridge.js'
import {foldExecutorState,type RecoveryBinding} from './executor-identity-projection.js'
import {houdiniSnapshot,recordHoudiniContext,workspaceOpeningMessage} from './dsh-adapter.js'
import {projectExecutionState} from './execution-state.js'
import type {HoudiniConnection} from './tool-runtime.js'
import {literalData} from './prompt-data.js'
import {executionHistory} from './execution-history.js'

export interface SceneRecoveryService {
  beforeTool?(agent:Agent,signal:AbortSignal):Promise<void>
  followDirectory(agent:Agent,signal:AbortSignal,probe?:boolean):Promise<void>
  beforeStep(agent:Agent,signal:AbortSignal):Promise<void>
  inspect(agent:Agent,signal:AbortSignal):Promise<any>
  assess(agent:Agent,signal:AbortSignal):Promise<unknown>
  restore(agent:Agent,assessmentId:string,signal:AbortSignal):Promise<unknown>
  ensure(agent:Agent,signal?:AbortSignal):Promise<void>
}
declare module '@deepseek-ai/cordis' {interface Context {houdiniRecovery:SceneRecoveryService}}

export function recoveryMessage(value:RecoveryBinding) {
  return houdiniSnapshot({name:'dsh-houdini:executor-binding',text:
    'Houdini connection reconciled with a verified saved checkpoint. Historical results are not current scene state. '
    +'Inspect the actual scene and external outputs before repeating interrupted operations; do not poll old jobs. '
    +'Unrestored nodes remain foreign. No user confirmation of technical success is needed. '
    +'Load warnings must be checked against affected nodes and dependencies; reconnection does not certify cross-version compatibility. '
    +(value.load_warning_details?'Warning previews may omit the middle. If stored, read the original using houdini_resource(kind="result", ref=load_warning_details.sha256, pointer="/result/load_warnings"). If unavailable, missing detail remains unverified. ':'')+'\n'
    +literalData(JSON.stringify(value))})
}

export async function relocateDirectory(ctx:Context,agent:Agent,directory:string,hipPath:string,signal:AbortSignal,hipIsNew=false) {
  const current=agent.session.header.cwd
  if(current&&(process.platform==='win32'?path.resolve(current).toLowerCase()===path.resolve(directory).toLowerCase():path.resolve(current)===path.resolve(directory)))return
  const registry=ctx.get('workspaceRegistry')
  if(!registry||!('relocateSession' in registry)||typeof registry.relocateSession!=='function')
    throw new Error('当前 DSH 尚未加载会话目录接续能力；本轮未继续文件操作，原对话与工程保留。')
  signal.throwIfAborted()
  await registry.relocateSession(agent.id,directory)
  recordHoudiniContext(agent,houdiniSnapshot({name:'dsh-houdini:workspace-directory',text:
    'This conversation now follows the explicitly selected or verified saved project directory. Earlier paths remain historical references.\n'
    +literalData(JSON.stringify({previous_directory:current,directory:agent.session.header.cwd,hip_path:hipPath,
      executor_id:foldExecutorState(agent.session.snapshotEvents()).identity,hip_is_new:hipIsNew}))}))
  if(await ctx.sessions.flush(agent.session)!==true)throw new Error('工程目录接续记录尚未可靠保存。')
}

export function installSceneRecovery(ctx:Context,connection:HoudiniConnection):void {
  if(!(connection instanceof HoudiniBridge)) {
    const services=new WeakMap<Agent,{bridge:HoudiniBridge;service:SceneRecoveryService}>()
    const selections=new WeakMap<Agent,Promise<void>>()
    const workbench=()=>Boolean((ctx.get('houdiniTargets') as {workbench?:boolean}|undefined)?.workbench)
    const serviceFor=async(agent:Agent,signal:AbortSignal,recovery=false)=>{
      if(recovery&&!foldExecutorState(agent.session.snapshotEvents()).identity) {
        const controller=ctx.get('houdiniTargets') as import('./executor-controller.js').ExecutorController|undefined
        if(!controller?.workbench)throw new Error('请先选择要操作的 Houdini 工程。')
        const registry=connection.registry
        if(!registry)throw new Error('工作台没有可用的工程登记位置。')
        const router=controller.getRouter(registry)
        const records=(await router.directory.list()).filter(record=>record.workbench&&record.state==='registered')
        const questions=ctx.get('userQuestions')
          if(!questions||!records.length)throw new Error('目前没有可用的 Houdini 工程。可以继续讨论；要操作工程，可点工程图标打开或新建，也可从已有 Houdini 的 Open Workspace 接入。')
          const projectLabel=(record:(typeof records)[number])=>record.hip_is_new
            ?ctx.get('workspaceRegistry')?.list?.().find(workspace=>path.resolve(workspace.path).toLowerCase()===path.resolve(record.workspace_path!).toLowerCase())?.title??'未保存工程'
            :path.basename(record.hip_path!)
          const names=records.map(projectLabel)
          const labels=names.map((name,index)=>names.filter(value=>value===name).length>1?name+'（'+(index+1)+'）':name)
        const answer=await questions.ask({agent,signal,questions:[{id:'houdini-project',header:'选择工程',
          question:'这段新对话要操作哪份工程？',options:[...records.map((record,index)=>({label:labels[index],
            description:(record.hip_path??'')+' · Houdini '+record.houdini_version})),{label:'只讨论，不操作工程',description:'不连接任何 Houdini。'}],multiSelect:false}]})
        const choice=answer.answers.find(item=>item.id==='houdini-project')
        const index=!choice?.custom&&choice?.selected?.length===1?labels.indexOf(choice.selected[0]):-1
        if(index<0)throw new Error('本轮只讨论，没有连接或修改工程。')
        const selected=records[index]
        await router.selectInitial(agent,selected.executor_id,selected.registration_id,signal,selected.hip_path!,true)
          recordHoudiniContext(agent,workspaceOpeningMessage({...selected,project_label:selected.hip_is_new?projectLabel(selected):undefined}))
        if(await ctx.sessions.flush(agent.session)!==true)throw new Error('工程选择尚未可靠保存。')
          await relocateDirectory(ctx,agent,selected.workspace_path!,selected.hip_path!,signal,selected.hip_is_new===true)
      }
      const target=recovery&&connection.recoveryTarget?await connection.recoveryTarget(agent,signal):await connection.resolve({agent,signal})
      let entry=services.get(agent)
      if(!entry||entry.bridge.targetExecutorId!==target.targetExecutorId||entry.bridge.baseUrl!==target.baseUrl) {
        entry={bridge:target,service:createSceneRecovery(ctx,target)}
        services.set(agent,entry)
      }
      return entry.service
    }
    ctx.provide('houdiniRecovery',{
      beforeTool:async(agent,signal)=>{
        const pending=selections.get(agent)
        if(pending){await pending;signal.throwIfAborted();return}
        if(!workbench()||services.has(agent)||foldExecutorState(agent.session.snapshotEvents()).identity)return
        const selection=serviceFor(agent,signal,true).then(()=>{})
        selections.set(agent,selection)
        try {await selection}
        finally {if(selections.get(agent)===selection)selections.delete(agent)}
      },
      beforeStep:async(agent,signal)=>{if(workbench()&&foldExecutorState(agent.session.snapshotEvents()).identity)await (await serviceFor(agent,signal,true)).beforeStep(agent,signal)},
      followDirectory:async(agent,signal,probe)=>{
        if(!workbench()||!foldExecutorState(agent.session.snapshotEvents()).identity)return
        try {await (await serviceFor(agent,signal)).followDirectory(agent,signal,probe)}
        catch {signal.throwIfAborted()}
      },
      ensure:async(agent,signal)=>(await serviceFor(agent,signal??new AbortController().signal)).ensure(agent,signal),
      inspect:async(agent,signal)=>(await serviceFor(agent,signal,true)).inspect(agent,signal),
      assess:async(agent,signal)=>(await serviceFor(agent,signal,true)).assess(agent,signal),
      restore:async(agent,id,signal)=>(await serviceFor(agent,signal,true)).restore(agent,id,signal),
    })
    return
  }
  ctx.provide('houdiniRecovery',createSceneRecovery(ctx,connection))
}

function createSceneRecovery(ctx:Context,connection:HoudiniBridge):SceneRecoveryService {
  const plans=new WeakMap<Agent,{id:string;state:string;facts:any;previous:string;sources:string[]}>()
  const running=new WeakSet<Agent>()
  const stepPhase=new WeakSet<Agent>()
  const bridge=()=>connection
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
    await relocateDirectory(ctx,agent,directory,value.hip_path,signal)
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
    const openCandidate=async(candidate:any,automatic=false)=>{
      if(key(agent)!==before)throw new Error('回答期间对话绑定已变化，未切换工程。')
      await persisted(agent)
      const opened=await target.recover('open',{...request,checkpoint_id:candidate.checkpoint_id,
        expected:{scene_id:sceneId,scene_epoch:located.scene_epoch,hip_path:located.hip_path,checkpoint_id:located.checkpoint_id,
          ...(automatic?{replace_empty:true}:{open_original:true,discard_unsaved:located.dirty===true})}},signal)
      if(opened.status!=='opened'||opened.executor_id!==target.targetExecutorId||opened.scene_id!==sceneId
        ||opened.checkpoint_id!==candidate.checkpoint_id)throw new Error('原工程打开结果未确认，尚未恢复修改权。')
      return service.assess(agent,signal)
    }
    if(candidates.length===1&&!located.unavailable?.length&&located.empty_new_scene===true&&located.dirty_reliable===true){
      agent.session.append('user/message',houdiniSnapshot({name:'dsh-houdini:project-resume',text:
        'The current scene is a verified untouched empty new scene. Continue this conversation in its single verified saved project; preserve all load warnings.\n'
        +literalData(JSON.stringify({hip_path:candidates[0].hip_path,checkpoint_id:candidates[0].checkpoint_id}))}),{surfaceOp:'append'})
      return openCandidate(candidates[0],true)
    }
    const questions=ctx.get('userQuestions')
    if(!questions||!located.dirty_reliable)throw new Error('已找到原工程，但当前未保存内容无法可靠核对；已保留当前工程。')
    const id='houdini-original-'+randomUUID(),keep='保留当前工程'
    const displayPath=(value:string)=>value.replaceAll('\\','/')
    const labels=candidates.map((item:any,index:number)=>
      (located.dirty?'放弃当前修改，打开':'打开')+(candidates.length===1&&!located.unavailable?.length?'原工程继续':'保存点 '+(index+1)+'：'+path.basename(item.hip_path)))
    const keepOption={label:keep,description:(located.hip_is_new?'未命名工程（尚未保存）':displayPath(located.hip_path))+'\n保留当前内容，本轮继续讨论。'}
    const openOptions=labels.map((label:string,index:number)=>({label,description:displayPath(candidates[index].hip_path)+'\n打开此文件，接着完成原对话的任务。'}))
    const answer=await questions.ask({agent,signal,questions:[{id,header:'工程接续',
      question:'要继续哪份工程？',
      detail:(located.dirty?'当前有未保存修改。打开原工程会放弃这些修改。':located.hip_is_new?'当前是尚未保存的新场景。此对话对应的工程已找到。':'当前打开了另一份工程，没有未保存修改。')
        +(located.unavailable?.length?'\n\n另有 '+located.unavailable.length+' 个保存点暂不可用，系统未自动改用较旧版本。':''),
      options:located.dirty?[keepOption,...openOptions]:[...openOptions,keepOption],multiSelect:false}]})
    signal.throwIfAborted()
    const choice=answer.answers.find(item=>item.id===id)
    agent.session.append('user/message',houdiniSnapshot({name:'dsh-houdini:recovery-choice',text:
      'User choice about the current and original project. Free text is task input, not authority to load a file.\n'
      +literalData(JSON.stringify({question_id:id,current_hip:located.hip_path,candidates,unavailable:located.unavailable??[],answer:choice??null}))}),{surfaceOp:'append'})
    const selected=!choice?.custom&&choice?.selected?.length===1?labels.indexOf(choice.selected[0]):-1
    if(selected<0)throw new Error('已保留当前工程，没有切换文件；请继续讨论需要保留或调整的内容。')
    return openCandidate(candidates[selected])
  }
  const service:SceneRecoveryService={
    async followDirectory(agent,signal,probe=false) {
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
    async inspect(agent,signal) {
      const target=bridge(),state=foldExecutorState(agent.session.snapshotEvents())
      if(!state.identity||(state.identity===target.targetExecutorId&&!state.recovery
        &&!executionHistory(agent.session.snapshotEvents()).anchor)) {
        await target.inspectExecutor(signal)
        return {status:'new_task',executor_id:target.targetExecutorId,message:'尚未执行过 Houdini 操作。'}
      }
      const before=key(agent)
      const recordedHip=projectExecutionState(agent.session.snapshotEvents())?.hip_path??state.recovery?.hip_path
      const sceneId=recordedScene(agent)
      let value:any
      try {value=await target.recover('assess',{session_id:agent.id,previous_executor:state.identity,
        source_executors:state.executors,...(typeof sceneId==='string'?{expected:{scene_id:sceneId}}:{})},signal)
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
      const target=bridge(),state=foldExecutorState(agent.session.snapshotEvents()),before=key(agent)
      const value=await service.inspect(agent,signal)
      if(key(agent)!==before)throw new Error('任务在检查期间发生变化，请重新检查。')
      if(value.status!=='ready')return value
      if(!state.identity)throw new Error('当前任务没有可核对的原连接身份。')
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
          load_warnings:prepared.load_warnings??[],
          ...(prepared.load_warning_details?{load_warning_details:prepared.load_warning_details}:{}),
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
  return service
}
