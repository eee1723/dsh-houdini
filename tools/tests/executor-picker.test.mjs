import fs from 'node:fs/promises'
import vm from 'node:vm'
import assert from 'node:assert/strict'

const source=await fs.readFile(new URL('../../client.js',import.meta.url),'utf8')
assert(!source.includes('createExecutorPicker('),'one compact selector replaces the separate legacy dock picker')
assert(!source.includes('houdini-executor-picker'),'no duplicate executor panel is registered')
const fragment=source.slice(source.indexOf('    function Button('),source.indexOf('    // >>> houdini-node-delivery'))
const executor='a'.repeat(32),runtime='b'.repeat(32),epoch='c'.repeat(32),registration='d'.repeat(32)
const first={executor_id:executor,runtime_id:runtime,scene_epoch:epoch,scene_id:'e'.repeat(32),registration_id:registration,
  hip_path:'C:/work/ship.hip',hip_is_new:false,houdini_version:'22.0.368',workspace_path:'C:/work',state:'registered',same_workspace:true,pid:9876,workbench:true}
const second={...first,executor_id:'f'.repeat(32),hip_path:'D:/other/rocks.hip',same_workspace:false,pid:4321}
let task='task-a',generation={id:1},project=null,preset='houdini',hidden=false,failPresence=false,presenceReply=null
const native=new Map(),requests=[],projectionRefreshes=[],intervals=[],visibility=new Set(),generationListeners=new Set()
const componentHooks=new Map();let currentHooks=null,cursor=0,queued=[]
const React={
 createElement:(tag,props,...children)=>({tag,props:props||{},children:children.flat(Infinity)}),
 useState:initial=>{const i=cursor++;if(!(i in currentHooks))currentHooks[i]={value:initial};const slot=currentHooks[i];return[slot.value,next=>{slot.value=typeof next==='function'?next(slot.value):next}]},
 useRef:initial=>{const i=cursor++;return currentHooks[i]||(currentHooks[i]={current:initial})},
 useSyncExternalStore:(_subscribe,get)=>get(),
 useEffect:(effect,deps)=>{const i=cursor++;if(!currentHooks[i]||deps.some((value,index)=>!Object.is(value,currentHooks[i].deps[index]))){currentHooks[i]?.dispose?.();const slot={deps};currentHooks[i]=slot;queued.push(()=>slot.dispose=effect())}}
}
const document={get visibilityState(){return hidden?'hidden':'visible'},addEventListener:(kind,fn)=>{if(kind==='visibilitychange')visibility.add(fn)},removeEventListener:(kind,fn)=>visibility.delete(fn)}
const context={React,AbortController,AbortSignal,setTimeout,clearTimeout,setInterval:fn=>{intervals.push(fn);return intervals.length},clearInterval:()=>{},document,
 require:()=>({Tooltip:'tooltip',Menu:'menu',MenuItemButton:'menuitem',Button:'button',Toast:'toast'})}
vm.createContext(context);vm.runInContext(fragment,context)
const observed=record=>({executorId:record.executor_id,runtimeId:record.runtime_id,sceneEpoch:record.scene_epoch,hipPath:record.hip_path,
 status:'online',observedAt:Date.now(),ownerSessionId:null,activeRequests:0,activeJobs:0,busy:false,candidate:record})
