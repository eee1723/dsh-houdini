import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

const source=fs.readFileSync('client.js','utf8')
const fragment=source.slice(source.indexOf('    function createVideoSettings('),source.indexOf('    function createSupportReporter('))
const settle=async()=>{for(let n=0;n<30;n++)await Promise.resolve()}
const initial=()=>({revision:1,
  selected:{provider:'',model:'fixture-asr',protocol:'openai-transcriptions',endpoint:'http://127.0.0.1:9876/v1/audio/transcriptions',authentication:'bearer',concurrency:2,requestsPerSecond:1},
  defaults:{concurrency:2,requestsPerSecond:1},routes:[{provider:'fixture-provider',display_name:'已有服务商',settingsSource:{ns:'llm-provider-fixture',revision:1}}],
  service:{displayName:'本机转录',provider:null,model:'fixture-asr',protocol:'openai-transcriptions',endpoint:'http://127.0.0.1:9876/v1/audio/transcriptions',
    authentication:'bearer',credentialRef:'DSH_HOUDINI_ASR_FIXTURE_API_KEY',credential:{configured:false,writable:true},dataLocation:'loopback',support:'unverified'},
  adapters:[{id:'openai-transcriptions',label:'OpenAI 兼容文件转录'},{id:'qwen-chat-asr',label:'千问音频 Chat'}],diagnostics:[],writable:true})

function fixture(){
 const hooks=[],effects=[],calls=[],events=new Map()
 let cursor=0,generation={id:1},metadata=initial(),credentialHandler,revision=1,providerRevision=1,providerStatus='ready',mutable=true
 const React={Fragment:'fragment',createElement(tag,props,...children){
   if(typeof tag==='function')return tag({...props,children:children.flat(Infinity)})
   if(tag==='input'&&props.ref&&!props.ref.current)props.ref.current={value:''}
   return {tag,props:props??{},children:children.flat(Infinity)}
 },useRef(value){const index=cursor++;return hooks[index]??(hooks[index]={current:value})},
 useState(value){const index=cursor++;if(!(index in hooks))hooks[index]=value;return [hooks[index],next=>{hooks[index]=next}]},
 useSyncExternalStore:(_subscribe,get)=>get(),useEffect(callback,deps){const index=cursor++;
   if(!hooks[index]||deps.some((value,key)=>value!==hooks[index].deps[key])){hooks[index]?.dispose?.();hooks[index]={deps};effects.push(()=>hooks[index].dispose=callback())}
 }}
 const create=vm.runInNewContext(fragment+';createVideoSettings;',{React,Button:'button',AbortController,Set,
  setTimeout:()=>1,clearTimeout(){},require(name){assert.equal(name,'@deepseek-ai/dsh-client-ui-primitives');return {Modal:props=>React.createElement('dialog',{'aria-label':props.title},props.children,props.footer)}}})
 const connection={generation:{getSnapshot:()=>generation,subscribe:()=>()=>{}},rpc:{call:async(channel,method,payload,signal)=>{
  calls.push({channel,method,args:payload.args,signal});assert.equal(channel,'/api');assert(payload.args,'raw Native RPC arguments must be wrapped')
  if(method==='houdiniFrontend/videoSettings')return {ok:true,value:structuredClone(metadata)}
  if(method==='houdiniFrontend/videoDiagnostics')return {ok:true,value:{dependencies:[],note:'fixture'}}
  if(method==='houdiniFrontend/videoConfigure'){
   const input=payload.args.input
   if(input.expected_revision!==revision)return {ok:false,error:{message:'设置版本已变化'}}
   if(input.expected_provider_revision!==undefined&&input.expected_provider_revision!==providerRevision)return {ok:false,error:{message:'服务商设置已变化，请刷新后重新确认。'}}
   Object.assign(metadata.selected,{provider:input.provider,endpoint:input.endpoint,protocol:input.protocol,model:input.model,authentication:input.authentication,
    concurrency:input.concurrency,requestsPerSecond:input.requests_per_second})
   revision++;metadata.revision=revision
   Object.assign(metadata.service,{provider:input.provider||null,displayName:input.provider?'已有服务商':'自定义转录',model:input.model,protocol:input.protocol,
    endpoint:input.provider?'https://provider.example/v1/chat/completions':input.endpoint,authentication:input.authentication,
    credentialRef:input.provider?'PROVIDER_KEY':input.authentication==='none'?'':'NEW_ORIGIN_API_KEY',dataLocation:input.endpoint.includes('127.0.0.1')?'loopback':'network',
    credential:{configured:false,writable:true},settingsSource:input.provider?{ns:'llm-provider-fixture',revision:providerRevision}:undefined})
   return {ok:true,value:structuredClone(metadata)}
  }
  if(method==='credentials/set'){if(credentialHandler)return credentialHandler(payload.args);metadata.service.credential.configured=true;return {ok:true}}
  throw Error('Unexpected RPC '+method)
 }}}
 const form={getSnapshot(){assert.equal(this,form);return {revision,status:'ready',writable:mutable}},subscribe:()=>()=>{}}
 const providerForm={getSnapshot(){assert.equal(this,providerForm);return {revision:providerRevision,status:providerStatus,writable:true}},subscribe:()=>()=>{}}
 const component=create(connection,{get:ns=>ns==='houdini-frontend'?form:providerForm},{$on:(name,handler)=>{events.set(name,handler);return()=>events.delete(name)}})
 function render(){cursor=0;const tree=component();while(effects.length)effects.shift()();return tree}
 function nodes(tree){return tree&&typeof tree==='object'?[tree,...tree.children.flatMap(nodes)]:[]}
 function find(attribute){const value=nodes(render()).find(node=>node.props[attribute]!==undefined);assert(value,'missing '+attribute);return value}
 function text(){return JSON.stringify(render(),(key,value)=>key==='ref'?undefined:value)}
 async function ready(){render();await settle();return render()}
 function change(attribute,value){find(attribute).props.onChange({target:{value}});return render()}
 return {calls,hooks,events,render,nodes,find,text,ready,change,
   metadata:value=>{metadata=value;revision=value.revision},providerRevision:value=>providerRevision=value,providerStatus:value=>providerStatus=value,
   mutable:value=>mutable=value,generation:value=>generation=value,bumpRevision(){revision++},
   credentialHandler:value=>credentialHandler=value,
   cleanup(){for(const hook of hooks)hook?.dispose?.()}}
}

