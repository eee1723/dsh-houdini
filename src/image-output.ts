/** Return Houdini images directly through DSH's native attachment channel. */
import path from 'node:path'
import { createUserMessage, type ContentBlock } from '@deepseek-ai/dsh-llm'
import type { ExecResult, HoudiniBridge } from './bridge.js'

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
    const llm = ctx.get?.('llm')
    const routed = exec.agent?.session?.requestHeader?.()?.config
    const route = { provider: routed?.provider ?? exec.agent?.options?.provider, model: routed?.model ?? exec.agent?.options?.model }
    if (!attachments || !llm || !route?.provider || !route?.model) throw new Error('native image channel or model route unavailable')
    const signal = exec.signal ? AbortSignal.any([exec.signal, AbortSignal.timeout(1500)]) : AbortSignal.timeout(1500)
    signal.throwIfAborted()
    let onAbort = () => {}
    const aborted = new Promise<never>((_, reject) => {
      onAbort = () => reject(new Error('image route lookup aborted'))
      signal.addEventListener('abort', onAbort, { once: true })
    })
    let info: any
    try { info = await Promise.race([llm.resolveModelInfo(route.provider, route.model, signal), aborted]) }
    finally { signal.removeEventListener('abort', onAbort) }
    if (!info.inputModalities?.includes('image')) throw new Error('current model route does not declare image input')
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
  const result = { ...value, imageAttachments }
  // Nested/code-mode results need explicit multimodal context, as in DSH read_image.
  const blocks = imageBlocks(result)
  if (exec.parent !== undefined && blocks.length) exec.deferContext(createUserMessage({
    content: [{type:'text',text:'Houdini output images: inspect these directly; attachment delivery alone does not verify their content.'}, ...blocks],
    source: {kind:'plugin',plugin:'dsh-houdini'},
  }))
  return result
}
