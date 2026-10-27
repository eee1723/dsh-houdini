import {randomUUID} from 'node:crypto'
import type {AuthorizationService,AuthorizationSession} from '@deepseek-ai/dsh-authorization'
import type {Account,AccountState,AccountView,Fetcher,LoginView,ModelView,PendingTokens,StatusView,AccountGeneration} from './types.js'
import {PLAN_SCOPE,PROVIDER,RESOURCE} from './types.js'
import {AccountStore,profileKey} from './store.js'
import {SiwcProtocol} from './oauth.js'
import {SubscriptionError,safeFailure} from './errors.js'
import {attributionHeaders} from '@deepseek-ai/dsh-llm'
import {getBuiltinModels} from '@earendil-works/pi-ai/providers/all'

type Attempt={view:LoginView;accountId:string;abort:AbortController;done:Promise<void>;reopen?:()=>Promise<void>}
const accountView=(account:Account,activeId?:string):AccountView=>({id:account.id,label:account.label,status:account.status,
  sharing:account.status==='connected'&&!!account.tokens&&account.scopes.includes(PLAN_SCOPE),active:account.id===activeId,
  verificationPending:!!account.pending,needsPlanNotice:account.status==='connected'&&account.scopes.includes(PLAN_SCOPE)&&!account.planNoticeAcknowledged,
  ...account.identity?{identity:{...account.identity}}:{}})

