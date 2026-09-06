// Actual Node tool -> HTTP -> owning-thread Bridge; subagent model is deterministic.
import assert from 'node:assert/strict'
import {HoudiniBridge} from '../../lib/bridge.js'
import {registerHoudiniTools} from '../../lib/tools.js'
const bridge=new HoudiniBridge(process.argv[2],15000)
const definitions=new Map()
registerHoudiniTools({tools:{register:d=>definitions.set(d.name,d)}},bridge)
let runtime,id=0
const agent={id:'review-http-author',ctx:{get:n=>n==='subagents'?runtime:undefined,tools:{get:n=>definitions.get(n)}},
  session:{header:{},snapshotEvents:()=>[{type:'user/message',data:{content:[{type:'text',text:'Create a small configurable native shape and review its dimensions.'}]}}]}}
const context=who=>({agent:who||agent,callId:String(++id),signal:new AbortController().signal})
const run=code=>definitions.get('houdini_exec').execute({code},context())
const created=await run(`p=tab_create('/obj','geo',name='__review_http')
c=tab_create(p,'null',name='CTRL')
create_spare_parms(c,spec=[{'name':'size','type':'float','default':1}])
build_module(p,[{'name':'shape','type':'box','parms':{'sizex':"ch('../CTRL/size')"}},{'name':'OUT','type':'null','inputs':['shape']}],output='OUT')
__result__=p.path()`)
assert(created.ok,created.error)
const scope={parent:created.result,controller:created.result+'/CTRL',output:created.result+'/OUT'}
let disposed=false
runtime={async start(name,request){
  assert.equal(name,'spawn');assert.equal(request.maxDepth,1)
  const child={id:'review-http-child',session:{header:{parentSession:agent.id}},ctx:agent.ctx}
  const result=(async()=>{
    const invoke=args=>definitions.get('houdini_exec').execute(args,context(child))
    const baseline=await invoke({review_test:{}})
    assert(baseline.result.network.healthy)
    await assert.rejects(run('__result__=1'),/wait before editing/)
    await assert.rejects(bridge.exec('__result__=1',undefined,undefined,{sessionId:agent.id,callId:'bypass'}),/review is active/)
    await assert.rejects(invoke({code:`set_parm('${scope.controller}','size',9)`}),/arbitrary edits/)
    const measured=await invoke({review_test:{tests:[{id:'size',values:{size:2},expectations:[{metric:'bounds_size',axis:0,delta:[.99,1.01]}]}]}})
    assert.equal(measured.result.cases[0].status,'pass');assert(measured.result.cases[0].restored)
    const observed=await definitions.get('houdini_query').execute({code:`__result__=hou.node('${scope.controller}').evalParm('size')`},context(child))
    assert.equal(observed.result,1)
    return {stopReason:'completed',output:[{type:'text',text:'Size test passed and restored. Visual semantics unverified.'}]}
  })()
  return {id:child.id,localAgent:child,result,async dispose(){disposed=true}}
}}
const reviewed=await definitions.get('houdini_exec').execute({review:scope},context())
assert(reviewed.ok,reviewed.error);assert(disposed);assert.match(reviewed.result.report,/restored/)
await assert.rejects(definitions.get('houdini_exec').execute({review_test:{}},context()),/active reviewer/)
assert.equal((await run(`delete_node('${scope.parent}')`)).ok,true)
console.log('real Node review tool -> HTTP -> owning thread -> child batch tests -> cleanup passed')
