/** Root Loader entry for browser delivery. Houdini tools live in the preset. */
import type {Context, Volatile} from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'
import {Remote,TypertRemoteService} from '@deepseek-ai/dsh-typert-protocol'
import {openDeliveredNode} from './node-delivery.js'
import {videoModels} from './video-transcription.js'
import {videoDiagnostics} from './video-runtime.js'
import {createSupportReport} from './support-report.js'
import type {} from '@deepseek-ai/dsh-session-title'
import type {} from '@deepseek-ai/dsh-api-session-controller'
import {desktopRequest} from './workbench-desktop.js'
import {foldExecutorState} from './executor-identity-projection.js'
import {EXPECTED_EXECUTION_CONTRACT_VERSION} from './generated-verb-contract.js'

export const name='dsh-houdini-frontend-host'

export interface Config {
  videoProvider: Volatile<string>
  videoModel: Volatile<string>
  videoPython: Volatile<string>
}

export const Config = Schema.object({
  videoProvider: Schema.string().default('').volatile(),
  videoModel: Schema.string().default('').volatile(),
  videoPython: Schema.string().default('').volatile(),
})

export class HoudiniFrontend extends TypertRemoteService {
  constructor(ctx:Context, private readonly config:Config) {super(ctx,'houdiniFrontend')}

  videoSelection() {
    return {provider:this.config.videoProvider.get(),model:this.config.videoModel.get(),
      python:this.config.videoPython.get()}
  }

  @Remote
  videoSettings() {return videoModels(this.ctx)}

  @Remote
  videoDiagnostics() {return videoDiagnostics(this.videoSelection().python)}

  @Remote
  capabilities() {
    const targets=this.ctx.get('houdiniTargets') as {workbench?:boolean}|undefined
    return {sharedExecutors:Boolean(targets)&&!targets?.workbench,nodeDeliveries:true,workbench:Boolean(targets?.workbench)}
  }

  @Remote
  openNode(input:unknown,signal:AbortSignal) {return openDeliveredNode(this.ctx,input,signal)}

  @Remote
  supportReport(input:unknown,signal:AbortSignal) {return createSupportReport(this.ctx,input,signal)}

  @Remote
  async projectPresence(signal:AbortSignal) {
    // Single live projection for the bound-project icon, menu and detail. The
    // desktop owns reachability; this layer only refuses to paint a mismatched
    // execution contract as online, because commands would fail against it.
    const records=await desktopRequest('presence',{},signal)
    return records.map((record:any)=>({...record,status:record.status==='online'&&record.contractVersion!==EXPECTED_EXECUTION_CONTRACT_VERSION?'unknown':record.status}))
  }

  @Remote
  async projectAction(input:unknown,signal:AbortSignal) {
    const data=input as {action:string;sessionId?:string}
    if(!data||typeof data!=='object'||Array.isArray(data)||Object.keys(data).some(key=>!['action','sessionId'].includes(key))
      ||!['open','new','reopen'].includes(data.action)||data.sessionId!==undefined&&(typeof data.sessionId!=='string'||!data.sessionId||data.sessionId.length>256))
      throw new Error('请选择打开或新建工程。')
    if(data.action==='reopen') {
      if(!data.sessionId)throw new Error('请先选择要继续的对话。')
      const query=this.ctx.get('sessionQuery')
      if(!query)throw new Error('当前工作台暂时无法读取对话，请稍后重试。')
      const history=await query.readSession(data.sessionId as any)
      const state=foldExecutorState(history.events),project=state.project
      if(!project?.hipPath||project.hipIsNew!==false)throw new Error('这段对话没有可直接打开的已保存工程，请选择已有 HIP 文件。')
      return desktopRequest('dialog',{action:'reopen',hip:project.hipPath,sessionId:data.sessionId,executorId:state.identity},signal)
    }
    let bindSessionId:string|undefined
    if(data.sessionId) {
      const query=this.ctx.get('sessionQuery')
      if(!query)throw new Error('当前工作台暂时无法读取对话，请稍后重试。')
      const history=await query.readSession(data.sessionId as any)
      if(!foldExecutorState(history.events).identity) {
        const agent=this.ctx.get('agents')?.get(data.sessionId as any)
        if(agent&&agent.status!=='idle')throw new Error('当前对话还在运行，请等本轮结束或停止后，再把工程接到这段对话。')
        bindSessionId=data.sessionId
      }
    }
    return desktopRequest('dialog',{action:data.action,...(bindSessionId?{bindSessionId}:{})},signal)
  }

  @Remote
  async refreshTitle(input:unknown,signal:AbortSignal) {
    if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).join(',')!=='sessionId'
      ||typeof (input as any).sessionId!=='string'||!(input as any).sessionId.length||(input as any).sessionId.length>256)
      throw new Error('请选择需要重新命名的对话。')
    const controller=this.ctx.get('sessionController'),titles=this.ctx.get('sessionTitle'),sessions=this.ctx.get('sessions')
    if(!controller||!titles||!sessions)throw new Error('当前环境没有提供自动命名能力。')
    signal.throwIfAborted()
    const resolved=await controller.resolveAgent((input as any).sessionId)
    if('error' in resolved)throw new Error('无法读取这段对话。')
    const session=resolved.agent.session,events=session.snapshotEvents()
    if(!events.some(event=>event.type==='user/message'&&event.data.source.kind==='user'
      &&event.data.content.some(block=>block.type==='text'&&block.text.trim())))throw new Error('先发送一条消息，系统就能根据内容命名。')
    const title=await titles.refresh(session,signal)
    if(await sessions.flush(session)!==true)throw new Error('新标题尚未可靠保存，请稍后重试。')
    return {title:title?.title??null}
  }

}

export function apply(ctx:Context,config:Config):void {
  new HoudiniFrontend(ctx,config)
  ctx.inject(['settings'],child => {
    child.effect(() => (child as any).settings.configure({auto:false},ctx.fiber))
  })
}