/** Account selection and refreshed credentials remain in one protected native record. */
export class SubscriptionAccounts {
  private attempt?:Attempt
  private starting=false
  private closed=false
  private readonly calls=new Map<AbortController,string>()
  private readonly tokenOperations=new Set<Promise<unknown>>()
  private readonly catalogs=new Map<string,{revision:number;models:ModelView[]}>()
  private readonly flows=new Map<string,()=>void>()
  constructor(readonly store:AccountStore,readonly protocol:SiwcProtocol,private readonly authorization:AuthorizationService,
    private readonly openBrowser:(url:string)=>Promise<void>,private readonly fetcher:Fetcher=fetch,
    private readonly changed:()=>void=()=>{}){}
  async status():Promise<StatusView>{
    const state=await this.store.read(),active=state?.accounts.find(account=>account.id===state.activeId)
    const catalog=active?this.catalogs.get(active.id):undefined,catalogRead=!!(catalog&&catalog.revision===active?.revision)
    return {provider:PROVIDER,accounts:(state?.accounts??[]).map(account=>accountView(account,state?.activeId)),activeAccountId:state?.activeId??null,
      login:this.attempt?structuredClone(this.attempt.view):null,models:catalogRead?catalog!.models:[],catalogRead,protection:this.store.protector.id,
      usageUrl:'https://chatgpt.com/settings/usage',note:'账户连接和目录不代表当次请求成功；模型由 DSH 原生选择，不会自动更换默认模型。'}
  }
  async beginLogin(input:{accountId?:string;newAccount?:boolean}={}){
    if(this.closed)throw new SubscriptionError('UNAVAILABLE','订阅插件已停用。')
    if(this.starting||this.attempt?.view.status==='pending')throw new SubscriptionError('BUSY','请先完成或取消当前登录。')
    if(Object.keys(input).some(key=>!['accountId','newAccount'].includes(key))||input.accountId!==undefined&&typeof input.accountId!=='string'
      ||input.newAccount!==undefined&&typeof input.newAccount!=='boolean'||input.accountId&&input.newAccount)throw new SubscriptionError('INVALID_INPUT','请选择已有账户或新增账户。')
    this.starting=true
    try{
      const state=await this.store.ensure()
      let id=input.accountId??(!input.newAccount?state.activeId:undefined)
      if(id&&!state.accounts.some(account=>account.id===id))throw new SubscriptionError('ACCOUNT_MISSING','该账户记录已不存在，请刷新。')
      if(!id){id='account-'+randomUUID();await this.store.updateAccount(id,()=>({id:id!,label:'连接 '+(state.accounts.length+1),status:'disconnected',scopes:[],revision:0}))}
      const attempt:Attempt={view:{attemptId:randomUUID(),status:'pending',message:'正在准备 ChatGPT 授权…'},accountId:id,
        abort:new AbortController(),done:Promise.resolve()}
      this.attempt=attempt
      if(!this.flows.has(id))this.flows.set(id,this.authorization.registerFlow({key:profileKey(id),label:'ChatGPT 订阅（SiWC）',
        methods:[{id:'oauth',label:'Continue with ChatGPT'}],run:session=>this.login(session)}))
      const timeout=setTimeout(()=>attempt.abort.abort(),10*60*1000);timeout.unref?.()
      attempt.done=this.authorization.begin({key:profileKey(id),method:'oauth',signal:attempt.abort.signal,interaction:{
        notify:notice=>{if(this.attempt===attempt)attempt.view.message=notice.message},
        prompt:async()=>{throw new SubscriptionError('UNSUPPORTED_PROMPT','请在系统浏览器中完成此登录。')},
      }}).then(outcome=>{attempt.view.status=outcome.status==='authorized'?'authorized':'cancelled';delete attempt.view.message},error=>{
        attempt.view.status=attempt.abort.signal.aborted?'cancelled':'failed';attempt.view.error=safeFailure(error);delete attempt.view.message
      }).finally(()=>clearTimeout(timeout))
      return structuredClone(attempt.view)
    }finally{this.starting=false}
  }
  loginStatus(input:{attemptId:string}){
    if(!this.attempt||input.attemptId!==this.attempt.view.attemptId)throw new SubscriptionError('ATTEMPT_MISSING','这次登录已结束，请查看当前登录状态。')
    return structuredClone(this.attempt.view)
  }
  async cancelLogin(input:{attemptId:string}){
    this.loginStatus(input);this.attempt!.abort.abort();await this.attempt!.done;return this.loginStatus(input)
  }
  async reopenBrowser(input:{attemptId:string}){
    this.loginStatus(input)
    if(this.attempt!.view.status!=='pending'||!this.attempt!.reopen)throw new SubscriptionError('ATTEMPT_MISSING','当前授权页面已结束或正在验证，请查看最新状态。')
    await this.attempt!.reopen!();return {opened:true}
  }
  async acknowledgePlanNotice(input:{accountId:string}){
    await this.store.updateAccount(input.accountId,account=>{
      if(!account||account.status!=='connected'||!account.scopes.includes(PLAN_SCOPE))throw new SubscriptionError('ACCOUNT_MISSING','此账户尚未启用订阅权限。')
      account.planNoticeAcknowledged=true;return account
    })
    return this.status()
  }
  private async login(session:AuthorizationSession){
    const attempt=this.attempt
    if(!attempt)throw new SubscriptionError('ATTEMPT_MISSING','请从订阅设置页开始登录。')
    const state=await this.store.ensure(),account=state.accounts.find(row=>row.id===attempt.accountId)
    if(!account)throw new SubscriptionError('ACCOUNT_MISSING','账户记录已不存在。')
    const revision=account.revision
    if(account.pending){await this.commitLogin(account,account.pending,account.clientId!,session);return}
    const result=await this.protocol.authorize({account:structuredClone(account),hostId:state.hostId,signal:session.signal,openBrowser:this.openBrowser,
      notify:message=>session.notify({message}),launch:value=>{
        attempt.reopen=value?.reopen
        if(value)attempt.view.launchUrl=value.url;else delete attempt.view.launchUrl
      },onRegistration:async clientId=>{
        await this.store.withAccountLock(account.id,()=>this.store.updateAccount(account.id,row=>{if(!row||row.revision!==revision)throw new SubscriptionError('ACCOUNT_CHANGED','账户刚刚发生变化，请重新登录。');row.clientId=clientId;return row},session.signal),session.signal)
      }})
    session.signal.throwIfAborted()
    await this.commitLogin(account,result.pending,result.clientId,session)
  }
  private async commitLogin(account:Account,pending:PendingTokens,clientId:string,session:AuthorizationSession){
    const identity=await this.protocol.verify(pending,clientId,account.identity?.subject)
    await this.store.withAccountLock(account.id,async()=>{
    session.signal.throwIfAborted()
    const current=await this.store.readAccount(account.id,true)
    if(!current||current.revision!==account.revision||current.clientId!==clientId||pending.nonce===undefined&&current.pending?.idToken!==pending.idToken)
      throw new SubscriptionError('ACCOUNT_CHANGED','账户已变化，未覆盖现有连接。')
    const next={...current,identity,tokens:pending.tokens,scopes:[...pending.scopes],idToken:pending.idToken,status:'connected' as const,revision:current.revision+1,connectionRevision:(current.connectionRevision??0)+1}
    delete next.pending
    const record=await this.store.encode(next)
    // The public native commit is the admission point: later cancellation
    // waits for its write. No private authorization flags or ack ledger.
    await session.commit(record)
    await this.store.metadata(state=>{state.activeId=account.id})
    this.cancelCalls(account.id);this.catalogs.delete(account.id);this.changed()
    },session.signal)
  }
  private async publishVerified(id:string,pending:PendingTokens,clientId:string,subject:string|undefined,revision:number){
    let identity
    try{identity=await this.protocol.verify(pending,clientId,subject)}
    catch(error){
      if(error instanceof SubscriptionError&&error.code==='INVALID_IDENTITY')await this.store.updateAccount(id,account=>{
        if(!account)throw new SubscriptionError('ACCOUNT_MISSING','账户记录已不存在。')
        if(account.revision===revision&&account.pending?.idToken===pending.idToken){account.status='reauth_required';delete account.pending;account.revision++}
        return account
      })
      throw error
    }
    const next=await this.store.updateAccount(id,account=>{
      if(account&&account.revision>revision&&!account.pending&&account.identity?.subject===identity.subject)return account
      if(!account||account.revision!==revision||account.clientId!==clientId||account.pending?.idToken!==pending.idToken)
        throw new SubscriptionError('ACCOUNT_CHANGED','账户已变化，未覆盖现有连接。')
      account.identity=identity;account.tokens=pending.tokens;account.scopes=[...pending.scopes];account.idToken=pending.idToken
      account.status='connected';account.revision++;delete account.pending
      return account
    })
    const cached=this.catalogs.get(id)
    if(cached)this.catalogs.set(id,{...cached,revision:next.revision})
    return next
  }
  async selectAccount(input:{accountId:string}){
    const account=await this.store.readAccount(input.accountId)
    if(!account||account.status!=='connected'||account.pending)throw new SubscriptionError('REAUTH_REQUIRED','请先完成该账户的登录验证。')
    if((await this.store.read())?.activeId===account.id)return this.status()
    await this.store.metadata(state=>{state.activeId=account.id})
    this.changed();return this.status()
  }
  async disconnect(input:{accountId:string}){
    this.cancelCalls(input.accountId)
    return this.store.withAccountLock(input.accountId,async()=>{
    const current=await this.store.readAccount(input.accountId,true)
    if(!current)throw new SubscriptionError('ACCOUNT_MISSING','账户记录已不存在。')
    const remoteRevocationConfirmed=await this.protocol.revoke(current,AbortSignal.timeout(15000))
    await this.store.updateAccount(current.id,account=>{
      if(!account||account.revision!==current.revision)throw new SubscriptionError('ACCOUNT_CHANGED','账户已更新，未清除新的连接。')
      delete account.tokens;delete account.idToken;delete account.pending;account.scopes=[];account.status='disconnected';account.revision++;account.connectionRevision=(account.connectionRevision??0)+1;return account})
    this.cancelCalls(current.id)
    this.catalogs.delete(current.id);this.changed()
    return {disconnected:true,remoteRevocationConfirmed,message:remoteRevocationConfirmed?'已退出此账户。':'已在本机退出；远端撤销尚未确认，可到 ChatGPT 设置断开此应用。'}
    })
  }
  async selection(){
    if(this.closed)throw new SubscriptionError('UNAVAILABLE','订阅插件已停用。')
    const state=await this.store.read(),account=state?.accounts.find(row=>row.id===state.activeId)
    if(!account||account.status!=='connected'||!account.tokens||!account.scopes.includes(PLAN_SCOPE))throw new SubscriptionError('SIGN_IN_REQUIRED','请先连接 ChatGPT 并允许此应用使用订阅额度。')
    return {account:structuredClone(account),generation:{accountId:account.id,connectionRevision:account.connectionRevision??0}}
  }
  async selected(){return (await this.selection()).account}
  async assertGeneration(expected:AccountGeneration){
    if(this.closed)throw new SubscriptionError('UNAVAILABLE','订阅插件已停用。')
    this.checkGeneration(expected,await this.store.readAccount(expected.accountId))
  }
  private checkGeneration(expected:AccountGeneration,current:Account|undefined){
    if(!current||current.id!==expected.accountId||current.status!=='connected'||!current.tokens||!current.scopes.includes(PLAN_SCOPE)||(current.connectionRevision??0)!==expected.connectionRevision)
      throw new SubscriptionError('ACCOUNT_CHANGED','此账户的连接已变化。请确认账户状态后继续对话。')
  }
  /** Captures an account, never silently resolves a later active account. */
  tokenFor(id:string,signal:AbortSignal,expected?:AccountGeneration):Promise<{account:Account;accessToken:string}>{
    if(this.closed)return Promise.reject(new SubscriptionError('UNAVAILABLE','订阅插件已停用。'))
    const task=this.tokenOperation(id,signal,expected);this.tokenOperations.add(task)
    void task.finally(()=>this.tokenOperations.delete(task)).catch(()=>{})
    return task
  }
  private async tokenOperation(id:string,signal:AbortSignal,expected?:AccountGeneration):Promise<{account:Account;accessToken:string}>{
    return this.store.withAccountLock(id,async()=>{
    signal.throwIfAborted()
    let account=await this.store.readAccount(id,true)
    if(expected)this.checkGeneration(expected,account)
    if(!account||account.status!=='connected'||!account.tokens||!account.scopes.includes(PLAN_SCOPE))throw new SubscriptionError('SIGN_IN_REQUIRED','此账户需要重新连接或开启订阅额度权限。')
    if(account.pending?.nonce)throw new SubscriptionError('VERIFICATION_PENDING','请先在订阅设置中完成此账户的登录验证。')
    if(account.pending){account=await this.publishVerified(account.id,account.pending,account.clientId!,account.identity?.subject,account.revision)}
    if(account.tokens!.expiresAt<=Date.now()+60000){
      // Only this account's public cross-process lock spans network I/O.
      // Native modifyRecord is a quick CAS/checkpoint, never a network lock.
      const row=account,capturedRevision=row.revision
      const checkpoint=(pending:PendingTokens|undefined,invalid=false)=>this.store.updateAccount(id,current=>{
        if(!current||current.revision!==capturedRevision||current.clientId!==row.clientId||current.tokens?.refreshToken!==row.tokens?.refreshToken)
          throw new SubscriptionError('ACCOUNT_CHANGED','此账户的连接已变化。请确认账户状态后继续对话。')
        if(invalid)current.status='reauth_required';else current.pending=pending!
        current.revision++;return current
      })
        const earliest=row.tokens!.earliestRefreshAt
        const earliestMs=typeof earliest==='number'?earliest*1000:typeof earliest==='string'?Date.parse(earliest):0
        if(Number.isFinite(earliestMs)&&earliestMs>Date.now()){
          if(row.tokens!.expiresAt<=Date.now())throw new SubscriptionError('REFRESH_WAIT','服务尚未允许刷新，请稍后重试。',true)
          // The current token is still usable; do not rotate before the server's bound.
        }else{
          try{const pending=await this.protocol.refresh(structuredClone(row),AbortSignal.timeout(60000));await checkpoint(pending)}
          catch(error){if(error instanceof SubscriptionError&&error.code==='REAUTH_REQUIRED')await checkpoint(undefined,true);else throw error}
        }
      account=(await this.store.readAccount(id))!
      if(account.status!=='connected')throw new SubscriptionError('REAUTH_REQUIRED','账户授权已失效，请重新登录。')
      if(account.pending)account=await this.publishVerified(account.id,account.pending,account.clientId!,account.identity?.subject,account.revision)
    }
    signal.throwIfAborted()
    if(expected)await this.assertGeneration(expected)
    if(!account.tokens||account.tokens.expiresAt<=Date.now())throw new SubscriptionError('REAUTH_REQUIRED','账户需要重新登录。')
    return {account:structuredClone(account),accessToken:account.tokens.accessToken}
    },signal)
  }
  async models(input:{refresh?:boolean}={},signal:AbortSignal=AbortSignal.timeout(15000)){
    const selected=await this.selected()
    const models=await this.catalogFor(selected.id,signal,input.refresh)
    if((await this.store.read())?.activeId!==selected.id)throw new SubscriptionError('ACCOUNT_CHANGED','读取目录时已切换账户，请刷新。')
    this.changed()
    return models
  }
  async catalogFor(id:string,signal:AbortSignal,refresh=false){
    const selected=await this.store.readAccount(id)
    if(!selected||selected.status!=='connected')throw new SubscriptionError('SIGN_IN_REQUIRED','请先连接此账户。')
    const saved=this.catalogs.get(selected.id)
    if(!refresh&&saved&&saved.revision===selected.revision)return saved.models
    const {account,accessToken}=await this.tokenFor(selected.id,signal)
    const response=await this.fetcher(RESOURCE+'/models',{headers:{...attributionHeaders(),Authorization:'Bearer '+accessToken,accept:'application/json'},signal,redirect:'error'})
    if(!response.ok)throw new SubscriptionError('CATALOG_UNAVAILABLE','无法读取此账户的模型目录，请检查授权后重试。',true)
    const body=await response.json() as {models?:unknown}
    if(!Array.isArray(body.models))throw new SubscriptionError('CATALOG_INVALID','服务没有返回 SiWC 账户模型目录。')
    const models:ModelView[]=[],seen=new Set<string>(),known=new Set(getBuiltinModels('openai').filter(model=>model.api==='openai-responses').map(model=>model.id))
    for(const row of body.models as Array<Record<string,unknown>>)if(row.visibility==='list'&&typeof row.slug==='string'&&row.slug&&typeof row.display_name==='string'&&!seen.has(row.slug)){
      seen.add(row.slug);const supported=known.has(row.slug)
      models.push({id:row.slug,name:row.display_name,supported,...supported?{}:{unsupportedReason:'当前版本暂未适配此模型；可在账户目录查看，暂不能在 DSH 模型菜单选择。'}})
    }
    const current=await this.store.readAccount(account.id)
    if(!current||current.revision!==account.revision)throw new SubscriptionError('ACCOUNT_CHANGED','读取目录时账户发生变化，请刷新。')
    this.catalogs.set(account.id,{revision:account.revision,models});return models
  }
  trackCall(accountId:string){const controller=new AbortController();this.calls.set(controller,accountId);return {signal:controller.signal,close:()=>this.calls.delete(controller)}}
  private cancelCalls(accountId?:string){for(const [controller,id] of this.calls)if(accountId===undefined||id===accountId){controller.abort();this.calls.delete(controller)}}
  async close(){this.closed=true;this.attempt?.abort.abort();this.cancelCalls();await this.attempt?.done
    // An admitted refresh may already have rotated the server token. Let its
    // bounded operation persist/verify the replacement before releasing the store.
    await Promise.allSettled([...this.tokenOperations]);for(const release of this.flows.values())release();this.flows.clear()}
}
