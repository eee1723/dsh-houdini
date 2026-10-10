import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import {Context} from '@deepseek-ai/cordis'
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt'
import {ToolRuntime} from '@deepseek-ai/dsh-tools'
import {Session} from '@deepseek-ai/dsh-session'
import {createToolResultMessage} from '@deepseek-ai/dsh-llm'
import {validateStoredEvents} from '@deepseek-ai/dsh-session-persistence'
import {registerHoudiniTools} from '../../lib/tools.js'
import {installHoudiniExecutionLog} from '../../lib/dsh-adapter.js'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {generatedNodeDeliveryBlock,generatedNodeDeliveryFactory} from '../gen-trace-client.mjs'

const read = file => fs.readFileSync(new URL('../../'+file,import.meta.url),'utf8').replaceAll('\r\n','\n')
const client = read('client.js')
assert(client.includes(generatedNodeDeliveryBlock()),'production client must embed the maintained factory')
assert(client.includes('conversation.events.register(delivery.definition)'))
assert(client.includes('conversation.views.register(delivery.view)'))
assert(client.includes('name: "conversation.chat.turnTail", id: "houdini-node-delivery"'))
const parser = client.slice(client.indexOf('    function readHoudiniCanonical('),client.indexOf('    // This is a last-observed fact'))
const factory = vm.runInNewContext('('+generatedNodeDeliveryFactory()+')',{AbortController,setTimeout,clearTimeout})
const readCanonical = vm.runInNewContext(parser+'\nreadHoudiniCanonical;')
const projection = factory({},readCanonical)

// Execute the released public DSH assembler itself. Its browser bundle includes
// React/DOM code; load just the unchanged target-neutral contract and assembly
// regions so the check does not replace DSH grouping or Location resolution.
const dshSource = fs.readFileSync('node_modules/@deepseek-ai/dsh-client-ui-conversation/lib/client.js','utf8')
const core = dshSource.slice(dshSource.indexOf('//#region lib/types/client/contract/conversation.js'),dshSource.indexOf('//#region lib/types/client/conversation/definition-registry.js'))
const Assembler = vm.runInNewContext(core+'\nConversationNodeAssembler;',{})
function assemble(events) {
  const assembler = new Assembler({entries:()=>[projection.definition],fallbackEntry:()=>undefined},{entries:()=>[projection.view]})
  assembler.replaceWindow(events.map(event=>({type:'event',event})),false)
  assembler.activateTarget(projection.view.target)
  assembler.flush()
  return assembler
}
const executorId='a'.repeat(32), uuid='c'.repeat(32)
const ctx=new Context()
new SystemPrompt(ctx,{})
const runtime=new ToolRuntime(ctx,{mode:'both'})
installHoudiniExecutionLog(ctx)
const session=Session.create('node-delivery-client-task-a')
await new ExecutorBinding().ensure(session,executorId)
const agent={id:session.id,session,options:{provider:'fixture',model:'text'}}
const receipt={ok:true,stdout:'',stderr:'',result:{kind:'houdini/node-delivery-v1',nodes:[
  {id:uuid,path:'/obj/bicycle/CTRL',label:'工程控制',role:'control',type:'null',context:'Sop',description:'调整尺寸和重复数量'},
  {id:'d'.repeat(32),path:'/obj/bicycle/OUT',label:'模型输出',role:'output',type:'null'}
]},execution:{executor_id:executorId,runtime_id:'b'.repeat(32),hip_path:'E:/fixture/bicycle.hip',owner_session:session.id}}
receipt.verbs=[{verb:'present_nodes',ok:true,result:receipt.result}]
// Wrapping or omitting the model return must not suppress the original declaration.
receipt.result={entries:receipt.result,other:'unrelated result'}
let executed=0
registerHoudiniTools(ctx,{targetExecutorId:executorId,async exec(){executed++;return structuredClone(receipt)}})
ctx.provide('ptcRuntime',{language:'typescript',resolve:request=>request,async run(request){
  const value=await request.bindings[0].functions.houdini_exec({code:'__result__=deliver_nodes(...)'})
  return {value,logs:[]}
}})
const signal=new AbortController().signal
session.append('turn/start',{turn:1})
session.append('step/start',{turn:1,step:1})
async function run(callId,name,args) {
  session.append('tool/call',{turn:1,step:1,callId,name,arguments:JSON.stringify(args)})
  const result=await runtime.execute({callId,name,arguments:args,agent,signal})
  assert.equal(result.isError,false,JSON.stringify(result))
  session.append('tool/result',{turn:1,step:1,message:createToolResultMessage({callId,content:result.content,isError:result.isError}),
    ...(result.meta===undefined?{}:{meta:result.meta})},{surfaceOp:'append'})
  return result
}
await run('native','houdini_exec',{code:'delivery'})
const nativeEvent=session.snapshotEvents().find(event=>event.type==='tool/result')
receipt.verbs[0].result.nodes[0].path='/obj/bicycle/CTRL_RENAMED'
await run('program','run_code',{code:'return await tools.houdini_exec({code:"delivery"})',description:'Deliver Houdini nodes'})
assert.equal(executed,2,'projection must not repeat scene operations')
const nestedEvent=session.snapshotEvents().find(event=>event.type==='tool/ptc-dispatch')
assert.equal(nestedEvent.data.turn,undefined,'actual PTC event has no invented turn field')
assert.equal(nestedEvent.data.rootCallId,'program')
const events=session.snapshotEvents()
const assembler=assemble(events)
const owner={sessionId:session.id,turn:{turn:1},seq:events.at(-1).seq+1}
const cards=projection.forClosing(assembler.snapshot(projection.view.target),owner)
assert.equal(cards.length,2,'latest declaration of each persistent identity appears once')
assert.equal(cards[0].path,'/obj/bicycle/CTRL_RENAMED')
assert.equal(cards[0].eventSeq,nestedEvent.seq)
assert.equal(cards[0].index,0)
assert.equal(cards[0].description,'调整尺寸和重复数量')
assert.equal(cards[0].context,'Sop')
assert.equal(cards[0].callId,nestedEvent.data.subCallId)
assert.equal(projection.forClosing(assembler.snapshot(projection.view.target),{...owner,turn:{turn:2}}).length,0)
assert.equal(projection.forClosing(assembler.snapshot(projection.view.target),{...owner,sessionId:'another-task'}).length,0,'execution owner must be the selected task')
const beforeNested=projection.forClosing(assembler.snapshot(projection.view.target),{...owner,seq:nestedEvent.seq})
assert.equal(beforeNested[0].path,'/obj/bicycle/CTRL','closing sequence excludes later observations')
const stored=validateStoredEvents(session.header,JSON.parse(JSON.stringify(events)))
const restored=Session.create(session.id,stored,session.header)
assert.equal(JSON.stringify(projection.forClosing(assemble(restored.snapshotEvents()).snapshot(projection.view.target),owner)),JSON.stringify(cards),
  'real native and PTC delivery projection survives durable DSH replay')

