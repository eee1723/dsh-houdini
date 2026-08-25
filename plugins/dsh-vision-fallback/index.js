import fs from 'node:fs/promises'
import path from 'node:path'
import z from '@deepseek-ai/schemastery'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'vision-fallback'
export const inject = ['tools', 'systemPrompt', 'settings']

export const SETTINGS_NAMESPACE = 'vision-fallback'

export const Config = z.object({
  apiKey: z.string().default('').role('secret').description('视觉模型 API Key'),
  model: z.string().default('qwen/qwen3-vl-plus').description('供应商/模型，例如 qwen/qwen3-vl-plus'),
})

export const SettingsSchema = z.object({
  apiKey: z.string().role('secret').description('备用视觉模型 API Key'),
  model: z.string().default('qwen/qwen3-vl-plus').description('provider/model，例如 qwen/qwen3-vl-plus'),
})

const BACKENDS = Object.freeze({
  qwen: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
  dashscope: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
  openai: 'https://api.openai.com/v1/chat/completions',
  openrouter: 'https://openrouter.ai/api/v1/chat/completions',
})

const MAX_IMAGES = 4
const MAX_IMAGE_BYTES = 12 * 1024 * 1024
const MAX_TOTAL_BYTES = 24 * 1024 * 1024
const REQUEST_TIMEOUT_MS = 60_000

export function resolveVisionModel(value) {
  const text = String(value ?? '').trim()
  const slash = text.indexOf('/')
  if (slash <= 0 || slash === text.length - 1) {
    throw new Error('model must use provider/model form, for example qwen/qwen3-vl-plus')
  }
  const provider = text.slice(0, slash).toLowerCase()
  const model = text.slice(slash + 1)
  const endpoint = BACKENDS[provider]
  if (!endpoint) {
    throw new Error(`unsupported vision provider "${provider}"; supported: ${Object.keys(BACKENDS).join(', ')}`)
  }
  return { provider, model, endpoint }
}

export function imageMediaType(bytes) {
  if (bytes.length >= 8 && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) return 'image/png'
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return 'image/jpeg'
  if (bytes.length >= 12 && bytes.subarray(0, 4).toString('ascii') === 'RIFF' && bytes.subarray(8, 12).toString('ascii') === 'WEBP') return 'image/webp'
  if (bytes.length >= 6 && ['GIF87a', 'GIF89a'].includes(bytes.subarray(0, 6).toString('ascii'))) return 'image/gif'
  return null
}

function workspaceOf(exec) {
  const cwd = exec?.agent?.session?.header?.cwd
  return typeof cwd === 'string' && cwd.trim() ? path.resolve(cwd) : null
}

export function resolveWorkspacePath(workspace, input) {
  if (!workspace) throw new Error('session workspace is unavailable')
  const root = path.resolve(workspace)
  const target = path.resolve(root, String(input ?? ''))
  const relative = path.relative(root, target)
  if (!relative || relative === '.') throw new Error('image path must name a file')
  if (relative.startsWith(`..${path.sep}`) || relative === '..' || path.isAbsolute(relative)) {
    throw new Error(`image path escapes the session workspace: ${input}`)
  }
  return target
}

async function loadImages(inputs, workspace) {
  if (!Array.isArray(inputs) || inputs.length < 1 || inputs.length > MAX_IMAGES) {
    throw new Error(`paths must contain 1-${MAX_IMAGES} images`)
  }
  const images = []
  let total = 0
  for (const input of inputs) {
    const target = resolveWorkspacePath(workspace, input)
    const stat = await fs.stat(target)
    if (!stat.isFile()) throw new Error(`image path is not a regular file: ${input}`)
    if (stat.size > MAX_IMAGE_BYTES) throw new Error(`image exceeds ${MAX_IMAGE_BYTES} bytes: ${input}`)
    total += stat.size
    if (total > MAX_TOTAL_BYTES) throw new Error(`images exceed ${MAX_TOTAL_BYTES} bytes in total`)
    const bytes = await fs.readFile(target)
    const mediaType = imageMediaType(bytes)
    if (!mediaType) throw new Error(`unsupported image bytes: ${input}`)
    images.push({ input: String(input), mediaType, data: bytes.toString('base64') })
  }
  return images
}

