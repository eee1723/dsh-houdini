/** A UI adapter for DSH's account, settings and model services. OAuth and grants stay native. */
import {randomUUID} from 'node:crypto'
import fs from 'node:fs/promises'
import type {Context} from '@deepseek-ai/cordis'
import {hostService} from './api-route.js'

const PROVIDER='openai',KEY='llm-pi-ai/openai'
const LEGACY_ID_FILE='dsh-houdini-chatgpt-host-id.json'
type SafeError={code:string;message:string}
type Selection={model:string;reasoningEffort?:string}
type AccountView={issuer:string;subject:string;email?:string;name?:string}
type PromptView={id:string;kind:'text'|'secret'|'select';message:string;placeholder?:string;options?:Array<{id:string;label:string;description?:string}>}
type LoginView={attemptId:string;status:'pending'|'authorized'|'cancelled'|'failed';notice?:{message:string;url?:string;code?:string};prompt?:PromptView;error?:SafeError}
type Attempt={view:LoginView;controller:AbortController;done:Promise<void>;timer?:ReturnType<typeof setTimeout>;answer?:{id:string;resolve:(value:string)=>void;reject:(error:Error)=>void;cleanup:()=>void}}
export interface ChatGptAccountOptions {
  /** Test/deployment injection of the native login preparation, never a credential writer. */
  prepareLogin?:(ctx:Context)=>Promise<void>
  loginTimeoutMs?:number
}
const MESSAGES:Record<string,string>={
  UNAVAILABLE:'当前运行环境尚未提供 ChatGPT 登录能力，请更新运行环境后重试。',
  CREDENTIAL_UNAVAILABLE:'暂时无法读取账户保存状态，请稍后重试。',
  READ_ONLY:'当前配置为只读，无法保存此修改。',
  BUSY:'登录或账户操作仍在进行，请完成或取消后再试。',
  STALE_ATTEMPT:'这次登录已结束或被替换，请使用当前登录窗口。',
  STALE_PROMPT:'这项登录输入已失效，请查看当前提示。',
  INVALID_INPUT:'请检查所选模型或登录输入。',
  ROUTE_CONFLICT:'现有 OpenAI 配置包含其他认证或请求地址，请先在模型设置中处理；此页面不会覆盖它。',
  API_KEY_CONFLICT:'当前 OpenAI 记录是 API Key。请先在模型设置中处理该记录，避免覆盖现有账户。',
  AUTH:'登录未完成或已失效，请重新登录后再试。',
  RATE_LIMIT:'当前账户的请求频率或额度受限，请稍后重试或查看 ChatGPT 套餐与用量。',
  FORBIDDEN:'当前账户未获准使用所选模型，请检查账户权限或选择其他模型。',
  MODEL_UNAVAILABLE:'所选模型不在当前可用目录中，请刷新后重新选择。',
  NETWORK:'暂时无法连接授权或模型服务，请检查网络后重试。',
  CANCELLED:'操作已取消。',
  TIMEOUT:'等待超时，请重新发起操作。',
  SETTINGS_CONFLICT:'模型配置刚刚发生变化，请刷新后重试。',
  MIGRATION_UNAVAILABLE:'无法定位当前运行环境的原登录设备记录，请更新运行环境后重试。',
  MIGRATION_INVALID:'原登录设备记录无法读取或格式无效，已保留原文件，请使用运行诊断处理。',
  INCOMPLETE:'服务没有返回完整文本答复，本次连接尚未验证。',
  FAILED:'操作未完成，请刷新状态后重试。',
}
export class ChatGptAccountError extends Error {
  constructor(readonly code:string){super(MESSAGES[code]??MESSAGES.FAILED);this.name='ChatGptAccountError'}
}
function safeError(error:any):SafeError {
  const raw=error?.failure??error,code=String(raw?.code??error?.code??'').toUpperCase(),status=raw?.status??error?.status
  const normalized=error instanceof ChatGptAccountError?error.code
    :code==='SETTINGS_CONFLICT'?'SETTINGS_CONFLICT'
    :code==='ALREADY_IN_FLIGHT'?'BUSY'
    :code==='UNSUPPORTED_REASONING_EFFORT'?'INVALID_INPUT'
    :status===401||['AUTH','UNAUTHORIZED','AUTHENTICATION_FAILED'].includes(code)?'AUTH'
    :status===403?'FORBIDDEN':status===429||['RATE_LIMIT','QUOTA_EXCEEDED','INSUFFICIENT_QUOTA'].includes(code)?'RATE_LIMIT'
    :['ABORTED','CANCELLED'].includes(code)||error?.name==='AbortError'?'CANCELLED'
    :code==='TIMEOUT'||error?.name==='TimeoutError'?'TIMEOUT'
    :['NETWORK','NETWORK_ERROR','CONNECTION_ERROR'].includes(code)?'NETWORK'
    :['NO_FLOW','NO_ADAPTER','NO_SERVICE','UNKNOWN_METHOD','ERR_MODULE_NOT_FOUND'].includes(code)?'UNAVAILABLE':'FAILED'
  return {code:normalized,message:MESSAGES[normalized]??MESSAGES.FAILED}
}
function fail(code:string):never{throw new ChatGptAccountError(code)}
const object=(value:any):value is Record<string,any>=>value!==null&&typeof value==='object'&&!Array.isArray(value)
const present=(value:any)=>value!==undefined&&value!==null&&value!==''
function selection(input:unknown):Selection {
  if(!object(input)||Object.keys(input).some(key=>!['model','reasoningEffort'].includes(key))
    ||typeof input.model!=='string'||!input.model.trim()||input.model.length>256
    ||input.reasoningEffort!==undefined&&(typeof input.reasoningEffort!=='string'||!input.reasoningEffort||input.reasoningEffort.length>64))fail('INVALID_INPUT')
  return {model:input.model,...(input.reasoningEffort!==undefined?{reasoningEffort:input.reasoningEffort}:{})}
}
function officialEndpoint(value:unknown):boolean {
  if(typeof value!=='string')return false
  try {const url=new URL(value);return url.protocol==='https:'&&url.hostname==='api.openai.com'&&!url.port&&!url.username&&!url.password
    &&!url.search&&!url.hash&&url.pathname.replace(/\/+$/,'')==='/v1'}catch{return false}
}
/** Inspect configured fields only; never expose their values or rewrite a profile. */
export function chatGptRouteConflicts(profile:unknown):Array<{field:string;message:string}> {
  const result:Array<{field:string;message:string}>=[]
  const check=(value:any,prefix='')=>{
    if(!object(value))return
    const add=(field:string)=>result.push({field:prefix+field,message:`${prefix+field} 会改变 ChatGPT 的认证或官方请求路由，请在模型设置中处理。`})
    for(const field of ['apiKeyEnv','apiKey','key'])if(present(value[field]))add(field)
    if(present(value.headers)&&(!object(value.headers)||Object.keys(value.headers).length))add('headers')
    for(const field of ['baseURL','baseUrl'])if(present(value[field])&&!officialEndpoint(value[field]))add(field)
    for(const field of ['api','protocol'])if(present(value[field])&&value[field]!=='openai-responses')add(field)
    if(present(value.provider)&&value.provider!==PROVIDER)add('provider')
  }
  check(profile)
  if(object(profile)){
    if(Array.isArray(profile.models))profile.models.forEach((model:any,index:number)=>check(model,`models[${index}].`))
    if(object(profile.modelOverrides))for(const [id,value] of Object.entries(profile.modelOverrides))check(value,`modelOverrides[${id}].`)
  }
  return result
}

