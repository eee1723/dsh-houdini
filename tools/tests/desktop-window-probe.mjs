// CDP consumer of one explicitly owned native Electron window and main inspector.
import fs from 'node:fs/promises'
import path from 'node:path'
import assert from 'node:assert/strict'
import {NATIVE_SELECTION} from './browser-selection.mjs'

const config=JSON.parse(await fs.readFile(process.argv[2],'utf8'))
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function connect(url) {
  const socket=new WebSocket(url)
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})})
  let serial=0;const pending=new Map()
  socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.id)pending.get(value.id)?.(value)})
  return {close:()=>socket.close(),async call(method,params={},timeout=15000) {
    const id=++serial,result=new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method))},timeout)
      pending.set(id,value=>{clearTimeout(timer);pending.delete(id);value.error?reject(Error(JSON.stringify(value.error))):resolve(value.result)})
    });socket.send(JSON.stringify({id,method,params}));return result
  }}
}
const report={phase:config.phase}
let connection
let browserEvaluate
try {
  if(config.phase==='quit') {
    connection=await connect(config.mainInspector)
    const result=await connection.call('Runtime.evaluate',{returnByValue:true,expression:
      `(()=>{if(process.pid!==${JSON.stringify(config.expectedPid)})throw Error('Foreign native carrier');
      const electron=process.getBuiltinModule('module').createRequire(process.resourcesPath+'/app.asar/package.json')('electron');
      const fs=process.getBuiltinModule('fs'),file=${JSON.stringify(config.output.replace(/\.json$/,'-dialog.json'))};
      if(!globalThis.__ownedQuitDialogObservation){
        const observation={pid:process.pid,calls:[]},persist=()=>{try{fs.writeFileSync(file,JSON.stringify(observation,null,2))}catch{}};
        const original=electron.dialog.showMessageBox;
        electron.dialog.showMessageBox=function(...args){
          const options=args.find(arg=>arg&&typeof arg==='object'&&('message' in arg||'buttons' in arg))||{};
          const row={at:Date.now(),status:'pending',title:options.title,message:options.message,detail:options.detail,buttons:options.buttons};
          observation.calls.push(row);persist();let answer;
          try{answer=Reflect.apply(original,this,args)}catch(error){row.status='threw';row.error=String(error);persist();throw error}
          if(answer&&typeof answer.then==='function')answer.then(value=>{row.status='returned';row.result=value;persist()},error=>{row.status='rejected';row.error=String(error);persist()});
          return answer;
        };
        globalThis.__ownedQuitDialogObservation=observation;persist();
      }
      const windows=electron.BrowserWindow.getAllWindows().map(window=>window.getNativeWindowHandle().readBigUInt64LE().toString());
      setTimeout(()=>electron.app.quit(),100);return {pid:process.pid,nativeWindowHandles:windows,dialogObservation:file}})()`})
    assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails))
    report.normalAppQuitRequested=true
    report.ownedMainWindows=result.result.value
  }else if(config.phase==='health') {
    const state=JSON.parse(await fs.readFile(config.stateFile,'utf8'))
    const response=await fetch(state.record.bridge_url+'/health',{headers:{'X-DSH-Houdini-Executor':state.target.executor_id},signal:AbortSignal.timeout(5000)})
    assert.equal(response.status,200)
    const value=await response.json()
    assert.equal(value.executorId,state.target.executor_id);assert.equal(value.runtimeId,state.target.runtime_id);assert.equal(value.sceneEpoch,state.target.scene_epoch)
    report.sameHoudiniBridge=true
    report.health={executorId:value.executorId,runtimeId:value.runtimeId,sceneEpoch:value.sceneEpoch,houVersion:value.houVersion,
      activeRequests:value.activeRequests,activeJobs:value.activeJobs}
  }else {
    const targets=await(await fetch('http://127.0.0.1:'+config.port+'/json/list')).json()
    const page=targets.find(row=>row.type==='page'&&row.url.startsWith('dsh-app://app'))
    assert(page,'No owned native Desktop page')
    report.targetUrl=page.url
    connection=await connect(page.webSocketDebuggerUrl)
    async function evaluate(expression) {
      const result=await connection.call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true})
      assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value
    }
    browserEvaluate=evaluate
    async function until(expression,description,timeout=30000) {
      const end=Date.now()+timeout
      while(Date.now()<end){const value=await evaluate(expression);if(value)return value;await sleep(100)}
      throw Error('Native page did not reach '+description)
    }
    async function rpc(method,args={}) {
      return evaluate(`(async()=>{const response=await fetch('/api/'+${JSON.stringify(method)},{method:'POST',headers:{'content-type':'application/json'},credentials:'include',body:JSON.stringify({type:'client-request',rpcId:'owned-'+crypto.randomUUID(),method:${JSON.stringify(method)},payload:{args:${JSON.stringify(args)}}})});const text=await response.text();let body;try{body=JSON.parse(text)}catch{throw Error('Native RPC '+${JSON.stringify(method)}+' HTTP '+response.status+' '+response.headers.get('content-type')+' '+text.slice(0,500))}const result=body.result;if(!result?.ok)throw Error(JSON.stringify(result?.error||body));return result.value})()`)
    }
    async function untilRpc(method,accept,description,timeout=30000) {
      const end=Date.now()+timeout
      do {const value=await rpc(method);if(accept(value))return value;await sleep(100)}while(Date.now()<end)
      throw Error('Native Host did not reach '+description)
    }
    async function showOwnedWindow() {
      const main=await connect(config.mainInspector)
      try {
        const result=await main.call('Runtime.evaluate',{returnByValue:true,expression:
          `(()=>{if(process.pid!==${JSON.stringify(config.expectedPid)})throw Error('Foreign native carrier');const electron=process.getBuiltinModule('module').createRequire(process.resourcesPath+'/app.asar/package.json')('electron');const windows=electron.BrowserWindow.getAllWindows().filter(window=>window.webContents.getURL().startsWith('dsh-app://app/'));if(windows.length!==1)throw Error('No unique owned native app window');const window=windows[0];if(window.isMinimized())window.restore();window.show();window.focus();return{pid:process.pid,nativeWindowHandle:window.getNativeWindowHandle().readBigUInt64LE().toString(),visible:window.isVisible(),focused:window.isFocused(),at:Date.now()}})()`})
        assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails))
        return result.result.value
      }finally{main.close()}
    }
    await connection.call('Runtime.enable');await connection.call('Page.enable')
    await until('document.readyState==="complete"','native page load')
    // HTML completion precedes the native client/backend handshake. Consume its
    // first real Session instead of racing a not-yet-forwarded /api request.
    await until(NATIVE_SELECTION,'native initial session selection',45000)
    const roster=await rpc('agentPresets/list')
    assert(roster.presets.find(row=>row.id==='standard'&&row.isDefault))
    assert(roster.presets.find(row=>row.id==='houdini'&&!row.isDefault))
    await untilRpc('houdiniFrontend/capabilities',value=>value.desktop===true,'Desktop service publication')
    const required=['include:workspace-controller','include:houdini-frontend','include:houdini-executor-host']
    const inventory=await untilRpc('pluginInventory/list',value=>required.every(id=>value.entries.some(row=>row.entryId===id&&row.fiberPhase==='active')),'required native services')
    report.services=inventory.entries.filter(row=>['include:workspace-controller','include:houdini-frontend','include:houdini-executor-host'].includes(row.entryId))
      .map(row=>({entryId:row.entryId,fiberPhase:row.fiberPhase}))
    for(const id of required)assert(report.services.some(row=>row.entryId===id&&row.fiberPhase==='active'),id)
    if(config.phase==='reopen') {
      const state=JSON.parse(await fs.readFile(config.stateFile,'utf8'))
      if(config.pendingLaunch) {
        await fs.writeFile(config.barrierRelease,'release owned startup barrier\n')
        let status;const end=Date.now()+config.timeoutMs
        do {
          status=await rpc('houdiniFrontend/projectLaunchStatus',{input:{id:state.ticketId}})
          if(status.phase==='error'||status.phase==='detached')throw Error(JSON.stringify(status))
          if(status.phase==='ready')break
          await sleep(500)
        }while(Date.now()<end)
        assert.equal(status.phase,'ready',JSON.stringify(status))
        assert.equal(status.result.sessionId,state.sessionId)
        const listing=await rpc('houdiniTargets/list',{input:{sessionId:state.sessionId}})
        const record=listing.candidates.find(row=>row.executor_id===listing.selectedTarget?.executor_id)
        assert.equal(record?.pid,state.record.pid);assert.equal(record?.processStarted,state.record.processStarted)
        state.record=record;state.target=listing.selectedTarget
        await fs.writeFile(config.stateFile,JSON.stringify(state,null,2))
        report.originalPendingTicketCompleted={id:state.ticketId,phase:status.phase,sessionId:status.result.sessionId,
          pid:record.pid,processStarted:record.processStarted}
      }
      const listing=await rpc('houdiniTargets/list',{input:{sessionId:state.sessionId}})
      assert.equal(listing.selectedTarget.executor_id,state.target.executor_id)
      assert.equal(listing.selectedTarget.runtime_id,state.target.runtime_id)
      assert.equal(listing.selectedTarget.scene_epoch,state.target.scene_epoch)
      const record=listing.candidates.find(row=>row.executor_id===state.target.executor_id)
      assert.equal(record.pid,state.record.pid);assert.equal(record.processStarted,state.record.processStarted)
      await until(`(${NATIVE_SELECTION})?.sessionId===${JSON.stringify(state.sessionId)}&&!!document.querySelector('[data-houdini-project-label]')`,'the original native Houdini session',45000)
      report.restoredSelection=await evaluate(NATIVE_SELECTION)
      report.sameNativeSessionAndHoudini=true
      // This is additional consumer evidence after the required pending resume.
      // Show only the already-verified fixture carrier through public Electron
      // APIs, then let the real visibility/5-second client refresh do its work.
      try {
        const shown=await showOwnedWindow();report.ownedWindowShown=shown
        await until('document.visibilityState==="visible"&&!document.hidden','visible native app document',15000)
        const fresh=await untilRpc('houdiniFrontend/projectPresence',rows=>rows.some(row=>
          row.executorId===state.target.executor_id&&row.runtimeId===state.target.runtime_id&&row.sceneEpoch===state.target.scene_epoch
          &&row.status==='online'&&row.contractMismatch===false&&row.observedAt>=shown.at),'fresh online scene observation',30000)
        const observed=fresh.find(row=>row.executorId===state.target.executor_id)
        await until(`document.visibilityState==='visible'&&!!document.querySelector('[data-houdini-project-label][data-houdini-presence="online"]')`,'fresh online chip in native client',30000)
        report.onlineObservation={ok:true,executorId:observed.executorId,runtimeId:observed.runtimeId,sceneEpoch:observed.sceneEpoch,
          observedAt:observed.observedAt,activeRequests:observed.activeRequests,activeJobs:observed.activeJobs,
          client:await evaluate(`(()=>{const chip=document.querySelector('[data-houdini-project-label]');return{visibility:document.visibilityState,presence:chip.dataset.houdiniPresence,state:chip.dataset.state,text:chip.innerText}})()`)}
      }catch(error){report.onlineObservation={ok:false,error:String(error.stack||error)}}
    }else {
      report.ownedWindowShown=await showOwnedWindow()
      await until('document.visibilityState==="visible"&&!document.hidden','visible initial native app document',15000)
      const created=await rpc('workspace/create',{request:{path:config.conversation}})
      report.workspaceCreated=Boolean(created.workspace?.workspaceId)
      assert(report.workspaceCreated)
      if(config.lifetimeHfs) {
        const initial=await until(NATIVE_SELECTION,'native selected blank session')
        await rpc('agentPresets/select',{agentId:initial.sessionId,agentPreset:'houdini'})
        await until(`!!document.querySelector('[data-houdini-project-label]')`,'selected Houdini mode')
        const selected=await evaluate(NATIVE_SELECTION);assert.equal(selected.sessionId,initial.sessionId)
        const installations=await rpc('houdiniFrontend/projectInstallations')
        const installation=installations.find(row=>path.win32.normalize(row.hfs).toLowerCase()===path.win32.normalize(config.lifetimeHfs).toLowerCase())
        assert(installation,'Explicit test Houdini installation was not discovered')
        const ticket=await rpc('houdiniFrontend/projectAction',{input:{action:'new',sessionId:selected.sessionId,hfs:installation.hfs}})
        assert(ticket.id)
        if(config.pendingLaunch) {
          assert.equal(ticket.phase,'waiting')
          const persisted=JSON.parse(await fs.readFile(path.join(config.launchesRoot,ticket.id+'.json'),'utf8'))
          assert.equal(persisted.phase,'waiting');assert(persisted.pid&&persisted.processStarted)
          const record={pid:persisted.pid,processStarted:persisted.processStarted}
          await fs.writeFile(config.stateFile,JSON.stringify({sessionId:selected.sessionId,ticketId:ticket.id,target:null,record},null,2))
          report.pending={id:ticket.id,phase:ticket.phase,sessionId:selected.sessionId,...record}
        }else {
          const end=Date.now()+config.timeoutMs;let status
          do {
            status=await rpc('houdiniFrontend/projectLaunchStatus',{input:{id:ticket.id}})
            if(status.phase==='error')throw Error(JSON.stringify(status))
            if(status.phase==='ready')break
            await sleep(500)
          }while(Date.now()<end)
          assert.equal(status.phase,'ready',JSON.stringify(status))
          const listing=await rpc('houdiniTargets/list',{input:{sessionId:selected.sessionId}})
          assert.equal(listing.state.status,'selected')
          const record=listing.candidates.find(row=>row.executor_id===listing.selectedTarget.executor_id)
          assert(record&&record.pid&&record.processStarted)
          await fs.writeFile(config.stateFile,JSON.stringify({sessionId:selected.sessionId,ticketId:ticket.id,target:listing.selectedTarget,record},null,2))
          report.launched={sessionId:selected.sessionId,pid:record.pid,processStarted:record.processStarted,executorId:record.executor_id}
        }
      }
    }
    // An occluded native window can stop producing compositor frames while its
    // DOM/RPC remains live. Do not make an image stall the pending-quit boundary.
    if(!config.pendingLaunch||config.phase==='reopen')try {
      await connection.call('Page.bringToFront',{},5000)
      const shot=await connection.call('Page.captureScreenshot',{format:'png'},5000)
      await fs.writeFile(config.output.replace(/\.json$/,'.png'),Buffer.from(shot.data,'base64'))
    }catch(error){report.screenshotError=String(error)}
  }
  report.ok=true
}catch(error){
  report.error=String(error.stack||error);process.exitCode=1
  if(browserEvaluate)try{
    report.nativeFailure=await browserEvaluate(`({text:document.body.innerText,selection:${NATIVE_SELECTION},rows:[...document.querySelectorAll('[data-row-key]')].map(row=>({key:row.dataset.rowKey,selected:row.getAttribute('aria-selected')}))})`)
    if(!config.pendingLaunch){const shot=await connection.call('Page.captureScreenshot',{format:'png'},5000)
      await fs.writeFile(config.output.replace(/\.json$/,'-failure.png'),Buffer.from(shot.data,'base64'))}
  }catch{}
}
finally{connection?.close();await fs.writeFile(config.output,JSON.stringify(report,null,2))}
