import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import vm from 'node:vm'

const source=await readFile(new URL('../../client.js',import.meta.url),'utf8')
const flush=async()=>{for(let n=0;n<30;n++)await Promise.resolve();await new Promise(resolve=>setTimeout(resolve,0))}
const deferred=()=>{let resolve;const promise=new Promise(value=>resolve=value);return {promise,resolve}}
function store(value){const listeners=new Set();return {getSnapshot:()=>value,subscribe:fn=>{listeners.add(fn);return()=>listeners.delete(fn)},
 set:next=>{value=next;for(const listener of [...listeners])listener()},listeners}}
function element(){return {style:{},dataset:{},children:[],setAttribute(){},appendChild(child){this.children.push(child)},remove(){this.removed=true}}}

async function fixture(options={}){
 const target={workspaceId:'w',sessionId:'houdini-a',executorId:'executor-a',source:'menu',...options.target}
 const row=(id,preset)=>({id,cwd:'E:/fixture',blank:false,projectionValues:{agentPreset:preset}})
 const sessions=store({phase:'ready',ids:['standard','houdini-a'],byId:{standard:row('standard','standard'),'houdini-a':row('houdini-a',options.preset||'houdini')},
  projectionsBySession:{'houdini-a':{values:{houdiniExecutorIdentity:{target:{executor_id:options.executor||'executor-a'}}}}}})
 const workspaces=store({phase:'ready',state:'idle',archivedSessionIds:[],items:[{workspaceId:'w',path:'E:/fixture',sessionIds:['standard','houdini-a']}]})
 const current=store({key:options.current||'standard'}), generation=store(1)
 const opened=[],acks=[],calls=[],disposers=[],slotsMap=new Map(),pending=[]
 let navigation=new AbortController(),load,refreshGate=options.refreshGate
 const layout={beginNavigation(){navigation.abort();navigation=new AbortController();return navigation.signal},selectPanel(){navigation.abort()}}
 const connection={generation,rpc:{call:async(_namespace,method,payload,signal)=>{
  const input=payload.args?.input;calls.push({method,input,signal})
  if(method==='houdiniFrontend/desktopIntent')return new Promise((resolve,reject)=>{
   const request={input,resolve:value=>resolve({ok:true,value})};pending.push(request)
   signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true})
  })
  if(method==='houdiniFrontend/desktopIntentAck'){acks.push(input.sequence);return {ok:true,value:{acknowledged:true}}}
  throw Error('Unexpected RPC '+method)
 }}}
 const uiWorkspace={openSession:id=>{opened.push(id);if(!options.rejectSelection)current.set({key:id});layout.selectPanel()}}
 const services={connection,layout,uiSession:{adapter:{current},sessionStatus:store(new Map())},uiWorkspace,
  sessions:{list:sessions,refresh:async()=>{if(refreshGate)await refreshGate.promise},refreshProjections:async()=>{}},workspaces:{list:workspaces},
  configForms:{whileServed:(_names,fn)=>fn(),get:()=>({})},
  slots:{inject:(_name,install)=>{const stop=install();if(stop)disposers.push(stop);return stop},register:(entry,Component)=>{
   assert(!slotsMap.has(entry.id),'duplicate slot '+entry.id);slotsMap.set(entry.id,{entry,Component});return()=>slotsMap.delete(entry.id)
  }}}
 const window={__ModuleLoader__:{load:value=>load=value}},document={head:element(),body:element(),querySelector:()=>({}),createElement:element}
 vm.runInNewContext(source,{window,document,URL,AbortSignal,AbortController,setTimeout,clearTimeout,setInterval,clearInterval,console})
 const React={createElement:(type,props,...children)=>({type,props:props||{},children}),useState:value=>[value,()=>{}],
  useEffect:()=>{},useSyncExternalStore:(_subscribe,get)=>get(),useRef:value=>({current:value})}
 const plugin=load.factory(name=>{if(name==='react')return React;throw Error(name)})
 const scope={get:name=>services[name],effect:fn=>{const stop=fn();if(stop)disposers.push(stop)}}
 plugin.apply({get:scope.get,effect:scope.effect,inject:(_deps,fn)=>fn(scope)})
 await flush()
 function intent(sequence,selection=target){const request=pending.shift();assert(request,'navigation consumer has an outstanding long poll');request.resolve({sequence,selection})}
 return {target,opened,acks,calls,slotsMap,sessions,workspaces,current,generation,layout,document,window,
  intent,async close(){for(const stop of disposers.reverse())stop();await flush()},refreshGate(value){refreshGate=value}}
}

