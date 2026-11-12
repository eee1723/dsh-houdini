/** Houdini observations contributed through DSH's native context channel. */
import type { Context } from '@deepseek-ai/cordis'
import { executionNoticeFromFacts } from './execution-state.js'
import { SceneContextProvider, type AgentView, type SceneBridge } from './scene-context.js'
import { literalData } from './prompt-data.js'
import {projectedExecutorState,projectedExecutionFacts} from './executor-identity-projection.js'

const SCENE = 'dsh-houdini:scene-context'
const EXECUTION = 'dsh-houdini:execution-state'

export function installSceneContext(ctx: Context, bridge: SceneBridge): void {
  const provider = new SceneContextProvider(bridge,agent=>projectedExecutorState(ctx,agent.session).sceneObservation)
  // DSH refreshes registered context providers again at request admission.
  // Keep the asynchronously prepared text available to that synchronous read;
  // mutating assembly.contexts alone is overwritten by refreshContext().
  const prepared = new WeakMap<object, Record<string,string>>()
  ctx.on('agent/inbox/inserted', ({agent,message}) => provider.receive(agent as unknown as AgentView,message))
  ctx.on('agent/inbox/claimed', ({agent,message}) => provider.claim(agent,message))
  ctx.on('agent/inbox/discarded', ({agent,message}) => provider.discard(agent,message))
  for (const [name,order] of [[SCENE,150],[EXECUTION,151]] as const)
    ctx.systemPrompt.context({name,order,text:context => {
      const agent = (context as typeof context & {agent?:AgentView}).agent
      return agent ? prepared.get(agent)?.[name] ?? '' : ''
    }})

  ctx.on('system-prompt/assemble', async (_assembly,context,next) => {
    const result = await next()
    const agent = (context as typeof context & {agent?:AgentView}).agent
    if (!agent || !context.scope) return result
    const previous = prepared.get(agent) ?? {}
    // A scoped override or a suppressed section remains owned by DSH.
    const owned = (name:string) => result.contexts.find(section => section.name === name && section.text === (previous[name] ?? ''))
    // PTC and native schemas share this step's admitted definitions. Drop only
    // our previous contributions when the step cannot use Houdini tools.
    if (!ctx.tools.get('houdini_inspect',context.scope,context.toolSet)) {
      for(const name of [SCENE,EXECUTION]) {
        const section=owned(name)
        if(section)result.contexts.splice(result.contexts.indexOf(section),1)
      }
      prepared.delete(agent);return result
    }
    const scene = owned(SCENE), execution = owned(EXECUTION)
    const texts = {...previous}
    if (scene) texts[SCENE] = scene.text = await provider.observe(agent,context.signal)
    if (execution) {
      const notice = executionNoticeFromFacts(projectedExecutionFacts(ctx,agent.session))
      texts[EXECUTION] = execution.text = notice ? 'Houdini recorded execution state.\n'+literalData(JSON.stringify(notice)) : ''
    }
    prepared.set(agent,texts)
    return result
  },{prepend:true})
}