{
 const f=fixture();await f.ready()
 assert.equal(f.hooks[1]&&f.hooks[1].source,'custom','first load initializes the complete draft')
 assert(f.find('data-houdini-video-endpoint'))
 f.change('data-houdini-video-endpoint','https://relay.example/v1/audio/transcriptions')
 f.change('data-houdini-video-model','relay-asr');f.change('data-houdini-video-concurrency','3');f.change('data-houdini-video-rate','2')
 assert.equal(f.find('data-houdini-video-source').props.value,'custom',JSON.stringify(f.hooks[1]))
 assert.equal(f.find('data-houdini-video-protocol').props.value,'openai-transcriptions',JSON.stringify(f.hooks[1]))
 await f.find('data-houdini-video-save-config').props.onClick();await settle()
 const write=f.calls.find(row=>row.method==='houdiniFrontend/videoConfigure');assert(write,f.text())
 assert.deepEqual({...write.args.input},{provider:'',endpoint:'https://relay.example/v1/audio/transcriptions',protocol:'openai-transcriptions',model:'relay-asr',
  authentication:'bearer',concurrency:3,requests_per_second:2,expected_revision:1})
 assert(!f.calls.some(row=>row.method==='session/prompt'),'deterministic settings never invoke an Agent')
 assert.match(f.text(),/配置已保存/);assert.equal(f.find('data-houdini-video-model').props.value,'relay-asr')
 f.cleanup()
}

{
 const f=fixture();await f.ready()
 f.change('data-houdini-video-source','provider');f.change('data-houdini-video-protocol','qwen-chat-asr');f.change('data-houdini-video-model','qwen-asr')
 await f.find('data-houdini-video-save-config').props.onClick();await settle()
 const write=f.calls.find(row=>row.method==='houdiniFrontend/videoConfigure');assert.equal(write.args.input.expected_provider_revision,1)
 assert.equal(write.args.input.endpoint,'');assert.equal(write.args.input.provider,'fixture-provider')
 assert.match(f.text(),/当前生效：已有服务商/)
 f.cleanup()
}

{
 const f=fixture();await f.ready()
 f.change('data-houdini-video-source','provider');f.providerRevision(2)
 await f.find('data-houdini-video-save-config').props.onClick();await settle()
 assert.match(f.text(),/服务商设置已变化/);assert.equal(f.calls.filter(row=>row.method==='credentials/set').length,0)
 f.cleanup()
}

{
 const f=fixture();await f.ready();f.bumpRevision();f.render()
 assert.equal(f.find('data-houdini-video-save-config').props.disabled,true)
 await f.find('data-houdini-video-save-config').props.onClick();await settle()
 assert.equal(f.calls.filter(row=>row.method==='houdiniFrontend/videoConfigure').length,0)
 assert.match(f.text(),/配置已变化或当前不可写/)
 f.cleanup()
}

