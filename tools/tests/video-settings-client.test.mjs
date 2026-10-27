import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

const source=fs.readFileSync('client.js','utf8')
const fragment=source.slice(source.indexOf('    function createVideoSettings('),source.indexOf('    function createSupportReporter('))
const settle=async()=>{for(let n=0;n<30;n++)await Promise.resolve()}
const deferred=()=>{let resolve;const promise=new Promise(value=>resolve=value);return {promise,resolve}}
const initial=()=>({revision:1,selected:{model:'fixture-asr',concurrency:2,requestsPerSecond:1},defaults:{concurrency:2,requestsPerSecond:1},
  service:{displayName:'本机转录',model:'fixture-asr',protocol:'openai-transcriptions',endpoint:'http://127.0.0.1:9876/v1/audio/transcriptions',
    authentication:'bearer',credentialRef:'DSH_HOUDINI_ASR_FIXTURE_API_KEY',credential:{configured:false,writable:true},dataLocation:'loopback',support:'unverified'},
  adapters:[{id:'openai-transcriptions',label:'OpenAI 兼容文件转录'}],diagnostics:[]})

function fixture(){
 const hooks=[],effects=[],calls=[],opened=[],events=new Map()
 let cursor=0,session='hoodini-a',preset='houdini',generation={id:1},metadata=initial(),credentialHandler,promptHandler,closed=0,nonce=0,revision=1,providerRevision=1,providerStatus='ready'
 const React={Fragment:'fragment',createElement(tag,props,...children){
   if(typeof tag==='function')return tag({...props,children:children.flat(Infinity)})
   if(tag==='input'&&props.ref&&!props.ref.current)props.ref.current={value:''}
   return {tag,props:props??{},children:children.flat(Infinity)}
 },useRef(value){const index=cursor++;return hooks[index]??(hooks[index]={current:value})},
 useState(value){const index=cursor++;if(!(index in hooks))hooks[index]=value;return [hooks[index],next=>hooks[index]=next]},
 useSyncExternalStore:(_subscribe,get)=>get(),useEffect(callback,deps){const index=cursor++;
   if(!hooks[index]||deps.some((value,key)=>value!==hooks[index].deps[key])){hooks[index]?.dispose?.();hooks[index]={deps};effects.push(()=>hooks[index].dispose=callback())}
 }}
 const create=vm.runInNewContext(fragment+';createVideoSettings;',{React,Button:'button',AbortController,Set,
  crypto:{randomUUID:()=>`native-guide-${++nonce}`},setTimeout:()=>1,clearTimeout(){},
  require(name){assert.equal(name,'@deepseek-ai/dsh-client-ui-primitives');return {Modal:props=>React.createElement('dialog',{'aria-label':props.title},props.children,props.footer)}}})
 const connection={generation:{getSnapshot:()=>generation,subscribe:()=>()=>{}},rpc:{call:async(channel,method,payload,signal)=>{
  calls.push({channel,method,args:payload.args,signal});assert.equal(channel,'/api');assert(payload.args,'raw Native RPC arguments must be wrapped')
  if(method==='houdiniFrontend/videoSettings')return {ok:true,value:structuredClone(metadata)}
  if(method==='houdiniFrontend/videoDiagnostics')return {ok:true,value:{dependencies:[],note:'fixture'}}
  if(method==='credentials/set'){if(credentialHandler)return credentialHandler(payload.args);metadata.service.credential.configured=true;return {ok:true}}
  if(method==='session/prompt')return promptHandler?promptHandler(payload.args.request):{ok:true,value:{accepted:true}}
  throw Error('Unexpected RPC '+method)
 }}}
 const form={getSnapshot(){assert.equal(this,form);return {revision,status:'ready',writable:true}},subscribe:()=>()=>{},mutate(){throw Error('status UI must not write preferences')}}
 const providerForm={getSnapshot(){assert.equal(this,providerForm);return {revision:providerRevision,status:providerStatus,writable:true}},subscribe:()=>()=>{}}
 const component=create(connection,{get:ns=>ns==='houdini-frontend'?form:providerForm},{adapter:{current:{getSnapshot:()=>({key:session}),subscribe:()=>()=>{}}}},
  {list:{getSnapshot:()=>({byId:{[session]:{id:session,projectionValues:{agentPreset:preset}}}}),subscribe:()=>()=>{}}},
  {openSession:id=>opened.push(id)},{$on:(name,handler)=>{events.set(name,handler);return()=>events.delete(name)}})
 function render(){cursor=0;const tree=component({close:()=>closed++});while(effects.length)effects.shift()();return tree}
 function nodes(tree){return tree&&typeof tree==='object'?[tree,...tree.children.flatMap(nodes)]:[]}
 function find(attribute){return nodes(render()).find(node=>node.props[attribute]!==undefined)}
 function text(){return JSON.stringify(render(),(key,value)=>key==='ref'?undefined:value)}
 async function ready(){render();await settle();return render()}
 return {calls,opened,hooks,events,render,nodes,find,text,ready,closed:()=>closed,
   metadata:value=>{metadata=value;revision=value.revision},preset:value=>preset=value,session:value=>session=value,generation:value=>generation=value,
   providerRevision:value=>providerRevision=value,providerStatus:value=>providerStatus=value,
   credentialHandler:value=>credentialHandler=value,promptHandler:value=>promptHandler=value,
   cleanup(){for(const hook of hooks)hook?.dispose?.()}}
}

