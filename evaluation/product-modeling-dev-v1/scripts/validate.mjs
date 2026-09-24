import { validateSuite } from './suite.mjs'

try {
  const { manifest } = validateSuite()
  process.stdout.write(`validated ${manifest.suiteId}: ${manifest.cases.length} development cases\n`)
} catch (error) {
  process.stderr.write(`${error.message}\n`)
  process.exitCode = 1
}
