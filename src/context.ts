/** Houdini observations contributed through DSH's native context channel. */
import type { Context } from '@deepseek-ai/cordis'
import { projectExecutionNotice } from './execution-state.js'
import { visualCapability } from './image-output.js'
import { SceneContextProvider, type AgentView, type SceneBridge } from './scene-context.js'
import { literalData } from './prompt-data.js'

const SCENE = 'dsh-houdini:scene-context'
const EXECUTION = 'dsh-houdini:execution-state'
const VISION = 'dsh-houdini:visual-capability'

export function installSceneContext(ctx: Context, bridge: SceneBridge): void {
  const provider = new SceneContextProvider(bridge)
  const visionCache = new WeakMap<object, {
    key:string; llm:unknown; attachments:unknown; value:Awaited<ReturnType<typeof visualCapability>>
  }>()
  ctx.on('agent/inbox/inserted', ({agent,message}) => provider.receive(agent as unknown as AgentView,message))
  ctx.on('agent/inbox/claimed', ({agent,message}) => provider.claim(agent,message))
  for (const [name,order] of [[SCENE,150],[EXECUTION,151],[VISION,152]] as const)
    ctx.systemPrompt.context({name,order,text:''})

  ctx.on('system-prompt/assemble', async (_assembly,context,next) => {
    const result = await next()
    const agent = (context as typeof context & {agent?:AgentView}).agent
    if (!agent || !context.scope || !result.tools.some(tool => tool.name === 'houdini_inspect')) return result
    const empty = (name:string) => result.contexts.find(section => section.name === name && !section.text)
    const scene = empty(SCENE), execution = empty(EXECUTION), vision = empty(VISION)
    if (scene) scene.text = await provider.observe(agent,context.signal)
    if (execution) {
      const notice = projectExecutionNotice(agent.session.snapshotEvents())
      if (notice) execution.text = 'Houdini recorded execution state.\n'+literalData(JSON.stringify(notice))
    }
    if (vision && typeof ctx.get === 'function') {
      const llm = ctx.get('llm'), attachments = ctx.get('attachments')
      const variables = result.variables
      const route = variables?.provider && variables?.model
        ? {provider:variables.provider,model:variables.model}
        : (agent as any).session.requestHeader?.()?.config
      const key = JSON.stringify(route ?? (agent as any).options)
      let cached = visionCache.get(agent)
      if (!cached || cached.key !== key || cached.llm !== llm || cached.attachments !== attachments
          || cached.value.status === 'unavailable') {
        cached = {key,llm,attachments,value:await visualCapability({agent,route,signal:context.signal},ctx)}
        visionCache.set(agent,cached)
      }
      vision.text = 'Houdini image input capability (declared metadata).\n'+literalData(JSON.stringify(cached.value))
    }
    return result
  },{prepend:true})
}