const saved={...first,hip_path:'D:/delivery/ship-final.hip',hip_is_new:false,workspace_path:'D:/delivery'}
const unsaved={target:{...first,hip_path:'C:/work/untitled.hip',hip_is_new:true,label:'未保存工程'},hipPath:'C:/work/untitled.hip',hipIsNew:true}
const originalSelection=JSON.stringify(unsaved)
const fresh={available:true,visible:true,observedAt:Date.now(),records:{[executor]:observed(saved)}}
assert.equal(context.houdiniProjectName(context.houdiniDisplayProject(unsaved,fresh)),'ship-final.hip','Save As updates the displayed current HIP without a new tool call')
const samePathUnsaved={...unsaved,target:{...unsaved.target,hip_path:saved.hip_path}}
assert.equal(context.houdiniProjectName(context.houdiniDisplayProject(samePathUnsaved,fresh)),'ship-final.hip','saving to the same filename still updates the unsaved state')
assert.equal(context.houdiniProjectName({target:saved,hipIsNew:true}),'ship-final.hip','the selected target’s explicit saved state takes precedence over stale outer compatibility fields')
assert.equal(JSON.stringify(unsaved),originalSelection,'live presentation never rewrites the native selection or conversation cwd')
for(const patch of [{status:'offline'},{status:'unknown'},{contractMismatch:true},{observedAt:Date.now()-20000},
 {runtimeId:'9'.repeat(32)},{sceneEpoch:'9'.repeat(32)},{sceneId:'9'.repeat(32)},{candidate:{...saved,executor_id:'9'.repeat(32)}},
 {candidate:{...saved,runtime_id:'9'.repeat(32)}},{candidate:{...saved,scene_epoch:'9'.repeat(32)}},{candidate:{...saved,scene_id:'9'.repeat(32)}}]){
 const snapshot={...fresh,records:{[executor]:{...observed(saved),...patch}}}
 assert.equal(context.houdiniDisplayProject(unsaved,snapshot),unsaved,'an unconfirmed or different live scene cannot rename the historical selected target')
}
assert.equal(context.houdiniDisplayProject(unsaved,{...fresh,visible:false}),unsaved)
assert.equal(context.houdiniDisplayProject(unsaved,{...fresh,observedAt:Date.now()-20000}),unsaved)
const pendingReview={...unsaved,needsReview:true}
assert.equal(context.houdiniDisplayProject(pendingReview,fresh),pendingReview)
let observations=[observed(first),observed(second)]
const connection={generation:{getSnapshot:()=>generation,subscribe:fn=>{generationListeners.add(fn);return()=>generationListeners.delete(fn)}},rpc:{call:async(_channel,method,payload,signal)=>{
 requests.push({method,payload,signal})
 if(method==='houdiniFrontend/capabilities')return{ok:true,value:{desktop:true}}
 if(method==='houdiniFrontend/windowPin')return{ok:true,value:{pinned:false}}
 if(method==='houdiniFrontend/projectPresence'){if(presenceReply)return presenceReply();if(failPresence)throw Error('connection lost');return{ok:true,value:observations}}
 if(method==='houdiniTargets/select')return{ok:true,value:{status:'selected',sessionId:task,selectedTarget:first}}
 if(method==='houdiniTargets/clear')return{ok:true,value:{selectedTarget:null}}
 throw Error('unexpected RPC '+method)
}}}
const ui=context.createHoudiniDesktopUi(connection,{sessionStatus:{getSnapshot:()=>native,subscribe:()=>()=>{}},adapter:{current:{getSnapshot:()=>({key:task}),subscribe:()=>()=>{}}}},
 {refreshProjections:async id=>projectionRefreshes.push(id)})
