import { createHash } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { readFile, realpath, stat } from 'node:fs/promises'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

export async function checkPackage(manifest) {
  const root = await realpath(path.dirname(manifest))
  const { hda, files } = JSON.parse(await readFile(manifest, 'utf8'))
  if (typeof hda !== 'string' || !/\.(?:hda|otl)(?:lc|nc)?$/i.test(hda) || !Array.isArray(files)) {
    throw new Error('Expected hda and files[]; a file receipt does not certify Engine compatibility')
  }
  const receipts = []
  for (const name of [hda, ...files]) {
    if (typeof name !== 'string' || !name || name.includes('\\') || name.includes(':') || path.posix.isAbsolute(name) || name.split('/').includes('..')) {
      throw new Error(`Expected portable package-relative file: ${name}`)
    }
    const target = await realpath(path.join(root, name))
    const relative = path.relative(root, target)
    if (relative.startsWith(`..${path.sep}`) || relative === '..' || path.isAbsolute(relative) || !(await stat(target)).isFile()) {
      throw new Error(`Not a file inside the package: ${name}`)
    }
    const hash = createHash('sha256')
    let bytes = 0
    for await (const chunk of createReadStream(target)) { hash.update(chunk); bytes += chunk.length }
    receipts.push({ path: name, bytes, sha256: hash.digest('hex') })
  }
  return { scope: 'declared-files-only', files: receipts }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try { console.log(JSON.stringify(await checkPackage(path.resolve(process.argv[2])), null, 2)) }
  catch (error) { console.error(error.message); process.exitCode = 1 }
}
