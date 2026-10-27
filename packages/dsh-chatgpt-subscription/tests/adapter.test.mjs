import assert from 'node:assert/strict'
import test from 'node:test'
import {fixture,model} from './fixture.mjs'
import {SubscriptionAdapter,siwcPayload} from '../lib/adapter.js'
import {PROVIDER} from '../lib/types.js'
import {BlockAssembler,createToolResultMessage} from '@deepseek-ai/dsh-llm'
import {getBuiltinModels} from '@earendil-works/pi-ai/providers/all'

test('real public PiAiAdapter composition produces a completed Responses call, no ambient credentials',async()=>{
  const f=await fixture();try{
    await f.login();const adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher),models=await adapter.listModels()
    assert.equal(models.length,1);assert.equal(models[0].provider,PROVIDER)
    const chunks=await Array.fromAsync(adapter.stream({provider:PROVIDER,model:model.id,messages:[{role:'user',content:[{type:'text',text:'owned test'}]}],maxTokens:100,temperature:.2}))
    const finish=chunks.find(row=>row.type==='finish');assert(finish);assert.equal(finish.reason.kind,'stop')
    assert.equal(finish.replayState.response.provider,PROVIDER)
    assert.equal(finish.replayState.response.siwcAccountId,(await f.accounts.status()).activeAccountId)
    const request=f.seen.find(row=>row.url.endsWith('/responses'));assert(request)
    const payload=JSON.parse(request.init.body);assert.equal(payload.store,false);assert.equal(payload.stream,true);assert(!Object.hasOwn(payload,'max_output_tokens'));assert(!Object.hasOwn(payload,'temperature'))
    assert.equal(new Headers(request.init.headers).get('authorization'),'Bearer owned-access-1')
    assert(new Headers(request.init.headers).get('user-agent'))
  }finally{await f.close()}
})
test('models and inference obey official bearer wire and isolate ambient Platform tenant/log/header settings',async()=>{
  const keys=['OPENAI_API_KEY','OPENAI_ORG_ID','OPENAI_PROJECT_ID','OPENAI_BASE_URL','OPENAI_CUSTOM_HEADERS','OPENAI_LOG'],previous=Object.fromEntries(keys.map(key=>[key,process.env[key]]))
  const poisoned={OPENAI_API_KEY:'owned-ambient-key',OPENAI_ORG_ID:'owned-ambient-org',OPENAI_PROJECT_ID:'owned-ambient-project',OPENAI_BASE_URL:'https://wrong.invalid/v1',
    OPENAI_CUSTOM_HEADERS:'Authorization: Bearer owned-ambient-override\nOpenAI-Organization: wrong-org\nOpenAI-Project: wrong-project',OPENAI_LOG:'debug'}
  Object.assign(process.env,poisoned)
  const debug=console.debug,logs=[];console.debug=(...args)=>logs.push(args)
  const f=await fixture();try{
    await f.login();const adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher)
    await Array.fromAsync(adapter.stream({provider:PROVIDER,model:model.id,messages:[{role:'user',content:[{type:'text',text:'owned-private-prompt-marker'}]}]}))
    const directory=f.seen.find(row=>row.url.endsWith('/models')),inference=f.seen.find(row=>row.url.endsWith('/responses'))
    for(const request of [directory,inference]){
      assert(request);const headers=new Headers(request.init.headers)
      assert.equal(headers.get('authorization'),'Bearer owned-access-1')
      assert(headers.get('user-agent'));assert.equal(headers.get('openai-organization'),null);assert.equal(headers.get('openai-project'),null)
      assert.equal(headers.get('chatgpt-account-id'),null,'Codex/backend-api headers are not SiWC account headers')
      assert.equal(request.init.redirect,'error')
    }
    assert.equal(new Headers(directory.init.headers).get('accept'),'application/json')
    assert.equal(new Headers(inference.init.headers).get('accept'),'text/event-stream')
    const token=f.seen.find(row=>row.url.endsWith('/oauth/token')),form=new URLSearchParams(token.init.body)
    assert.equal(form.get('client_id'),'issued-1');assert.equal(form.get('resource'),'https://api.openai.com/v1');assert.equal(form.has('client_secret'),false)
    assert.deepEqual(Object.fromEntries(keys.map(key=>[key,process.env[key]])),poisoned,'one adapter must not mutate the host environment')
    assert(!JSON.stringify(logs).includes('owned-private-prompt-marker'));assert(!JSON.stringify(logs).includes('owned-access'))
  }finally{console.debug=debug;for(const key of keys){if(previous[key]===undefined)delete process.env[key];else process.env[key]=previous[key]}await f.close()}
})
test('server catalog order is retained and unknown capabilities stay explicit',async()=>{
  const f=await fixture();try{
    await f.login();const known=getBuiltinModels('openai').filter(row=>row.api==='openai-responses').slice(0,2);assert.equal(known.length,2)
    f.catalog([{slug:known[1].id,display_name:'Server first',visibility:'list'},{slug:'new-unknown-id',display_name:'Not guessed',visibility:'list'},
      {slug:known[0].id,display_name:'Server second',visibility:'list'}])
    const catalog=await f.accounts.models({refresh:true});assert.deepEqual(catalog.map(row=>row.id),[known[1].id,'new-unknown-id',known[0].id])
    assert.equal(catalog[1].supported,false);assert.match(catalog[1].unsupportedReason,/暂未适配/)
    const adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher);assert.deepEqual((await adapter.listModels()).map(row=>row.id),[known[1].id,known[0].id])
  }finally{await f.close()}
})
test('reconnect invalidates old prepared credentials; same-account reselection is a no-op',async()=>{
  const f=await fixture();try{
    await f.login();const adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher),id=(await f.accounts.status()).activeAccountId
    const first=await adapter.prepareCall(PROVIDER,model.id);await f.login({accountId:id})
    await assert.rejects(Array.fromAsync(first.stream({provider:PROVIDER,model:model.id,messages:[]})),error=>error.code==='ACCOUNT_CHANGED')
    const second=await adapter.prepareCall(PROVIDER,model.id);await f.accounts.selectAccount({accountId:id})
    const chunks=await Array.fromAsync(second.stream({provider:PROVIDER,model:model.id,messages:[{role:'user',content:[{type:'text',text:'owned'}]}]}))
    assert.equal(chunks.at(-1).reason.kind,'stop')
    assert.equal(f.seen.filter(row=>row.url.endsWith('/responses')).length,1)
  }finally{await f.close()}
})
test('A to B and back does not invalidate prepared A or cancel unrelated active A work',async()=>{
  const f=await fixture();try{
    await f.login();const a=(await f.accounts.status()).activeAccountId
    await f.login();const b=(await f.accounts.status()).activeAccountId
    await f.accounts.selectAccount({accountId:a})
    const adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher),preparedA=await adapter.prepareCall(PROVIDER,model.id),activeA=f.accounts.trackCall(a)
    await f.accounts.selectAccount({accountId:b});assert.equal(activeA.signal.aborted,false)
    const preparedB=await adapter.prepareCall(PROVIDER,model.id)
    await f.accounts.selectAccount({accountId:a});assert.equal(activeA.signal.aborted,false);activeA.close()
    const input={provider:PROVIDER,model:model.id,messages:[{role:'user',content:[{type:'text',text:'owned frozen connection'}]}]}
    await Promise.all([Array.fromAsync(preparedA.stream(input)),Array.fromAsync(preparedB.stream(input))])
    const headers=f.seen.filter(row=>row.url.endsWith('/responses')).map(row=>new Headers(row.init.headers).get('authorization')).sort()
    assert.deepEqual(headers,['Bearer owned-access-1','Bearer owned-access-2'])
  }finally{await f.close()}
})