const props=()=>({sessionId:task,useSessions:select=>select({byId:{[task]:{id:task,cwd:'C:/work',blank:false,projectionValues:{agentPreset:preset}}},projectionsBySession:{[task]:{values:{houdiniExecutorIdentity:project}}}})})
function render(component,parameters=props()){
 if(!componentHooks.has(component))componentHooks.set(component,[])
 currentHooks=componentHooks.get(component);cursor=0
 const tree=component(parameters);while(queued.length)queued.shift()()
 return tree
}
function expand(node){if(!node||typeof node!=='object')return node;if(typeof node.tag==='function')return expand(node.tag({...node.props,children:node.children}));return node}
function nodes(tree){const n=expand(tree);return !n||typeof n!=='object'?[]:[n,...(n.props.anchor?[n.props.anchor]:[]).flatMap(nodes),...n.children.flatMap(nodes)]}
const by=(tree,predicate)=>nodes(tree).find(predicate)
const chip=tree=>by(tree,n=>n.props['data-houdini-project-label'])
const text=tree=>{const n=expand(tree);return typeof n==='string'?n:n&&typeof n==='object'?n.children.map(text).join(''):''}
const settle=async()=>{await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve))}
render(ui.Lifecycle);await settle()
const menu=ui.Label(props()).tag
let tree=render(menu);tree=render(menu)
assert.equal(chip(tree).props['data-state'],'unbound')
assert.match(text(chip(tree)),/未绑定工程/)
assert.equal(requests.filter(r=>r.method==='houdiniTargets/list').length,0,'observing visible state never polls conversation lists')
chip(tree).props.onClick();await settle();tree=render(menu)
assert.equal(Boolean(by(tree,n=>n.props.role==='menu')),true)
const candidates=nodes(tree).filter(n=>n.props['data-houdini-target'])
assert.deepEqual(candidates.map(n=>n.props['data-houdini-target']),[executor,second.executor_id],'unbound windows keep their observation order without implying workspace membership')
assert.match(text(tree),/可选工程/)
assert(!/同一工作区|其他工作区/.test(text(tree)))
assert.match(text(candidates[0]),/work · Houdini 22 · 已就绪/)
assert(!text(candidates[0]).includes('9876'),'PID is confined to the optional tooltip')
const choose=tree=>by(tree,n=>n.props.role==='menuitem'&&by(n,child=>child.props['data-houdini-target']===executor))
choose(tree).props.onClick();await settle();tree=render(menu)
const selectedCall=requests.find(r=>r.method==='houdiniTargets/select')
assert.equal(selectedCall.payload.args.input.sessionId,'task-a')
assert.equal(selectedCall.payload.args.input.runtimeId,runtime)
assert.equal(selectedCall.payload.args.input.sceneEpoch,epoch)
assert.equal(selectedCall.payload.args.input.expectedHip,first.hip_path)
assert.deepEqual(projectionRefreshes,['task-a'])
assert.equal(chip(tree).props['data-state'],'unbound','a successful RPC cannot create a second frontend binding source')
project={target:first,executorId:executor,runtimeId:runtime,sceneEpoch:epoch,hipPath:first.hip_path,hipIsNew:false}
tree=render(menu);assert.equal(chip(tree).props['data-state'],'ready')
project=unsaved;observations=[observed(second),observed(saved)];intervals.at(-1)();await settle();tree=render(menu)
if(!by(tree,n=>n.props.role==='menu')){chip(tree).props.onClick();await settle();tree=render(menu)}
assert.match(text(chip(tree)),/ship-final\.hip/)
assert(!text(chip(tree)).includes('未保存工程'))
assert.match(text(tree),/ship-final\.hip.*当前工程.*其他工程/)
assert.equal(nodes(tree).filter(n=>n.props['data-houdini-target'])[0].props['data-houdini-target'],executor,'the selected scene stays first after Save As outside the conversation cwd')
assert.match(text(tree),/D:\/delivery\/ship-final\.hip/)
assert(by(tree,n=>n.props['data-houdini-project-action']==='reopen'),'the currently saved live file can be reopened even if the historical selection was unsaved')
assert.equal(JSON.stringify(project),originalSelection)
project={target:first,executorId:executor,runtimeId:runtime,sceneEpoch:epoch,hipPath:first.hip_path,hipIsNew:false}
observations=[observed(first),observed(second)];intervals.at(-1)();await settle();tree=render(menu)
native.set(task,{running:true});tree=render(menu);assert.equal(chip(tree).props['data-state'],'working');assert.match(text(chip(tree)),/对话工作中/)
if(!Boolean(by(tree,n=>n.props.role==='menu'))){chip(tree).props.onClick();await settle();tree=render(menu)}
assert.equal(by(tree,n=>n.props['data-houdini-target']===second.executor_id).props['data-state'],'ready','a running current conversation cannot mark a different idle candidate as its work')
assert.equal(by(tree,n=>n.props['data-houdini-target']===first.executor_id).props['data-state'],'working','the selected candidate retains the actual current conversation activity')
native.set(task,{running:false});observations[0]={...observed(first),ownerSessionId:'other',busy:false}
intervals.at(-1)();await settle();tree=render(menu);assert.equal(chip(tree).props['data-state'],'ready','an idle writer reservation is not active work')
native.set('other',{running:true});tree=render(menu);assert.equal(chip(tree).props['data-state'],'occupied')
if(!Boolean(by(tree,n=>n.props.role==='menu'))){chip(tree).props.onClick();await settle();tree=render(menu)}
assert.equal(choose(tree).props.disabled,false,'another busy conversation does not prevent choosing a read-only target')
native.set('other',{running:false});native.set('reader-b',{running:true})
observations[0]={...observed(first),ownerSessionId:task,activeRequests:1,busy:true}
intervals.at(-1)();await settle();tree=render(menu)
assert.equal(chip(tree).props['data-state'],'working');assert.match(text(chip(tree)),/工程处理中/,'an idle writer cannot claim another conversation’s read request')
const reading=context.houdiniPresence(project,{available:true,visible:true,observedAt:Date.now(),records:{[executor]:observations[0]}},'reader-b',native)
assert.equal(reading.state,'working');assert.equal(reading.label,'对话工作中','the running read-only conversation is not marked occupied by an idle writer')
const unrelated=context.houdiniPresence(project,{available:true,visible:true,observedAt:Date.now(),records:{[executor]:observations[0]}},'observer-c',native)
assert.equal(unrelated.label,'工程处理中','request ownership is unknown without a running native current/owner or writer job')
native.set('reader-b',{running:false});observations[0]={...observed(first),ownerSessionId:task,activeJobs:1,busy:true}
intervals.at(-1)();await settle();tree=render(menu);assert.equal(chip(tree).props['data-state'],'working','Bridge jobs remain busy after a native agent stops')
const selectedBeforeChanged=JSON.stringify(project)
for(const patch of [{status:'changed'},{sceneId:'9'.repeat(32)}]){
 observations[0]={...observed(first),...patch};intervals.at(-1)();await settle();tree=render(menu)
 assert.equal(chip(tree).props['data-state'],'changed','a known changed observation or scene ID cannot be presented as unknown or ready')
 assert.match(text(chip(tree)),/场景已变化/);assert.match(text(chip(tree)),/ship\.hip/)
 assert.equal(JSON.stringify(project),selectedBeforeChanged,'known changes preserve the original selected scene')
}
for(const sceneId of [undefined,'']){
 observations[0]={...observed(first),sceneId};intervals.at(-1)();await settle();tree=render(menu)
 assert.equal(chip(tree).props['data-state'],'ready','missing legacy scene ID is not evidence of a scene change')
}
observations[0]={...observed(first),runtimeId:'9'.repeat(32)};intervals.at(-1)();await settle();tree=render(menu);assert.equal(chip(tree).props['data-state'],'changed')
observations[0]={...observed(first),status:'offline'};intervals.at(-1)();await settle();tree=render(menu);assert.equal(chip(tree).props['data-state'],'offline')
assert(!by(tree,n=>n.props['data-houdini-target']===first.executor_id),'a dead process must leave the candidate list even when its old record still says registered')
assert.match(text(tree),/ship\.hip.*已断开/,'the original conversation keeps its offline selection')
observations=[observed(first),observed(second)];intervals.at(-1)();await settle();tree=render(menu);assert.equal(chip(tree).props['data-state'],'ready')
const third={...second,executor_id:'1'.repeat(32),hip_path:'D:/other/new-window.hip'}
observations.push(observed(third));intervals.at(-1)();await settle();tree=render(menu)
assert(by(tree,n=>n.props['data-houdini-target']===third.executor_id),'a newly connected window appears while the menu stays open')
observations[2]={...observed(third),status:'unknown'};intervals.at(-1)();await settle();tree=render(menu)
assert.equal(by(tree,n=>n.props['data-houdini-target']===third.executor_id).props['data-state'],'unknown','a live but unresponsive process remains available for confirmation')
const changedThird={...third,registration_id:'2'.repeat(32),scene_epoch:'3'.repeat(32),hip_path:'D:/other/changed.hip'}
observations[2]=observed(changedThird);intervals.at(-1)();await settle();tree=render(menu)
assert.match(text(by(tree,n=>n.props['data-houdini-target']===third.executor_id)),/changed\.hip/,'an existing window changes its file without retaining the old list snapshot')
assert.equal(requests.filter(r=>r.method==='houdiniTargets/list').length,0,'membership and state consume one live projection')
const beforePress=by(tree,n=>n.props.role==='menuitem'&&by(n,child=>child.props['data-houdini-target']===third.executor_id))
beforePress.props.onPointerDown()
const pressedHip=changedThird.hip_path
observations[2]=observed({...changedThird,hip_path:'D:/other/late-scene.hip',scene_epoch:'6'.repeat(32)})
intervals.at(-1)();await settle();tree=render(menu)
const afterPress=by(tree,n=>n.props.role==='menuitem'&&by(n,child=>child.props['data-houdini-target']===third.executor_id))
afterPress.props.onClick({type:'click',detail:1});await settle();tree=render(menu)
assert.equal(requests.filter(r=>r.method==='houdiniTargets/select').at(-1).payload.args.input.expectedHip,pressedHip,'the actual rendered button forwards pointer-down and preserves the pressed scene when click dispatches')

