import fs from 'node:fs'

const endpoint = process.argv[2] || 'http://127.0.0.1:8765'
const groups = Number(process.argv[3] || 40)
const logPath = 'Z:/tmp/dsh-timeline-race-triplet-probe.log'

function mark(message) {
  fs.appendFileSync(logPath, `${Date.now()} ${message}\n`, 'utf8')
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

mark(`probe_start groups=${groups}`)
for (let group = 1; group <= groups; group += 1) {
  const code = `
before_frame = float(hou.frame())
items = []
for render_frame in (1, 46, 240):
    result = render_view(
        '/obj/rubik/OUT', direction='iso', frame=render_frame,
        framing_frame=1, width=720, height=720, framing='full',
        picture='Z:/tmp/dsh-rubik-replay-gl-probe/triplet_slot_' + str(render_frame) + '.png')
    items.append({'frame': render_frame, 'bytes': result.get('file_bytes'), 'stale': result.get('stale')})
after_frame = float(hou.frame())
__result__ = {'before_frame': before_frame, 'after_frame': after_frame, 'items': items}
`
  mark(`group_${String(group).padStart(2, '0')}_before`)
  try {
    const response = await fetch(`${endpoint}/exec`, {
      method: 'POST',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({code}),
    })
    const envelope = await response.json()
    if (!envelope.ok) {
      mark(`group_${String(group).padStart(2, '0')}_error ${JSON.stringify(envelope.error)}`)
      process.exitCode = 1
      break
    }
    const value = envelope.result
    mark(
      `group_${String(group).padStart(2, '0')}_after ` +
      `before_frame=${value.before_frame} after_frame=${value.after_frame} ` +
      `items=${JSON.stringify(value.items)}`,
    )
  } catch (error) {
    mark(`group_${String(group).padStart(2, '0')}_fetch_error ${error.stack || error}`)
    process.exitCode = 2
    break
  }
  await delay(100)
}
mark(`probe_end exit_code=${process.exitCode || 0}`)
