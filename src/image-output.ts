/** Return Houdini images directly through DSH's native attachment channel. */
import path from 'node:path'
import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import type { ExecResult, HoudiniBridge } from './bridge.js'

/** Metadata-only preflight: no render, model inference, or scene mutation. */
export async function visualCapability(exec: any, ctx: any) {
  // A pending user selection belongs to a later step. Tool execution has no
  // modelSelection field in DSH's public contract, so its committed request
  // header is the current step's route; out-of-turn diagnostics use current().
  const routed = exec.route ?? exec.modelSelection ?? exec.agent?.session?.requestHeader?.()?.config
    ?? exec.agent?.model?.current()
  const route = {provider:routed?.provider,model:routed?.model}
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
      ...(supported?{}:{reason:'current model route does not declare image input',
        next_action:'Select a route that declares image input, or enable image input for this exact provider/model in DSH model settings if the provider supports it. Then read existing images with houdini_request, houdini_isolated(operation="read"), or read_image for a saved local file.'})}
  } catch(error) {
    return {...base,status:'unavailable',image_input:null,reason:String(error),
      next_action:'Check DSH model settings and the native attachment channel, then read existing images when the route is available.'}
  }
}

/** Attachment facts a model may safely use: the stored bytes and their
 * intrinsic dimensions. The native request channel can derive a smaller
 * preview, which must not be read as source pixels. */
export function imageAttachmentFacts(attachment:any) {
  const ref = attachment ?? {}, facts:any = {}
  for(const key of ['mediaType','bytes','width','height'])if(ref[key]!==undefined)facts[key]=ref[key]
  if(ref.originalDimensions)facts.normalized_from=ref.originalDimensions
  facts.preview_policy=ref.originalDimensions
    ? 'Stored bytes are the native channel\'s normalized raster (single-frame 8-bit sRGB, '+String(ref.width)+'x'+String(ref.height)+'), possibly downscaled from the source; the request preview can be resized or re-encoded again.'
    : 'Stored bytes are the native channel\'s normalized raster (single-frame 8-bit sRGB); the source file may have had another bit depth, color space or metadata, and the request preview can be resized or re-encoded again.'
  facts.scope='Use the preview for composition and shape visible at its delivered scale, not for source-pixel, aliasing or fine-edge claims. For 1:1 claims use original-file pixel checks such as render_check or a source-framing detail render, not a rescaled preview.'
  return facts
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
    let totalBytes = 0, attachedCount = 0
    for (const from of paths) {
      try {
        if (attachedCount >= attachments.imageLimits.maxImagesPerMessage) throw new Error('native image message count limit reached')
        const mediaType = ({'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif'} as Record<string,string>)[path.extname(from).toLowerCase()]
        if (!mediaType || !attachments.imageLimits.mediaTypes.includes(mediaType)) throw new Error('format unsupported by native image channel; use a PNG/JPEG preview for visual inspection')
        const cap = Math.min(attachments.imageLimits.maxImageBytes, attachments.imageLimits.maxMessageImageBytes - totalBytes)
        if (cap <= 0) throw new Error('native image message byte limit reached')
        const data = await bridge.fetchMedia(from, exec.signal, cap)
        const attachment = await attachments.saveImage({ data, mediaType, name: path.basename(from.replaceAll('\\', '/')) })
        attachedCount++
        totalBytes += attachment.bytes
        imageAttachments.push({ from, attachment, image:imageAttachmentFacts(attachment), semantic_status: 'unverified', capability_status: capability.status })
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
