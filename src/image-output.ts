/** Return Houdini images directly through DSH's native attachment channel. */
import path from 'node:path'
import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import type { ExecResult, HoudiniBridge } from './bridge.js'

/** Metadata-only preflight: no render, model inference, or scene mutation. */
export async function visualCapability(exec: any, ctx: any) {
  const routed = exec.route ?? exec.agent?.session?.requestHeader?.()?.config
  const route = {provider:routed?.provider ?? exec.agent?.options?.provider,
    model:routed?.model ?? exec.agent?.options?.model}
  const base = {...route, semantic_status:'unverified',
    render_backend:'not_probed', boundary:'Declared image input and native attachment channel only; GUI renderer, transport and semantic inspection require actual evidence.'}
  try {
    const attachments = ctx.get?.('attachments'), llm = ctx.get?.('llm')
    if (!attachments || !llm || !route.provider || !route.model)
      throw new Error('native image channel or model route unavailable')
    const signal = exec.signal ? AbortSignal.any([exec.signal,AbortSignal.timeout(1500)]) : AbortSignal.timeout(1500)
    signal.throwIfAborted()
    let onAbort = () => {}
    const aborted = new Promise<never>((_,reject) => {
      onAbort = () => reject(new Error('image route lookup aborted'))
      signal.addEventListener('abort',onAbort,{once:true})
    })
    let info:any
    try { info = await Promise.race([llm.resolveModelInfo(route.provider,route.model,signal),aborted]) }
    finally { signal.removeEventListener('abort',onAbort) }
    const supported = info.inputModalities?.includes('image') === true
    return {...base,status:supported?'available':'unsupported',image_input:supported,
      attachment_channel:true,limits:attachments.imageLimits,
      ...(supported?{}:{reason:'current model route does not declare image input'}),
      observation:'Declared model input capability. An attached image can be inspected by the model; metadata alone does not describe its content.'}
  } catch(error) {
    return {...base,status:'unavailable',image_input:null,reason:String(error),
      next_action:'Inspect the route/channel configuration; do not infer visual capability from a successful render.'}
  }
}

export function imageBlocks(value: ExecResult): ContentBlock[] {
  return (Array.isArray(value.imageAttachments) ? value.imageAttachments : [])
    .filter((item: any) => item?.attachment)
    .map((item: any) => ({ type: 'image' as const, attachment: item.attachment }))
}

/** No workspace copies or secondary vision agent. Failure never retries HOM. */
export async function attachImages<T extends ExecResult>(value: T, exec: any, bridge: HoudiniBridge, ctx: any): Promise<T> {
  const paths = Array.isArray(value.images) ? [...new Set(value.images.filter((p): p is string => typeof p === 'string'))] : []
  if (!paths.length) return value
  const imageAttachments: any[] = []
  try {
    const attachments = ctx.get?.('attachments')
    const capability = await visualCapability(exec,ctx)
    if (capability.status !== 'available') throw new Error(capability.reason)
    let totalBytes = 0
    for (const from of paths) {
      try {
        if (imageAttachments.filter(item => item.attachment).length >= attachments.imageLimits.maxImagesPerMessage) throw new Error('native image message count limit reached')
        const mediaType = ({'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif'} as Record<string,string>)[path.extname(from).toLowerCase()]
        if (!mediaType || !attachments.imageLimits.mediaTypes.includes(mediaType)) throw new Error('format unsupported by native image channel; use a PNG/JPEG preview for visual inspection')
        const cap = Math.min(attachments.imageLimits.maxImageBytes, attachments.imageLimits.maxMessageImageBytes - totalBytes)
        if (cap <= 0) throw new Error('native image message byte limit reached')
        const data = await bridge.fetchMedia(from, exec.signal, cap)
        const attachment = await attachments.saveImage({ data, mediaType, name: path.basename(from.replaceAll('\\', '/')) })
        totalBytes += attachment.bytes
        imageAttachments.push({ from, attachment, semantic_status: 'unverified' })
      } catch (error) {
        imageAttachments.push({ from, error: String(error), semantic_status: 'unverified' })
      }
    }
  } catch (error) {
    imageAttachments.push(...paths.map(from => ({ from, error: String(error), semantic_status: 'unverified' })))
  }
  // DSH carries native blocks to the caller and ferries nested images once.
  return { ...value, imageAttachments }
}
