import type { Context } from '@deepseek-ai/cordis'

const QUESTION_KEYS = new Set(['id', 'question', 'header', 'options', 'multi_select'])
const OPTION_KEYS = new Set(['label', 'description'])

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
 * Question wording, option count and single/multi-select presentation are not
 * transport errors: the upstream schema permits text-only questions and does
 * not constrain the number of options. Keep UX recommendations in the preset.
 */
export function validateAskUserQuestionArgs(args: unknown): string | null {
  const root = record(args)
  if (!root || !Array.isArray(root.questions) || root.questions.length === 0) return null

  for (let index = 0; index < root.questions.length; index++) {
    const question = record(root.questions[index])
    if (!question) {
      return `ask_user_question question[${index}] must be an object. Retry using exact {id, question, header, options, multi_select} fields.`
    }
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

    if (question.options === undefined) continue

    if (!Array.isArray(question.options)) {
      return `ask_user_question question[${index}].options must be an array. Retry using exact {label, description} option objects, or omit options for a text-only question.`
    }
    for (let optionIndex = 0; optionIndex < question.options.length; optionIndex++) {
      const option = record(question.options[optionIndex])
      if (!option) {
        return `ask_user_question question[${index}].options[${optionIndex}] must be an object. Retry using exact {label, description} fields.`
      }
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