export function buildVisionRequest(model, images, question) {
  return {
    model,
    messages: [{
      role: 'user',
      content: [
        ...images.map((image) => ({
          type: 'image_url',
          image_url: { url: `data:${image.mediaType};base64,${image.data}` },
        })),
        { type: 'text', text: String(question || 'Describe the visible content and report any visual defects.') },
      ],
    }],
    temperature: 0,
    max_tokens: 2048,
  }
}

function answerFromResponse(payload) {
  const content = payload?.choices?.[0]?.message?.content
  if (typeof content === 'string' && content.trim()) return content.trim()
  if (Array.isArray(content)) {
    const text = content.filter((item) => item?.type === 'text' && typeof item.text === 'string').map((item) => item.text).join('\n').trim()
    if (text) return text
  }
  throw new Error('vision provider returned no text answer')
}

function failureCode(error, status) {
  if (status === 401 || status === 403) return 'VISION_AUTH_FAILED'
  if (status === 429) return 'VISION_RATE_LIMITED'
  if (status && status >= 500) return 'VISION_BACKEND_UNAVAILABLE'
  if (error?.name === 'TimeoutError') return 'VISION_TIMEOUT'
  if (error?.name === 'AbortError') return 'VISION_ABORTED'
  return 'VISION_REQUEST_FAILED'
}

async function describe(config, args, exec) {
  if (!String(config.apiKey ?? '').trim()) {
    return { ok: false, semanticOk: false, code: 'VISION_NOT_CONFIGURED', reason: 'Set API Key in the vision-fallback plugin.' }
  }
  try {
    const route = resolveVisionModel(config.model)
    const images = await loadImages(args.paths, workspaceOf(exec))
    const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS)
    const signal = exec?.signal ? AbortSignal.any([exec.signal, timeout]) : timeout
    const response = await fetch(route.endpoint, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${String(config.apiKey).trim()}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify(buildVisionRequest(route.model, images, args.question)),
      signal,
    })
    const raw = await response.text()
    let payload
    try { payload = JSON.parse(raw) } catch { payload = null }
    if (!response.ok) {
      const reason = payload?.error?.message || raw.slice(0, 500) || `HTTP ${response.status}`
      return { ok: false, semanticOk: false, code: failureCode(null, response.status), reason, status: response.status }
    }
    const answer = answerFromResponse(payload)
    return {
      ok: true,
      semanticOk: true,
      provider: route.provider,
      model: route.model,
      images: images.map((image) => image.input),
      answer,
    }
  } catch (error) {
    return {
      ok: false,
      semanticOk: false,
      code: failureCode(error),
      reason: error instanceof Error ? error.message : String(error),
    }
  }
}

export function apply(ctx, config) {
  const base = {
    model: config.model,
    ...(String(config.apiKey ?? '').trim() ? { apiKey: String(config.apiKey).trim() } : {}),
  }
  const settings = ctx.settings.register(SETTINGS_NAMESPACE, SettingsSchema, { base })

  ctx.tools.register(defineTool({
    name: 'vision_describe',
    description: 'Fallback visual inspection for a text-only session model. Send 1-4 workspace image paths to the separately configured vision model; this does not change or duplicate the chat model.',
    parameters: {
      paths: { type: 'array', items: { type: 'string' }, required: true, description: 'Image paths inside the current session workspace' },
      question: { type: 'string', description: 'What visual facts to inspect' },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: true,
        properties: {
          ok: { type: 'boolean', required: true },
          semanticOk: { type: 'boolean', required: true },
          code: { type: 'string' },
          reason: { type: 'string' },
          provider: { type: 'string' },
          model: { type: 'string' },
          images: { type: 'array', items: { type: 'string' } },
          answer: { type: 'string' },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: value.ok
          ? `Visual inspection succeeded via ${value.provider}/${value.model}.\n\n${value.answer}`
          : JSON.stringify(value),
      }],
    },
    async execute(args, exec) {
      return describe(settings.get(), args, exec)
    },
  }))

  ctx.systemPrompt.section({
    name: 'vision-fallback:guidance',
    order: 149,
    text: 'Use native image input when the active model supports it. If the active model is text-only, or read_image refuses because image input is unsupported, call vision_describe with workspace paths. This fallback inspects pixels with the configured vision model and returns text to the current chat model; it never creates a derived model route.',
  })
}
