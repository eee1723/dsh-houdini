import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {randomUUID,randomBytes} from 'node:crypto'
import {fileURLToPath} from 'node:url'
import {writeBridgeCredential} from './fixture-bridge.mjs'

// Media fixture servers stand in for one explicitly selected Houdini. Publish
// them only in the test Host's private registry, using the Desktop contract.
export async function mediaTarget(ctx, {runtimeId, hip, workspace, houdiniVersion, runtime}) {
  const executorId=process.env.DSH_HOUDINI_EXECUTOR_ID
  const registrationId=randomUUID().replaceAll('-',''), sceneEpoch=randomUUID().replaceAll('-','')
  const registry=path.join(process.env.DSH_HOME,'dsh-houdini','executors')
  assert.equal(path.resolve(ctx.houdiniTargets.registry),path.resolve(registry))
  const record={schema:1,executor_id:executorId,registration_id:registrationId,runtime_id:runtimeId,
    installation:fileURLToPath(new URL('../../',import.meta.url)),bridge_auth:'bearer-v1',bridge_url:process.env.DSH_HOUDINI_BRIDGE_URL,
    houdini_version:houdiniVersion,pid:process.pid,state:'registered',task_id:null,hip_path:hip,hip_is_new:false,
    workbench:true,scene_id:randomUUID().replaceAll('-',''),scene_epoch:sceneEpoch,workspace_path:workspace,
    ...(runtime ? {runtime} : {})}
  const file=path.join(registry,'endpoints',executorId+'.json')
  function publish(hipPath) {
    record.hip_path=hipPath
    fs.mkdirSync(path.dirname(file),{recursive:true})
    fs.writeFileSync(file+'.tmp',JSON.stringify(record))
    fs.renameSync(file+'.tmp',file)
  }
  const token=randomBytes(32).toString('hex')
  await writeBridgeCredential(registry,record,token)
  publish(hip)
  return {
    health:{executorId,runtimeId,sceneEpoch,houVersion:houdiniVersion},
    accepts:request=>request.headers.authorization==='Bearer '+token&&request.headers['x-dsh-houdini-executor']===executorId,
    select:sessionId=>ctx.houdiniTargets.select({sessionId,executorId,registrationId,
      expectedHip:record.hip_path,runtimeId,sceneEpoch},AbortSignal.timeout(5000)),
    publish,
  }
}
