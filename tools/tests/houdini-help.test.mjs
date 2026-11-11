import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import {Context} from '@deepseek-ai/cordis'
import LocalSubprocessRuntime from '@deepseek-ai/dsh-subprocess-local'
import {resolveHelpInstallation,readHoudiniHelp} from '../../lib/houdini-help.js'
import {registerHoudiniTools} from '../../lib/tools.js'

const root=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-help-host-'))
const installs=[{hfs:path.join(root,'H21'),version:'21.0.440'},{hfs:path.join(root,'H22'),version:'22.0.368'}]
let selected=null,inventory=installs,requests=[],runtimeReads=0,stateReads=0
const exec={agent:{id:'help-reader',session:{id:'help-reader'}},signal:new AbortController().signal}
const result={ok:true,result:{reference:'hom/hou/Node',text:'synthetic reference',source:{houdini_version:'21.0.440'}}}
const context={houdiniDesktop:{listInstallations:async()=>inventory},
  houdiniExecutorState:{stateOf:()=>{stateReads++;return {selectedTarget:selected}}},subprocess:{spawn(spec){requests.push(spec);return {
    done:Promise.resolve({exitCode:0}),terminate(){},waitForExit:async()=>true,
    collected:{stdout:{readFrom:()=>({text:JSON.stringify(result),lossy:false})},stderr:{readFrom:()=>({text:'',lossy:false})}},
  }}}}
context.get=name=>context[name]
const connection={resolve(){assert.fail('help must never resolve a live Bridge')},async resolveRuntime(){runtimeReads++;
  return {runtime:{hfs:installs[0].hfs,python:path.join(installs[0].hfs,'python311/python.exe')},houdiniVersion:'21.0.440'}}}
