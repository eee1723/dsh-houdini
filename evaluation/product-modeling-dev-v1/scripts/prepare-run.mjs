import { prepareRun } from './suite.mjs'

const args = process.argv.slice(2)
const options = {}
for (let index = 0; index < args.length; index += 2) {
  const flag = args[index]
  if (!['--case', '--out', '--baseline-hip'].includes(flag) || !args[index + 1] || options[flag]) {
    process.stderr.write('usage: node prepare-run.mjs --case <case-id> [--out <absolute-dir>] [--baseline-hip <absolute-file.hip|.hiplc|.hipnc>]\n')
    process.exit(2)
  }
  options[flag] = args[index + 1]
}
try {
  const result = prepareRun({ caseId: options['--case'], output: options['--out'], baselineHip: options['--baseline-hip'] })
  process.stdout.write(`${result.destination}\n`)
} catch (error) {
  process.stderr.write(`${error.message}\n`)
  process.exitCode = 1
}
