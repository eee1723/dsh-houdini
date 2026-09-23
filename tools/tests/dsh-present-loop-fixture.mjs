// Deterministic local adapter: call the mounted present tool through the real
// DSH Agent loop, without an external model or Houdini scene mutation.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { LlmAdapter } from '@deepseek-ai/dsh-llm'

export const inject = ['llm', 'sessions']

export function apply(ctx) {
  class PresentFixture extends LlmAdapter {
    async resolveModel(provider, model) {
      return { provider, id: model, name: 'Present fixture', inputModalities: ['text'], context: { contextWindow: 500000 } }
    }

    async *stream(options) {
      const text = (value) => {
        const block = { type: 'text', text: value }
        return [
          { type: 'block-start', index: 0, blockType: 'text' },
          { type: 'block-end', index: 0, block },
          { type: 'finish', reason: { kind: 'stop' } },
        ]
      }
      if (options.purpose) {
        yield* text('Present fixture')
        return
      }
      const result = options.messages.flatMap(message => message.content)
        .find(content => content.type === 'tool-result' && content.toolCallId === 'present-fixture-call')
      if (!result) {
        const files = JSON.parse(process.env.DSH_PRESENT_FIXTURE_FILES)
        const block = { type: 'tool-call', id: 'present-fixture-call', name: 'present', arguments: JSON.stringify({ files }) }
        yield { type: 'block-start', index: 0, blockType: 'tool-call' }
        yield { type: 'block-end', index: 0, block }
        yield { type: 'finish', reason: { kind: 'tool-calls' } }
        return
      }
      assert.equal(result.isError, false, JSON.stringify(result))
      const session = ctx.sessions.get(options.sessionId)
      const events = session.snapshotEvents()
      const presented = events.filter(event => event.type === 'deliverables/presented')
      assert.equal(presented.length, 1, 'the mounted tool must append exactly one delivery event')
      assert.equal(presented[0].data.callId, 'present-fixture-call')
      assert.deepEqual(presented[0].data.files, JSON.parse(process.env.DSH_PRESENT_FIXTURE_FILES))
      await ctx.sessions.flush(session)
      const output = process.env.DSH_PRESENT_FIXTURE_OUT
      fs.writeFileSync(output + '.tmp', JSON.stringify({ sessionId: options.sessionId, seq: presented[0].seq,
        files: presented[0].data.files }))
      fs.renameSync(output + '.tmp', output)
      yield* text('Files delivered by the mounted present tool.')
    }
  }
  ctx.llm.registerAdapter(['present-fixture'], new PresentFixture())
}
