/** Root Loader entry for browser delivery. Houdini tools live in the preset. */
import type {Context} from '@deepseek-ai/cordis'
import {Remote,TypertRemoteService} from '@deepseek-ai/dsh-typert-protocol'

export const name='dsh-houdini-frontend-host'

class HoudiniFrontend extends TypertRemoteService {
  constructor(ctx:Context) {super(ctx,'houdiniFrontend')}

  @Remote
  capabilities() {
    return {sharedExecutors:Boolean(this.ctx.get('houdiniTargets'))}
  }
}

export function apply(ctx:Context):void {new HoudiniFrontend(ctx)}
