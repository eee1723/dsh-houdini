import assert from 'node:assert/strict'
import path from 'node:path'
import {
  apply,
  buildVisionRequest,
  imageMediaType,
  resolveVisionModel,
  resolveWorkspacePath,
} from '../../plugins/dsh-vision-fallback/index.js'

assert.deepEqual(resolveVisionModel('qwen/qwen3-vl-plus'), {
  provider: 'qwen',
  model: 'qwen3-vl-plus',
  endpoint: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
})
assert.equal(resolveVisionModel('openai/gpt-4.1').provider, 'openai')
assert.throws(() => resolveVisionModel('qwen3-vl-plus'), /provider\/model/)
assert.throws(() => resolveVisionModel('unknown/model'), /unsupported vision provider/)

assert.equal(imageMediaType(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])), 'image/png')
assert.equal(imageMediaType(Buffer.from([0xff, 0xd8, 0xff, 0x00])), 'image/jpeg')
assert.equal(imageMediaType(Buffer.from('GIF89a......')), 'image/gif')
assert.equal(imageMediaType(Buffer.from('not an image')), null)

const workspace = path.resolve('Z:/session-workspace')
assert.equal(resolveWorkspacePath(workspace, 'images/a.png'), path.join(workspace, 'images/a.png'))
assert.throws(() => resolveWorkspacePath(workspace, '../secret.png'), /escapes/)

const request = buildVisionRequest('qwen3-vl-plus', [{
  input: 'a.png', mediaType: 'image/png', data: 'AAAA',
}], 'inspect it')
assert.equal(request.model, 'qwen3-vl-plus')
assert.equal(request.messages[0].content[0].image_url.url, 'data:image/png;base64,AAAA')
assert.equal(request.messages[0].content[1].text, 'inspect it')

let registration
let tool
apply({
  settings: {
    register: (namespace, schema, options) => {
      registration = { namespace, schema, options }
      return { get: () => ({ model: 'qwen/qwen3-vl-plus' }) }
    },
  },
  tools: { register: value => { tool = value } },
  systemPrompt: { section: () => {} },
}, { apiKey: '', model: 'qwen/qwen3-vl-plus' })
assert.equal(registration.namespace, 'vision-fallback')
assert.deepEqual(registration.options.base, { model: 'qwen/qwen3-vl-plus' })
const notConfigured = await tool.execute({ paths: ['image.png'] }, {})
assert.equal(notConfigured.code, 'VISION_NOT_CONFIGURED')

console.log('vision fallback tests passed')