try{
  for(const [i,item] of installs.entries()){
    await fs.mkdir(path.join(item.hfs,i?'python313':'python311'),{recursive:true})
    await fs.writeFile(path.join(item.hfs,i?'python313/python.exe':'python311/python.exe'),'not executed by fake subprocess')
  }
  const ambiguous=await readHoudiniHelp(context,connection,{ref:'hom/hou/Node'},exec)
  assert.equal(ambiguous.ok,false);assert.equal(ambiguous.result.status,'ambiguous_installation')
  assert.equal(requests.length,0);assert.equal(runtimeReads,0)
  selected={executor_id:'selected'}
  const page=await readHoudiniHelp(context,connection,{ref:'hom/hou/Node'},exec)
  assert.equal(page.ok,true);assert.equal(page.result.installation_selection,'selected-runtime')
  assert.equal(runtimeReads,1);assert.equal(requests.length,1)
  assert.deepEqual(requests[0].argv.slice(1,6),['-I','-S','-B','-X','utf8'])
  assert.equal(JSON.parse(requests[0].stdio.stdin.data).version,'21.0.440')
  assert(!requests[0].argv.some(arg=>/hython|shell/i.test(arg)))
  const observedState=stateReads
  await readHoudiniHelp(context,connection,{ref:'vex/functions/noise',houdini_installation:installs[1].hfs},exec)
  assert.equal(runtimeReads,1,'explicit documentation version does not inspect or rebind the selected scene')
  assert.equal(stateReads,observedState,'explicit documentation does not require a scene projection')
  assert.equal(JSON.parse(requests[1].stdio.stdin.data).version,'22.0.368')
  await assert.rejects(()=>resolveHelpInstallation(context,connection,exec,root),/inventory/)
  inventory=[{...installs[0],version:'21.0.999'}]
  await assert.rejects(()=>resolveHelpInstallation(context,connection,exec),/changed build/)
  selected=null;inventory=[installs[1]]
  assert.equal((await resolveHelpInstallation(context,connection,exec)).selection,'sole-installation')
  inventory=[]
  assert.equal((await readHoudiniHelp(context,connection,{ref:'hom/hou/Node'},exec)).result.status,'installation_unavailable')
  inventory=installs
  await assert.rejects(()=>readHoudiniHelp(context,connection,{ref:'hom/hou/Node',limit:16001},exec),/limit/)
  const tools=new Map();registerHoudiniTools({...context,tools:{register:def=>tools.set(def.name,def)}},connection)
  const resource=tools.get('houdini_resource')
  assert(resource.parameters.properties.kind.enum.includes('help'))
  assert.equal((await resource.execute({kind:'help',ref:'hom/hou/Node',houdini_installation:installs[0].hfs},exec)).ok,true)
  await assert.rejects(()=>resource.execute({kind:'help',ref:'hom/hou/Node',pointer:'/text'},exec),/pointer/)
  await assert.rejects(()=>resource.execute({kind:'source',ref:'index',houdini_installation:installs[0].hfs},exec),/only used for help/)

  // The real Cordis plugin context refuses direct reads of absent undeclared
  // services. A fixed/developer Host need not compose the Desktop service:
  // public optional lookup must use the shared installation discovery there.
  const fixedHost=new Context();let fixedScope
  try {
    await fixedHost.plugin({name:'help-fixed-host-scope',apply(scope){fixedScope=scope}}).await()
    assert.equal(fixedScope.get('houdiniDesktop'),undefined)
    assert.throws(()=>fixedScope.houdiniDesktop,/without inject/)
    const discovered=await resolveHelpInstallation(fixedScope,connection,{signal:exec.signal})
    assert('ambiguous' in discovered||typeof discovered.hfs==='string')
    // When Desktop is provided, real scoped optional reads still work without
    // making that service a mandatory dependency of all Houdini tools.
    fixedHost.provide('houdiniDesktop',{listInstallations:async()=>[installs[0]]})
    const available=await resolveHelpInstallation(fixedScope,connection,exec,installs[0].hfs)
    assert.equal(available.version,'21.0.440')
    await assert.rejects(()=>readHoudiniHelp(fixedScope,connection,{ref:'hom/hou/Node',houdini_installation:installs[0].hfs},exec),/subprocess service is unavailable/)
  }finally{await fixedHost.fiber.dispose()}

  // Optional real installed archives, using the actual DSH process owner and
  // ordinary bundled Python. No Houdini process, socket, license or model.
  const hfss=[process.env.DSH_HELP_H21_HFS,process.env.DSH_HELP_H22_HFS].filter(Boolean)
  if(hfss.length){
    const host=new Context();await host.plugin(LocalSubprocessRuntime)
    try{
      for(const hfs of hfss){
        const version=hfs===process.env.DSH_HELP_H21_HFS?'21.0.440':'22.0.368'
        const ctx={get:name=>name==='subprocess'?host.subprocess:name==='houdiniDesktop'?{listInstallations:async()=>[{hfs,version}]}:undefined}
        for(const ref of ['hom/hou/Node','vex/functions/noise','nodes/sop/box']){
          const value=await readHoudiniHelp(ctx,connection,{ref,houdini_installation:hfs,limit:80},exec)
          assert.equal(value.ok,true,value.error);assert.equal(value.result.text.length,80)
          assert.equal(value.result.source.houdini_version,version)
          assert.equal(value.result.reference,ref)
          if(value.result.next){
            const next=await readHoudiniHelp(ctx,connection,value.result.next,exec)
            assert.equal(next.ok,true,next.error)
            assert.equal(next.result.source.sha256,value.result.source.sha256)
            assert.equal(next.result.offset,80)
          }
        }
      }
      console.log('Installed H21/H22 exact archive pages and continuation passed through native DSH subprocess')
    }finally{await host.fiber.dispose()}
  }
}finally{
  assert.equal(path.dirname(path.resolve(root)),path.resolve(os.tmpdir()))
  assert(path.basename(root).startsWith('dsh-help-host-'))
  await fs.rm(root,{recursive:true,force:true})
}
console.log('Houdini help: deterministic installation, strict resource namespace, bounded managed reader and no live route passed')
