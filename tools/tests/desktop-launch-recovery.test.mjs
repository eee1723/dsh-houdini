import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {EventEmitter,once} from 'node:events'
import {spawn} from 'node:child_process'
import {DesktopIntegration} from '../../lib/desktop-integration.js'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {foldExecutorState} from '../../lib/executor-identity-projection.js'
import {fixtureSession} from './fixture-session.mjs'
const previous=process.env.DSH_HOME,fixtures=[]
const gate=()=>{let enter,release;return {entered:new Promise(r=>enter=r),wait:new Promise(r=>release=r),enter:()=>enter(),release:()=>release()}}
async function until(read){for(let n=0;n<100;n++){if(await read())return;await new Promise(r=>setTimeout(r,10))}throw Error('fixture deadline')}
async function fixture(name){
 const home=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-launch-'+name+'-'))
 const session=fixtureSession('native-'+name,{agentPreset:'houdini',cwd:home}),agent={id:session.id,status:'idle',session}
 const record={schema:1,executor_id:'a'.repeat(32),registration_id:'b'.repeat(32),runtime_id:'c'.repeat(32),installation:home,
  bridge_url:'http://127.0.0.1:18765',houdini_version:'22.0.368',pid:process.pid,processStarted:'1001',state:'registered',task_id:null,
  hip_path:path.join(home,'untitled.hip'),hip_is_new:true,workbench:true,scene_id:'d'.repeat(32),scene_epoch:'e'.repeat(32),workspace_path:home,
  runtime:{hfs:home,python:path.join(home,'python313/python.exe'),executable:path.join(home,'bin/houdini.exe'),pythonVersion:'3.13.0'}}
 const state={available:false,birth:'1001',probes:0,spawns:0,calls:0,bindings:0,failSpawn:false,before:null,after:null}
 const binding=new ExecutorBinding()
 const targets={registry:path.join(home,'dsh-houdini/executors'),getRouter:()=>({directory:{list:async()=>state.available?[record]:[],find:async()=>record},
  inspectSelectedTarget:async(target,signal)=>{signal?.throwIfAborted();return record}}),
  openWorkspace:async(input,signal,revision,beforeCommit)=>{
   state.calls++;if(state.before){state.before.enter();await state.before.wait}
   signal.throwIfAborted();assert.equal(foldExecutorState(session.snapshotEvents()).selectionRevision,revision)
   beforeCommit?.();await binding.select(session,record,signal);state.bindings++
   if(state.after){state.after.enter();await state.after.wait}
   return {sessionId:input.bindSessionId,executorId:input.executorId,workspaceId:'native-workspace'}
  }}
 const ctx={logger:{warn:()=>{}},sessionController:{resolveAgent:async id=>{assert.equal(id,session.id);return{agent}}},
  sessionProjections:{stateOf:(value,key)=>key==='agentPreset'?'houdini':foldExecutorState(value.snapshotEvents())},workspaceRegistry:{archivedSessionIds:[],list:()=>[]}}
 ctx.get=name=>name==='sessionProjections'?ctx.sessionProjections:undefined
 const services=[],create=()=>{
  process.env.DSH_HOME=home
  const service=new DesktopIntegration(ctx,targets,async()=>[{hfs:home,version:'22.0.368',series:'22.0',executable:record.runtime.executable}],
   async()=>{state.probes++;return state.birth},()=>{state.spawns++;if(state.failSpawn)throw Error('fixture: not submitted')
    return Object.assign(new EventEmitter(),{pid:process.pid,exitCode:null,unref(){}})},async()=>({ok:true,helperId:'a'.repeat(16),helperRoot:home,requiresRestart:true,
      migration:{reportPath:null,disabledCount:0,reviewCount:0},message:'fixture helper ready'}))
  services.push(service);return service
 }
 const f={home,session,record,state,create,services,action:(requestId='1'.repeat(32))=>({action:'new',sessionId:session.id,hfs:home,requestId}),
  callback:t=>({id:t.id,executorId:record.executor_id,registrationId:record.registration_id,expectedHip:record.hip_path}),
  disk:async t=>JSON.parse(await fs.readFile(path.join(home,'dsh-houdini/launches',t.id+'.json'),'utf8'))}
 fixtures.push(f);return f
}
async function request(f,route,payload){
 const d=JSON.parse(await fs.readFile(path.join(f.home,'dsh-houdini/desktop.json'),'utf8'))
 const r=await fetch('http://127.0.0.1:'+d.port+route,{method:'POST',headers:{'content-type':'application/json',Authorization:'Bearer '+d.token},
  body:JSON.stringify(payload),signal:AbortSignal.timeout(3000)})
 return {status:r.status,...await r.json()}
}
try{
 const f=await fixture('resume'),first=f.create();await first.start()
 const t=await first.project(f.action(),new AbortController().signal)
 assert.equal(t.id,f.action().requestId);assert.equal(t.phase,'waiting');assert.equal((await f.disk(t)).schemaVersion,2)
 assert.equal((await first.project(f.action(),new AbortController().signal)).id,t.id);assert.equal(f.state.spawns,1)
 await first.detach({id:t.id});f.state.available=true
 assert.deepEqual((await request(f,'/launch-attached',f.callback(t))).value,{phase:'detached'})
 assert.ok((await f.disk(t)).receipt)
 assert.equal((await first.project(f.action('2'.repeat(32)),new AbortController().signal)).phase,'detached')
 await first.dispose();const second=f.create();await second.start()
 assert.notEqual(first.generation,second.generation);assert.equal((await f.disk(t)).generation,first.generation)
 const admitted=await request(f,'/ticket-current',{id:t.id,pid:process.pid,processStarted:'1001',hfs:f.home,hipPath:f.record.hip_path,hipIsNew:true})
 assert.equal(admitted.status,200,JSON.stringify(admitted))
 assert.equal((await second.resume({id:t.id})).phase,'ready','resume consumes saved receipt after its producer has ended')
 assert.equal(f.state.spawns,1);assert.equal(f.state.bindings,1)
 await second.dispose();const third=f.create();await third.start()
 assert.equal((await third.status({id:t.id})).phase,'ready')
 assert.equal((await request(f,'/launch-attached',f.callback(t))).status,200);assert.equal(f.state.bindings,1)
 await third.dispose()
 const d=await fixture('detach'),ds=d.create();await ds.start()
 const dt=await ds.project(d.action(),new AbortController().signal);d.state.available=true;d.state.before=gate()
 const attaching=request(d,'/launch-attached',d.callback(dt));await d.state.before.entered
 assert.equal((await ds.detach({id:dt.id})).phase,'detached');d.state.before.release();await attaching
 assert.equal(d.state.bindings,0);assert.equal((await ds.status({id:dt.id})).phase,'detached')
 d.state.before=null;assert.equal((await ds.resume({id:dt.id})).phase,'ready');assert.equal(d.state.spawns,1);assert.equal(d.state.bindings,1)
 await ds.dispose()
 const c=await fixture('parallel'),cs=c.create();await cs.start()
 const ct=await cs.project(c.action(),new AbortController().signal);c.state.available=true;c.state.after=gate()
 const one=request(c,'/launch-attached',c.callback(ct)),two=request(c,'/launch-attached',c.callback(ct));await c.state.after.entered
 const stop=cs.detach({id:ct.id});c.state.after.release()
 const [a,b,stopped]=await Promise.all([one,two,stop]);assert.equal(a.status,200);assert.equal(b.status,200);assert.deepEqual(a.value,b.value)
 assert.equal(stopped.phase,'ready');assert.equal(c.state.calls,1);assert.equal(c.state.bindings,1)
 assert.equal((await cs.intents.read(0,new AbortController().signal)).sequence,1);await cs.dispose()
 const p=await fixture('probe');p.state.birth=null;const ps=p.create();await ps.start()
 const pt=await ps.project(p.action(),new AbortController().signal);assert.equal(pt.process,'unknown');p.state.birth='1001'
 assert.equal((await ps.status({id:pt.id})).process,'alive');assert.ok(p.state.probes>1);await ps.dispose()
 const filename=path.join(p.home,'dsh-houdini/launches',pt.id+'.json'),unknown=await p.disk(pt)
 delete unknown.processStarted;await fs.writeFile(filename,JSON.stringify(unknown))
 const restored=p.create();await restored.start();assert.equal((await restored.status({id:pt.id})).process,'unknown')
 assert.equal((await request(p,'/launch-attached',p.callback(pt))).status,503);await restored.dispose()
 const e=await fixture('failed'),es=e.create();await es.start();e.state.failSpawn=true
 await assert.rejects(es.project(e.action(),new AbortController().signal),/not submitted/)
 assert.equal((await es.status({id:e.action().requestId})).phase,'error');e.state.failSpawn=false
 assert.equal((await es.project(e.action('2'.repeat(32)),new AbortController().signal)).phase,'waiting');await es.dispose()
 const s=await fixture('selection'),ss=s.create();await ss.start();const st=await ss.project(s.action(),new AbortController().signal)
 await new ExecutorBinding().select(s.session,{...s.record,executor_id:'f'.repeat(32)});s.state.available=true
 assert.equal((await request(s,'/launch-attached',s.callback(st))).status,400);assert.equal(s.state.bindings,0)
 assert.equal((await ss.status({id:st.id})).phase,'error');await ss.dispose()
 const u=await fixture('unload'),us=u.create();await us.start()
 const discovering=gate(),installations=us.installations
 us.installations=async()=>{discovering.enter();await discovering.wait;return installations()}
 const submission=us.project(u.action(),new AbortController().signal)
 await discovering.entered
 const closing=us.dispose();discovering.release()
 await assert.rejects(submission,/unloaded/);await closing
 assert.equal(u.state.spawns,0,'an unloaded service cannot submit a process after async discovery returns')
 const successor=u.create();await successor.start();await successor.dispose()
 const early=await fixture('early-stop'),earlyService=early.create();await earlyService.start()
 const discovery=gate(),findInstall=earlyService.installations
 earlyService.installations=async()=>{discovery.enter();await discovery.wait;return findInstall()}
 const earlySubmit=earlyService.project(early.action(),new AbortController().signal);await discovery.entered
 assert.equal((await earlyService.detach({id:early.action().requestId})).phase,'detached')
 discovery.release();const earlyTicket=await earlySubmit
 assert.equal(earlyTicket.phase,'detached','stop during initial discovery is retained before the ticket exists')
 early.state.available=true
 assert.deepEqual((await request(early,'/launch-attached',early.callback(earlyTicket))).value,{phase:'detached'})
 assert.equal(early.state.bindings,0);await earlyService.dispose()
 const stale=await fixture('stale-hip'),staleService=stale.create();await staleService.start()
 const exited=spawn(process.execPath,['-e','']);const deadPid=exited.pid;await once(exited,'exit')
 stale.record.pid=deadPid;stale.state.birth=null;stale.state.available=true;stale.record.hip_is_new=false
 const saved=path.join(stale.home,'saved.hip');await fs.writeFile(saved,'fixture only; no HOM is executed')
 stale.record.hip_path=saved
 const opened=await staleService.project({...stale.action(),action:'open',hip:saved},new AbortController().signal)
 assert.equal(opened.phase,'waiting');assert.equal(stale.state.spawns,1,'OS-confirmed exited discovery cannot block an explicit new open')
 assert.equal(stale.state.bindings,0,'the stale row is preserved as history, never adopted')
 await staleService.dispose()
 const r=await fixture('cleanup'),rs=r.create();await rs.start();const rt=await rs.project(r.action(),new AbortController().signal)
 await rs.dispose();r.state.birth='1002'
 const startup=path.join(r.home,'dsh-houdini/launches',rt.id),outside=path.join(r.home,'foreign-startup'),source='from dsh_workbench_entry import after_ui_ready\nafter_ui_ready()\n'
 await fs.mkdir(outside);await fs.writeFile(path.join(outside,'uiready.py'),source)
 await fs.unlink(path.join(startup,'python3.11libs/uiready.py'));await fs.rmdir(path.join(startup,'python3.11libs'))
 await fs.symlink(outside,path.join(startup,'python3.11libs'),process.platform==='win32'?'junction':'dir')
 const rr=r.create();await rr.start();await until(async()=>(await r.disk(rt)).bootstrapRetired===true)
 assert.equal(await fs.readFile(path.join(outside,'uiready.py'),'utf8'),source);assert.ok(await fs.stat(path.join(r.home,'dsh-houdini/launches',rt.id+'.log')))
 assert.equal((await rr.project(r.action(),new AbortController().signal)).phase,'error','ended request identity remains terminal')
 assert.equal(r.state.spawns,1,'a network retry of a retired operation cannot launch another window')
 await rr.dispose()
 console.log('Desktop launch recovery: cross-generation admission, explicit resume, commit fence, concurrent receipt, retryable identity, prepare failure, stale selection and safe cleanup passed')
}finally{
 for(const f of fixtures)for(const s of f.services)await s.dispose()
 if(previous===undefined)delete process.env.DSH_HOME;else process.env.DSH_HOME=previous
}
