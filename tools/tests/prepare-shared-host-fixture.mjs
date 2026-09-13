import fs from 'node:fs'
import path from 'node:path'
import {createRequire} from 'node:module'
import {pathToFileURL} from 'node:url'
const [bin,home,plugin]=process.argv.slice(2)
if(process.env.DSH_HOME!==home||!path.isAbsolute(home)||fs.existsSync(home))throw Error('Fresh isolated DSH home required')
const require=createRequire(bin)
const boot=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')))
const profile=boot.resolveProfileDir('web')
boot.initProfile(profile,[...boot.PROFILE_TEMPLATES.web.bundles,'dsh-houdini'],boot.PROFILE_TEMPLATES.web.patchReload)
const link=path.join(profile,'node_modules/dsh-houdini')
fs.mkdirSync(path.dirname(link),{recursive:true})
fs.symlinkSync(plugin,link,'junction')
boot.loadProfile('dsh','web',path.join(path.dirname(path.dirname(bin)),'package.json'))
for(const name of ['houdini','houdini-dev'])fs.cpSync(path.join(plugin,'presets',name),path.join(home,'.agent-presets',name),{recursive:true})
fs.writeFileSync(path.join(path.dirname(home),'shared-host-test.json'),JSON.stringify({kind:'isolated-shared-host-test',plugin:path.resolve(plugin)}),{flag:'wx'})
console.log('Prepared shared Host fixture without models or user data')