const fake=(type,data,seq=100,surfaceOp='append')=>({type,data,seq,time:seq,surfaceOp})
const start={event:fake('tool/call',{callId:'invalid',name:'houdini_exec'})}
const empty=projection.definition.start({},start)
function rejected(event) {
  assert.equal(projection.definition.update({state:empty},{event}),empty)
}
rejected(fake('tool/result',{message:{source:{callId:'invalid'}},meta:{canonical:{...receipt,verbs:[],result:receipt.verbs[0].result}}}))
rejected(fake('tool/result',{message:{source:{callId:'invalid'},isError:true},meta:{canonical:receipt}}))
rejected(fake('tool/result',{message:{source:{callId:'invalid'},isError:false},meta:{canonical:{...receipt,ok:false}}}))
rejected(fake('tool/result',{message:{source:{callId:'invalid'},isError:false},meta:{canonical:{...receipt,outcome:{operations:{failed:1}}}}}))
rejected(fake('tool/result',{message:{source:{callId:'invalid'},isError:false},meta:{canonical:{...receipt,verbs:[{name:'deliver_nodes',ok:false}]}}}))
rejected(fake('tool/result',{message:{source:{callId:'invalid'},isError:false},meta:{canonical:{...receipt,execution:{...receipt.execution,owner_session:''}}}}))
rejected(fake('tool/result',{message:{source:{callId:'invalid'},isError:false,content:[{type:'text',text:JSON.stringify(receipt)}]}}))
const ptcData={rootCallId:'parent',parentCallId:'parent',subCallId:'child',name:'houdini_exec',isError:false}
const wrapper=(callId='child',tool='houdini_exec')=>[{type:'text',text:JSON.stringify({kind:'dsh-houdini/execution-v1',callId,tool,value:receipt})}]
rejected(fake('tool/ptc-dispatch',{...ptcData,content:wrapper('wrong-call')}))
rejected(fake('tool/ptc-dispatch',{...ptcData,content:wrapper('child','wrong-tool')}))
rejected(fake('tool/ptc-dispatch',{...ptcData,isError:true,content:wrapper()}))
assert.equal(projection.definition.match(fake('tool/result',{message:{source:{callId:'invalid'}}},100,'replace')),null,
  'surface replacement is not an original completed call')

