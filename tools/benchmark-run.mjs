import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { prepareIsolatedRunWorkspace } from './benchmark-smoke.mjs'

function option(values, name) {
  const index = values.indexOf(name)
  return index >= 0 ? values[index + 1] : undefined
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isMain) {
  const [command, ...values] = process.argv.slice(2)
  if (command !== 'prepare'
      || !option(values, '--kit')
      || !option(values, '--family')
      || !option(values, '--run-id')
      || !option(values, '--model')
      || !option(values, '--protocol')) {
    console.error('usage: node tools/benchmark-run.mjs prepare --kit <root> --family <family> --run-id <id> --model <provider/model> --protocol <protocol.json>')
    process.exitCode = 2
  } else {
    try {
      console.log(JSON.stringify(prepareIsolatedRunWorkspace({
        kitRoot: option(values, '--kit'),
        family: option(values, '--family'),
        runId: option(values, '--run-id'),
        model: option(values, '--model'),
        protocolFile: option(values, '--protocol'),
        phase: 'discovery',
      }), null, 2))
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error))
      process.exitCode = 1
    }
  }
}
