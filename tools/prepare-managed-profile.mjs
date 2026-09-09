// Invoked only after the signed payload has been verified. No package manager.
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const context = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
if (process.env.DSH_HOME !== context.home) throw new Error('isolated DSH_HOME is required')
const app = path.join(context.install, 'app')
const require = createRequire(path.join(app, 'package.json'))
const boot = await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')).href)
const { resolveDshHome } = await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-home-paths')).href)
if (path.resolve(resolveDshHome()) !== path.resolve(context.home)) throw new Error('DSH home isolation failed')
const profile = boot.resolveProfileDir('web')
const bundles = [...boot.PROFILE_TEMPLATES.web.bundles, 'dsh-houdini']
boot.initProfile(profile, bundles, boot.PROFILE_TEMPLATES.web.patchReload)
const manifest = boot.readProfileManifest('dsh', profile)
if (JSON.stringify(manifest.dsh?.profile?.bundles) !== JSON.stringify(bundles) || Object.keys(manifest.dependencies || {}).length) {
  throw new Error('The managed profile was changed outside the installer. Preserve its data and restore the profile before starting.')
}
boot.loadProfile('dsh', 'web', path.join(app, 'node_modules/@deepseek-ai/dsh/package.json'))
// DSH's public bundle resolver finds installation siblings, but its runtime
// loader resolves bundle entries from the profile. Project only this signed
// package into that profile; peers still resolve from the one frozen app tree.
const pluginTarget = path.join(app, 'node_modules/dsh-houdini')
const pluginLink = path.join(profile, 'node_modules/dsh-houdini')
fs.mkdirSync(path.dirname(pluginLink), { recursive: true })
if (fs.existsSync(pluginLink)) {
  if (fs.realpathSync(pluginLink).toLowerCase() !== fs.realpathSync(pluginTarget).toLowerCase()) throw new Error('managed profile plugin link points outside this installation')
} else {
  fs.symlinkSync(pluginTarget, pluginLink, 'junction')
}
const fromProfile = createRequire(path.join(profile, 'package.json')).resolve('dsh-houdini')
await import(pathToFileURL(fromProfile).href)
for (const name of ['houdini', 'houdini-dev']) {
  const source = path.join(app, 'node_modules/dsh-houdini/presets', name)
  const dest = path.join(context.home, '.agent-presets', name)
  fs.cpSync(source, dest, { recursive: true })
  const filename = path.join(dest, 'agent.cordis.yml')
  // Preserve all !!js and prose verbatim; only the known transport URL changes.
  const input = fs.readFileSync(filename, 'utf8')
  const marker = 'bridgeUrl: http://127.0.0.1:8765'
  if (input.split(marker).length !== 2) throw new Error('preset bridge binding is ambiguous')
  if (!Number.isInteger(context.bridgePort) || context.bridgePort < 1024 || context.bridgePort > 65535) throw new Error('invalid managed bridge port')
  fs.writeFileSync(filename, input.replace(marker, 'bridgeUrl: http://127.0.0.1:' + context.bridgePort))
}
console.log('Isolated DSH profile and presets are ready; no package manager was invoked')
