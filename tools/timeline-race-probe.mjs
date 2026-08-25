import fs from 'node:fs'

const endpoint = process.argv[2] || 'http://127.0.0.1:8765'
const iterations = Number(process.argv[3] || 120)
const logPath = 'Z:/tmp/dsh-timeline-race-probe.log'

function mark(message) {
  fs.appendFileSync(logPath, `${Date.now()} ${message}\n`, 'utf8')
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

mark(`probe_start iterations=${iterations}`)
for (let index = 1; index <= iterations; index += 1) {
  const renderFrame = [1, 46, 240][(index - 1) % 3]
  const code = `
before_frame = float(hou.frame())
result = render_view(
    '/obj/rubik/OUT', direction='iso', frame=${renderFrame},
    framing_frame=1, width=720, height=720, framing='full',
    picture='Z:/tmp/dsh-rubik-replay-gl-probe/timeline_slot_${index % 3}.png')
after_frame = float(hou.frame())
__result__ = {
    'before_frame': before_frame,
    'after_frame': after_frame,
    'render_frame': ${renderFrame},
    'bytes': result.get('file_bytes'),
    'stale': result.get('stale'),
}
`
  mark(`request_${String(index).padStart(3, '0')}_before render_frame=${renderFrame}`)
  try {
    const response = await fetch(`${endpoint}/exec`, {
      method: 'POST',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({code}),
    })
    const envelope = await response.json()
    if (!envelope.ok) {
      mark(`request_${String(index).padStart(3, '0')}_error ${JSON.stringify(envelope.error)}`)
      process.exitCode = 1
      break
    }
    const value = envelope.result
    mark(
      `request_${String(index).padStart(3, '0')}_after ` +
      `before_frame=${value.before_frame} after_frame=${value.after_frame} ` +
      `bytes=${value.bytes} stale=${value.stale}`,
    )
  } catch (error) {
    mark(`request_${String(index).padStart(3, '0')}_fetch_error ${error.stack || error}`)
    process.exitCode = 2
    break
  }
  // Let Houdini process queued UI input between render requests.
  await delay(100)
}
mark(`probe_end exit_code=${process.exitCode || 0}`)
