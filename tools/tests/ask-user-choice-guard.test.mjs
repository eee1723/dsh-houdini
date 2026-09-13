import assert from 'node:assert/strict'
import { validateAskUserQuestionArgs } from '../../lib/ask-user-guard.js'

const choices = [
  { label: 'Preview (Recommended)', description: 'Fast network and validation preview.' },
  { label: 'Final', description: 'Higher quality with more time and render cost.' },
]

assert.equal(validateAskUserQuestionArgs({
  questions: [{
    id: 'quality',
    header: 'Quality',
    question: '选择哪种质量级别？',
    options: choices,
    multi_select: false,
  }],
}), null)

const trailing = validateAskUserQuestionArgs({
  questions: [{
    id: 'shape',
    question: '沙尘冲击想要哪种形态？',
    'header ': '效果形态',
    'options ': choices,
  }],
})
assert.match(trailing, /unsupported key\(s\): header , options /)
assert.match(trailing, /trim to valid names: header, options/)

assert.match(validateAskUserQuestionArgs({ questions: ['not-an-object'] }), /must be an object/)
assert.match(validateAskUserQuestionArgs({
  questions: [{
    id: 'shape',
    question: '选择哪种形态？',
    header: '形态',
    options: [{ label: 'A', description: 'A' }, 'not-an-object'],
  }],
}), /options\[1\] must be an object/)

assert.match(validateAskUserQuestionArgs({
  questions: [{ id: 'mode', question: '选择模式', options: { label: 'Preview' } }],
}), /options must be an array/)

assert.match(validateAskUserQuestionArgs({
  questions: [{
    id: 'mode',
    question: '选择模式',
    options: [{ 'label ': 'Preview' }, { label: 'Final' }],
  }],
}), /options\[0\].*unsupported key/)

assert.equal(validateAskUserQuestionArgs({
  questions: [{ id: 'path', question: '请输入精确的 HIP 文件路径。' }],
}), null)

assert.equal(validateAskUserQuestionArgs({
  questions: [{ id: 'details', question: '请补充其他具体限制。' }],
}), null)

// Wording does not determine whether a question can have useful preset options.
// These formerly hit the plugin's language regex despite the valid Host schema.
for (const question of [
  '交付文件保存到哪个路径？',
  '请输入需要匹配的完整节点类型名。',
  '深度需要精确设成多少毫米？',
  '实现方式偏好？',
  'Which exact output filename should I use?',
  'What do you prefer to call this asset?',
]) {
  assert.equal(validateAskUserQuestionArgs({ questions: [{ id: 'text', question }] }), null, question)
}

// Upstream options are optional and have no minItems/maxItems contract. UI
// guidance may recommend a small set, but the plugin must not narrow the API.
for (const count of [0, 1, 5]) {
  assert.equal(validateAskUserQuestionArgs({
    questions: [{
      id: 'outputs',
      question: '选择需要交付的输出。',
      options: Array.from({ length: count }, (_, index) => ({ label: `Output ${index + 1}` })),
      multi_select: true,
    }],
  }), null)
}

console.log('ask-user choice guard tests passed')
