import assert from 'node:assert/strict'
import {EventEmitter} from 'node:events'
import {componentAuthorPrompt,componentInfraReport,componentStopOutcome,componentWorkerSnapshot,infraReportCause,
  infraReportDelivery,stopComponentWorker,completedTurnSequence,COMPONENT_IDLE_RELEASE_MS} from '../../lib/component-host.js'

const brief='Build a bounded wheel with a local visual check.'
const gui=componentAuthorPrompt(brief,true)
assert(gui.endsWith(brief))
assert.match(gui,/current HIP.*Host/)
assert.match(gui,/scene_save\(\).*never Save As/)
assert.match(gui,/render_view.*inside houdini_exec/)
assert.match(gui,/Do not traverse project\/install directories inside houdini_query or houdini_exec/)
assert.match(gui,/inspect its native image attachment/)
assert.match(gui,/cannot silently cancel an explicit visual or control obligation/)
const headless=componentAuthorPrompt(brief,false)
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
{
  const ready={exited:false,record:{executor_id:'w1'},workspace:'/asm/dsh-components/c1/workspace'}
  assert.equal(infraReportCause(ready),undefined,'a healthy ready worker has no report cause')
  assert.equal(componentInfraReport('c1',ready),undefined)
  assert.equal(infraReportCause({exited:true,error:'boom'}),undefined,'pre-readiness failure reaches the parent synchronously')
  assert.equal(infraReportCause({exited:true,record:{},stopRequested:true}),undefined,'requested stops are known to the parent')
  const crashed={exited:true,record:{},workspace:'/asm/dsh-components/c1/workspace',error:'Worker exited (1): oom'}
  const report=componentInfraReport('c1',crashed)
  assert.match(report,/child c1.*dsh-components\/c1\/workspace/)
  assert.match(report,/workerStatus=stopped, checkpoint=unknown/)
  assert.match(report,/Worker exited \(1\): oom/)
  assert.match(report,/not a verified delivery/)
  assert.match(report,/delegate a revision/)
  const silent={exited:true,record:{},workspace:'/asm/dsh-components/c2/workspace'}
  assert.match(componentInfraReport('c2',silent),/checkpoint=saved/,'clean exit keeps its saved-checkpoint account')
  assert.match(componentInfraReport('c2',silent),/without a stop request/)
  const stuck={exited:false,record:{},workspace:'/asm/dsh-components/c3/workspace',error:'stdin broken'}
  assert.match(componentInfraReport('c3',stuck),/workerStatus=ready, checkpoint=unknown/)
  assert.equal(infraReportDelivery('idle'),'followup')
  assert.equal(infraReportDelivery('running'),'steer')
}
console.log('component author Host facts distinguish verb/tool, HIP and visual obligations')
