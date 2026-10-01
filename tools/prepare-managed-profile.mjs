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
boot.initProfile(profile, bundles)
const manifest = boot.readProfileManifest('dsh', profile)
if (JSON.stringify(manifest.dsh?.profile?.bundles) !== JSON.stringify(bundles) || Object.keys(manifest.dependencies || {}).length) {
  throw new Error('The managed profile was changed outside the installer. Preserve its data and restore the profile before starting.')
}
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
const agentFromProfile = createRequire(path.join(profile, 'package.json')).resolve('dsh-houdini/agent')
await import(pathToFileURL(agentFromProfile).href)
const loaded = boot.loadProfile('dsh', 'web', path.join(app, 'node_modules/@deepseek-ai/dsh/package.json'))
if (loaded.skippedBundles.length) throw new Error('Managed profile skipped bundles: ' + JSON.stringify(loaded.skippedBundles))
const entries = boot.composeEntries([...loaded.layers.map(layer => layer.patches), loaded.patches])
const frontend = entries.filter(entry => !entry.disabled && entry.name === 'dsh-houdini')
const presets = entries.filter(entry => !entry.disabled && entry.name === '@deepseek-ai/dsh-agent-preset')
const agent = presets[0]?.config?.plugins?.filter(entry => !entry.disabled && entry.name === 'dsh-houdini/agent')
if (frontend.length !== 1 || presets.length !== 1 || presets[0].config.id !== 'houdini' || agent?.length !== 1) {
  throw new Error('Managed profile must deliver one browser carrier and one scoped Houdini agent')
}
if (entries.some(entry => !entry.disabled && entry.name === 'dsh-houdini/agent')) {
  throw new Error('Houdini tools must stay in the preset scope')
}
const { interpolate } = await import(pathToFileURL(require.resolve('@deepseek-ai/cordis-plugin-loader')).href)
if (interpolate({}, agent[0].config).bridgeUrl !== process.env.DSH_HOUDINI_BRIDGE_URL) {
  throw new Error('Scoped Houdini agent does not target this managed Bridge')
}
console.log('Isolated DSH profile is ready; the bundle registers the Houdini preset')
