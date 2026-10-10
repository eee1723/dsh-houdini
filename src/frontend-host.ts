/** Root Loader entry for browser delivery. Houdini tools live in the preset. */
import type {Context, Volatile} from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'
import {Remote,TypertRemoteService} from '@deepseek-ai/dsh-typert-protocol'
import {openDeliveredNode} from './node-delivery.js'
import {videoModels} from './video-transcription.js'
import {videoDiagnostics} from './video-runtime.js'

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
    return {sharedExecutors:Boolean(this.ctx.get('houdiniTargets')),nodeDeliveries:true}
  }

  @Remote
  openNode(input:unknown,signal:AbortSignal) {return openDeliveredNode(this.ctx,input,signal)}
}

export function apply(ctx:Context,config:Config):void {
  new HoudiniFrontend(ctx,config)
  ctx.inject(['settings'],child => {
    child.effect(() => (child as any).settings.configure({auto:false},ctx.fiber))
  })
}
