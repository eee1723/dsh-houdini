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
        boundary:'Metadata declaration only; it does not test the provider or model.',
        recovery:[
          {kind:'ask_user',action:'Ask the user once, naming this exact route, whether to enable image input or switch routes; then continue after their answer.'},
          {kind:'probe',action:'After the user confirms this exact route accepts images, re-run the same image-producing call through houdini_exec or houdini_inspect (or houdini_isolated read) with allow_undeclared_image_input=true. The real model response decides; a provider rejection is evidence, not permission to keep overriding.'},
          {kind:'config',action:'Enable image input for this provider/model route in DSH configuration; tools cannot change route configuration.'}],
        next_action:'Ask the user once or run one explicitly authorized probe before treating visual verification as blocked. Metadata refusal is not proof the route cannot accept images.'}),
      observation:'Declared model input capability only. Native images may be attempted even when metadata is absent; route acceptance and semantic inspection require an actual model response.'}
  } catch(error) {
    return {...base,status:'unavailable',image_input:null,reason:String(error),
      recovery:[
        {kind:'config',action:'Inspect the route and attachment channel configuration; a failed lookup does not describe the model itself.'},
        {kind:'ask_user',action:'If the route or attachment channel is expected to work, ask the user to confirm the configuration before concluding visual work is impossible.'}],
      next_action:'Inspect the route/channel configuration; do not infer visual capability from a successful render.'}
  }
}

/** Small per-step projection for the runtime-context section. The complete
 * answer, including recovery steps, is returned on demand by houdini_capabilities. */
export function visualCapabilityBrief(value:any) {
  const {provider,model,status,image_input,reason}=value??{}
  return {...(provider?{provider,model}:{}),status,image_input,
    ...(reason?{reason}:{}),
    ...(status==='unsupported'?{recovery:['ask_user','probe','config'],
      next_action:'Ask the user once or run one user-authorized probe; call houdini_capabilities for the exact steps. Metadata refusal is not proof the route cannot accept images.'}:{}),
    ...(status==='available'?{boundary:'Declared metadata only; semantic inspection requires an actual response.'}:{}),
    ...(status==='unavailable'?{next_action:'Inspect route/channel configuration; do not infer visual capability from a successful render.'}:{})}
}

/** Attachment facts a model may safely use: the stored bytes and their
 * intrinsic dimensions. The native request channel can derive a smaller
 * preview, which must not be read as source pixels. */
export function imageAttachmentFacts(attachment:any) {
  const ref = attachment ?? {}, facts:any = {}
  for(const key of ['mediaType','bytes','width','height'])if(ref[key]!==undefined)facts[key]=ref[key]
  if(ref.originalDimensions)facts.normalized_from=ref.originalDimensions
  facts.preview_policy=ref.originalDimensions
    ? 'Stored bytes are the native channel\'s normalized raster (single-frame 8-bit sRGB, '+String(ref.width)+'x'+String(ref.height)+'), downscaled from the source; the request preview can be resized or re-encoded again.'
    : 'Stored bytes are the native channel\'s normalized raster (single-frame 8-bit sRGB); the source file may have had another bit depth, color space or metadata, and the request preview can be resized or re-encoded again.'
  facts.scope='Normalized preview pixels are not source-pixel or geometric evidence. For 1:1 claims use render_check numbers or render a detail view at source framing, not a rescaled preview.'
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
    // Missing image metadata is not proof that the routed model rejects images.
    // An explicit user-backed override permits one native attempt; the actual
    // request establishes support. Channel/lookup failures still stop the read.
    if (capability.status === 'unavailable'
        || (capability.status === 'unsupported' && exec.allow_undeclared_image_input !== true))
      throw new Error(capability.reason)
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
