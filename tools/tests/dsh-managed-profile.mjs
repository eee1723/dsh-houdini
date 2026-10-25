/** Exact frozen DSH profile preparation; fresh and copied native feature settings. */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createRequire} from 'node:module'
import {pathToFileURL,fileURLToPath} from 'node:url'
import {spawnSync} from 'node:child_process'

const install=path.resolve(process.argv[2]??(()=>{throw Error('Pass a verified install/payload root containing app')})())
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..')
const require=createRequire(path.join(install,'app/package.json'))
const boot=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')))
const defaults=[...boot.PROFILE_TEMPLATES.web.bundles,'dsh-houdini']
if(process.argv[3]==='--enable-native-team'){
 const profile=boot.resolveProfileDir('web',path.resolve(process.argv[4]))
 const manifest=boot.readProfileManifest('dsh',profile)
 const selected=manifest.dsh.profile.bundles
 const team='@deepseek-ai/dsh-experimental-agent-team-profile'
 boot.writeProfileBundles(profile,manifest,[...new Set([...selected,team])])
 console.log('Enabled native team through the public DSH profile API in the explicit fixture home')
 process.exit(0)
}
const folder=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-managed-profile-'))
console.log('Managed profile evidence:',folder)
const run=(home)=>{
 const context=path.join(home,'context.json')
 fs.writeFileSync(context,JSON.stringify({install,home,workbench:true,executorRegistry:path.join(home,'executors')}))
 return spawnSync(process.execPath,[path.join(root,'tools/prepare-managed-profile.mjs'),context],{
  cwd:path.join(install,'app'),env:{...process.env,DSH_HOME:home,DSH_HOUDINI_EXECUTOR_REGISTRY:path.join(home,'executors')},
  encoding:'utf8',windowsHide:true,timeout:30000})
}
const fixture=(name,bundles,dependencies={})=>{
 const home=path.join(folder,name),profile=path.join(home,'profiles/web')
 fs.mkdirSync(profile,{recursive:true})
 boot.initProfile(profile,defaults)
 const manifest=boot.readProfileManifest('dsh',profile)
 manifest.dependencies=dependencies
 boot.writeProfileBundles(profile,manifest,bundles)
 fs.writeFileSync(path.join(profile,'cordis.patch.yml'),'# User configuration is preserved.\n[]\n')
 fs.writeFileSync(path.join(home,'user-data.txt'),'sessions/settings sentinel')
 return {home,profile,before:fs.readFileSync(path.join(profile,'package.json')),
  patch:fs.readFileSync(path.join(profile,'cordis.patch.yml'))}
}
for(const [name,extra] of [['fresh',[]],['native-team',['@deepseek-ai/dsh-experimental-agent-team-profile']],
 ['other-native-feature',['@deepseek-ai/dsh-experimental-session-search']]]){
 const f=fixture(name,[...defaults,...extra])
 const result=run(f.home)
 assert.equal(result.status,0,result.stderr||result.stdout)
 assert.deepEqual(fs.readFileSync(path.join(f.profile,'package.json')),f.before,'preparing cannot reset feature choices')
 assert.deepEqual(fs.readFileSync(path.join(f.profile,'cordis.patch.yml')),f.patch)
 assert.equal(fs.readFileSync(path.join(f.home,'user-data.txt'),'utf8'),'sessions/settings sentinel')
 const loaded=boot.loadProfile('dsh','web',path.join(install,'app/node_modules/@deepseek-ai/dsh/package.json'),f.home)
 assert.deepEqual(loaded.skippedBundles,[])
 assert.deepEqual(loaded.layers.map(layer=>layer.packageName),[...defaults,...extra])
 if(extra.includes('@deepseek-ai/dsh-experimental-agent-team-profile')){
  const entries=boot.composeEntries([...loaded.layers.map(layer=>layer.patches),loaded.patches])
  assert(entries.some(entry=>entry.id==='agent-team'&&!entry.disabled))
  assert(entries.some(entry=>entry.id==='tool-agent-team'&&!entry.disabled))
 }
 const repeated=run(f.home)
 assert.equal(repeated.status,0,repeated.stderr||repeated.stdout)
 assert.deepEqual(fs.readFileSync(path.join(f.profile,'package.json')),f.before)
 console.log('PASS',name)
}
for(const [name,bundles,dependencies,reason] of [
 ['unknown-extension',[...defaults,'@fixture/external'],{},'当前发行包无法加载'],
 ['extra-dependency',defaults,{'@fixture/external':'1.0.0'},'发行包外的依赖'],
 ['missing-product',defaults.filter(name=>name!=='dsh-houdini'),{},'缺少必要组件'],
]){
 const f=fixture(name,bundles,dependencies),result=run(f.home)
 assert.notEqual(result.status,0)
 assert(result.stderr.includes(reason),result.stderr)
 assert(!result.stderr.includes('changed outside the installer'))
 assert.deepEqual(fs.readFileSync(path.join(f.profile,'package.json')),f.before)
 assert.deepEqual(fs.readFileSync(path.join(f.profile,'cordis.patch.yml')),f.patch)
 console.log('PASS',name,'preserves input and explains the actual boundary')
}
console.log('Managed profile defaults, native optional layers, repeated preparation and precise unsupported boundaries passed')
