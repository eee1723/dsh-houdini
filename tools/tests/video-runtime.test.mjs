import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {videoRuntime,resolveVideoRuntime,videoDiagnostics} from '../../lib/video-runtime.js'

const root=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-private-video-runtime-'))
try {
  const hfs=path.join(root,'Houdini'),python=path.join(hfs,'python311','python.exe')
  const options={packageRoot:root,environment:{HFS:hfs,PATH:'an-unrelated-global-runtime'},exists:filename=>filename===python}
  const automatic=videoRuntime('',options)
  assert.equal(automatic.python,python)
  assert.equal(automatic.pythonSource,'houdini')
  assert.equal(automatic.pythonScope,'host-launch','settings without a task only observe the Host launch environment')
  assert.equal(videoRuntime('python',options).python,python,'legacy default selects Houdini automatically')
  assert.equal(automatic.ffmpeg,path.join(root,'runtime','video','ffmpeg','bin','ffmpeg.exe'))
  assert.equal(automatic.ffprobe,path.join(root,'runtime','video','ffmpeg','bin','ffprobe.exe'))
  assert.equal(automatic.repair.kind,'source-private')
  assert.equal(videoRuntime('',{...options,environment:{HFS:hfs,DSH_HOUDINI_MANAGED_CONTEXT:'owned-context'}}).repair.kind,'managed-version')
  assert.equal(videoRuntime('',{...options,environment:{PATH:process.env.PATH}}).python,'','no global Python fallback')
  assert.throws(()=>videoRuntime('my-python',options),/绝对路径/)
  assert.equal(videoRuntime(process.execPath,options).python,process.execPath)
  assert.equal(videoRuntime(process.execPath,options).pythonScope,'explicit')
  const newer=path.join(hfs,'python313','python.exe')
  assert.equal(videoRuntime('',{...options,exists:()=>true}).python,newer)
  let inspections=0
  const executorId='a'.repeat(32),runtimeId='b'.repeat(32)
  const h22=path.join(root,'Houdini22'),h22Python=path.join(h22,'python313','python.exe')
  const selected={inspectExecutor:async()=>{inspections++;return {ok:true,executorId,runtimeId,houVersion:'22.0.368',
    runtime:{hfs:h22,python:h22Python,pythonVersion:'3.13.10',executable:path.join(h22,'bin','houdini.exe')}}}}
  for (const environment of [{PATH:process.env.PATH},{HFS:hfs}]) {
    const resolved=await resolveVideoRuntime('',{...options,environment,bridge:selected,exists:file=>file===h22Python})
    assert.equal(resolved.python,h22Python,'the selected H22 runtime wins over missing or H21 Host HFS')
    assert.equal(resolved.pythonScope,'selected-executor')
    assert.equal(resolved.hfs,h22)
    assert.equal(resolved.pythonVersion,'3.13.10')
    assert.equal(resolved.executorId,executorId)
    assert.equal(resolved.runtimeId,runtimeId)
  }
  const beforeOverride=inspections
  assert.equal((await resolveVideoRuntime(process.execPath,{...options,bridge:selected})).python,process.execPath)
  assert.equal(inspections,beforeOverride,'explicit Python needs no executor health request')
  await assert.rejects(resolveVideoRuntime('',{...options,bridge:{inspectExecutor:async()=>({ok:true})}}),/所选 Houdini 未提供/,
    'an old Bridge cannot fall back to the Host HFS')
  await assert.rejects(resolveVideoRuntime('',{...options,bridge:selected,exists:()=>false}),/所选 Houdini 的 Python 不存在/)
  const oldPython={inspectExecutor:async()=>({...await selected.inspectExecutor(),
    runtime:{hfs:h22,python:h22Python,pythonVersion:'3.10.1',executable:path.join(h22,'bin','hython.exe')}})}
  await assert.rejects(resolveVideoRuntime('',{...options,bridge:oldPython,exists:()=>true}),/需要 Python 3\.11/)
  await assert.rejects(resolveVideoRuntime('',{...options,bridge:{inspectExecutor:async()=>{throw Error('executor mismatch')}}}),/executor mismatch/)
  const diagnostics=await videoDiagnostics('',{packageRoot:root,environment:{},exists:()=>false})
  assert.equal(diagnostics.cloud_request,false)
  assert(diagnostics.dependencies.every(row=>row.available===false),'global dependencies cannot hide missing private tools')
  assert.match(diagnostics.dependencies[0].error,/Houdini/)
  assert.match(diagnostics.note,/没有任务执行器上下文/)
  assert.equal(diagnostics.runtime.pythonScope,'unavailable')
  assert.match(diagnostics.dependencies[1].error,/私有/)
  assert.equal(diagnostics.dependencies[1].path,automatic.ffmpeg)
  console.log('private tutorial runtime resolution and exact-command diagnostics passed')
} finally {
  assert.equal(path.dirname(root),path.resolve(os.tmpdir()))
  assert(path.basename(root).startsWith('dsh-private-video-runtime-'))
  await fs.rm(root,{recursive:true,force:true})
}
