import type { Context } from '@deepseek-ai/cordis'

const QUESTION_KEYS = new Set(['id', 'question', 'header', 'options', 'multi_select'])
const OPTION_KEYS = new Set(['label', 'description'])
const CHOICE_QUESTION = /(?:哪种|哪个|选择|偏好|是否|要不要|交付|风格|质量|模式|类型|方式|形态|路线|深度|which|choose|prefer|whether)/i

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function invalidKeys(value: Record<string, unknown>, allowed: Set<string>): string[] {
  return Object.keys(value).filter((key) => !allowed.has(key))
}

/**
 * Return actionable feedback for malformed ask_user_question arguments.
 *
 * The upstream tool intentionally allows additional properties. Some models
 * therefore emit near-miss keys such as `options `; its executor ignores them
 * and the UI silently falls back to a blank text box. Arguments are immutable
 * by the tools pipeline, so this guard rejects before UI dispatch and asks the
 * model to retry with the exact logged schema instead of rewriting history.
 */
export function validateAskUserQuestionArgs(args: unknown): string | null {
  const root = record(args)
  if (!root || !Array.isArray(root.questions) || root.questions.length === 0) return null

  for (let index = 0; index < root.questions.length; index++) {
    const question = record(root.questions[index])
    if (!question) continue
    const unknown = invalidKeys(question, QUESTION_KEYS)
    if (unknown.length) {
      const aliases = unknown
        .map((key) => key.trim())
        .filter((key) => QUESTION_KEYS.has(key))
      const hint = aliases.length
        ? ` Near-miss key(s) trim to valid names: ${aliases.join(', ')}.`
        : ''
      return `ask_user_question question[${index}] has unsupported key(s): ${unknown.join(', ')}.${hint} Retry the same questions using only exact keys: id, question, header, options, multi_select.`
    }

    const text = typeof question.question === 'string' ? question.question : ''
    if (question.options === undefined) {
      if (CHOICE_QUESTION.test(text)) {
        return `ask_user_question question[${index}] is a user choice but has no options. Retry with 2–4 concrete mutually exclusive options using exact {label, description} objects; put the recommended option first. The UI automatically preserves a custom free-text answer for supplemental constraints.`
      }
      continue
    }

    if (!Array.isArray(question.options) || question.options.length < 2 || question.options.length > 4) {
      return `ask_user_question question[${index}].options must contain 2–4 choices. Retry with concrete mutually exclusive {label, description} options; use a text-only question only for an inherently unique path, name, number, or custom specification.`
    }
    for (let optionIndex = 0; optionIndex < question.options.length; optionIndex++) {
      const option = record(question.options[optionIndex])
      if (!option) continue
      const optionUnknown = invalidKeys(option, OPTION_KEYS)
      if (optionUnknown.length) {
        return `ask_user_question question[${index}].options[${optionIndex}] has unsupported key(s): ${optionUnknown.join(', ')}. Retry using only exact option keys: label, description.`
      }
    }
  }
  return null
}

export function installAskUserChoiceGuard(ctx: Context): void {
  ctx.on('tools/pre-execute', async (exec, next) => {
    if (exec.name !== 'ask_user_question') return next()
    const reason = validateAskUserQuestionArgs(exec.arguments)
    return reason === null ? next() : { kind: 'deny', reason }
  })
}
