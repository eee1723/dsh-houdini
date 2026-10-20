/** Houdini observations contributed through DSH's native context channel. */
import type { Context } from '@deepseek-ai/cordis'
import { executionNoticeFromFacts } from './execution-state.js'
import { visualCapability } from './image-output.js'
import { SceneContextProvider, type AgentView, type SceneBridge } from './scene-context.js'
import { literalData } from './prompt-data.js'
import {projectedExecutorState,projectedExecutionFacts} from './executor-identity-projection.js'

const SCENE = 'dsh-houdini:scene-context'
const EXECUTION = 'dsh-houdini:execution-state'
const VISION = 'dsh-houdini:visual-capability'

export function installSceneContext(ctx: Context, bridge: SceneBridge): void {
  const provider = new SceneContextProvider(bridge,agent=>projectedExecutorState(ctx,agent.session).sceneObservation)
  // DSH refreshes registered context providers again at request admission.
  // Keep the asynchronously prepared text available to that synchronous read;
  // mutating assembly.contexts alone is overwritten by refreshContext().
  const prepared = new WeakMap<object, Record<string,string>>()
  let visionGeneration = 0
  const visionCache = new WeakMap<object, {
    key:string; generation:number; llm:unknown; attachments:unknown; value:Awaited<ReturnType<typeof visualCapability>>
  }>()
  // DSH replaces provider routes without replacing the shared LLM service.
  // Its native event invalidates same-name model capability metadata as well.
  ctx.on('llm/adapters-updated', () => { visionGeneration++ })
  ctx.on('agent/inbox/inserted', ({agent,message}) => provider.receive(agent as unknown as AgentView,message))
  ctx.on('agent/inbox/claimed', ({agent,message}) => provider.claim(agent,message))
  for (const [name,order] of [[SCENE,150],[EXECUTION,151],[VISION,152]] as const)
    ctx.systemPrompt.context({name,order,text:context => {
      const agent = (context as typeof context & {agent?:AgentView}).agent
      return agent ? prepared.get(agent)?.[name] ?? '' : ''
    }})

  ctx.on('system-prompt/assemble', async (_assembly,context,next) => {
    const result = await next()
    const agent = (context as typeof context & {agent?:AgentView}).agent
    if (!agent || !context.scope) return result
    // PTC exposes run_code in the request schema while retaining the same
    // Houdini capabilities in the scoped registry.
    if (!ctx.tools.get('houdini_inspect',context.scope)) { prepared.delete(agent); return result }
    const previous = prepared.get(agent) ?? {}
    // A scoped override or a suppressed section remains owned by DSH.
    const owned = (name:string) => result.contexts.find(section => section.name === name && section.text === (previous[name] ?? ''))
    const scene = owned(SCENE), execution = owned(EXECUTION), vision = owned(VISION)
    const texts = {...previous}
    if (scene) texts[SCENE] = scene.text = await provider.observe(agent,context.signal)
    if (execution) {
      const notice = executionNoticeFromFacts(projectedExecutionFacts(ctx,agent.session))
      texts[EXECUTION] = execution.text = notice ? 'Houdini recorded execution state.\n'+literalData(JSON.stringify(notice)) : ''
    }
    if (vision && typeof ctx.get === 'function') {
      const llm = ctx.get('llm'), attachments = ctx.get('attachments')
      const variables = result.variables
      const route = variables?.provider && variables?.model
        ? {provider:variables.provider,model:variables.model}
        : (agent as any).session.requestHeader?.()?.config
      const key = JSON.stringify(route ?? (agent as any).options)
      let cached = visionCache.get(agent)
      if (!cached || cached.key !== key || cached.generation !== visionGeneration
          || cached.llm !== llm || cached.attachments !== attachments
          || cached.value.status === 'unavailable') {
        cached = {key,generation:visionGeneration,llm,attachments,value:await visualCapability({agent,route,signal:context.signal},ctx)}
        visionCache.set(agent,cached)
      }
      texts[VISION] = vision.text = 'Houdini image input capability (declared metadata).\n'+literalData(JSON.stringify(cached.value))
    }
    prepared.set(agent,texts)
    return result
  },{prepend:true})
}