{
 const f=fixture();await f.ready()
 assert(!f.nodes(f.render()).some(node=>['input','select','textarea'].includes(node.tag)),'normal page is status, not a duplicate provider configuration form')
 assert.match(f.text(),/同时最多 2 个 \/ 每秒最多 1 次/);assert.match(f.text(),/等待安全录入密钥/)
 f.find('data-houdini-video-key').props.onClick()
 const field=f.nodes(f.render()).find(node=>node.tag==='input')
 assert.equal(field.props.type,'password');assert.equal(field.props.autoComplete,'new-password');assert.equal(field.props.value,undefined)
 field.props.ref.current.value='fixture-only-private-key'
 await f.find('data-houdini-video-save-key').props.onClick();await settle()
 assert.equal(field.props.ref.current.value,'','secret draft is cleared immediately after native submission')
 const writes=f.calls.filter(row=>row.method==='credentials/set')
 assert.equal(writes.length,1);assert.equal(writes[0].args.ref,initial().service.credentialRef);assert.equal(writes[0].args.value,'fixture-only-private-key')
 assert.equal(f.calls.filter(row=>row.method==='session/prompt').length,0,'a key is never sent to the Agent')
 assert(!f.calls.filter(row=>row.method!=='credentials/set').some(row=>JSON.stringify(row.args).includes('fixture-only-private-key')))
 assert(!JSON.stringify(f.hooks).includes('fixture-only-private-key'),'React state and refs never retain the submitted secret')
 assert(!f.text().includes('fixture-only-private-key'));assert.match(f.text(),/服务配置已保存/)
 assert(!f.nodes(f.render()).some(node=>node.tag==='input'),'native acceptance closes the secret form')
 f.cleanup()
}

{
 const f=fixture();await f.ready();let request
 f.promptHandler(value=>{request=value;throw Error('reply lost')})
 await f.find('data-houdini-video-guide').props.onClick()
 assert.match(f.text(),/重试引导请求/)
 f.promptHandler(value=>{assert.equal(value.requestId,request.requestId);return {ok:true,value:{accepted:true}}})
 await f.find('data-houdini-video-guide').props.onClick()
 assert.equal(request.sessionId,'hoodini-a');assert.equal(request.mode,'queue')
 assert.equal(f.calls.filter(row=>row.method==='session/prompt').length,2)
 assert.match(request.content[0].text,/不要索取或输出 API Key/)
 assert.deepEqual(f.opened,['hoodini-a']);assert.equal(f.closed(),1)
 assert.equal(f.calls.filter(row=>row.method==='credentials/set').length,0)
 f.cleanup()
}

{
 const f=fixture();await f.ready()
 const stale=f.find('data-houdini-video-guide').props.onClick
 f.preset('standard');await stale()
 assert.equal(f.calls.filter(row=>row.method==='session/prompt').length,0,'a late Houdini control cannot prompt another mode')
 f.preset('houdini');const gate=deferred();f.promptHandler(()=>gate.promise)
 const pending=f.find('data-houdini-video-guide').props.onClick()
 f.session('hoodini-b');gate.resolve({ok:true,value:{accepted:true}});await pending
 assert.deepEqual(f.opened,[],'late acceptance cannot take selection back from the user')
 assert.equal(f.closed(),0)
 f.cleanup()
}

{
 const f=fixture();await f.ready();f.find('data-houdini-video-key').props.onClick()
 const field=f.nodes(f.render()).find(node=>node.tag==='input');field.props.ref.current.value='never-send-stale-key'
 const stale=f.find('data-houdini-video-save-key').props.onClick
 f.preset('standard');await stale()
 assert.equal(f.calls.filter(row=>row.method==='credentials/set').length,0,'a stale secret dialog cannot write from another mode')
 f.render();assert(!f.nodes(f.render()).some(node=>node.tag==='input'))
 f.cleanup()
}