// Invalid array members retain their original index; the Host resolves that
// exact event coordinate rather than trusting any browser-supplied node path.
const indexed={...receipt,verbs:[{verb:'present_nodes',ok:true,result:{kind:'houdini/node-delivery-v1',nodes:[{id:'bad'},receipt.verbs[0].result.nodes[1]]}}]}
const indexState=projection.definition.update({state:empty},{event:fake('tool/result',{message:{source:{callId:'invalid'}},meta:{canonical:indexed}})})
assert.equal(indexState.nodes[0].index,1)
const declarations={...receipt,result:null,verbs:[receipt.verbs[0],{verb:'present_nodes',ok:true,result:{kind:'houdini/node-delivery-v1',nodes:[receipt.verbs[0].result.nodes[0]]}}]}
const multiple=projection.definition.update({state:empty},{event:fake('tool/result',{message:{source:{callId:'invalid'}},meta:{canonical:declarations}})})
assert.equal(multiple.nodes.length,3,'each explicit declaration is retained even without a Python return')
assert.equal(multiple.nodes[2].index,2,'Host and client share flattened verb-declaration coordinates')
const liveAssembler=assemble(events.slice(0,2))
for(const event of events.slice(2)){liveAssembler.append({type:'event',event});liveAssembler.flush()}
assert.equal(JSON.stringify(projection.forClosing(liveAssembler.snapshot(projection.view.target),owner)),JSON.stringify(cards),'live append and reopened history have the same facts')
liveAssembler.replaceWindow(events.map(event=>({type:'event',event})),false);liveAssembler.flush()
assert.equal(projection.forClosing(liveAssembler.snapshot(projection.view.target),owner).length,2,'reconnect replay does not duplicate deliveries')

