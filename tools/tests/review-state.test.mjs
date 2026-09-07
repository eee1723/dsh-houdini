import assert from 'node:assert/strict'
import {ReviewController,reviewScope,reviewTaskMaterials,reviewPriorEvidence} from '../../lib/review.js'
import {registerHoudiniTools} from '../../lib/tools.js'

const events=[{type:'user/message',data:{content:[{type:'text',text:'Build a configurable generic asset.'},{type:'image',attachment:{id:'user-reference'}}]}},
  {type:'user/message',data:{content:[{type:'text',text:'Current runtime context. not task material'}]}},
  {type:'assistant/message',data:{message:{content:[{type:'text',text:'AUTHOR CLAIMS EVERYTHING PERFECT'}]}}},
  {type:'tool/call',data:{name:'ask_user_question',callId:'q',arguments:'{"questions":[]}'}},
  {type:'tool/result',data:{message:{source:{callId:'q'},content:[{type:'tool_result',content:[{type:'text',text:'User chose network and preview'}]}]}}}]
let runtime,mode='success',requestSeen,released=0,child,disposeCount=0,controller
const bridge={async review(request,owner){
  if(request.action==='begin')return {ok:true,result:{token:'PRIVATE-TOKEN',scope:{parent:'/obj/g',output:'/obj/g/OUT',controller:'/obj/g/C'},snapshot:{test_support:{supported:false,reason:'unsupported fixture'}}}}
  if(request.action==='end'){released++;if(mode==='release-failure')throw new Error('restoration fault at release')}
  if(request.action==='test')return {ok:true,result:{cases:[{id:'size',status:'pass',restored:true}]}}
  return {ok:true,result:{}}
}}
const parent={id:'author',session:{header:{},snapshotEvents:()=>events},ctx:{get:n=>n==='subagents'?runtime:undefined,tools:{get:n=>['houdini_exec','houdini_query','read_image','read','skill'].includes(n)?{}:undefined}}}
const owner={sessionId:'author',callId:'call'}
const exec={agent:parent,callId:'call',signal:new AbortController().signal}
const scope={parent:'/obj/g',output:'/obj/g/OUT',controller:'/obj/g/C'}
controller=new ReviewController(bridge)
runtime={async start(provider,request){
  requestSeen=request;assert.equal(provider,'spawn');assert.equal(request.parent,parent)
  assert(!JSON.stringify(request.prompt).includes('PRIVATE-TOKEN'))
  assert(!JSON.stringify(request.prompt).includes('AUTHOR CLAIMS'))
  assert.equal(request.prompt[1].type,'image');assert.equal(request.prompt[1].attachment.id,'user-reference')
  assert(!request.toolFilter.allow.includes('pwsh'));assert(!request.toolFilter.allow.includes('subagent'))
  assert.deepEqual(request.toolFilter.allow,['houdini_query','houdini_exec','read_image'])
  assert(JSON.stringify(request.prompt).includes('unsupported fixture'))
  if(mode==='start-failure')throw new Error('start failed')
  child={id:'child',session:{header:{parentSession:'author'}}}
  const childExec={agent:child,callId:'test',signal:request.signal}
  // Exercise the publication race: the child calls before start has returned.
  const result=(async()=>{
    assert.equal(await controller.isReviewer(childExec),true)
    await assert.rejects(controller.guard(childExec,false),/arbitrary edits/)
    await controller.guard(childExec,true)
    await assert.rejects(controller.guard(exec,false),/wait before editing/)
    const reply=await controller.test({tests:[{id:'size',values:{size:2}}]},childExec,{sessionId:'child',callId:'test'})
    assert.equal(reply.result.cases[0].status,'pass')
    return {stopReason:mode==='abort'?'aborted':'completed',output:[{type:'text',text:'Evidence-backed review; limitations stated.'}]}
  })()
  return {id:'child',localAgent:child,result,async dispose(){disposeCount++}}
}}
assert.throws(()=>reviewScope({...scope,owner:'forged'}),/scope only/)
assert.throws(()=>reviewScope({parent:'relative',output:'/obj/g/O'}),/absolute/)
const material=reviewTaskMaterials(parent)
assert(material.includes('Build a configurable'));assert(material.includes('User chose'))
assert(!material.includes('runtime context'));assert(!material.includes('AUTHOR CLAIMS'))
await assert.rejects(controller.test({},exec,owner),/active reviewer/)
const reply=await controller.start(scope,exec,owner)
assert(reply.ok);assert.equal(reply.result.reviewer,'child');assert.equal(released,1);assert.equal(disposeCount,1)
assert.equal(reply.result.experiments[0].cases[0].status,'pass')
assert(reply.result.acceptance.includes('No automatic pass'))
await assert.rejects(controller.guard({agent:child},true),/permission has ended/)
await controller.guard(exec,false)
mode='start-failure';await assert.rejects(controller.start(scope,exec,owner),/start failed/);assert.equal(released,2)
mode='abort';assert.equal((await controller.start(scope,exec,owner)).ok,false);assert.equal(released,3)
mode='release-failure';await assert.rejects(controller.start(scope,exec,owner),/restoration fault/);assert.equal(released,4)
mode='success';await controller.guard(exec,false)
const definitions=new Map()
registerHoudiniTools({tools:{register:d=>definitions.set(d.name,d)}},bridge)
assert.equal(definitions.size,5)
const tool=definitions.get('houdini_exec')
assert(!('delivery' in tool.parameters.properties));assert('review' in tool.parameters.properties);assert('review_test' in tool.parameters.properties)
await assert.rejects(tool.execute({code:'x',review:scope},exec),/exactly one/)
await assert.rejects(tool.execute({review:scope,allow_raw:'no'},exec),/allow_raw/)
await assert.rejects(tool.execute({review_test:{}},exec),/active reviewer/)