{
 const f=fixture(),metadata=initial();metadata.service.provider='existing-provider';metadata.service.settingsSource={ns:'llm-provider-fixture',revision:1}
 f.metadata(metadata);await f.ready();f.find('data-houdini-video-key').props.onClick()
 const field=f.nodes(f.render()).find(node=>node.tag==='input');field.props.ref.current.value='do-not-write-old-provider-origin'
 assert.match(f.text(),/该服务商的其他用途也会使用新密钥/,'shared DSH credentials are not described as ASR-only')
 const stale=f.find('data-houdini-video-save-key').props.onClick
 const changed=structuredClone(metadata);changed.service.settingsSource.revision=2;changed.service.endpoint='https://provider-new-origin.example/asr'
 f.providerRevision(2);f.metadata(changed)
 await stale()
 assert.equal(f.calls.filter(row=>row.method==='credentials/set').length,0,'the provider namespace independently fences old-origin writes while the Houdini namespace revision stays unchanged')
 f.render();assert.equal(f.find('data-houdini-video-key').props.disabled,true)
 await settle();assert.equal(f.find('data-houdini-video-key').props.disabled,false)
 assert(!f.nodes(f.render()).some(node=>node.tag==='input'))
 f.providerStatus('unavailable');assert.equal(f.find('data-houdini-video-key').props.disabled,true,'unserved native provider settings cannot authorize secret edits')
 f.cleanup()
}

{
 const f=fixture();await f.ready();f.find('data-houdini-video-key').props.onClick()
 const field=f.nodes(f.render()).find(node=>node.tag==='input');field.props.ref.current.value='do-not-overwrite-old-origin'
 const stale=f.find('data-houdini-video-save-key').props.onClick
 const changed=initial();changed.revision=2;changed.service.endpoint='https://new-origin.example/asr';changed.service.credentialRef='NEW_ORIGIN_API_KEY'
 f.metadata(changed)
 await stale()
 assert.equal(f.calls.filter(row=>row.method==='credentials/set').length,0,'native revision changes synchronously fence the previous origin before React/effects/async service refresh')
 f.render();assert.equal(f.find('data-houdini-video-key').props.disabled,true)
 assert(!f.nodes(f.render()).some(node=>node.tag==='input'))
 await settle();assert.equal(f.find('data-houdini-video-key').props.disabled,false)
 f.cleanup()
}

{
 const f=fixture();await f.ready();f.credentialHandler(()=>({ok:false,error:{message:'Native credentials: reference is read-only'}}))
 f.find('data-houdini-video-key').props.onClick();const field=f.nodes(f.render()).find(node=>node.tag==='input')
 field.props.ref.current.value='native-rejected-fixture-key';await f.find('data-houdini-video-save-key').props.onClick()
 assert.match(f.text(),/Native credentials: reference is read-only/,'credential refusal uses the native diagnostic')
 assert.equal(field.props.ref.current.value,'');assert(!f.text().includes('native-rejected-fixture-key'))
 f.cleanup()
}

{
 const f=fixture();await f.ready();f.find('data-houdini-video-key').props.onClick()
 const field=f.nodes(f.render()).find(node=>node.tag==='input');field.props.ref.current.value='old-connection-draft'
 f.generation({id:2})
 const immediate=f.render(),save=f.nodes(immediate).find(node=>node.props['data-houdini-video-save-key'])
 await save.props.onClick()
 assert.equal(f.calls.filter(row=>row.method==='credentials/set').length,0,'a replacement connection cannot submit a previous connection draft, even before effects remove its tree')
 f.cleanup()
}

{
 const f=fixture(),metadata=initial();metadata.service.credential.writable=false;f.metadata(metadata);await f.ready()
 assert.equal(f.find('data-houdini-video-key').props.disabled,true,'read-only credentials cannot be submitted')
 metadata.service.credential.configured=true;f.metadata(metadata)
 f.events.get('credentials/reference-updated')();await settle();assert.match(f.text(),/服务配置已保存/,'native credential events refresh presence without copying values')
 metadata.service.authentication='none';metadata.service.credentialRef='';metadata.service.credential={configured:true,writable:false,required:false}
 f.metadata(metadata);await f.find('data-houdini-video-refresh').props.onClick();await settle()
 assert.match(f.text(),/当前配置不使用密钥/);assert.equal(f.find('data-houdini-video-key').props.disabled,true)
 f.cleanup()
}

{
 const f=fixture();await f.ready();const gate=deferred();f.promptHandler(()=>gate.promise)
 const pending=f.find('data-houdini-video-guide').props.onClick(),request=f.calls.at(-1)
 f.generation(null);f.render();assert.equal(request.signal.aborted,true)
 gate.resolve({ok:true,value:{accepted:true}});await pending
 assert.deepEqual(f.opened,[],'old transport replies cannot navigate after reconnect')
 f.cleanup()
}

console.log('PASS tutorial status + native prompt and write-only credentials: mode/current-session fences, secret isolation, native errors/events and transport retry')
