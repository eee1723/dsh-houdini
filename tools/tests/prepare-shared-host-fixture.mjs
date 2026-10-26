import fs from 'node:fs'
import path from 'node:path'
import {createRequire} from 'node:module'
import {pathToFileURL} from 'node:url'
const [bin,home,plugin]=process.argv.slice(2)
if(process.env.DSH_HOME!==home||!path.isAbsolute(home)||fs.existsSync(home))throw Error('Fresh isolated DSH home required')
const require=createRequire(bin)
const boot=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')))
// Match the plugin's published file allowlist. A test installation must never
// let the Host's installation protection operate on the development checkout.
const installedRoot=path.join(path.dirname(home),'installed'),installed=path.join(installedRoot,'dsh-houdini')
const manifest=JSON.parse(fs.readFileSync(path.join(plugin,'package.json'),'utf8'))
fs.mkdirSync(installed,{recursive:true})
for(const item of ['package.json','README.md','LICENSE',...manifest.files]) {
  const source=path.resolve(plugin,item),relative=path.relative(path.resolve(plugin),source)
  if(relative.startsWith('..')||path.isAbsolute(relative))throw Error('Package entry escapes plugin root')
  if(fs.existsSync(source))fs.cpSync(source,path.join(installed,relative),{recursive:true})
}
const officialModules=path.resolve(path.dirname(bin),'../../..')
if(!officialModules.endsWith(path.sep+'node_modules'))throw Error('Expected exact official runtime node_modules')
fs.symlinkSync(officialModules,path.join(installedRoot,'node_modules'),'junction')
const profile=boot.resolveProfileDir('web')
boot.initProfile(profile,[...boot.PROFILE_TEMPLATES.web.bundles,'dsh-houdini'],boot.PROFILE_TEMPLATES.web.patchReload)
const link=path.join(profile,'node_modules/dsh-houdini')
fs.mkdirSync(path.dirname(link),{recursive:true})
fs.symlinkSync(installed,link,'junction')
boot.loadProfile('dsh','web',path.join(path.dirname(path.dirname(bin)),'package.json'))
fs.writeFileSync(path.join(path.dirname(home),'shared-host-test.json'),JSON.stringify({kind:'isolated-shared-host-test',plugin:installed,source:path.resolve(plugin),officialModules}),{flag:'wx'})
console.log('Prepared shared Host fixture without models or user data')