test('a v1 connected account without optional connectionRevision consistently uses generation zero',async()=>{
  const f=await fixture();try{
    await f.login();const id=(await f.accounts.status()).activeAccountId
    await f.store.updateAccount(id,account=>{delete account.connectionRevision;return account})
    assert.equal((await f.accounts.selection()).generation.connectionRevision,0)
    const adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher),prepared=await adapter.prepareCall(PROVIDER,model.id)
    const chunks=await Array.fromAsync(prepared.stream({provider:PROVIDER,model:model.id,messages:[{role:'user',content:[{type:'text',text:'owned generation zero'}]}]}))
    assert.equal(chunks.find(row=>row.type==='finish').reason.kind,'stop')
  }finally{await f.close()}
})

test('disconnect excludes new wire admission during revocation and cancels calls before releasing the account',async()=>{
  const f=await fixture();let release=()=>{}
  try{
    await f.login();const id=(await f.accounts.status()).activeAccountId,adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher)
    const prepared=await adapter.prepareCall(PROVIDER,model.id)
    let enter;const entered=new Promise(resolve=>enter=resolve),gate=new Promise(resolve=>release=resolve)
    f.revokeGate(async()=>{enter();await gate})
    const logout=f.accounts.disconnect({accountId:id});await entered
    const tracked=f.accounts.trackCall(id)
    const pending=Array.fromAsync(prepared.stream({provider:PROVIDER,model:model.id,messages:[{role:'user',content:[{type:'text',text:'owned revocation race'}]}]}))
    await new Promise(resolve=>setTimeout(resolve,30))
    assert.equal(f.seen.filter(row=>row.url.endsWith('/responses')).length,0)
    release();assert.equal((await logout).disconnected,true)
    const chunks=await pending;assert.equal(chunks.find(row=>row.type==='finish').reason.kind,'aborted')
    assert.equal(tracked.signal.aborted,true);tracked.close()
    assert.equal(f.seen.filter(row=>row.url.endsWith('/responses')).length,0)
  }finally{release();await f.close()}
})
test('ordinary token refresh preserves a prepared connection while actual wire uses its new token',async()=>{
  const f=await fixture();try{
    await f.login();const adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher),id=(await f.accounts.status()).activeAccountId
    const prepared=await adapter.prepareCall(PROVIDER,model.id)
    await f.store.updateAccount(id,account=>{account.tokens.expiresAt=Date.now()-1;return account})
    const chunks=await Array.fromAsync(prepared.stream({provider:PROVIDER,model:model.id,messages:[{role:'user',content:[{type:'text',text:'owned'}]}]}))
    assert.equal(chunks.at(-1).reason.kind,'stop');assert.equal(f.refreshes(),1)
    assert.equal(new Headers(f.seen.find(row=>row.url.endsWith('/responses')).init.headers).get('authorization'),'Bearer owned-access-2')
  }finally{await f.close()}
})
test('canonical history survives an account switch but opaque provider replay does not cross it',async()=>{
  const f=await fixture();try{
    await f.login();const adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher),user={role:'user',content:[{type:'text',text:'owned'}]}
    const assembler=new BlockAssembler();for await(const chunk of adapter.stream({provider:PROVIDER,model:model.id,messages:[user]}))assembler.push(chunk)
    const assistant=assembler.message({provider:PROVIDER,model:model.id});assert.equal(assistant.source.provider,PROVIDER)
    await f.login();await Array.fromAsync(adapter.stream({provider:PROVIDER,model:model.id,messages:[user,assistant,{role:'user',content:[{type:'text',text:'continue'}]}]}))
    const request=f.seen.filter(row=>row.url.endsWith('/responses')).at(-1),wire=String(request.init.body)
    assert(wire.includes('Owned completed response'));assert(!wire.includes('msg_owned'));assert(!wire.includes('resp_owned'))
    assert.equal(new Headers(request.init.headers).get('authorization'),'Bearer owned-access-2')
  }finally{await f.close()}
})
test('actual model tool call and matching canonical tool result reach the next native encoder request',async()=>{
  const f=await fixture();try{
    await f.login();const adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher)
    const fc={type:'function_call',id:'fc_owned',call_id:'call_owned',name:'owned_tool',arguments:'{"value":7}',status:'completed'}
    f.response((_url,init)=>{
      const body=JSON.parse(init.body);assert(body.input.some(row=>row.type==='additional_tools'&&row.tools.some(tool=>tool.name==='owned_tool')))
      const events=[{type:'response.created',response:{id:'resp_tool',model:body.model,status:'in_progress'}},
        {type:'response.output_item.added',output_index:0,item:{...fc,arguments:'',status:'in_progress'}},
        {type:'response.function_call_arguments.delta',output_index:0,item_id:fc.id,delta:fc.arguments},
        {type:'response.function_call_arguments.done',output_index:0,item_id:fc.id,arguments:fc.arguments},
        {type:'response.output_item.done',output_index:0,item:fc},
        {type:'response.completed',response:{id:'resp_tool',model:body.model,status:'completed',output:[fc],usage:{input_tokens:2,output_tokens:3,total_tokens:5}}}]
      return new Response(events.map(event=>'data: '+JSON.stringify(event)+'\n\n').join('')+'data: [DONE]\n\n',{headers:{'content-type':'text/event-stream'}})
    })
    const user={role:'user',content:[{type:'text',text:'invoke the owned tool'}]},tools=[{name:'owned_tool',description:'owned mock',parameters:{type:'object',properties:{value:{type:'number'}},required:['value']}}]
    const assembler=new BlockAssembler();for await(const chunk of adapter.stream({provider:PROVIDER,model:model.id,messages:[user],tools}))assembler.push(chunk)
    assert.equal(assembler.finish.kind,'tool-calls',String(f.seen.filter(row=>row.url.endsWith('/responses')).at(-1)?.init.body));const assistant=assembler.message({provider:PROVIDER,model:model.id}),tool=assistant.content.find(row=>row.type==='tool-call')
    assert.equal(tool.name,'owned_tool');assert.deepEqual(JSON.parse(tool.arguments),{value:7})
    const result=createToolResultMessage({callId:tool.id,content:[{type:'text',text:'{"real_fixture_result":49}'}],isError:false})
    f.response(undefined);await Array.fromAsync(adapter.stream({provider:PROVIDER,model:model.id,messages:[user,assistant,result],tools}))
    const wire=JSON.parse(f.seen.filter(row=>row.url.endsWith('/responses')).at(-1).init.body)
    assert(wire.input.some(row=>row.type==='function_call'&&row.name==='owned_tool'))
    assert(wire.input.some(row=>row.type==='function_call_output'&&String(row.output).includes('real_fixture_result')))
  }finally{await f.close()}
})
test('selected model image input uses the public attachment projection and actual inline bytes',async()=>{
  const f=await fixture();try{
    await f.login();const bytes=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZXsAAAAASUVORK5CYII=','base64')
    const ref={attachmentId:'owned-image',mediaType:'image/png',bytes:bytes.length,width:1,height:1};let target
    f.ctx.provide('attachments',{imageHostPath:()=>undefined,readImageRequest:async(_ref,value)=>{target=value;return {variantId:'owned-variant',attachment:ref,data:bytes,mediaType:'image/png',bytes:bytes.length,width:1,height:1,depth:'uchar',space:'srgb',hasAlpha:true}}})
    const adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher)
    await Array.fromAsync(adapter.stream({provider:PROVIDER,model:model.id,messages:[{role:'user',content:[{type:'text',text:'owned image transport'},{type:'image',attachment:ref}]}]}))
    assert.deepEqual(target,adapter.imageRequestTarget(PROVIDER,model.id,ref))
    const wire=String(f.seen.find(row=>row.url.endsWith('/responses')).init.body);assert(wire.includes('data:image/png;base64,'+bytes.toString('base64')))
  }finally{await f.close()}
})
test('incomplete terminal cannot be reported as success',async()=>{
  const f=await fixture();try{await f.login();f.mode('incomplete');const adapter=new SubscriptionAdapter(f.accounts,f.ctx,f.fetcher)
    const chunks=await Array.fromAsync(adapter.stream({provider:PROVIDER,model:model.id,messages:[{role:'user',content:[{type:'text',text:'owned'}]}]}))
    assert.equal(chunks.find(row=>row.type==='finish').reason.kind,'error')
  }finally{await f.close()}
})
test('SiWC shaping retains tools and full history, removes unsupported state and system items',()=>{
  const input=[{role:'system',content:'system context'},{role:'user',content:'user context'}]
  const value=siwcPayload({input,tools:[{type:'function',name:'owned_tool'}],max_output_tokens:100,previous_response_id:'old',metadata:{a:1},temperature:.5})
  assert.equal(value.input[0].type,'additional_tools');assert.equal(value.input[1].role,'developer');assert.equal(input[0].role,'system')
  assert(!value.tools&&!value.max_output_tokens&&!value.previous_response_id&&!value.metadata)
  assert.throws(()=>siwcPayload({input,tools:[{type:'tool_search'}]}),/hosted tool/)
})
