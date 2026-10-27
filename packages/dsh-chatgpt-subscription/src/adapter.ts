/** Public adapter composition: a unique DSH route, private inner OpenAI route.
 * No global openai registration, native encoder copy or core modification. */
import {LlmAdapter,LlmError,resolveRetryPolicy,resolveImageAttachmentAccess,type GenerateOptions,type PreparedAdapterCall,type LlmResolvedModelInfo} from '@deepseek-ai/dsh-llm'
import {PiAiAdapter,type ResolvedPiAiProviderProfile} from '@deepseek-ai/dsh-llm-pi-ai'
import {openaiProvider} from '@earendil-works/pi-ai/providers/openai'
import {getBuiltinModels} from '@earendil-works/pi-ai/providers/all'
import {type Model,type SimpleStreamOptions,type Provider} from '@earendil-works/pi-ai'
import type {Context} from '@deepseek-ai/cordis'
import {requestImageDimensions,type ImageAttachmentRef} from '@deepseek-ai/dsh-attachment'
import {SubscriptionAccounts} from './accounts.js'
import {PROVIDER,type Fetcher,type AccountGeneration} from './types.js'
import {SubscriptionError} from './errors.js'
import {subscriptionStream} from './transport.js'
export {siwcPayload} from './transport.js'
function provider(models:readonly Model<'openai-responses'>[],fetcher:Fetcher,resolveToken:(signal:AbortSignal)=>Promise<string>):Provider<'openai-responses'>{
  const base=openaiProvider()
  return {...base,getModels:()=>models,getAllModels:()=>models,
    auth:{apiKey:{name:'SiWC authorized account only',resolve:async({signal})=>({auth:{apiKey:await resolveToken(signal)},source:'ChatGPT subscription'})}},
    stream(model,context,options){return subscriptionStream(model,context,options,fetcher)},
    streamSimple(model,context,options){return subscriptionStream(model,context,options,fetcher)}}
}

export class SubscriptionAdapter extends LlmAdapter {
  constructor(private readonly accounts:SubscriptionAccounts,private readonly ctx:Context,private readonly fetcher:Fetcher=fetch){super()}
  providerInfo(){return {id:PROVIDER,name:'ChatGPT 订阅（SiWC）'}}
  providerRetryPolicy(){return resolveRetryPolicy({mode:'normal',maxRetries:0},PROVIDER)}
  imageRequestTarget(_provider:string,_model:string,image:ImageAttachmentRef){
    return {...requestImageDimensions(image.width,image.height,2048*2048),maxBytes:1024*1024}
  }
  private async capture(signal:AbortSignal=AbortSignal.timeout(15000)){
    const selection=await this.accounts.selection(),{account,generation}=selection,catalog=await this.accounts.catalogFor(account.id,signal)
    const known=new Map(getBuiltinModels('openai').filter(model=>model.api==='openai-responses').map(model=>[model.id,model]))
    const models=catalog.flatMap(row=>{const model=known.get(row.id);return model?[{...model,name:row.name,
      compat:{...model.compat,supportsDeveloperRole:true,supportsMaxOutputTokens:false,supportsAdditionalTools:true,
        supportsMidConvoSystemMessages:true,supportsToolSearch:false}}]:[]}) as Model<'openai-responses'>[]
    await this.accounts.assertGeneration(generation)
    const piProvider=provider(models,this.fetcher,async callSignal=>(await this.accounts.tokenFor(account.id,callSignal,generation)).accessToken)
    const profile:ResolvedPiAiProviderProfile={provider:'openai',displayName:'ChatGPT 订阅（SiWC）',api:'openai-responses',baseURL:'https://api.openai.com/v1',
      piProvider,modelErrors:new Map(),configuredMaxTokens:new Map(),retryPolicy:resolveRetryPolicy({mode:'normal',maxRetries:0},PROVIDER),streamIdleTimeoutMs:300000,
      maxRequestImageBytes:20*1024*1024,requestImagePixelBudget:2048*2048,requestImageMaxBytes:1024*1024,transport:'sse'}
    const profiles=new Map([['openai',profile]])
    const inner=new PiAiAdapter({profiles:()=>profiles,resolveApiKey:async()=>{
      const current=await this.accounts.store.readAccount(account.id)
      if(!current||current.status!=='connected'||!current.tokens)throw new LlmError('请先连接此 ChatGPT 账户。','MISSING_CREDENTIAL')
      // The private provider resolves the owning OAuth grant. No virtual env
      // reference, API-key override or ambient discovery is introduced.
      return undefined
    },auth:{credentials:{read:async()=>undefined,list:async()=>[],modify:async()=>{throw new Error('No secondary credential writer')},delete:async()=>{}},
      authContext:{env:async()=>undefined,fileExists:async()=>false}},resolveAttachments:()=>this.ctx.get('attachments'),
      resolveImageAccess:(attachments,ref)=>resolveImageAttachmentAccess(attachments,host=>this.ctx.get('fs')?.processPathFromHostPath(host),ref)})
    return {inner,accountId:account.id,generation,models}
  }
  async listModels(){
    try{const {models}=await this.capture();return models.map(model=>({provider:PROVIDER,id:model.id,name:model.name,inputModalities:[...model.input]}))}
    catch(error){if(error instanceof SubscriptionError&&['SIGN_IN_REQUIRED','REAUTH_REQUIRED'].includes(error.code))return [];throw error}
  }
  async resolveModel(_provider:string,model:string,signal?:AbortSignal):Promise<LlmResolvedModelInfo>{
    const snapshot=await this.capture(signal);return {...await snapshot.inner.resolveModel('openai',model,signal),provider:PROVIDER}
  }
  async prepareCall(_provider:string,model:string,signal?:AbortSignal):Promise<PreparedAdapterCall>{
    const snapshot=await this.capture(signal),prepared=await snapshot.inner.prepareCall('openai',model,signal)
    return {model:{...prepared.model,provider:PROVIDER},stream:options=>this.run(snapshot.generation,prepared,options)}
  }
  async *stream(options:GenerateOptions){const prepared=await this.prepareCall(PROVIDER,options.model,options.signal);yield*prepared.stream(options)}
  private async *run(generation:AccountGeneration,prepared:PreparedAdapterCall,options:GenerateOptions){
    await this.accounts.assertGeneration(generation)
    const accountId=generation.accountId,call=this.accounts.trackCall(accountId)
    const messages=options.messages.map(message=>{
      if(message.role!=='assistant'||message.source.provider!==PROVIDER)return message
      const replay=message.source.replayState as {response?:Record<string,unknown>;blocks?:readonly unknown[]}|undefined
      if(replay?.response?.siwcAccountId===accountId){
        const {siwcAccountId:_binding,...response}=replay.response
        return {...message,source:{...message.source,provider:'openai',replayState:{...replay,response:{...response,provider:'openai'}}}}
      }
      const {replayState:_discarded,...source}=message.source
      return {...message,source}
    })
    try{for await(const chunk of prepared.stream({...options,messages,provider:'openai',signal:options.signal?AbortSignal.any([options.signal,call.signal]):call.signal})){
      if(chunk.type==='finish'&&chunk.replayState&&chunk.replayState.response&&typeof chunk.replayState.response==='object')
        yield {...chunk,replayState:{...chunk.replayState,response:{...chunk.replayState.response,provider:PROVIDER,siwcAccountId:accountId}}}
      else yield chunk
    }}
    finally{call.close()}
  }
}
