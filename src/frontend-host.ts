/** Root Loader entry for browser delivery. Houdini tools live in the preset. */
import type {Context, Volatile} from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'
import {Remote,TypertRemoteService} from '@deepseek-ai/dsh-typert-protocol'
import {openDeliveredNode} from './node-delivery.js'
import {videoModels,tutorialRuntime} from './video-transcription.js'
import {videoDiagnostics} from './video-runtime.js'
import {createSupportReport} from './support-report.js'
import type {} from '@deepseek-ai/dsh-api-session-controller'
import {EXPECTED_EXECUTION_CONTRACT_VERSION} from './generated-verb-contract.js'
import {DesktopIntegration} from './desktop-integration.js'
import type {ExecutorController} from './executor-controller.js'
import {VIDEO_DEFAULTS} from './video-configuration.js'

export const name='dsh-houdini-frontend-host'

export interface Config {
  videoProvider: Volatile<string>
  videoModel: Volatile<string>
  videoPython: Volatile<string>
  videoProtocol: Volatile<string>
  videoEndpoint: Volatile<string>
  videoAuthentication: Volatile<string>
  videoCredentialRef: Volatile<string>
  videoConcurrency: Volatile<number>
  videoRequestsPerSecond: Volatile<number>
}

export const Config = Schema.object({
  videoProvider: Schema.string().default('').volatile(),
  videoModel: Schema.string().default('').volatile(),
  videoPython: Schema.string().default('').volatile(),
  videoProtocol: Schema.string().default('').volatile(),
  videoEndpoint: Schema.string().default('').volatile(),
  videoAuthentication: Schema.string().default('bearer').volatile(),
  videoCredentialRef: Schema.string().default('').volatile(),
  videoConcurrency: Schema.number().default(VIDEO_DEFAULTS.concurrency).volatile(),
  videoRequestsPerSecond: Schema.number().default(VIDEO_DEFAULTS.requestsPerSecond).volatile(),
})

export class HoudiniFrontend extends TypertRemoteService {
  constructor(ctx:Context, private readonly config:Config) {
    super(ctx,'houdiniFrontend')
  }

  videoSelection() {
    return {provider:this.config.videoProvider.get(),model:this.config.videoModel.get(),
      python:this.config.videoPython.get(),protocol:this.config.videoProtocol.get(),endpoint:this.config.videoEndpoint.get(),
      authentication:this.config.videoAuthentication.get(),credentialRef:this.config.videoCredentialRef.get(),
      concurrency:this.config.videoConcurrency.get(),requestsPerSecond:this.config.videoRequestsPerSecond.get()}
  }

  @Remote
  videoSettings() {return videoModels(this.ctx)}

  @Remote
  async videoDiagnostics() {
    const runtime=await tutorialRuntime(this.ctx,this.videoSelection().python)
    const result=await videoDiagnostics(runtime.python)
    return {...result,runtime,note:'使用自动发现或明确选择的普通 Houdini Python 与插件私有媒体程序；未执行HOM、未上传音频。服务实际支持以短段试转录为准。'}
  }

  @Remote
  capabilities() {
    return {sharedExecutors:Boolean(this.ctx.get('houdiniTargets')),nodeDeliveries:true,desktop:Boolean(this.ctx.get('houdiniDesktop'))}
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
    signal.throwIfAborted()
    const records=await this.desktop().presence()
    return records.map((record:any)=>{
      const contractMismatch=record.status==='online'&&record.contractVersion!==EXPECTED_EXECUTION_CONTRACT_VERSION
      return {...record,contractMismatch,status:contractMismatch?'unknown':record.status}
    })
  }

  @Remote
  projectInstallations() {return this.desktop().listInstallations()}
  @Remote
  prepareBridge(input:unknown) {return this.desktop().prepareBridge(input)}

  private desktop(){const service=this.ctx.get('houdiniDesktop');if(!service)throw Error('Houdini 插件接入服务尚未就绪。');return service}

  @Remote
  projectAction(input:unknown,signal:AbortSignal) {return this.desktop().project(input,signal)}
  @Remote
  projectLaunchStatus(input:unknown) {return this.desktop().status(input)}
  @Remote
  projectLaunchDetach(input:unknown) {return this.desktop().detach(input)}
  @Remote
  projectLaunchResume(input:unknown) {return this.desktop().resume(input)}
  @Remote
  desktopIntent(input:{after:number},signal:AbortSignal) {
    if(!input||Object.keys(input).join(',')!=='after'||!Number.isSafeInteger(input.after)||input.after<0)throw Error('Invalid navigation cursor')
    return this.desktop().intent(input.after,signal)
  }
  @Remote
  desktopIntentAck(input:{sequence:number}) {
    if(!input||Object.keys(input).join(',')!=='sequence'||!Number.isSafeInteger(input.sequence)||input.sequence<0)throw Error('Invalid navigation acknowledgement')
    this.desktop().intents.acknowledge(input.sequence);return {ok:true}
  }

}

export function apply(ctx:Context,config:Config):void {
  new HoudiniFrontend(ctx,config)
  ctx.inject(['houdiniTargets','workspaceRegistry','sessionController','sessions','sessionProjections'],async child => {
    const service=new DesktopIntegration(child,child.get('houdiniTargets') as ExecutorController)
    child.effect(()=>()=>service.dispose())
    await service.start()
    child.provide('houdiniDesktop',service)
  })
}
