/** Remove only the generated TypeScript output directory before a fresh build. */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const output = path.resolve(root, 'lib')
if (path.dirname(output) !== root || path.basename(output) !== 'lib') {
  throw new Error(`refusing to clean unexpected build output: ${output}`)
}
fs.rmSync(output, { recursive: true, force: true })
