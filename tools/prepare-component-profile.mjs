// Explicit source-candidate profile preparation. Does not install or launch a runtime.
import fs from 'node:fs'
import path from 'node:path'
import {createRequire} from 'node:module'
import {fileURLToPath,pathToFileURL} from 'node:url'

const [bin,home,python,houdini,workerRoot,registry]=process.argv.slice(2)
const plugin=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
if([bin,home,python,houdini,workerRoot,registry].some(p=>typeof p!=='string'||!path.isAbsolute(p)))
  throw new Error('Arguments: absolute DSH bin.js, new DSH home, Python, Houdini GUI executable, worker root, registry')
if(process.env.DSH_HOME!==home||fs.existsSync(home))throw new Error('Set DSH_HOME to a new dedicated directory; existing user data is never copied or overwritten')
const require=createRequire(bin)
const boot=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')))
const profile=boot.resolveProfileDir('web')
boot.initProfile(profile,[...boot.PROFILE_TEMPLATES.web.bundles,'dsh-houdini'],boot.PROFILE_TEMPLATES.web.patchReload)
const link=path.join(profile,'node_modules/dsh-houdini')
fs.mkdirSync(path.dirname(link),{recursive:true})
fs.symlinkSync(plugin,link,'junction')
boot.loadProfile('dsh','web',path.join(path.dirname(path.dirname(bin)),'package.json'))
for(const name of ['houdini','houdini-dev'])fs.cpSync(path.join(plugin,'presets',name),path.join(home,'.agent-presets',name),{recursive:true})
const overlay=path.join(home,'component.cordis.yml')
const settings={python,houdini,workerRoot,executorRegistry:registry,gui:true,memoryMb:4096,threads:2,startupTimeoutSeconds:90,maxWorkers:2,projectLocalWorkers:true}
fs.writeFileSync(overlay,'- insert:\n    - id: component-executors\n      name: dsh-houdini/executor-host\n      config: '
  +JSON.stringify({executorRegistry:registry,requestTimeoutMs:120000})+'\n'
  +'    - id: component-host\n      name: dsh-houdini/component-host\n      config: '+JSON.stringify(settings)+'\n',{flag:'wx'})
console.log(JSON.stringify({profile,overlay,registry,workerRoot,boundary:'Source candidate only. Requires the patched DSH continuation cwd implementation. No account data copied, no process launched.'},null,2))
