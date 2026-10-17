/** Opt-in Host-plane service. Mount once in the shared DSH Host, never per preset. */
import type {Context} from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {ExecutorDirectory,ExecutorRouter} from './executor-routing.js'
import {ExecutorBinding} from './executor-binding.js'
import {ExecutorController} from './executor-controller.js'
import {projectedExecutorBindingState,projectedExecutorIdentity,registerExecutorIdentityProjection} from './executor-identity-projection.js'
import {recordHoudiniContext} from './dsh-adapter.js'

export const name='dsh-houdini-executor-host'
export const inject=['agents','sessionProjections']
export interface Config {executorRegistry:string;requestTimeoutMs:number;workbench:boolean}
export const Config:Schema<Config>=Schema.object({
  executorRegistry:Schema.string().required(),requestTimeoutMs:Schema.number().default(120000),
  workbench:Schema.boolean().default(false),
})
export function apply(ctx:Context,config:Config):void {
  if(ctx.get('houdiniTargets')) throw new Error('Shared Houdini Host service already mounted; keep exactly one Host-plane instance')
  registerExecutorIdentityProjection(ctx)
  const directory=new ExecutorDirectory(config.executorRegistry,path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'))
  const router=new ExecutorRouter(directory,config.requestTimeoutMs,new ExecutorBinding(session=>
      projectedExecutorBindingState(ctx,session as Parameters<typeof projectedExecutorBindingState>[1]),(session,message)=>{
        const current=session as Parameters<typeof projectedExecutorBindingState>[1]
        const agent=ctx.agents.get(current.id)
        if(!agent||agent.session!==session)throw new Error('必须先打开精确的任务，再记录工程选择。')
        recordHoudiniContext(agent,message)
      }),session=>
      projectedExecutorIdentity(ctx,session as Parameters<typeof projectedExecutorIdentity>[1]),
    async session=>await ctx.get('sessions')?.flush(session as any)===true,
    async(taskId,candidates,signal)=>{
      const agent=ctx.agents.get(taskId as any),questions=agent?.ctx.get('userQuestions')
      if(!agent||!questions)return
      const labels=candidates.map((record,index)=>'工程窗口 '+(index+1))
      const answer=await questions.ask({agent,signal,questions:[{id:'houdini-resume-window',header:'继续工程',
        question:'原工程有多个可接续的窗口，要继续哪一个？',multiSelect:false,
        options:[...candidates.map((record,index)=>({label:labels[index],description:record.hip_path+' · Houdini '+record.houdini_version})),
          {label:'暂不连接',description:'保留当前内容，本轮继续讨论。'}]}]})
      const choice=answer.answers.find(item=>item.id==='houdini-resume-window')
      const index=!choice?.custom&&choice?.selected?.length===1?labels.indexOf(choice.selected[0]):-1
      return candidates[index]?.executor_id
    })
  ctx.effect(()=>()=>router.dispose(),'Houdini shared executor lifetime')
  if(config.workbench)ctx.inject(['workspaceRegistry','sessionController','sessionQuery','sessions'],scope=>{
    new ExecutorController(scope,router,true)
  })
  else new ExecutorController(ctx,router)
}

/** Resolve afresh per call so unloaded/replaced services cannot remain cached in a preset. */
export function sharedExecutorConnection(ctx:Context,registry:string) {
  const router=()=>{
    const service=ctx.get('houdiniTargets') as ExecutorController|undefined
    if(!service) throw new Error('Shared Houdini Host service unavailable; no live request sent and no single-target fallback')
    return service.getRouter(registry)
  }
  return {
    registry,
    resolve:(exec:Parameters<ExecutorRouter['resolve']>[0])=>router().resolve(exec),
    recoveryTarget:(agent:Parameters<ExecutorRouter['recoveryTarget']>[0],signal:AbortSignal,target?:string)=>router().recoveryTarget(agent,signal,target),
    sceneContextFor:(session:Parameters<ExecutorRouter['sceneContextFor']>[0],signal?:AbortSignal)=>router().sceneContextFor(session,signal),
  }
}
