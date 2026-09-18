// Deterministic model boundary for the actual DSH/provider/worker composition.
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import {createHash} from 'node:crypto'
import {createRequire} from 'node:module'
export const inject=['llm','agents']
export function apply(ctx) {
  let childRequests=0
  const expectChildFailure=process.env.DSH_COMPONENT_EXPECT_CHILD_FAILURE==='1'
  const expectStartupFailure=process.env.DSH_COMPONENT_EXPECT_STARTUP_FAILURE==='1'
  const expectStopFailure=process.env.DSH_COMPONENT_EXPECT_STOP_FAILURE==='1'
  const expectRejection=process.env.DSH_COMPONENT_EXPECT_REJECTION==='1'
  const expectAdapterThrow=process.env.DSH_COMPONENT_EXPECT_ADAPTER_THROW==='1'
  const expectProcessExit=process.env.DSH_COMPONENT_EXPECT_WORKER_PROCESS_EXIT==='1'
  const expectBuiltExit=process.env.DSH_COMPONENT_EXPECT_BUILT_EXIT==='1'
  // Whether the PREVIOUS parent turn returned synthetic tool calls. The
  // built-exit drill uses it to prove the kill happens on an idle parent turn
  // and that the infrastructure notice - not a fixture tool-call chain - woke
  // the parent into the checkpoint inspection.
  let lastParentHadToolCall=false
  // Captured when the built-exit drill issues its checkpoint inspection:
  // the wake is proven by the fact that the kill turn ended with plain text
  // and the infrastructure notice - not a fixture tool-call chain - provoked
  // the next request.
  let builtExitWake=null
  // Monotonic parent-turn identifier: recorded into the idle marker and the
  // built-exit report so the causal chain (idle turn -> driver kill ->
  // infrastructure notice -> NEW parent turn -> status check) carries real
  // turn ids instead of conventions.
  let parentTurnNo=0
  // R6: record which DSH runtime modules this composition ACTUALLY loaded, so a
  // negative result can never be explained by an unexpected module source.
  const requireFromHost=createRequire(process.argv[1]||import.meta.url)
  let moduleSource
  try {
    const subagentPkg=requireFromHost.resolve('@deepseek-ai/dsh-subagent/package.json')
    moduleSource={subagent:subagentPkg,version:JSON.parse(fs.readFileSync(subagentPkg,'utf8')).version,
      executable:process.execPath,pid:process.pid,cli:process.argv[1]||null}
  }catch(error){moduleSource={resolutionError:String(error).slice(0,400),cli:process.argv[1]||null}}
  try{
    // The dsh-houdini plugin is loaded from the isolated profile's node_modules
    // junction (prepared by prepare-shared-host-fixture.mjs), not from the CLI's
    // own require stack - resolve it there.
    const profileNodeModules=path.join(process.env.DSH_HOME,'profiles/web/node_modules')
    const hostPkg=path.join(profileNodeModules,'dsh-houdini/package.json')
    const hostRoot=path.dirname(hostPkg)
    let hostContract=null
    try{
      const built=fs.readFileSync(path.join(hostRoot,'lib','generated-verb-contract.js'),'utf8')
      const match=built.match(/EXPECTED_EXECUTION_CONTRACT_VERSION\s*=\s*(\d+)/)
      hostContract=match?Number(match[1]):null
    }catch(error){}
    moduleSource={...moduleSource,host:{package:hostPkg,
      version:JSON.parse(fs.readFileSync(hostPkg,'utf8')).version,hostContractVersion:hostContract}}
  }catch(error){moduleSource={...moduleSource,host:{resolutionError:String(error).slice(0,400)}}}
  fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'module-source.json'),JSON.stringify(moduleSource,null,2))
  ctx.on('agent/disposed',({agent})=>{
    if(process.env.DSH_COMPONENT_EXPECT_REJECTION==='1'&&agent.session.header.parentSession){
      assert.equal(childRequests,0)
      // R6: pin the ACTUAL refusal cause. Walk the parent session's events and
      // keep every delegate-shaped failure so the negative result cannot be
      // explained by cwd, permissions or preparation problems instead.
      const events=agent.session.snapshotEvents().slice(-14).map(e=>({
        type:e.type,name:e.data?.name??null,
        detail:String(JSON.stringify(e.data)?.slice(0,420)??'')}))
      fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'rejected.json'),JSON.stringify({
        rejected:true,childRequests,events},null,2))
    }
  })
  class Fixture extends LlmAdapter {
    async resolveModel(provider,model){return {provider,id:model,name:'Component fixture',inputModalities:['text'],context:{contextWindow:500000}}}
    async *stream(options){
      const agent=ctx.agents.get(options.sessionId)
      let blocks=[]
      if(options.purpose||!agent){blocks=[{type:'text',text:'Component fixture'}]}
      else if(agent.session.header.parentSession){
        childRequests++
        const promptText=options.messages.flatMap(message=>message.content
          .filter(block=>block.type==='text').map(block=>block.text)).join('\n')
        const failingAuthor=expectChildFailure&&promptText.includes('Fixture part 0:')
        assert(agent.session.header.cwd.startsWith(process.env.DSH_COMPONENT_TEST_WORKERS))
        assert(promptText.includes('render_view is a Houdini verb called inside houdini_exec'),
          'Host execution facts must reach the child before its first model request')
        assert(promptText.includes(`Authoritative workspace: ${JSON.stringify(agent.session.header.cwd)}`),
          'Host must inject the allocated child workspace before the parent-authored brief')
        assert(promptText.includes(`Authoritative current HIP: ${JSON.stringify(path.join(agent.session.header.cwd,'component.hip'))}`),
          'Host must inject the exact fixed child HIP before the parent-authored brief')
        assert(promptText.includes('These Host facts override every workspace, HIP or export-directory path stated in the parent brief'))
        assert(promptText.includes('Z:\\wrong-parent-path\\component.hip'),
          'the negative control must retain the parent-authored fake path as untrusted brief text')
        assert(agent.session.snapshotEvents().some(e=>e.type==='user/message'&&e.data.source?.plugin==='dsh-houdini'
          &&e.data.source.sections?.some(s=>s.name==='dsh-houdini:executor-binding')))
        const results=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'))
        for(const result of results){
          if(result.toolCallId==='outside-write')assert(result.isError, 'child wrote outside its workspace')
          else if(failingAuthor&&result.toolCallId==='component-export')
            assert.match(result.content.filter(c=>c.type==='text').map(c=>c.text).join('\n'),
              /Execution failed:[\s\S]*missing\/ambiguous\/unconnected public output 1/)
          else assert(!result.isError,JSON.stringify(result))
        }
        if(expectAdapterThrow&&promptText.includes('Fixture part 0:')&&results.some(r=>r.toolCallId==='component-build')){
          // The fixture's model adapter throws INSIDE the child session after
          // readiness and a real build. This is an adapter-level failure, not a
          // worker process exit: the child process keeps running. The real
          // process-exit drill lives in --expect-worker-process-exit.
          throw new Error('injected adapter throw after readiness and build')
        }
        if(!results.length){
          blocks=[{type:'tool-call',id:'inside-write',name:'write',arguments:JSON.stringify({file_path:'local.txt',content:'local fixture'})},
            {type:'tool-call',id:'outside-write',name:'write',arguments:JSON.stringify({file_path:path.join(process.env.DSH_COMPONENT_TEST_OUT,'forbidden-'+agent.id+'.txt'),content:'must not be written'})}]
        }else if(!results.some(r=>r.toolCallId==='component-build')){
          assert(fs.existsSync(path.join(agent.session.header.cwd,'local.txt')))
          assert(!fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'forbidden-'+agent.id+'.txt')))
          const filename=path.join(agent.session.header.cwd,'part.dshcomponent')
          let code="g=tab_create('/obj','geo','component')\ns=tab_create(g,'subnet','part')\n"
            +"create_spare_parms(s,layout=[{'type':'float','name':'width','default':1}])\n"
            +"b=tab_create(s,'box','shape')\nset_parms(b,{'sizex':'ch(\"../width\")'})\n"
            +"detail=tab_create(s,'polybevel','bevel',inputs=[b])\nsop_set_output(detail,output_index=0)\n"
          const deferExport=expectBuiltExit&&promptText.includes('Fixture part 0:')
          code+=(failingAuthor||deferExport)?"scene_save()\n__result__={'modeled':True,'exported':False}"
            :`__result__=component_export(s,${JSON.stringify(filename)},{'module_id':'part','revision':1,'units':'m','outputs':[0]})`
          blocks=[{type:'tool-call',id:'component-build',name:'houdini_exec',arguments:JSON.stringify({code})}]
        }else if(expectBuiltExit&&promptText.includes('Fixture part 0:')&&!results.some(r=>r.toolCallId==='built-marker')){
          // R6 built-exit drill: this child BUILDS and saves its HIP but never
          // exports; its worker stays alive until the parent-side drill kills
          // the process while the parent is idle.
          assert(fs.existsSync(path.join(agent.session.header.cwd,'component.hip')),
            'the built HIP must be saved before the built-exit drill defers the export')
          try{fs.appendFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'built-exit-trace.jsonl'),
            JSON.stringify({child:agent.id,branch:'marker'})+'\n')}catch(_){}
          blocks=[{type:'tool-call',id:'built-marker',name:'write',arguments:JSON.stringify({file_path:'built.marker',content:'built; export deferred by the drill'})}]
        }else if(expectBuiltExit&&results.some(r=>r.toolCallId==='built-marker')){
          // R6 built-exit drill: built, saved, NOT exported and NOT ENDED.
          // The child parks at a deterministic synchronous hold point: a real
          // tool call that sleeps briefly (far below any request timeout) and
          // reports whether a release file appeared; the adapter re-issues the
          // hold for as long as the release never comes. The child therefore
          // stays mid-turn at a known state until the TEST DRIVER verifies the
          // worker's registry identity and terminates the process. The kill
          // never happens inside a parent model turn.
          const holdWorkspace=agent.session.header.cwd
          assert(fs.existsSync(path.join(holdWorkspace,'component.hip')),'the built HIP must exist at the hold point')
          assert(fs.existsSync(path.join(holdWorkspace,'built.marker')),'the built marker must exist at the hold point')
          assert(!fs.existsSync(path.join(holdWorkspace,'part.dshcomponent')),'nothing may export before the hold point')
          fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'built-hold.json'),
            JSON.stringify({child:agent.id,workspace:holdWorkspace,holdCall:'built-hold',releaseFile:'built-exit-release'}))
          const release=path.join(holdWorkspace,'built-exit-release').replace(/\\/g,'/')
          const code="import time,os\ntime.sleep(5)\n__result__={'released':os.path.exists('"+release+"')}"
          try{fs.appendFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'built-exit-trace.jsonl'),
            JSON.stringify({child:agent.id,branch:'hold-reissue'})+'\n')}catch(_){}
          blocks=[{type:'tool-call',id:'built-hold',name:'houdini_exec',arguments:JSON.stringify({code})}]
        }else if(failingAuthor&&!results.some(r=>r.toolCallId==='component-export')){
          assert(fs.existsSync(path.join(agent.session.header.cwd,'component.hip')),
            'the modeled HIP must be saved before exchange failure injection')
          const filename=path.join(agent.session.header.cwd,'part.dshcomponent')
          const code=`__result__=component_export('/obj/component/part',${JSON.stringify(filename)},{'module_id':'part','revision':1,'units':'m','outputs':[1]})`
          blocks=[{type:'tool-call',id:'component-export',name:'houdini_exec',arguments:JSON.stringify({code})}]
        }else if(failingAuthor){
          assert(!fs.existsSync(path.join(agent.session.header.cwd,'part.dshcomponent')),
            'failed exchange cannot publish a component artifact')
          blocks=[{type:'text',text:'Component exchange blocked at component_export: missing/ambiguous/unconnected public output 1. Modeled HIP retained; artifact and visual acceptance unverified. Do not import or rebuild this component.'}]
        }else{
          assert(fs.existsSync(path.join(agent.session.header.cwd,'part.dshcomponent')))
          fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,agent.id+'.json'),JSON.stringify({child:agent.id,cwd:agent.session.header.cwd,passed:true}))
          blocks=[{type:'text',text:'Component candidate exported; assembly remains unverified.'}]
        }
      }else{
        parentTurnNo+=1
        if(expectRejection&&!fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'rejection-reason.json'))){
          const failed=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.isError))
          if(failed.length){
            const reason=failed.map(r=>r.content.filter(c=>c.type==='text').map(c=>c.text).join('|')).join(' | ')
            fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'rejection-reason.json'),
              JSON.stringify({reason:reason.slice(0,2000),childRequests}))
          }
        }
        const autoRelease=process.env.DSH_COMPONENT_EXPECT_AUTO_RELEASE==='1'
        const checked=agent.session.snapshotEvents().some(e=>e.type==='tool/call'&&e.data.name==='component_status')
        const called=agent.session.snapshotEvents().some(e=>e.type==='tool/call'&&e.data.name==='component_delegate')
        const waited=agent.session.snapshotEvents().some(e=>e.type==='tool/call'&&e.data.name==='component_wait')
        // Drive assembly from the native child settlement notices actually
        // visible to the parent's model. Artifact existence is only checked
        // after both authors have reported; it is not a completion signal.
        const modelText=options.messages.flatMap(m=>m.content.filter(c=>c.type==='text').map(c=>c.text)).join('\n')
        const notices=[...modelText.matchAll(/Background subagent ([0-9a-f-]{36}) (finished and will do no further work|was stopped|ran out of room|declined the task|failed before it finished|ended abnormally)/g)]
        const settled=new Set(notices.filter(match=>match[2]==='finished and will do no further work').map(match=>match[1]))
        if(checked&&!called){
          const status=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId==='capacity')).at(-1)
          assert(status&&!status.isError,
            'read-only capacity must return a worker snapshot')
          assert(!fs.existsSync(process.env.DSH_COMPONENT_TEST_WORKERS),
            'capacity inspection must not start a worker or create its root')
        }
        if(waited){
          const waitResult=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId==='component-wait')).at(-1)
          if(waitResult){
            assert(!waitResult.isError,'component_wait must remain an API-level bounded wait')
            const value=JSON.parse(waitResult.content.find(c=>c.type==='text').text)
            assert.equal(typeof value.changed,'boolean')
            assert.equal(typeof value.timedOut,'boolean')
            assert(value.waitedMs>=0&&value.waitedMs<=2000,value)
          }
        }
        const assembly=agent.session.snapshotEvents().some(e=>e.type==='tool/call'&&e.data.name==='houdini_exec')
        {
          const turnLog=path.join(process.env.DSH_COMPONENT_TEST_OUT,'parent-turns.json')
          try{
            const turns=fs.existsSync(turnLog)?JSON.parse(fs.readFileSync(turnLog,'utf8')):[]
            if(turns.length<14)turns.push({turn:turns.length+1,childRequests,
              notices:notices.map(n=>n[2]),modelTextTail:modelText.slice(-500)})
            fs.writeFileSync(turnLog,JSON.stringify(turns,null,2))
          }catch(error){}
        }
        if(expectAdapterThrow){
          const throwNotice=notices.find(match=>match[2]==='failed before it finished'||match[2]==='ended abnormally')
          const throwEvents=throwNotice?agent.session.snapshotEvents().filter(e=>e.type==='user/message'
            &&JSON.stringify(e.data??{}).includes(throwNotice[0])):[]
          if(throwNotice&&!fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'adapter-throw.json'))){
            // The throw is bound to the exact childId the notice names: that
            // child finished authoring, so its built HIP and its exported
            // artifact are RETAINED, the other child owns its artifact too,
            // and the failed child's worker PROCESS is still alive - an
            // adapter throw is not a process exit.
            const failedChild=throwNotice[1]
            const survivorFiles=fs.readdirSync(process.env.DSH_COMPONENT_TEST_OUT)
              .filter(f=>/^[0-9a-f-]{36}\.json$/.test(f))
            if(survivorFiles.length===1){
              const survivorChild=JSON.parse(fs.readFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,survivorFiles[0]))).child
              const failedWorkspace=path.join(process.env.DSH_COMPONENT_TEST_WORKERS,failedChild,'workspace')
              const endpoints=path.join(process.env.DSH_HOUDINI_EXECUTOR_REGISTRY,'endpoints')
              const failedRecord=fs.readdirSync(endpoints).filter(f=>f.endsWith('.json'))
                .map(f=>JSON.parse(fs.readFileSync(path.join(endpoints,f),'utf8'))).find(r=>r.task_id===failedChild)
              let workerAlive=null
              if(failedRecord&&Number.isInteger(failedRecord.pid)){
                try{process.kill(failedRecord.pid,0);workerAlive=true}
                catch(error){workerAlive=error.code!=='ESRCH'}
              }
              const report={notice:throwNotice[0],outcome:throwNotice[2],failedChild,survivorChild,
                childRequests,assembled:assembly,
                artifacts:{failedHip:fs.existsSync(path.join(failedWorkspace,'component.hip')),
                  failedArtifact:fs.existsSync(path.join(failedWorkspace,'part.dshcomponent')),
                  survivorArtifact:fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_WORKERS,survivorChild,'workspace','part.dshcomponent'))},
                workerStillAlive:workerAlive,
                sessionEvents:throwEvents.slice(-2).map(e=>({type:e.type,source:e.data?.source?.plugin??null}))}
              // The throw fires after the failed child finished authoring and
              // exporting: its artifact is legitimately RETAINED, the failure
              // hit the model boundary only, and the worker process keeps
              // running - an adapter throw is not a process exit.
              assert(report.artifacts.failedHip,'the failed child must keep its built HIP')
              assert(report.artifacts.failedArtifact,'the failed child finished authoring; its artifact must be retained')
              assert(report.artifacts.survivorArtifact,'the surviving child must own its artifact')
              assert(workerAlive===true,'an adapter throw must NOT stop the worker process')
              assert(!assembly,'assembly must not run after an adapter throw')
              fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'adapter-throw.json'),JSON.stringify(report,null,2))
              blocks=[{type:'text',text:'Adapter throw confirmed for the named child: its built HIP and exported artifact are retained, the surviving child owns its artifact too, and the failed worker process is still running. No assembly was attempted.'}]
            }
          }
        }else if(expectProcessExit||expectBuiltExit){
          // A killed worker surfaces as the killed child's native failure
          // notice on top of the settlements (built-exit: the child dies
          // mid-hold, so its failure is NOT a settlement); uniqueness is
          // asserted only for the plain positive run
        }else{
          assert.equal(settled.size,notices.length,'each visible child settlement must be unique and completed')
        }
        const startupResult=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId==='delegate-0')).at(-1)
        if(expectStartupFailure&&startupResult){
          assert(startupResult.isError,'missing worker executable must reject before child admission')
          const error=startupResult.content.filter(c=>c.type==='text').map(c=>c.text).join('\n')
          assert.match(error,/ENOENT|not found|cannot find/i)
          assert.equal(childRequests,0,'failed startup must not request a child model')
          assert(!assembly,'failed startup must not mutate assembly')
          fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'startup-blocked.json'),JSON.stringify({
            error:error.slice(0,1000),childRequests,assembly:false}))
          blocks=[{type:'text',text:`Component startup blocked: ${error.slice(0,300)}. No child was admitted or assembly attempted; check the configured worker executable before retrying.`}]
        }else if(expectStopFailure&&settled.size===2&&!assembly){
          const failedChild=[...settled].sort()[0],survivingChild=[...settled].sort()[1]
          const readyFile=path.join(process.env.DSH_COMPONENT_TEST_OUT,'stop-ready.json')
          if(!fs.existsSync(readyFile)){
            assert(fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,failedChild+'.json')))
            assert(fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,survivingChild+'.json')))
            fs.writeFileSync(readyFile,JSON.stringify({failedChild,survivingChild}))
            blocks=[{type:'text',text:'Both component artifacts are retained. Awaiting the isolated worker-stop fault injection before checkpoint inspection.'}]
          }else{
            const statusResult=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId==='stop-fault-status')).at(-1)
            const stopResults=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId.startsWith('stop-fault-child-')))
            if(!statusResult)blocks=[{type:'tool-call',id:'stop-fault-status',name:'component_status',arguments:'{}'}]
            else if(!stopResults.length){
              assert(!statusResult.isError)
              const status=JSON.parse(statusResult.content.find(c=>c.type==='text').text)
              assert.match(status.observation,/Disk size or mtime does not reveal the live unsaved Houdini scene/)
              assert(status.children.every(child=>child.liveSceneState==='unobserved'
                &&child.hipPath===path.join(child.workspace,'component.hip')))
              const failed=status.children.find(child=>child.childId===failedChild)
              const surviving=status.children.find(child=>child.childId===survivingChild)
              assert.equal(failed.workerStatus,'stopped')
              assert.equal(failed.checkpoint,'unknown')
              assert.equal(surviving.workerStatus,'ready')
              blocks=[failedChild,survivingChild].map((childId,i)=>({type:'tool-call',id:'stop-fault-child-'+i,
                name:'component_stop',arguments:JSON.stringify({childId})}))
            }else{
              assert.equal(stopResults.length,2)
              assert(stopResults.every(result=>!result.isError))
              const outcomes=stopResults.map(result=>JSON.parse(result.content.find(c=>c.type==='text').text))
              const failed=outcomes.find(result=>result.childId===failedChild)
              const surviving=outcomes.find(result=>result.childId===survivingChild)
              assert.deepEqual({stopped:failed.stopped,ok:failed.ok,checkpoint:failed.checkpoint},
                {stopped:true,ok:false,checkpoint:'unknown'})
              assert.match(failed.error,/exited unexpectedly|Worker exited/i)
              assert.deepEqual({stopped:surviving.stopped,ok:surviving.ok,checkpoint:surviving.checkpoint},
                {stopped:true,ok:true,checkpoint:'saved'})
              fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'stop-unknown.json'),JSON.stringify({failed,surviving,assembly:false}))
              blocks=[{type:'text',text:'One owned worker exited unexpectedly: its checkpoint is unknown and its files are retained. The other worker stopped with a saved checkpoint. Assembly was not attempted.'}]
            }
          }
        }else if(expectBuiltExit&&!assembly&&called){
          // R6: REAL worker exit while the child is BUILT, SAVED, NOT
          // exported and NOT ended, and the parent task is IDLE. The fixture
          // never kills: it parks the built child at a synchronous hold
          // point and records every idle parent turn; the TEST DRIVER - the
          // Python loop test, outside any model turn - verifies the worker's
          // registry-bound identity and terminates the process. The fixture
          // then requires the infrastructure report to wake the idle parent
          // as an actual session event, the childId-bound status snapshot,
          // and the two children's distinct fates - with no replacement
          // dispatch and no assembly.
          const outDir=process.env.DSH_COMPONENT_TEST_OUT
          const killLog=path.join(outDir,'built-exit-kill.json')
          const statusResult=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId==='built-exit-status')).at(-1)
          try{fs.appendFileSync(path.join(outDir,'built-exit-trace.jsonl'),JSON.stringify({turn:parentTurnNo,killLog:fs.existsSync(killLog),statusResult:!!statusResult,statusError:statusResult?statusResult.isError:null,settled:settled.size,notices:notices.length,called,assembly})+'\n')}catch(_){}
          if(!fs.existsSync(killLog)){
            // Idle arm turn: this parent turn ends with plain text and no
            // synthetic call outstanding. The marker (with the real turn id)
            // is what the driver observes before performing the kill; the
            // kill itself is driver-owned and never runs inside a model turn.
            fs.writeFileSync(path.join(outDir,'parent-idle.json'),JSON.stringify({
              turn:parentTurnNo,childRequests,endedTextOnly:true,
              outstandingSyntheticCalls:false,prevTurnHadToolCall:lastParentHadToolCall,
              note:'this parent turn ends text-only (the arm text below is its only block); the driver kills outside any model turn'}))
            blocks=[{type:'text',text:'Arming the built-exit drill: the built-but-not-exported child is holding at its sync point and this parent turn stays idle until the test driver acts.'}]
          }else if(statusResult){
            try{
            assert(!statusResult.isError,JSON.stringify(statusResult))
            const status=JSON.parse(statusResult.content.find(c=>c.type==='text').text)
            const kill=JSON.parse(fs.readFileSync(killLog,'utf8'))
            const failed=status.children.find(c=>c.childId===kill.builtChild)
            const surviving=status.children.filter(c=>c.childId!==kill.builtChild)
            assert(failed,'the killed childId must appear in the status snapshot: '+JSON.stringify(status).slice(0,400))
            assert.equal(failed.workerStatus,'stopped')
            assert.equal(failed.checkpoint,'unknown')
            assert(surviving.length===1&&surviving[0].workerStatus==='ready',
              'the surviving child must stay ready: '+JSON.stringify(surviving))
            const events=agent.session.snapshotEvents()
            const noticeEvents=events.map((e,i)=>({e,i})).filter(x=>x.e.type==='user/message'
              &&x.e.data?.source?.plugin==='dsh-houdini'&&x.e.data?.source?.form==='notice'
              &&JSON.stringify(x.e.data).includes(kill.builtChild))
            const noticeIndex=noticeEvents.length?noticeEvents[noticeEvents.length-1].i:-1
            const noticeData=noticeIndex>=0?events[noticeIndex].data??{}:{}
            const statusCalls=events.map((e,i)=>({e,i})).filter(x=>x.e.type==='tool/call'&&x.e.data?.name==='component_status')
            const statusCallIndex=statusCalls.length?statusCalls[statusCalls.length-1].i:-1
            assert(noticeIndex>=0,'the infrastructure report must exist as an actual session event')
            assert(statusCallIndex>noticeIndex,'the parent may only inspect after the notice woke it: notice -> status call')
            const delegateCalls=events.filter(e=>e.type==='tool/call'&&e.data?.name==='component_delegate').length
            const builtWorkspace=path.join(process.env.DSH_COMPONENT_TEST_WORKERS,kill.builtChild,'workspace')
            const survivorChild=surviving[0].childId
            const report={builtChild:kill.builtChild,pid:kill.pid,killError:kill.killError,pidDead:kill.pidDead,
              killBy:kill.killBy,parentIdle:kill.preKill.parentIdle,turnOfStatusCall:parentTurnNo,
              infraEvent:{source:noticeData.source??null,text:JSON.stringify(noticeData).slice(0,500)},
              wake:{noticeEventIndex:noticeIndex,statusCallIndex,...(builtExitWake??{})},
              status:{failed,surviving:surviving[0]},
              artifacts:{builtHip:fs.existsSync(path.join(builtWorkspace,'component.hip')),
                builtMarker:fs.existsSync(path.join(builtWorkspace,'built.marker')),
                failedArtifact:fs.existsSync(path.join(builtWorkspace,'part.dshcomponent')),
                survivorArtifact:fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_WORKERS,survivorChild,'workspace','part.dshcomponent'))},
              delegateCalls,assembly,
              eventOrder:events.slice(Math.max(0,noticeIndex-2),statusCallIndex+1)
                .map((e,i)=>({index:Math.max(0,noticeIndex-2)+i,type:e.type,name:e.data?.name??null,plugin:e.data?.source?.plugin??null}))}
            assert(report.artifacts.builtHip&&report.artifacts.builtMarker,'the built-not-exported state must be preserved')
            assert(!report.artifacts.failedArtifact,'nothing may export the killed child artifact')
            assert(report.artifacts.survivorArtifact,'the survivor artifact must be retained')
            assert.equal(delegateCalls,2,'no replacement dispatch may follow the process exit')
            assert(!assembly,'assembly must never run in the built-exit drill')
            fs.writeFileSync(path.join(outDir,'built-exit.json'),JSON.stringify(report,null,2))
            blocks=[{type:'text',text:'One built-but-not-exported worker exited for real: the test driver verified its registry identity and terminated it outside any model turn, the infrastructure report woke this idle session, its HIP and marker are retained with nothing exported, and the surviving worker stays ready. Assembly was not attempted.'}]
            }catch(error){try{fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'built-exit-error.json'),
              String(error && error.stack || error))}catch(_){}throw error}
          }else{
            const kill=JSON.parse(fs.readFileSync(killLog,'utf8'))
            const infraVisible=agent.session.snapshotEvents().some(e=>e.type==='user/message'
              &&e.data?.source?.plugin==='dsh-houdini'&&e.data?.source?.form==='notice'
              &&JSON.stringify(e.data).includes(kill.builtChild))
            if(infraVisible){builtExitWake={prevTurnTextOnly:!lastParentHadToolCall}
              blocks=[{type:'tool-call',id:'built-exit-status',name:'component_status',arguments:'{}'}]}
            else{fs.writeFileSync(path.join(outDir,'built-exit-events.json'),JSON.stringify(
              agent.session.snapshotEvents().filter(e=>e.type==='user/message').map((e,i)=>({i,
                source:e.data?.source??null,text:JSON.stringify(e.data).slice(0,260)})),null,2))
              blocks=[{type:'text',text:'Awaiting the worker infrastructure report for the terminated process.'}]}
          }
        }else if(expectProcessExit&&settled.size===2&&!assembly){
          // R6: REAL worker process exit. One settled child's worker process is
          // killed via its registry-record PID; the drill then requires the
          // native infrastructure report as an actual session event, the
          // childId-bound component_status snapshot and both retained artifacts.
          const failedChild=[...settled].sort()[0],survivingChild=[...settled].sort()[1]
          const outDir=process.env.DSH_COMPONENT_TEST_OUT
          const killLog=path.join(outDir,'process-exit-kill.json')
          const statusResult=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId==='exit-status')).at(-1)
          if(!fs.existsSync(killLog)){
            const endpoints=path.join(process.env.DSH_HOUDINI_EXECUTOR_REGISTRY,'endpoints')
            const records=fs.readdirSync(endpoints).filter(f=>f.endsWith('.json'))
              .map(f=>JSON.parse(fs.readFileSync(path.join(endpoints,f),'utf8')))
            const failedRecord=records.find(r=>r.task_id===failedChild)
            const survivingRecord=records.find(r=>r.task_id===survivingChild)
            assert(failedRecord&&Number.isInteger(failedRecord.pid)&&failedRecord.pid>0,
              'the failed child must own a registry record with a real pid: '+JSON.stringify(records).slice(0,400))
            assert(survivingRecord&&Number.isInteger(survivingRecord.pid),'the surviving child must own a registry record')
            let killError=null
            try{process.kill(failedRecord.pid)}catch(error){killError=String(error)}
            fs.writeFileSync(killLog,JSON.stringify({failedChild,pid:failedRecord.pid,
              survivingChild,survivorPid:survivingRecord.pid,killError}))
            blocks=[{type:'text',text:'Both component artifacts are retained. One owned worker process was terminated for the real process-exit drill; awaiting the infrastructure report before checkpoint inspection.'}]
          }else if(statusResult){
            try{
            assert(!statusResult.isError,JSON.stringify(statusResult))
            const status=JSON.parse(statusResult.content.find(c=>c.type==='text').text)
            const kill=JSON.parse(fs.readFileSync(killLog,'utf8'))
            const failed=status.children.find(c=>c.childId===kill.failedChild)
            const surviving=status.children.find(c=>c.childId===kill.survivingChild)
            try{fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'process-exit-debug.json'),
              JSON.stringify({statusText:statusResult.content.map(c=>c.text).join('|').slice(0,1200)},null,2))}catch(error){}
            assert(failed&&surviving,JSON.stringify(status).slice(0,400))
            assert.equal(failed.workerStatus,'stopped')
            assert.equal(failed.checkpoint,'unknown')
            assert.equal(surviving.workerStatus,'ready')
            const infraEvent=agent.session.snapshotEvents().find(e=>e.type==='user/message'
              &&e.data?.source?.plugin==='dsh-houdini'&&e.data?.source?.form==='notice'
              &&JSON.stringify(e.data).includes(failedChild))
            const delegateCalls=agent.session.snapshotEvents().filter(e=>e.type==='tool/call'&&e.data?.name==='component_delegate').length
            const report={failedChild,pid:kill.pid,survivingChild,survivorPid:kill.survivorPid,
              killError:kill.killError??null,
              infraEvent:infraEvent?{type:infraEvent.type,source:infraEvent.data?.source,
                text:JSON.stringify(infraEvent.data).slice(0,900)}:null,
              status:{failed,surviving},
              artifacts:{failed:fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_WORKERS,failedChild,'workspace','part.dshcomponent')),
                surviving:fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_WORKERS,survivingChild,'workspace','part.dshcomponent'))},
              childRequests,delegateCalls,assembly}
            assert(report.artifacts.failed&&report.artifacts.surviving,'both artifacts must be retained after the process exit')
            assert(infraEvent,'the infrastructure report must exist as an actual session event')
            assert(!assembly,'assembly must never run in the process-exit drill')
            assert.equal(delegateCalls,2,'no replacement dispatch may follow the process exit')
            fs.writeFileSync(path.join(outDir,'process-exit.json'),JSON.stringify(report,null,2))
            blocks=[{type:'text',text:'One owned worker process exited for real: its checkpoint is unknown, its artifact is retained, and the infrastructure report reached this session. The surviving worker stays ready. Assembly was not attempted.'}]
            }catch(error){try{fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'process-exit-error.json'),
              String(error && error.stack || error))}catch(_){}throw error}
          }else{
            const events=agent.session.snapshotEvents()
            try{fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'process-exit-debug.json'),JSON.stringify(
              events.slice(-10).map(e=>({type:e.type,source:JSON.stringify(e.data?.source??null),
                dataHead:JSON.stringify(e.data??{}).slice(0,260)})),null,2))}catch(error){}
            const infraVisible=events.some(e=>e.type==='user/message'
              &&e.data?.source?.plugin==='dsh-houdini'&&e.data?.source?.form==='notice'
              &&JSON.stringify(e.data).includes(failedChild))
            if(infraVisible)blocks=[{type:'tool-call',id:'exit-status',name:'component_status',arguments:'{}'}]
            else blocks=[{type:'text',text:'Awaiting the worker infrastructure report for the terminated process.'}]
          }
        }else if(autoRelease&&fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'assembled.json'))){
          const status=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId==='release-status')).at(-1)
          if(!status)blocks=[{type:'tool-call',id:'release-status',name:'component_status',arguments:'{}'}]
          else{
            assert(!status.isError,JSON.stringify(status))
            const result=JSON.parse(status.content.find(c=>c.type==='text').text)
            assert.equal(result.occupied,0)
            assert.equal(result.children.length,2)
            assert(result.children.every(child=>child.workerStatus==='stopped'&&child.checkpoint==='saved'))
            fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'released.json'),JSON.stringify(result))
            blocks=[{type:'text',text:'Idle component workers released with saved checkpoints.'}]
          }
        }else if(expectChildFailure&&settled.size===2&&!assembly){
          assert.match(modelText,/Component exchange blocked at component_export: missing\/ambiguous\/unconnected public output 1/,
            'the original exchange failure must reach the parent in a native child notice')
          const files=fs.readdirSync(process.env.DSH_COMPONENT_TEST_OUT).filter(f=>f.endsWith('.json')&&!['parent-turns.json','module-source.json'].includes(f))
          assert.equal(files.length,1,'only the successful author may publish a fixture record')
          const survivor=JSON.parse(fs.readFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,files[0])))
          assert(settled.has(survivor.child),'the surviving artifact must belong to a completed child')
          const failedChild=[...settled].find(id=>id!==survivor.child)
          assert(failedChild)
          assert(fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_WORKERS,failedChild,'workspace','component.hip')))
          assert(!fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_WORKERS,failedChild,'workspace','part.dshcomponent')))
          fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'blocked.json'),JSON.stringify({
            failedChild,survivingChild:survivor.child,accepted:[...settled],assembly:false,
            error:'missing/ambiguous/unconnected public output 1'}))
          blocks=[{type:'text',text:'Component exchange blocked: missing/ambiguous/unconnected public output 1. The other child artifact is retained; assembly was not attempted. Geometry and visual acceptance remain unverified.'}]
        }else if(settled.size===2&&!assembly){
          const files=fs.readdirSync(process.env.DSH_COMPONENT_TEST_OUT).filter(f=>f.endsWith('.json')&&f!=='assembled.json'&&!['parent-turns.json','module-source.json'].includes(f))
          assert.equal(files.length,2,'both completed children must have published fixture records')
          assert.deepEqual(new Set(files.map(file=>JSON.parse(fs.readFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,file))).child)),settled,
            'parent must receive settlement notices from exactly the two publishing authors')
          let code="g=tab_create('/obj','geo','assembly')\nctrl=tab_create(g,'null','CTRL')\ncreate_spare_parms(ctrl,layout=[{'type':'float','name':'width','default':1}])\n"
          for(let i=0;i<files.length;i++){
            const info=JSON.parse(fs.readFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,files[i])))
            const artifact=path.join(info.cwd,'part.dshcomponent')
            const hash=createHash('sha256').update(fs.readFileSync(artifact)).digest('hex')
            code+=`component_import(g,${JSON.stringify(artifact)},'${hash}','part${i}',trusted=True)\n`
            code+=`set_parms(g.node('part${i}'),{'width':'ch("../CTRL/width")'})\n`
          }
          code+="offset=tab_create(g,'xform','offset',inputs=[g.node('part1')])\nset_parms(offset,{'tx':3})\n"
            +"out=tab_create(g,'merge','OUT',inputs=[g.node('part0'),offset])\nsop_set_output(out)\nverify_network(g,output=out)\n"
            +"report=test_controls(ctrl,out,[{'id':'shared_width','values':{'width':2},'expectations':[{'metric':'bounds_size','axis':0,'delta':[0.99,1.01]}]}])\n"
            +"assert report['restored'] and report['control_summary']['status']=='pass'\nscene_save()\n__result__={'assembly':True,'restored':report['restored']}"
          blocks=[{type:'tool-call',id:'assembly-build',name:'houdini_exec',arguments:JSON.stringify({code})}]
        }else if(assembly){
          const result=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId==='assembly-build')).at(-1)
          assert(result&&!result.isError,JSON.stringify(result))
          const stops=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId.startsWith('stop-child-')))
          if(autoRelease){
            fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'assembled.json'),JSON.stringify({passed:true}))
            blocks=[{type:'text',text:'Assembly saved; worker release pending idle-turn boundary.'}]
          }else if(stops.length===0){
            const files=fs.readdirSync(process.env.DSH_COMPONENT_TEST_OUT).filter(f=>f.endsWith('.json')&&f!=='assembled.json'&&!['parent-turns.json','module-source.json'].includes(f))
            blocks=files.map((file,i)=>({type:'tool-call',id:'stop-child-'+i,name:'component_stop',
              arguments:JSON.stringify({childId:JSON.parse(fs.readFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,file))).child})}))
          }else{
            assert.equal(stops.length,2)
            assert(stops.every(r=>!r.isError),JSON.stringify(stops))
            fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'assembled.json'),JSON.stringify({passed:true}))
            blocks=[{type:'text',text:'Two ordinary subnets assembled; shared control and recovery passed; both workers stopped.'}]
          }
        }else blocks=!checked?[{type:'tool-call',id:'capacity',name:'component_status',arguments:'{}'}]
          :called?(!waited?[{type:'tool-call',id:'component-wait',name:'component_wait',arguments:JSON.stringify({timeoutSeconds:1})}]
            :[{type:'text',text:'Component work accepted; awaiting its result.'}]):(expectStartupFailure?[0]:[0,1]).map(i=>({
          type:'tool-call',id:'delegate-'+i,name:'component_delegate',arguments:JSON.stringify({task:'Fixture part '+i+': create an ordinary subnet box in metres, publish output 0 and export part.dshcomponent. Do not create an HDA. Parent guesses the Host-assigned HIP is Z:\\wrong-parent-path\\component.hip; this negative-control claim must not become authoritative.'})}))
      }
      if(agent&&!agent.session.header.parentSession)lastParentHadToolCall=blocks.some(b=>b.type==='tool-call')
      for(let index=0;index<blocks.length;index++){
        yield {type:'block-start',index,blockType:blocks[index].type}
        yield {type:'block-end',index,block:blocks[index]}
      }
      yield {type:'finish',reason:{kind:blocks.some(b=>b.type==='tool-call')?'tool-calls':'stop'}}
    }
  }
  ctx.llm.registerAdapter(['component-fixture'],new Fixture())
}
