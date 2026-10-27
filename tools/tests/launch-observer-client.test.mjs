import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import vm from 'node:vm'

const source=await fs.readFile(new URL('../../client.js',import.meta.url),'utf8')
const fragment=source.slice(source.indexOf('    function createLaunchOwnership('),source.indexOf('    function createHoudiniDesktopUi('))
const timers=new Map();let timerId=0
const context={AbortController,AbortSignal,Map,Set,Number,setTimeout:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,delay});return id},clearTimeout:id=>timers.delete(id)}
vm.createContext(context);vm.runInContext(fragment,context)
const settle=async()=>{for(let n=0;n<30;n++)await Promise.resolve()}
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return{promise,resolve,reject}}
function store(value){const listeners=new Set();return{getSnapshot:()=>value,subscribe:fn=>{listeners.add(fn);return()=>listeners.delete(fn)},set:next=>{value=next;listeners.forEach(fn=>fn())}}}
function fixture(){
 const calls=[],views=[],completed=[],generation=store({id:1}),handlers={};let identity=0,target='original-target',current=true
 const connection={generation,rpc:{call:async(_channel,method,payload,signal)=>{
  const input=payload.args.input,name=method.split('/')[1];calls.push({name,input,signal})
  if(handlers[name])return{ok:true,value:await handlers[name](input,signal)}
  if(name==='projectLaunchDetach')return{ok:true,value:{id:input.id,phase:'detached'}}
  throw Error('Unexpected RPC '+name)
 }}}
 const ownership=context.createLaunchOwnership(connection)
 function observer(publish=views,ready=completed,guard=()=>current){return context.createProjectLaunchObserver(connection,ownership,{
  isCurrent:guard,target:()=>target,emit:value=>publish.push(value),ready:value=>ready.push(value),requestId:()=> (++identity).toString(16).padStart(32,'0')})}
 return{calls,views,completed,handlers,connection,generation,ownership,observer,target:value=>target=value,current:value=>current=value,
  close(...observers){observers.forEach(value=>value.dispose());ownership.dispose()}}
}
const parameters={action:'new',sessionId:'native-houdini',hfs:'D:/Houdini22'}
assert.match(context.launchTicketMessage({phase:'detached'}),/不会取消启动或关闭 Houdini/,'stop observation never claims an unconfirmed process already exists or was stopped')

{
 const f=fixture(),observer=f.observer();let ticket
 f.handlers.projectAction=input=>ticket={id:input.requestId,phase:'preparing',stage:'launching',message:'Host admission recorded',elapsedMs:50}
 f.handlers.projectLaunchStatus=()=>ticket
 await observer.submit(parameters)
 assert.equal(observer.snapshot().ticket.phase,'preparing');assert.equal(observer.snapshot().pending,true)
 assert.equal(context.launchTicketMessage(observer.snapshot().ticket),'Host admission recorded')
 ticket={...ticket,phase:'waiting',stage:'capturing',message:'Host captured current scene',elapsedMs:3456}
 await observer.reconnect()
 assert.equal(observer.snapshot().ticket.stage,'capturing');assert.equal(context.launchTicketMessage(observer.snapshot().ticket),ticket.message)
 ticket={...ticket,phase:'detached',message:''};await observer.reconnect()
 assert.equal(observer.snapshot().pending,false);assert.equal(f.calls.filter(row=>row.name==='projectLaunchResume').length,0)
 f.handlers.projectLaunchResume=input=>ticket={...ticket,id:input.id,phase:'waiting',stage:'binding',message:'Host revalidating original receipt'}
 await observer.resume()
 assert.equal(f.calls.filter(row=>row.name==='projectAction').length,1);assert.equal(f.calls.filter(row=>row.name==='projectLaunchResume').length,1)
 assert.equal(observer.snapshot().ticket.stage,'binding')
 ticket={...ticket,phase:'ready',result:{sessionId:parameters.sessionId,executorId:'actual'}};await observer.reconnect()
 assert.equal(f.completed.length,1)
 f.close(observer)
}