observations=[observed(first),observed(second)];intervals.at(-1)();await settle();tree=render(menu)
hidden=true;visibility.forEach(fn=>fn());tree=render(menu);assert.equal(chip(tree).props['data-state'],'unknown','hidden pages cannot retain a green reachable badge')
hidden=false;visibility.forEach(fn=>fn());await settle();tree=render(menu);assert.equal(chip(tree).props['data-state'],'ready')
failPresence=true;intervals.at(-1)();await settle();tree=render(menu);assert.equal(chip(tree).props['data-state'],'unknown','transport failures invalidate reachable state')
failPresence=false;observations[0]={...observed(first),observedAt:Date.now()-20000};intervals.at(-1)();await settle();tree=render(menu);assert.equal(chip(tree).props['data-state'],'unknown','a fresh response cannot refresh an old individual observation')
observations=[observed(first),observed(second)];intervals.at(-1)();await settle();tree=render(menu)
if(!Boolean(by(tree,n=>n.props.role==='menu'))){chip(tree).props.onClick();await settle();tree=render(menu)}
const clearAction=by(tree,n=>n.props.role==='menuitem'&&by(n,child=>child.props['data-houdini-project-action']==='clear'))
assert(clearAction)
clearAction.props.onClick();await settle();tree=render(menu)
assert.equal(chip(tree).props['data-state'],'ready','clearing waits for the authoritative native projection')
project=null;tree=render(menu);assert.equal(chip(tree).props['data-state'],'unbound')
let resolveList;presenceReply=()=>new Promise(resolve=>resolveList=resolve)
chip(tree).props.onClick();await settle();const stale=requests.at(-1)
task='task-b';tree=render(menu);tree=render(menu);assert.equal(stale.signal.aborted,false,'the shared read-only presence is independent of the selected conversation')
resolveList({ok:true,value:[observed(first)]});await settle();tree=render(menu)
assert.equal(Boolean(by(tree,n=>n.props.role==='menu')),false,'a late list must not reopen another conversation')
assert.equal(chip(tree).props['data-state'],'unbound')
presenceReply=null
chip(tree).props.onClick();await settle();tree=render(menu);chip(tree).props.onClick();tree=render(menu)
let finishClosed;presenceReply=()=>new Promise(resolve=>finishClosed=resolve)
chip(tree).props.onClick();await settle();tree=render(menu);chip(tree).props.onClick()
finishClosed({ok:true,value:[observed(first)]});await settle();tree=render(menu)
assert.equal(Boolean(by(tree,n=>n.props.role==='menu')),false,'a slow refresh cannot reopen a dismissed menu')
generation=undefined;generationListeners.forEach(fn=>fn());tree=render(menu);assert.equal(chip(tree).props['data-state'],'unbound')
preset='standard';assert.equal(ui.Label(props()),null,'other presets do not mount the Houdini selector')
assert(!source.includes('dangerouslySetInnerHTML'))
console.log('compact Houdini selector: native projection authority, explicit choices/clear, grouped targets, native/Bridge activity, visibility/transport freshness and stale request isolation passed')
