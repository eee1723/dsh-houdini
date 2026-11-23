// Publish only versions users can already install from the public npm registry.
import {mkdir, writeFile} from 'node:fs/promises'
import {fileURLToPath} from 'node:url'

const name = 'dsh-houdini'
const response = await fetch('https://registry.npmjs.org/' + name, {
  headers: {accept: 'application/json'},
  signal: AbortSignal.timeout(30000),
})
if (!response.ok) throw Error('npm registry returned HTTP ' + response.status)
const registry = await response.json()
if (registry.name !== name) throw Error('Unexpected npm package name')

const versions = []
for (const [version, manifest] of Object.entries(registry.versions)) {
  if (!manifest.dsh?.bundle || manifest.private || manifest.deprecated) continue
  const publishTimestamp = Math.floor(Date.parse(registry.time[version]) / 1000)
  const dsh = manifest.engines?.dsh
  if (manifest.name !== name || manifest.version !== version || !Number.isFinite(publishTimestamp)
      || typeof dsh !== 'string' || !dsh.trim()) {
    throw Error('Incomplete published bundle metadata for ' + version)
  }
  versions.push({version, publishTimestamp, source: {type: 'npm'}, engines: {dsh}})
}
if (!versions.length) throw Error('npm returned no installable DSH bundle versions')
versions.sort((a, b) => b.publishTimestamp - a.publishTimestamp || a.version.localeCompare(b.version))
const expected = process.argv[2]
if (expected && !versions.some(row => row.version === expected)) {
  throw Error('Expected release is not available from npm: ' + expected)
}

const index = {
  format: 1,
  title: 'DSH-Houdini',
  plugins: [{name, title: 'DSH-Houdini', homepage: 'https://github.com/eee1723/dsh-houdini', versions}],
}
const directory = new URL('../market/', import.meta.url)
await mkdir(directory, {recursive: true})
const file = new URL('index.json', directory)
await writeFile(file, JSON.stringify(index, null, 2) + '\n')
console.log('Indexed %d public versions in %s', versions.length, fileURLToPath(file))
