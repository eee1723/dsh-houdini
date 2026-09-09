// Release-maintainer operations. Private keys are never emitted or put in a package.
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const [command, ...args] = process.argv.slice(2)
if (command === 'keygen') {
  const [privateFile, publicFile, id] = args
  if (!privateFile || !publicFile || !/^[a-z0-9-]+$/.test(id || '')) throw new Error('keygen <private.pem outside repo> <public-trust.json> <key-id>')
  const relative = path.relative(root, path.resolve(privateFile))
  if (!relative.startsWith('..' + path.sep) && !path.isAbsolute(relative)) throw new Error('private key must be outside the repository')
  if (fs.existsSync(privateFile) || fs.existsSync(publicFile)) throw new Error('refusing to overwrite an existing key or trust file')
  const { privateKey, publicKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 3072 })
  const pub = publicKey.export({ format: 'jwk' })
  fs.writeFileSync(privateFile, privateKey.export({ type: 'pkcs8', format: 'pem' }), { flag: 'wx', mode: 0o600 })
  fs.writeFileSync(publicFile, JSON.stringify({ schemaVersion: 1, keys: [{ id, n: pub.n, e: pub.e }] }, null, 2), { flag: 'wx' })
  console.log('Signing key created outside the repository. Back it up securely; review and commit only the public trust file.')
} else if (command === 'sign') {
  const [manifest, output, keyId] = args
  if (!process.env.DSH_RELEASE_SIGNING_KEY || !manifest || !output || !keyId) throw new Error('sign <release.json> <release.sig.json> <key-id>; DSH_RELEASE_SIGNING_KEY points to a private PEM file')
  const privateKey = fs.readFileSync(process.env.DSH_RELEASE_SIGNING_KEY)
  const signature = crypto.sign('sha256', fs.readFileSync(manifest), { key: privateKey, padding: crypto.constants.RSA_PKCS1_PADDING })
  fs.writeFileSync(output, JSON.stringify({ keyId, signature: signature.toString('base64') }, null, 2), { flag: 'wx' })
} else if (command === 'import-lock') {
  const [source] = args
  if (!source) throw new Error('import-lock <previously validated complete npm lockfile>')
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'deployment/package.json')))
  const lock = JSON.parse(fs.readFileSync(source))
  if (lock.lockfileVersion !== 3 || lock.packages['node_modules/@deepseek-ai/dsh']?.version !== pkg.dependencies['@deepseek-ai/dsh']) throw new Error('lock does not contain required DSH')
  for (const [name, value] of Object.entries(lock.packages)) {
    if (!name) continue
    if (value.link || !value.integrity || !value.resolved?.startsWith('https://registry.npmjs.org/')) throw new Error('unlocked or non-registry dependency: ' + name)
  }
  lock.name = pkg.name
  lock.version = pkg.version
  lock.packages[''] = { name: pkg.name, version: pkg.version, dependencies: pkg.dependencies }
  fs.writeFileSync(path.join(root, 'deployment/package-lock.json'), JSON.stringify(lock, null, 2) + '\n')
  console.log('Imported exact runtime dependency tree; run npm ci and the isolated runtime smoke before release')
} else {
  throw new Error('expected keygen, sign or import-lock')
}