const enabledIds=['houdini-initial-project','houdini-initial-window-pin','houdini-project-label','houdini-window-pin','houdini-project-feedback','houdini-support-report']
const app=await fixture()
assert.equal(app.calls.filter(call=>call.method==='houdiniFrontend/desktopIntent').length,1,'root client owns one consumer')
assert.deepEqual([...app.slotsMap.keys()],['houdini-navigation-feedback','houdini-video','houdini-delivery-scope'],'other modes expose no scene controls; global tutorial settings remain available')
assert.equal(app.current.getSnapshot().key,'standard')
app.current.set({key:'houdini-a'})
await flush()
for(const id of enabledIds)assert(app.slotsMap.has(id),id+' appears in Houdini mode')
assert.equal(app.slotsMap.get('houdini-window-pin').entry.name,'conversation.session.header.utilities','the exact Native rc.3 header utilities is a list; single corner is already owned by the native sidebar action')
app.current.set({key:'standard'})
await flush()
for(const id of enabledIds)assert(!app.slotsMap.has(id),id+' leaves other modes untouched')
app.intent(1);await flush()
assert.deepEqual(app.opened,['houdini-a'],'menu explicitly navigates from another mode')
assert.deepEqual(app.acks,[1],'acknowledge only after actual native selection')
assert.equal(app.current.getSnapshot().key,'houdini-a')
app.intent(2,null);await flush();assert.deepEqual(app.opened,['houdini-a'],'idle long polls never steal selection')
await app.close();assert.equal(app.slotsMap.size,0,'all entries are removed with their owner')
assert(app.document.head.children.every(child=>child.removed),'owned styles are removed with the plugin')

const launch=await fixture({target:{source:'launch'}})
launch.intent(1);await flush()
assert.deepEqual(launch.opened,[],'a late launched scene cannot reclaim another selected conversation')
assert.deepEqual(launch.acks,[1],'discarded launch does not replay on refresh')
await launch.close()

const inPlace=await fixture({current:'houdini-a',target:{source:'launch'}})
inPlace.intent(1);await flush()
assert.deepEqual(inPlace.opened,[],'the originating launch updates the existing projection without reclaiming the Conversation panel')
assert.deepEqual(inPlace.acks,[1])
await inPlace.close()

const ungrouped=await fixture({target:{workspaceId:undefined}})
ungrouped.workspaces.set({...ungrouped.workspaces.getSnapshot(),items:[]})
ungrouped.intent(1);await flush()
assert.deepEqual(ungrouped.opened,['houdini-a'],'an exact native Ungrouped conversation opens without attaching or migrating a workspace')
assert.deepEqual(ungrouped.acks,[1])
await ungrouped.close()

const gate=deferred(),superseded=await fixture({refreshGate:gate})
superseded.intent(1);await flush();superseded.layout.selectPanel();gate.resolve();await flush()
assert.deepEqual(superseded.opened,[],'native navigation supersedes a waiting menu intent')
assert.deepEqual(superseded.acks,[1])
await superseded.close()

const waiting=await fixture()
waiting.workspaces.set({...waiting.workspaces.getSnapshot(),phase:'loading'})
waiting.intent(1);await flush();waiting.current.set({key:'houdini-a'})
waiting.workspaces.set({...waiting.workspaces.getSnapshot(),phase:'ready'});await flush()
assert.deepEqual(waiting.opened,[],'a separate selection while native lists load cancels the menu intent')
assert.deepEqual(waiting.acks,[1])
await waiting.close()

const rejected=await fixture({preset:'standard'})
rejected.intent(1);await flush()
assert.deepEqual(rejected.opened,[],'an incorrectly prepared Host session is never opened as Houdini')
assert.deepEqual(rejected.acks,[],'failure is not presented as successful consumption')
const feedbackEntry=rejected.slotsMap.get('houdini-navigation-feedback').Component()
const feedback=feedbackEntry.type(feedbackEntry.props)
assert.equal(feedback.props.role,'alert')
assert.match(feedback.props.text,/没有激活 Houdini 模式/)
assert(!source.includes('__dshHoudiniSelection'),'tests and production never need a selection backdoor')
const uiImports=[...source.matchAll(/require\("(@deepseek-ai\/dsh-client-ui-[^"]+)"\)/g)].map(match=>match[1])
assert.deepEqual([...new Set(uiImports)],['@deepseek-ai/dsh-client-ui-primitives'],'only the exact public static SDK primitives are imported; provider editors remain private')
await rejected.close()

const uncommitted=await fixture({rejectSelection:true})
uncommitted.intent(1);await flush()
assert.deepEqual(uncommitted.acks,[],'an openSession invocation does not prove actual selection')
await uncommitted.close()

const changed=await fixture()
changed.intent(7,null);await flush();changed.generation.set(2);await flush()
const latest=changed.calls.filter(call=>call.method==='houdiniFrontend/desktopIntent').at(-1)
assert.equal(latest.input.after,0,'a restarted Host has its own sequence')
// Ignore the aborted request left in the fixture queue.
changed.intent(8,null);await flush();changed.intent(1);await flush();assert.deepEqual(changed.opened,['houdini-a'])
await changed.close()

assert(!source.includes('createWorkbenchUpdates('),'host update ownership remains in Desktop')
assert(!source.includes('dsh-houdini-workspace'),'no private Qt URL navigation path remains')
console.log('Desktop client: native selected session, menu/launch isolation, mode-only controls and global settings, navigation cancellation, acknowledgement and reconnect passed')
