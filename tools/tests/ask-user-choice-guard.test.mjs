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
  questions: [{ id: 'mode', question: '实现方式偏好？' }],
}), /is a user choice but has no options/)

assert.match(validateAskUserQuestionArgs({
  questions: [{ id: 'mode', question: '选择模式', options: [choices[0]] }],
}), /must contain 2–4 choices/)

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

console.log('ask-user choice guard tests passed')
