/** Opt-in Host-plane service. Mount once in the shared DSH Host, never per preset. */
import type {Context} from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {ExecutorDirectory,ExecutorRouter} from './executor-routing.js'
import {ExecutorBindingBarrier} from './execution-state.js'
import {ExecutorController} from './executor-controller.js'

export const name='dsh-houdini-executor-host'
export const inject=['sessions','agents']
export interface Config {executorRegistry:string;requestTimeoutMs:number}
export const Config:Schema<Config>=Schema.object({
  executorRegistry:Schema.string().required(),requestTimeoutMs:Schema.number().default(120000),
})
export function apply(ctx:Context,config:Config):void {
  if(ctx.get('houdiniTargets')) throw new Error('Shared Houdini Host service already mounted; keep exactly one Host-plane instance')
  const directory=new ExecutorDirectory(config.executorRegistry,path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'))
  const router=new ExecutorRouter(directory,config.requestTimeoutMs,new ExecutorBindingBarrier(async session=>
    ctx.sessions.flush(session as Parameters<typeof ctx.sessions.flush>[0])))
  ctx.effect(()=>()=>router.dispose(),'Houdini shared executor lifetime')
  new ExecutorController(ctx,router)
}

/** Resolve afresh per call so unloaded/replaced services cannot remain cached in a preset. */
export function sharedExecutorConnection(ctx:Context,registry:string) {
  const router=()=>{
    const service=ctx.get('houdiniTargets') as ExecutorController|undefined
    if(!service) throw new Error('Shared Houdini Host service unavailable; no live request sent and no single-target fallback')
    return service.getRouter(registry)
  }
  return {
    resolve:(exec:Parameters<ExecutorRouter['resolve']>[0])=>router().resolve(exec),
    sceneContextFor:(session:Parameters<ExecutorRouter['sceneContextFor']>[0],signal?:AbortSignal)=>router().sceneContextFor(session,signal),
  }
}