/** The old plugin file contains only a device id. Import it through the native owner on explicit login. */
async function prepareNativeLogin(ctx:Context):Promise<void> {
  const native=hostService(ctx,'piAiAccounts')
  if(typeof native?.ensureInstallationId!=='function')fail('UNAVAILABLE')
  const credentials=hostService(ctx,'credentials'),info=await credentials.describeRecord(KEY)
  let previousId:string|undefined
  const installation=await credentials.describeRecord('llm-pi-ai-installation/openai')
  if(info.configured&&info.kind==='grant'&&!installation.configured){
    const homePath=hostService(ctx,'dshHomePath')
    if(typeof homePath!=='function')fail('MIGRATION_UNAVAILABLE')
    try {
      const file=await fs.open(homePath(LEGACY_ID_FILE),'r')
      try {
        if((await file.stat()).size>4096)fail('MIGRATION_INVALID')
        const value=JSON.parse(await file.readFile('utf8'))
        if(value?.schemaVersion!==1||value?.app!=='DSH-Houdini'||typeof value.deviceId!=='string'
          ||!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value.deviceId))fail('MIGRATION_INVALID')
        previousId=value.deviceId
      }finally{await file.close()}
    }catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')fail('MIGRATION_INVALID')}
  }
  await native.ensureInstallationId(PROVIDER,previousId?{previousId}:undefined)
}

