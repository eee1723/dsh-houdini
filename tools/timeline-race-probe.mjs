// Run with an explicitly selected, disposable Rubik fixture. DSH credentials stay in its registry.
import fs from 'node:fs'
import path from 'node:path'
import {randomUUID} from 'node:crypto'
import {fileURLToPath,pathToFileURL} from 'node:url'
import {setTimeout as delay} from 'node:timers/promises'
import {HoudiniBridge} from '../lib/bridge.js'
import {ExecutorDirectory,registeredCredential} from '../lib/executor-routing.js'
import {createRun} from './output-artifacts.mjs'

export async function runTimelineProbe(triplet=false) {
  const [registry,executorId,repeat] = process.argv.slice(2)
  const iterations = Number(repeat ?? (triplet ? 40 : 120))
  if (!registry || !path.isAbsolute(registry) || !/^[0-9a-f]{32}$/.test(executorId ?? '')
      || !Number.isSafeInteger(iterations) || iterations <= 0)
    throw Error('Usage: node '+path.basename(process.argv[1])+' <absolute fixture registry> <executor id> [iterations]')
  const directory = new ExecutorDirectory(registry,fileURLToPath(new URL('../',import.meta.url)),true)
  const record = await directory.find(executorId)
  const credential = registeredCredential(registry,record)
  if (!credential || !record.workbench) throw Error('Select a paired workbench fixture')
  const bridge = new HoudiniBridge(record.bridge_url,120000,executorId,undefined,
    {runtimeId:record.runtime_id,sceneEpoch:record.scene_epoch},credential)
  const sessionId = 'timeline-probe-'+randomUUID()
  await bridge.claimWriter(sessionId,record.registration_id,record.hip_path)
  const run = await createRun({kind:'evidence',label:triplet?'timeline-triplet':'timeline-race'})
  const log = path.join(run.directory,'probe.log')
  const mark = text=>fs.appendFileSync(log,Date.now()+' '+text+'\n','utf8')
  console.log(run.directory)
  try {
    for (let index=0;index<iterations;index++) {
      const frames = triplet ? [1,46,240] : [[1,46,240][index%3]]
      const code = `before_frame = float(hou.frame())
items = []
for frame in ${JSON.stringify(frames)}:
    result = render_view('/obj/rubik/OUT', direction='iso', frame=frame, framing_frame=1,
        width=720, height=720, framing='full', output_policy='managed', picture='timeline.png')
    items.append({'frame':frame,'output':result['output'],'bytes':result['file_bytes'],'stale':result['stale']})
__result__ = {'before_frame':before_frame,'after_frame':float(hou.frame()),'items':items}`
      mark('before '+JSON.stringify(frames))
      const result = await bridge.exec(code,{sessionId,callId:'preview-'+index})
      if (!result.ok) throw Error(JSON.stringify({error:result.error,requestReceipt:result.requestReceipt}))
      mark('after '+JSON.stringify(result.result))
      await delay(100)
    }
  } catch(error) {
    mark('failed '+String(error))
    await run.finish('failed')
    throw error
  }
  await run.finish('success')
}

if (import.meta.url===pathToFileURL(process.argv[1]).href) await runTimelineProbe()
