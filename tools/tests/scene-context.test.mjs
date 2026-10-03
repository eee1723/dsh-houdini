import assert from 'node:assert/strict'
import {installSceneContext} from '../../lib/context.js'
import {SceneContextProvider} from '../../lib/scene-context.js'
import {Session} from '@deepseek-ai/dsh-session'
const SCENE='dsh-houdini:scene-context',STATE='dsh-houdini:execution-state'
const user=(id,text)=>({id,role:'user',source:{kind:'user'},content:[{type:'text',text}]})
const data=section=>JSON.parse(section.text.slice(section.text.indexOf('\n')+1))
let calls=0,frame=1
const bridge={async sceneContext(){calls++;return {ok:true,result:{frame,hip_path:'{{scene}}.hip',selection:[{path:'/obj/selected'}]}}}}
const hooks={},registered=[]
installSceneContext({systemPrompt:{context:c=>registered.push(c)},on:(n,f)=>hooks[n]=f},bridge)
const session=Session.create('scene-native-context'),agent={session}
async function assemble(message,contexts=registered.map(c=>({...c})),tools=[{name:'houdini_inspect'}]) {
  if (message) {hooks['agent/inbox/inserted']({agent,message});hooks['agent/inbox/claimed']({agent,message})}
  const assembly={contexts,tools,variables:{}}
  await hooks['system-prompt/assemble'](assembly,{scope:{},agent},async()=>assembly)
  return assembly.contexts.filter(c=>c.text)
}
assert.equal((await assemble(user('greeting','你好'))).length,1)
const first=await assemble(user('selected','检查选中节点'))
assert.equal(data(first[0]).observation.result.frame,1)
assert(!first[0].text.includes('{{'),'scene strings cannot interpolate prompt variables')
frame=20
assert.equal((await assemble())[0].text,first[0].text)
assert.equal(calls,2,'one observation is tied to one received user message')
assert.equal(hooks['agent/pre-step'],undefined,'DSH owns context acceptance, compression and persistence')
session.append('user/message',user('selected','检查选中节点'),{surfaceOp:'append'})
session.append('user/message',{role:'user',content:[{type:'text',text:first[0].text}],
  source:{kind:'runtime-context',form:'snapshot',sections:first}},{surfaceOp:'append'})
const resumed=new SceneContextProvider(bridge)
assert.equal(await resumed.observe({session}),first[0].text)
assert.equal(calls,2,'resume reuses the original selection observation')
session.append('tool/call',{turn:1,step:1,callId:'bad',name:'houdini_exec',arguments:'{}'})
session.append('tool/result',{turn:1,step:1,message:{role:'tool',source:{kind:'tool',callId:'bad'},content:[]},meta:{canonical:{ok:false,error:'Bad parm',execution:{runtime_id:'r',sequence:1,observed_at:1}}}},{surfaceOp:'append'})
const notice=(await assemble()).find(c=>c.name===STATE)
assert.equal(notice,undefined,'settled failure does not append the same scene and capability again')
assert.equal((await assemble())[0].text,first[0].text)
session.append('tool/call',{turn:1,step:2,callId:'unknown',name:'houdini_exec',arguments:'{}'})
session.append('tool/result',{turn:1,step:2,message:{role:'tool',source:{kind:'tool',callId:'unknown'},content:[]},meta:{canonical:{ok:false,requestReceipt:{request_ref:'r.request',status:'unknown_transport'}}}},{surfaceOp:'append'})
const recovery=(await assemble()).find(c=>c.name===STATE)
assert.deepEqual(data(recovery).unresolved_requests,[['r.request','unknown_transport']])
assert.deepEqual(await assemble(undefined,[]),[],'runtime context suppression remains DSH-owned')
const override={name:SCENE,text:'Scoped observation override'}
assert.deepEqual(await assemble(undefined,[override]),[override])
console.log('scene context: message-time observation, resume, native DSH context and actual errors passed')
