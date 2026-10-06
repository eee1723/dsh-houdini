/** Root Loader entry for browser delivery. Houdini tools live in the preset. */
import type {Context} from '@deepseek-ai/cordis'
import {Remote,TypertRemoteService} from '@deepseek-ai/dsh-typert-protocol'
import {openDeliveredNode} from './node-delivery.js'

export const name='dsh-houdini-frontend-host'

export class HoudiniFrontend extends TypertRemoteService {
  constructor(ctx:Context) {super(ctx,'houdiniFrontend')}

  @Remote
  capabilities() {
    return {sharedExecutors:Boolean(this.ctx.get('houdiniTargets')),nodeDeliveries:true}
  }

  @Remote
  openNode(input:unknown,signal:AbortSignal) {return openDeliveredNode(this.ctx,input,signal)}
}

export function apply(ctx:Context):void {new HoudiniFrontend(ctx)}