// Exercise the actual React component callbacks with observable Host generation
// and current-slot task props, including two clicks before React can repaint.
const hooks=[],effects=[];let cursor=0,task=session.id,generation={id:1},requests=[],response
const React={
  createElement:(tag,props,...children)=>({tag,props:props||{},children:children.flat(Infinity)}),
  useRef:value=>{const index=cursor++;return hooks[index]||(hooks[index]={current:value})},
  useState:value=>{const index=cursor++;if(!(index in hooks))hooks[index]=value;return [hooks[index],next=>hooks[index]=typeof next==='function'?next(hooks[index]):next]},
  useSyncExternalStore:(_subscribe,getSnapshot)=>getSnapshot(),
  useEffect:(fn,deps)=>{const index=cursor++;if(!hooks[index]||deps.some((dep,i)=>!Object.is(hooks[index].deps[i],dep))){
    hooks[index]?.dispose?.();hooks[index]={deps};effects.push(()=>hooks[index].dispose=fn())
  }}
}
const connection={generation:{subscribe:()=>()=>{},getSnapshot:()=>generation},rpc:{call:async(channel,endpoint,payload,signal)=>{
  requests.push({channel,endpoint,payload,signal});return typeof response==='function'?response():response
}}}
const snapshots={[session.id]:assembler.snapshot(projection.view.target),'task-b':{calls:[]}}
const selected=[]
const conversation={binding:id=>{selected.push(id);return {target:target=>{
  assert.equal(target,projection.view.target);return {subscribe:()=>()=>{},getSnapshot:()=>snapshots[id]}
}}}}
const ui=factory(React,readCanonical)
const tail=ui.createTail(connection,conversation)
const tailTree=tail({...owner,sessionId:task})
assert.equal(selected.at(-1),task,'tail source comes from the currently selected slot Session')
const cardElement=tailTree.children[0]
const card=cardElement.tag
function render(node=cards[0]) {
  cursor=0
  const tree=card({sessionId:task,node})
  while(effects.length)effects.shift()()
  return tree
}
const nodes=tree=>tree&&typeof tree==='object'?[tree,...tree.children.flatMap(nodes)]:[]
const copy=tree=>tree&&typeof tree==='object'?tree.children.map(copy).join(''):typeof tree==='string'?tree:''
const button=tree=>nodes(tree).find(node=>node.tag==='button')
const message=tree=>nodes(tree).filter(node=>node.props.role==='status').map(copy).join('')
const settle=()=>new Promise(resolve=>setImmediate(resolve))
let resolve
response=()=>new Promise(r=>resolve=r)
let tree=render()
assert.equal(button(tree).props.className,'dsh-houdini-node-open','the complete node tile is the primary action')
assert.equal(button(tree).props['aria-label'],'打开控制：工程控制')
assert(copy(button(tree)).includes('工程控制')&&!copy(button(tree)).includes('CTRL_RENAMED'),'the compact reading line leads with the purpose and keeps technical names in details')
assert(!copy(button(tree)).includes(cards[0].path),'full path stays in expandable details rather than the primary reading line')
const details=nodes(tree).find(node=>node.tag==='details')
assert(details&&!details.props.open&&copy(details).includes(cards[0].path),'the real path remains available in closed native details')
assert(copy(details).includes('控制'),'the role remains available in details')
assert.equal(nodes(details).find(node=>node.tag==='summary').props['aria-label'],'节点详情','the icon-only disclosure has an accessible name')
assert.equal(nodes(button(tree)).filter(node=>node.tag==='button'||node.tag==='summary').length,1,'navigation and details never nest interactive controls')
assert(ui.css.includes('[data-conversation-content]:has([data-houdini-workspace]) [data-presented-file]'),'file appearance is scoped to the selected Houdini task')
assert(ui.css.includes('[data-presented-description]:not([data-error])'),'file error presentation retains DSH ownership')
button(tree).props.onClick();button(tree).props.onClick();await settle()
assert.equal(requests.length,1,'rapid repeat click submits exactly one GUI request')
assert.equal(requests[0].endpoint,'houdiniFrontend/openNode')
assert.equal(requests[0].channel,'/api')
assert.equal(JSON.stringify(requests[0].payload),JSON.stringify({args:{input:{sessionId:session.id,eventSeq:cards[0].eventSeq,index:0,callId:cards[0].callId}}}))
assert(!JSON.stringify(requests[0].payload).includes(cards[0].path),'browser cannot choose a target path or runtime')
tree=render();assert.equal(button(tree).props.disabled,true)
task='task-b';render();assert.equal(requests[0].signal.aborted,true,'changing task aborts its pending interaction')
resolve({ok:true,value:{ok:true}});await settle();tree=render()
assert.equal(message(tree),'','late task-a response must not announce a task-b success')
response={ok:false,error:{message:'当前工程与交付工程不同'}}
button(tree).props.onClick();await settle();tree=render()
assert.equal(requests.at(-1).payload.args.input.sessionId,'task-b','click uses current slot Session, independent of receipt owner')
assert.equal(message(tree),'当前工程与交付工程不同','Host refusal is actionable and visible')
response={ok:true,value:{ok:true}}
button(tree).props.onClick();await settle();tree=render()
assert.equal(message(tree),'已打开控制','failed requests allow an explicit retry')
response=()=>new Promise(r=>resolve=r)
button(tree).props.onClick();await settle()
const stale=requests.at(-1)
generation=undefined;tree=render();assert.equal(stale.signal.aborted,true)
assert.equal(button(tree).props.disabled,true,'disconnected Host cannot receive a GUI request')
resolve({ok:true,value:{ok:true}});await settle();tree=render()
assert.equal(message(tree),'','old connection cannot publish success')
generation={id:2};render()
response={ok:true,value:{ok:false,message:'节点已删除'}}
button(render()).props.onClick();await settle()
assert.equal(message(render()),'节点已删除','Bridge refusal cannot masquerade as an opened node')
task=session.id;render()
const outputTree=render(cards[1])
assert.equal(button(outputTree).props['aria-label'],'定位节点：模型输出')
assert(copy(button(outputTree)).includes('模型输出')&&copy(button(outputTree)).includes('定位'))
assert.equal(ui.createTail(connection,conversation)({...owner,sessionId:'task-b'}),null,'another selected task never shows task-a delivery cards')
for(const hook of hooks)hook?.dispose?.()
console.log('node deliveries: actual DSH native/PTC dispatch, released public assembler, durable/live replay, selected-task RPC, rapid-click lock, reconnect isolation and visible refusal passed')