{
 const f=fixture(),observer=f.observer();let ticket
 f.handlers.projectAction=input=>{ticket={id:input.requestId,phase:'waiting',stage:'registering',message:'Original request accepted'};throw Error('Transport reply lost')}
 f.handlers.projectLaunchStatus=input=>{assert.equal(input.id,ticket.id);return ticket}
 await observer.submit(parameters)
 assert.equal(observer.snapshot().ticket.id,f.calls.find(row=>row.name==='projectAction').input.requestId,'a lost initial response is recovered by the same request/ticket identity')
 f.generation.set({id:2});await observer.reconnect()
 assert.equal(f.calls.filter(row=>row.name==='projectAction').length,1,'Host reconnect cannot submit another process launch')
 f.handlers.projectLaunchStatus=()=>{throw Error('Status temporarily unavailable')};await observer.reconnect()
 const originalId=f.calls.find(row=>row.name==='projectAction').input.requestId
 await observer.submit(parameters)
 assert(f.calls.filter(row=>row.name==='projectAction').every(row=>row.input.requestId===originalId),'an explicit transport retry preserves one user-action identity')
 f.close(observer)
}

{
 const f=fixture(),observer=f.observer(),reply=deferred();let ticket
 f.handlers.projectAction=input=>{ticket={id:input.requestId,phase:'preparing',stage:'launching',message:'New Host preparing'};return reply.promise}
 f.handlers.projectLaunchStatus=()=>ticket
 const submitted=observer.submit(parameters);await settle()
 f.generation.set(null);await observer.reconnect();assert.equal(observer.snapshot().disconnected,true)
 f.generation.set({id:2});await observer.reconnect()
 reply.resolve({...ticket,phase:'waiting',stage:'capturing',message:'Old-generation reply'});await submitted
 assert.equal(f.calls.filter(row=>row.name==='projectAction').length,1)
 assert.equal(f.calls.filter(row=>row.name==='projectLaunchDetach').length,0,'transport cleanup never detaches an active reconnecting observation')
 assert.equal(observer.snapshot().ticket.message,'New Host preparing','late old-generation facts cannot replace the latest Host status')
 ticket={...ticket,phase:'detached'};await observer.reconnect();f.target('user-selected-another-target');await observer.resume()
 assert.equal(f.calls.filter(row=>row.name==='projectLaunchResume').length,0,'explicit resume cannot override a newer target choice')
 assert.match(observer.snapshot().error,/重新选择现场/)
 f.close(observer)
}

{
 const f=fixture(),first=f.observer(),reply=deferred();let originalId
 f.handlers.projectAction=input=>{originalId=input.requestId;return reply.promise}
 const submitted=first.submit(parameters);await settle();first.stop();await settle()
 assert.equal(f.calls.find(row=>row.name==='projectLaunchDetach').input.id,originalId,'stop can detach the known identity before the first response arrives')
 let secondCurrent=true;const newerViews=[],newerCompleted=[],second=f.observer(newerViews,newerCompleted,()=>secondCurrent)
 f.handlers.projectAction=()=>({id:originalId,phase:'detached',stage:'registering'})
 await second.submit(parameters)
 f.handlers.projectLaunchResume=()=>({id:originalId,phase:'ready',result:{sessionId:parameters.sessionId,executorId:'new-owner'}})
 await second.resume();assert.equal(newerCompleted.length,1)
 const detaches=f.calls.filter(row=>row.name==='projectLaunchDetach').length
 reply.resolve({id:originalId,phase:'waiting',stage:'binding'});await submitted
 assert.equal(f.calls.filter(row=>row.name==='projectLaunchDetach').length,detaches,'the old stopped submission cannot detach a newer observer/binding')
 assert.equal(f.completed.length,0)
 secondCurrent=false;f.close(first,second)
}

{
 const f=fixture(),observer=f.observer();let ticket
 f.handlers.projectAction=input=>ticket={id:input.requestId,phase:'waiting',stage:'launching'}
 f.handlers.projectLaunchStatus=()=>ticket
 await observer.submit(parameters);const id=ticket.id
 f.generation.set(null);observer.stop();await settle()
 assert.equal(f.calls.filter(row=>row.name==='projectLaunchDetach').length,0)
 f.generation.set({id:2});await settle()
 assert.equal(f.calls.find(row=>row.name==='projectLaunchDetach').input.id,id,'an offline stop retains only its exact pending detach intention')
 f.close(observer)
}
console.log('Launch observer UI: true preparing/stage facts, stable request IDs, lost admission response, reconnect without respawn, explicit resume, target precedence and stale detach isolation passed')