export class ChatGptAccountController {
  private attempt?:Attempt
  private closed=false
  private changing=false
  private readonly probes=new Set<AbortController>()
  constructor(private readonly ctx:Context,private readonly options:ChatGptAccountOptions={}){}
  private pending(){return this.attempt?.view.status==='pending'}
  private service(name:string){const value=hostService(this.ctx,name);if(!value)fail('UNAVAILABLE');return value}
  private route(){
    const llm=hostService(this.ctx,'llm'),settings=hostService(this.ctx,'settings')
    const entry=llm?.listConfigurableProviders().find((row:any)=>row.provider===PROVIDER)
    const descriptor=entry?settings?.describe({redactSecrets:true}).find((row:any)=>row.ns===entry.settingsNs):undefined
    let profile=descriptor?.value
    for(const key of entry?.settingsPath??[])profile=object(profile)?profile[key]:undefined
    return {entry,descriptor,profile,configured:object(profile),registered:Boolean(llm?.listProviders().some((row:any)=>row.id===PROVIDER)),
      writable:settings?.writable===true,conflicts:chatGptRouteConflicts(profile)}
  }
  async status(signal?:AbortSignal){
    try{return await this.readStatus(signal)}catch(error){throw new ChatGptAccountError(safeError(error).code)}
  }
  private async readStatus(signal?:AbortSignal){
    signal?.throwIfAborted()
    const auth=hostService(this.ctx,'authorization'),flow=auth?.describe(KEY)
    const native=hostService(this.ctx,'piAiAccounts')
    let credential:{stored:boolean|null;kind:'grant'|'api-key'|null;writable:boolean;error?:SafeError}={stored:null,kind:null,writable:false}
    let account:AccountView|undefined,registrationAvailable:boolean|undefined,disconnecting:boolean|undefined
    try {
      const info=typeof native?.describe==='function'?await native.describe(PROVIDER)
        :await this.service('credentials').describeRecord(KEY)
      credential={stored:info.configured===true,kind:info.kind??null,writable:info.writable===true}
      if(typeof info.registrationAvailable==='boolean')registrationAvailable=info.registrationAvailable
      if(typeof info.disconnecting==='boolean')disconnecting=info.disconnecting
      if(typeof info.account?.issuer==='string'&&typeof info.account?.subject==='string')account={issuer:info.account.issuer,subject:info.account.subject,
        ...(typeof info.account.email==='string'?{email:info.account.email}:{}),...(typeof info.account.name==='string'?{name:info.account.name}:{})}
    }
    catch{credential.error={code:'CREDENTIAL_UNAVAILABLE',message:MESSAGES.CREDENTIAL_UNAVAILABLE}}
    const route=this.route(),models:any[]=[]
    let catalogError:SafeError|undefined
    if(route.entry&&route.conflicts.length===0)try{
      const llm=this.service('llm'),catalog=route.registered?await llm.listModels(PROVIDER):await llm.discoverModels(route.entry.settingsNs,{provider:PROVIDER},signal)
      const resolved=await Promise.all(catalog.map(async(row:any)=>route.registered?llm.resolveModelInfo(PROVIDER,row.id,signal):row))
      for(const row of resolved)models.push({id:row.id,name:row.name??row.id,...(row.inputModalities?{inputModalities:[...row.inputModalities]}:{}),
        ...(row.context?.contextWindow??row.contextWindow?{contextWindow:row.context?.contextWindow??row.contextWindow}:{}),
        ...(row.reasoning?{reasoning:{efforts:row.reasoning.efforts.map((effort:any)=>({id:effort.id,name:effort.name,...(effort.description?{description:effort.description}:{})})),
          ...(row.reasoning.defaultEffort?{defaultEffort:row.reasoning.defaultEffort}:{})}}:{})})
    }catch(error){catalogError=safeError(error)}
    const current=hostService(this.ctx,'agentDefaultModel')?.currentSelection()
    return {nativeFlowAvailable:Boolean(flow?.methods.some((method:any)=>method.id==='oauth')
        &&typeof native?.ensureInstallationId==='function'&&typeof native?.describe==='function'&&typeof native?.disconnect==='function'),
      credential,route:{configured:route.configured,registered:route.registered,writable:route.writable,conflicts:route.conflicts},models,
      defaultSelection:current?{provider:current.provider,model:current.model,...(current.reasoningEffort?{reasoningEffort:current.reasoningEffort}:{})}:null,
      login:this.attempt?structuredClone(this.attempt.view):null,...(catalogError?{catalogError}:{}),...(account?{account}:{}),
      ...(registrationAvailable!==undefined?{registrationAvailable}:{}),...(disconnecting!==undefined?{disconnecting}:{})}
  }
  async start(){
    if(this.closed)fail('UNAVAILABLE')
    if(this.changing||this.pending())fail('BUSY')
    this.changing=true
    try{return await this.beginLogin()}catch(error){throw new ChatGptAccountError(safeError(error).code)}finally{this.changing=false}
  }
  private async beginLogin(){
    if(this.closed)fail('UNAVAILABLE')
    if(this.pending())fail('BUSY')
    const auth=this.service('authorization'),flow=auth.describe(KEY)
    this.service('piAiAccounts')
    if(!flow?.methods.some((method:any)=>method.id==='oauth'))fail('UNAVAILABLE')
    if(flow.inFlight)fail('BUSY')
    const info=await this.service('credentials').describeRecord(KEY)
    if(!info.writable)fail('READ_ONLY')
    if(info.kind==='api-key')fail('API_KEY_CONFLICT')
    // Reserve the presentation before any asynchronous preparation, so another click cannot replace it.
    if(this.closed)fail('UNAVAILABLE')
    if(this.pending())fail('BUSY')
    const attempt:Attempt={view:{attemptId:randomUUID(),status:'pending'},controller:new AbortController(),done:Promise.resolve()}
    this.attempt=attempt
    attempt.timer=setTimeout(()=>{if(attempt.view.status==='pending'){
      attempt.view.error={code:'TIMEOUT',message:MESSAGES.TIMEOUT};attempt.controller.abort()
    }},this.options.loginTimeoutMs??10*60*1000)
    attempt.timer.unref?.()
    attempt.done=(async()=>{
      try {
        if(this.options.prepareLogin)await this.options.prepareLogin(this.ctx)
        else await prepareNativeLogin(this.ctx)
        attempt.controller.signal.throwIfAborted()
        const outcome=await auth.begin({key:KEY,method:'oauth',signal:attempt.controller.signal,interaction:{
          notify:(notice:any)=>{if(this.attempt===attempt&&attempt.view.status==='pending')attempt.view.notice={message:String(notice.message),
            ...(typeof notice.url==='string'?{url:notice.url}:{}),...(typeof notice.code==='string'?{code:notice.code}:{})}},
          prompt:(prompt:any)=>this.prompt(attempt,prompt),
        }})
        attempt.view.status=outcome.status==='authorized'?'authorized':'cancelled'
      }catch(error){attempt.view.status=attempt.controller.signal.aborted?'cancelled':'failed';attempt.view.error??=safeError(error)}
      finally{if(attempt.timer)clearTimeout(attempt.timer);attempt.answer?.reject(new ChatGptAccountError('STALE_PROMPT'));attempt.answer?.cleanup();
        attempt.answer=undefined;delete attempt.view.prompt;delete attempt.view.notice}
    })()
    return this.status()
  }
  private prompt(attempt:Attempt,prompt:any):Promise<string>{
    if(attempt.controller.signal.aborted||prompt.signal?.aborted)return Promise.reject(new ChatGptAccountError('CANCELLED'))
    if(attempt.answer)return Promise.reject(new ChatGptAccountError('BUSY'))
    return new Promise((resolve,reject)=>{
      const id=randomUUID(),abort=()=>{if(attempt.answer?.id===id){attempt.answer.cleanup();attempt.answer=undefined;delete attempt.view.prompt}reject(new ChatGptAccountError('CANCELLED'))}
      const cleanup=()=>{prompt.signal?.removeEventListener('abort',abort);attempt.controller.signal.removeEventListener('abort',abort)}
      attempt.answer={id,resolve,reject,cleanup}
      attempt.view.prompt={id,kind:prompt.kind,message:String(prompt.message),...(typeof prompt.placeholder==='string'?{placeholder:prompt.placeholder}:{}),
        ...(Array.isArray(prompt.options)?{options:prompt.options.map((row:any)=>({id:row.id,label:row.label,...(row.description?{description:row.description}:{})}))}:{})}
      prompt.signal?.addEventListener('abort',abort,{once:true});attempt.controller.signal.addEventListener('abort',abort,{once:true})
    })
  }
  async submitPrompt(input:unknown){
    if(!object(input)||Object.keys(input).some(key=>!['attemptId','promptId','value'].includes(key))||typeof input.value!=='string'||input.value.length>16384)fail('INVALID_INPUT')
    const attempt=this.attempt
    if(!attempt||attempt.view.status!=='pending'||attempt.view.attemptId!==input.attemptId)fail('STALE_ATTEMPT')
    const answer=attempt.answer
    if(!answer||answer.id!==input.promptId)fail('STALE_PROMPT')
    if(attempt.view.prompt?.kind==='select'&&!attempt.view.prompt.options?.some(row=>row.id===input.value))fail('INVALID_INPUT')
    answer.cleanup();attempt.answer=undefined;delete attempt.view.prompt;answer.resolve(input.value)
    return this.status()
  }
  async cancel(input:unknown){
    if(!object(input)||Object.keys(input).join(',')!=='attemptId')fail('INVALID_INPUT')
    const attempt=this.attempt
    if(!attempt||attempt.view.attemptId!==input.attemptId)fail('STALE_ATTEMPT')
    if(attempt.view.status==='pending'){attempt.controller.abort();await attempt.done}
    return this.status()
  }
  private async ready(input:unknown,enable:boolean,signal?:AbortSignal){
    const picked=selection(input),credentials=this.service('credentials'),info=await credentials.describeRecord(KEY)
    this.service('piAiAccounts')
    if(info.kind==='api-key')fail('API_KEY_CONFLICT')
    if(!info.configured||info.kind!=='grant')fail('AUTH')
    const route=this.route()
    if(!route.entry||route.entry.nativeAuth?.oauth!==true)fail('UNAVAILABLE')
    if(route.conflicts.length)fail('ROUTE_CONFLICT')
    const llm=this.service('llm'),catalog=route.registered?await llm.listModels(PROVIDER):await llm.discoverModels(route.entry.settingsNs,{provider:PROVIDER},signal)
    if(!catalog.some((row:any)=>row.id===picked.model))fail('MODEL_UNAVAILABLE')
    if(!route.configured){
      if(!enable)fail('UNAVAILABLE')
      if(!route.writable||!route.descriptor)fail('READ_ONLY')
      await this.service('settings').mutate(route.entry.settingsNs,[{op:'set',path:route.entry.settingsPath,value:{displayName:'ChatGPT'}}],route.descriptor.revision)
    }
    const current=this.route()
    if(current.conflicts.length)fail('ROUTE_CONFLICT')
    if(!current.registered)fail('UNAVAILABLE')
    return llm.resolveCallConfig({provider:PROVIDER,...picked},signal)
  }
  async select(input:unknown){
    if(this.closed)fail('UNAVAILABLE')
    if(this.changing)fail('BUSY')
    this.changing=true
    try{const resolved=await this.ready(input,true);await this.service('agentDefaultModel').saveSelection({provider:PROVIDER,model:resolved.model,
      ...(resolved.reasoningEffort?{reasoningEffort:resolved.reasoningEffort}:{})});return await this.status()}
    catch(error){const safe=safeError(error);throw new ChatGptAccountError(safe.code)}finally{this.changing=false}
  }
  async signout(){
    if(this.closed)fail('UNAVAILABLE')
    if(this.changing)fail('BUSY')
    this.changing=true
    try{
      const credentials=this.service('credentials'),info=await credentials.describeRecord(KEY)
      if(info.kind==='api-key')fail('API_KEY_CONFLICT')
      if(!info.writable)fail('READ_ONLY')
      for(const probe of this.probes)probe.abort()
      if(this.attempt?.view.status==='pending')await this.cancel({attemptId:this.attempt.view.attemptId})
      // The native logout helper will coordinate revocation and local deletion with an in-flight grant commit.
      const native=this.service('piAiAccounts')
      if(typeof native.disconnect!=='function')fail('UNAVAILABLE')
      const result=await native.disconnect(PROVIDER)
      return {...await this.status(),signout:{revocation:['confirmed','unconfirmed','not-supported'].includes(result.revocation)?result.revocation:'unconfirmed',localCleared:result.localCleared===true}}
    }catch(error){throw new ChatGptAccountError(safeError(error).code)}finally{this.changing=false}
  }
  async probe(input:unknown,signal?:AbortSignal){
    const started=Date.now(),picked=selection(input),controller=new AbortController()
    let timedOut=false
    const abort=()=>controller.abort(),timer=setTimeout(()=>{timedOut=true;abort()},45000)
    this.probes.add(controller)
    signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort()
    try{
      if(this.closed)fail('UNAVAILABLE')
      const config=await this.ready(picked,false,controller.signal)
      let text='',finished=false
      for await(const chunk of this.service('llm').stream({...config,maxTokens:128,messages:[{role:'user',content:[{type:'text',text:'Reply with only OK.'}]}],tools:[],signal:controller.signal})){
        if(chunk.type==='text-delta')text=(text+chunk.text).slice(0,512)
        if(chunk.type==='finish'){
          if(chunk.reason.kind==='error'||chunk.reason.kind==='aborted')throw chunk.reason.failure
          finished=chunk.reason.kind==='stop'
        }
      }
      if(!finished||!text.trim())fail('INCOMPLETE')
      return {ok:true,code:'CONNECTED',message:'已收到所选模型的完整文本答复。此测试会使用少量账户额度。',model:picked.model,elapsedMs:Date.now()-started}
    }catch(error){const safe=controller.signal.aborted?{code:timedOut?'TIMEOUT':'CANCELLED',message:timedOut?MESSAGES.TIMEOUT:MESSAGES.CANCELLED}:safeError(error)
      return {ok:false,...safe,model:picked.model,elapsedMs:Date.now()-started}}
    finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);this.probes.delete(controller)}
  }
  async dispose(){this.closed=true;for(const probe of this.probes)probe.abort();const attempt=this.attempt;if(attempt?.view.status==='pending'){attempt.controller.abort();await attempt.done}this.attempt=undefined}
}
