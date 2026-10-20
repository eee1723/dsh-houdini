// Opt-in real DSH Team -> plugin tool -> independent hython integration.
// A local scripted adapter chooses calls; all agent, tool, job and HOM work is real.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {spawn,spawnSync} from 'node:child_process'
import net from 'node:net'
import {fileURLToPath} from 'node:url'

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..')
const args=process.argv.slice(2)
if(!args.length){
  console.log('SKIP dsh-isolated-tool-loop: opt in with --runtime-cache <prepared DSH> --hython <hython.exe> [--python <python.exe>]')
}else{
  const values={}
  for(let i=0;i<args.length;i+=2){assert(args[i].startsWith('--')&&args[i+1],'Expected --name value pairs');values[args[i].slice(2)]=args[i+1]}
  const runtime=path.resolve(values['runtime-cache']??''),hython=path.resolve(values.hython??'')
  assert(values['runtime-cache']&&values.hython,'--runtime-cache and --hython are required')
  const hfs=path.dirname(path.dirname(hython))
  const python=values.python?path.resolve(values.python):['python313','python311'].map(name=>path.join(hfs,name,'python.exe')).find(fs.existsSync)
  const cli=path.join(runtime,'node_modules/@deepseek-ai/dsh/lib/bin.js')
  const version=JSON.parse(fs.readFileSync(path.join(runtime,'node_modules/@deepseek-ai/dsh/package.json'),'utf8')).version
  assert.equal(version,JSON.parse(fs.readFileSync(path.join(root,'dsh-runtime-compatibility.json'),'utf8')).preferredVersion)
  for(const file of [cli,hython,python])assert(file&&fs.existsSync(file),'Missing actual runtime executable: '+file)
  const outputRoot=values['output-root']?path.resolve(values['output-root']):os.tmpdir()
  fs.mkdirSync(outputRoot,{recursive:true})
  const run=fs.mkdtempSync(path.join(outputRoot,'dsh-isolated-tool-loop-'))
  const workspace=path.join(run,'workspace'),home=path.join(run,'home'),temp=path.join(run,'temp'),output=path.join(run,'report.json')
  for(const folder of [workspace,temp])fs.mkdirSync(folder)
  const sandboxMode=values['sandbox-mode']??'workspace-write'
  assert(['workspace-write','danger-full-access'].includes(sandboxMode),'Unsupported fixture sandbox mode')
  const pythonVersion=spawnSync(python,['--version'],{encoding:'utf8',windowsHide:true}).stdout.trim().replace(/^Python /,'')
  const houProbe=spawnSync(hython,['-c','import hou; print(hou.applicationVersionString())'],{encoding:'utf8',windowsHide:true,timeout:30000})
  assert.equal(houProbe.status,0,houProbe.stderr||'Cannot identify the explicit Houdini installation')
  const houdiniVersion=houProbe.stdout.trim().split(/\r?\n/).find(line=>/^\d+\.\d+\.\d+$/.test(line))
  assert(houdiniVersion,'Actual Houdini version was not returned')
  assert(/^3\.(11|13)\./.test(pythonVersion),'Use the selected supported Houdini Python runtime')
  const reserved=net.createServer();await new Promise((resolve,reject)=>{reserved.once('error',reject);reserved.listen(0,'127.0.0.1',resolve)})
  const bridgePort=reserved.address().port;await new Promise(resolve=>reserved.close(resolve))
  const executorRegistry=path.join(run,'executor-registry')
  const config={root,runtime,workspace,output,hfs,hython,python,pythonVersion,houdiniVersion,sandboxMode,bridgePort,executorRegistry}
  const configFile=path.join(run,'fixture.json');fs.writeFileSync(configFile,JSON.stringify(config,null,2))
  const env=Object.fromEntries(['PATH','Path','SystemRoot','WINDIR','USERPROFILE','APPDATA','LOCALAPPDATA','COMSPEC','PATHEXT'].filter(name=>process.env[name]!==undefined).map(name=>[name,process.env[name]]))
  Object.assign(env,{TEMP:temp,TMP:temp,DSH_HOME:home,DSH_ISOLATED_TOOL_FIXTURE:configFile,
    DSH_HOUDINI_BRIDGE_URL:'http://127.0.0.1:'+bridgePort,DSH_HOUDINI_EXECUTOR_REGISTRY:executorRegistry})
  const prepare=`import fs from 'node:fs';import path from 'node:path';import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';
const [bin,plugin]=process.argv.slice(1);const require=createRequire(bin);const boot=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')));
const profile=boot.resolveProfileDir('web');boot.initProfile(profile,[...boot.PROFILE_TEMPLATES.web.bundles,'dsh-houdini','@deepseek-ai/dsh-experimental-agent-team-profile'],boot.PROFILE_TEMPLATES.web.patchReload);
const link=path.join(profile,'node_modules/dsh-houdini');fs.mkdirSync(path.dirname(link),{recursive:true});fs.symlinkSync(plugin,link,'junction');
boot.loadProfile('dsh','web',path.join(path.dirname(path.dirname(bin)),'package.json'));`
  const prepared=spawnSync(process.execPath,['--input-type=module','-e',prepare,cli,root],{cwd:run,env,encoding:'utf8',windowsHide:true,timeout:60000})
  assert.equal(prepared.status,0,prepared.stderr||prepared.stdout)
  const fixture=fileURLToPath(new URL('./dsh-isolated-tool-loop-fixture.mjs',import.meta.url))
  const patch=path.join(run,'fixture.patch.yml')
  fs.writeFileSync(patch,'- id: session-title-llm\n  disabled: true\n- id: spill-local\n  config:\n    root: '+JSON.stringify(path.join(run,'spill').replaceAll('\\','/'))+'\n    cleanupPeriodDays: 0\n- insert:\n    - id: isolated-executor-host\n      name: dsh-houdini/executor-host\n      config:\n        executorRegistry: '+JSON.stringify(executorRegistry.replaceAll('\\','/'))+'\n    - id: isolated-tool-loop-fixture\n      name: '+JSON.stringify(fixture.replaceAll('\\','/'))+'\n')
  const logPath=path.join(run,'host.log'),log=fs.openSync(logPath,'w')
  const host=spawn(process.execPath,[cli,'web','--patch',patch,'--host','127.0.0.1','--port','0','--no-open'],{cwd:workspace,env,stdio:['ignore',log,log],windowsHide:true})
  let exited;host.on('exit',code=>{exited=code})
  console.log('Isolated Team integration evidence: '+run)
  try{
    const deadline=Date.now()+240000
    while(!fs.existsSync(output)&&exited===undefined&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,150))
    assert(fs.existsSync(output),'DSH fixture did not finish; inspect '+logPath)
    const result=JSON.parse(fs.readFileSync(output,'utf8'));assert(result.ok,result.error)
    assert.equal(result.realTeamChildren,1);assert(result.checks.length>=8)
    console.log(JSON.stringify({ok:true,report:output,checks:result.checks,boundary:result.boundary},null,2))
  }finally{
    if(exited===undefined){
      if(process.platform==='win32')spawnSync(path.join(process.env.SystemRoot??'C:/Windows','System32/taskkill.exe'),['/PID',String(host.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'})
      else host.kill('SIGTERM')
    }
    fs.closeSync(log)
  }
}
