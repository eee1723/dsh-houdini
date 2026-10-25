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
const selected = manifest.dsh?.profile?.bundles
if (!Array.isArray(selected)) throw new Error('受管配置的组件列表格式无效，原配置已保留。')
const missing = bundles.filter(bundle => !selected.includes(bundle))
if (missing.length) throw new Error('受管配置缺少必要组件：' + missing.join(', ') + '。原配置已保留。')
const dependencies = Object.keys(manifest.dependencies || {})
if (dependencies.length) throw new Error('受管配置包含发行包外的依赖：' + dependencies.join(', ') + '。原配置已保留，未安装或移除依赖。')
// Native feature toggles legitimately add profile bundles. Resolve their
// declarations through DSH against the frozen installation, rather than
// comparing the user's choices with the initial defaults or a second catalog.
const installAnchor = path.join(app, 'node_modules/@deepseek-ai/dsh/package.json')
const modulesRoot = fs.realpathSync(path.join(app, 'node_modules'))
for (const bundle of selected) {
  let directory
  try { directory = fs.realpathSync(boot.resolveBundleDir('dsh', bundle, installAnchor, profile)) }
  catch { throw new Error('当前发行包无法加载配置组件：' + bundle + '。原配置已保留。') }
  const relative = path.relative(modulesRoot, directory)
  if (relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) {
    throw new Error('配置组件未从当前受管发行包加载：' + bundle + '。原配置已保留。')
  }
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
// Resolve the current profile's entries here; the serving Host imports them
// once. Staging already exercised both exports before selecting this package.
const profileRequire = createRequire(path.join(profile, 'package.json'))
profileRequire.resolve('dsh-houdini')
profileRequire.resolve('dsh-houdini/agent')
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
if (!context.workbench && interpolate({}, agent[0].config).bridgeUrl !== process.env.DSH_HOUDINI_BRIDGE_URL) {
  throw new Error('Scoped Houdini agent does not target this managed Bridge')
}
if (context.workbench && interpolate({}, agent[0].config).executorRegistry !== context.executorRegistry) {
  throw new Error('Scoped Houdini agent does not target this workbench registry')
}
console.log('Isolated DSH profile is ready; the bundle registers the Houdini preset')