const history=[]
function evidence(callId, facts, {prefix='Executed successfully.\n\n',name='houdini_exec',error=false}={}) {
  history.push({type:'tool/call',data:{callId,name}})
  history.push({type:'tool/result',time:123,data:{message:{source:{callId},content:[{type:'tool_result',isError:error,
    content:[{type:'text',text:prefix+'operation-evidence:\n'+JSON.stringify(facts)+'\n\nstdout:\nAUTHOR CLAIMS PERFECT'}]}]}}})
}
evidence('tests',[{verb:'test_controls',output:scope.output,baseline_sha256:'old-state',status:'pass',results:[{id:'size',values:{size:2},status:'pass',restored:true}]}])
evidence('wrong-output',[{verb:'test_controls',output:'/obj/other/OUT',results:[]}])
evidence('fake-stdout',[{verb:'test_controls',output:scope.output,status:'pass'}],{prefix:'Executed successfully.\n\nstdout:\n'})
evidence('failed',[{verb:'test_controls',output:scope.output,status:'pass'}],{error:true})
evidence('wrong-tool',[{verb:'test_controls',output:scope.output,status:'pass'}],{name:'read'})
evidence('image',[{verb:'render_view',target:scope.output,output:'E:/scene/render.png',source:{path:scope.output,signature:'old-image'},stale:false}])
history.push(history[1]) // compaction replay must not inflate evidence
const facts=reviewPriorEvidence(history,scope)
assert.equal(facts.length,2)
assert.equal(facts[0].cases[0].id,'size');assert.equal(facts[0].baseline_sha256,'old-state')
assert.equal(facts[1].images[0].path,'E:/scene/render.png')
assert(!JSON.stringify(facts).includes('AUTHOR CLAIMS'))
assert(facts.every(f=>f.provenance.includes('historical')))
console.log('foreground reviewer lifecycle/original requirements/restricted tools/publication race/cleanup/tool schema passed')
