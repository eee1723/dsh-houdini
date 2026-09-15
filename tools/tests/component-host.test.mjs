import assert from 'node:assert/strict'
import {EventEmitter} from 'node:events'
import {componentAuthorPrompt,componentStopOutcome,componentWorkerSnapshot,stopComponentWorker,
  completedTurnSequence,COMPONENT_IDLE_RELEASE_MS} from '../../lib/component-host.js'

const brief='Build a bounded wheel with a local visual check.'
const workspace='Z:\\project\\dsh-components\\child\\workspace'
const gui=componentAuthorPrompt(brief,true,workspace)
assert(gui.includes(`Parent component brief (check its interface and assumptions):\n${brief}`))
assert(gui.indexOf(brief)<gui.indexOf('Host closing constraints (authoritative after the parent brief)'))
assert.match(gui,/current HIP.*Host/)
assert.match(gui,/Authoritative workspace: "Z:\\\\project\\\\dsh-components\\\\child\\\\workspace"/)
assert.match(gui,/Authoritative current HIP: "Z:\\\\project\\\\dsh-components\\\\child\\\\workspace\\\\component\.hip"/)
assert.match(gui,/override every workspace, HIP or export-directory path stated in the parent brief/)
assert.match(gui,/\$HIP\/<name>\.dshcomponent.*ignore any parent-supplied absolute export path/)
assert.match(gui,/Report the exported artifact's full absolute path, sha256 and contract/)
assert.match(gui,/Give the parent the exact absolute filename returned by component_export/)
assert.match(gui,/scene_save\(\).*never Save As/)
assert.match(gui,/render_view.*inside houdini_exec/)
assert.match(gui,/component_delegate, component_status, component_wait and component_stop belong to the parent Host/)
assert.match(gui,/verb_help documents only those verbs, never top-level tools/)
assert.match(gui,/do not import a houdini_verbs module/)
assert.match(gui,/retain the preview as evidence/)
assert.match(gui,/Do not delete preview files with shell, os\.remove or allow_raw/)
assert.match(gui,/center_axis_surface_hits.*closed manifold/)
assert.match(gui,/argument binding reports an exact signature.*do not repeat a guessed signature/)
assert.match(gui,/Host closing constraints.*component_export.*\.dshcomponent, not bgeo\/FBX\/Alembic\/ROP output/s)
assert.match(gui,/node_info\(part,'circle',filter='radius'\)/)
assert.match(gui,/Do not traverse project\/install directories inside houdini_query or houdini_exec/)
assert.match(gui,/inspect its native image attachment/)
assert.match(gui,/cannot silently cancel an explicit visual or control obligation/)
const headless=componentAuthorPrompt(brief,false,workspace)
assert.match(headless,/headless.*render_view requires GUI.*render_frame.*visual unverified/)
assert(!headless.includes('render a bounded preview'))
assert.deepEqual(componentStopOutcome('a',{exited:true}),{
  childId:'a',stopped:true,ok:true,checkpoint:'saved',error:null,files_retained:true,
})
assert.deepEqual(componentStopOutcome('b',{exited:true,error:'idle checkpoint timed out'}),{
  childId:'b',stopped:true,ok:false,checkpoint:'unknown',error:'idle checkpoint timed out',files_retained:true,
})
assert.equal(componentStopOutcome('c',{exited:false}).checkpoint,'unknown')
const process=()=>{
  const proc=new EventEmitter()
  const writes=[]
  proc.stdin={end:value=>writes.push(value)}
  return {proc,writes}
}
{
  const {proc,writes}=process(),worker={process:proc,exited:false}
  proc.once('exit',()=>{worker.exited=true})
  const pending=stopComponentWorker(worker,100)
  assert.equal(stopComponentWorker(worker,100),pending,'a repeated stop cannot send another STOP')
  assert.deepEqual(writes,['STOP\n'])
  assert.equal(componentWorkerSnapshot(worker).workerStatus,'stopping')
  proc.emit('exit',0)
  await pending
  assert.equal(componentStopOutcome('normal',worker).checkpoint,'saved')
}
{
  const {proc,writes}=process(),worker={process:proc,exited:false,record:{}}
  proc.once('exit',()=>{worker.exited=true;worker.error=undefined})
  await assert.rejects(stopComponentWorker(worker,10),/checkpoint remains unknown/)
  assert.deepEqual(writes,['STOP\n'])
  assert.equal(componentWorkerSnapshot(worker).workerStatus,'stop_unknown')
  proc.emit('exit',0)
  assert.deepEqual(componentStopOutcome('late',worker),{
    childId:'late',stopped:true,ok:false,checkpoint:'unknown',
    error:'Component supervisor has not exited; checkpoint remains unknown',files_retained:true,
  })
  await assert.rejects(stopComponentWorker(worker,10),/checkpoint remains unknown/)
  assert.deepEqual(writes,['STOP\n'])
}
{
  const {proc}=process(),worker={process:proc,exited:false}
  proc.stdin.end=()=>{throw Error('broken stdin')}
  await assert.rejects(stopComponentWorker(worker,100),/broken stdin/)
  assert.equal(componentWorkerSnapshot(worker).checkpoint,'unknown')
  assert.match(componentStopOutcome('broken',worker).error,/broken stdin/)
}
assert.equal(COMPONENT_IDLE_RELEASE_MS,30_000)
assert.equal(completedTurnSequence([{type:'turn/end',seq:8,data:{reason:{kind:'completed'}}}]),8)
assert.equal(completedTurnSequence([{type:'turn/end',seq:8,data:{reason:{kind:'completed'}}},
  {type:'turn/start',seq:9,data:{}}]),undefined)
assert.equal(completedTurnSequence([{type:'turn/end',seq:8,data:{reason:{kind:'interrupted'}}}]),undefined)
console.log('component author Host facts distinguish verb/tool, HIP and visual obligations')