{
 const f=fixture();await f.ready()
 f.find('data-houdini-video-key').props.onClick()
 const field=f.nodes(f.render()).find(node=>node.tag==='input'&&node.props.type==='password')
 assert.equal(field.props.autoComplete,'new-password');assert.equal(field.props.value,undefined)
 field.props.ref.current.value='fixture-only-private-key'
 await f.find('data-houdini-video-save-key').props.onClick();await settle()
 assert.equal(field.props.ref.current.value,'','secret draft is cleared immediately after native submission')
 const writes=f.calls.filter(row=>row.method==='credentials/set')
 assert.equal(writes.length,1);assert.equal(writes[0].args.ref,initial().service.credentialRef);assert.equal(writes[0].args.value,'fixture-only-private-key')
 assert(!f.calls.filter(row=>row.method!=='credentials/set').some(row=>JSON.stringify(row.args).includes('fixture-only-private-key')))
 assert(!JSON.stringify(f.hooks).includes('fixture-only-private-key'),'React state and refs never retain the submitted secret')
 assert(!f.text().includes('fixture-only-private-key'));assert.match(f.text(),/配置已保存，实际效果以试转录为准/)
 assert(!f.nodes(f.render()).some(node=>node.props['data-houdini-video-credential']!==undefined),'native acceptance closes the secret form')
 f.cleanup()
}

{
 const f=fixture();await f.ready();f.find('data-houdini-video-key').props.onClick()
 const field=f.nodes(f.render()).find(node=>node.tag==='input'&&node.props.type==='password');field.props.ref.current.value='do-not-overwrite-old-origin'
 const stale=f.find('data-houdini-video-save-key').props.onClick
 const changed=initial();changed.revision=2;changed.service.endpoint='https://new-origin.example/asr';changed.service.credentialRef='NEW_ORIGIN_API_KEY'
 f.metadata(changed);await stale()
 assert.equal(f.calls.filter(row=>row.method==='credentials/set').length,0,'native revision changes fence the previous origin before React effects')
 f.render();assert.equal(f.find('data-houdini-video-key').props.disabled,true)
 assert(!f.nodes(f.render()).some(node=>node.props['data-houdini-video-credential']!==undefined))
 f.cleanup()
}

{
 const f=fixture(),metadata=initial();metadata.service.provider='fixture-provider';metadata.service.settingsSource={ns:'llm-provider-fixture',revision:1}
 f.metadata(metadata);await f.ready();f.find('data-houdini-video-key').props.onClick()
 const field=f.nodes(f.render()).find(node=>node.tag==='input'&&node.props.type==='password');field.props.ref.current.value='do-not-write-old-provider-origin'
 assert.match(f.text(),/该服务商的其他用途也会使用新密钥/,'shared DSH credentials are not described as ASR-only')
 const stale=f.find('data-houdini-video-save-key').props.onClick
 const changed=structuredClone(metadata);changed.service.settingsSource.revision=2;changed.service.endpoint='https://provider-new.example/asr'
 f.providerRevision(2);f.metadata(changed);await stale()
 assert.equal(f.calls.filter(row=>row.method==='credentials/set').length,0,'provider namespace independently fences old-origin writes')
 f.render();assert.equal(f.find('data-houdini-video-key').props.disabled,true)
 f.providerStatus('unavailable');assert.equal(f.find('data-houdini-video-key').props.disabled,true)
 f.cleanup()
}

{
 const f=fixture();await f.ready();f.find('data-houdini-video-key').props.onClick()
 const field=f.nodes(f.render()).find(node=>node.tag==='input'&&node.props.type==='password');field.props.ref.current.value='old-connection-draft'
 f.generation({id:2});const save=f.find('data-houdini-video-save-key').props.onClick;await save()
 assert.equal(f.calls.filter(row=>row.method==='credentials/set').length,0,'a replacement connection cannot submit an old draft')
 f.cleanup()
}

{
 const f=fixture(),metadata=initial();metadata.service.credential.writable=false;f.metadata(metadata);await f.ready()
 assert.equal(f.find('data-houdini-video-key').props.disabled,true,'read-only credentials cannot be submitted')
 metadata.service.credential.configured=true;f.events.get('credentials/reference-updated')();await settle();assert.match(f.text(),/配置已保存，实际效果以试转录为准/)
 metadata.service.authentication='none';metadata.service.credentialRef='';metadata.service.credential={configured:true,writable:false,required:false}
 f.metadata(metadata);await f.find('data-houdini-video-refresh').props.onClick();await settle()
 assert.match(f.text(),/不使用密钥/);assert.equal(f.find('data-houdini-video-key').props.disabled,true)
 f.cleanup()
}

assert(!source.includes('guideRequest'),'the old Agent configuration workflow is gone')
console.log('PASS tutorial settings: direct native configuration, revision fences, all-mode credentials and no Agent prompt')
