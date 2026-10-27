/** SiWC public OAuth/OIDC protocol. Based on current official documentation,
 * with JOSE validation; no pi-ai/Codex private auth files or SDK internals. */
import {createHash,randomBytes,timingSafeEqual} from 'node:crypto'
import {createServer} from 'node:http'
import {createRemoteJWKSet,customFetch,jwtVerify} from 'jose'
import type {Account,Fetcher,Identity,PendingTokens} from './types.js'
import {ISSUER,RESOURCE,PLAN_SCOPE} from './types.js'
import {SubscriptionError,aborted} from './errors.js'

type Discovery={issuer:string;authorization_endpoint:string;token_endpoint:string;jwks_uri:string;revocation_endpoint?:string}
const fresh=()=>randomBytes(32).toString('base64url')
const SCOPES='openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
const equal=(a:string,b:string)=>{const x=Buffer.from(a),y=Buffer.from(b);return x.length===y.length&&timingSafeEqual(x,y)}
export class SiwcProtocol {
  private discoveryPromise?:Promise<Discovery>
  private keys?:ReturnType<typeof createRemoteJWKSet>
  constructor(readonly fetcher:Fetcher=fetch,private readonly appName='DSH ChatGPT Subscription'){}
  private async discovery():Promise<Discovery>{
    return this.discoveryPromise??=(async()=>{
      try{
        const response=await this.fetcher(ISSUER+'/.well-known/openid-configuration',{signal:AbortSignal.timeout(15000),redirect:'error'})
        const data=await response.json() as Discovery
        if(!response.ok||data.issuer!==ISSUER)throw Error()
        for(const field of ['authorization_endpoint','token_endpoint','jwks_uri','revocation_endpoint'] as const){
          const value=data[field];if(field==='revocation_endpoint'&&value===undefined)continue
          const url=new URL(value!);if(url.origin!==ISSUER||url.username||url.password||url.hash)throw Error()
        }
        return data
      }catch{this.discoveryPromise=undefined;throw new SubscriptionError('IDENTITY_UNAVAILABLE','暂时无法验证 ChatGPT 授权服务，请稍后重试。',true)}
    })()
  }
  async verify(pending:PendingTokens,clientId:string,expectedSubject?:string):Promise<Identity>{
    const config=await this.discovery()
    this.keys??=createRemoteJWKSet(new URL(config.jwks_uri),{timeoutDuration:15000,[customFetch]:async(url,options)=>{
      try{const response=await this.fetcher(url,{...options,redirect:'error'});if(!response.ok)throw Error();return response}
      catch{throw new SubscriptionError('IDENTITY_UNAVAILABLE','暂时无法完成身份验证，请稍后重试。',true)}
    }})
    try{
      const resolver=this.keys
      const {payload}=await jwtVerify(pending.idToken,async(header,token)=>{
        try{return await resolver(header,token)}catch{if(this.keys===resolver)this.keys=undefined
          throw new SubscriptionError('IDENTITY_UNAVAILABLE','暂时无法完成身份验证，请稍后重试。',true)}
      },{issuer:ISSUER,audience:clientId,algorithms:['RS256'],
        requiredClaims:['iss','aud','exp','iat','sub'],clockTolerance:5,currentDate:new Date(pending.receivedAt)})
      if(typeof payload.sub!=='string'||!payload.sub||typeof payload.iat!=='number'||payload.iat>pending.receivedAt/1000+5
        ||pending.nonce!==undefined&&payload.nonce!==pending.nonce||expectedSubject!==undefined&&payload.sub!==expectedSubject
        ||payload.azp!==undefined&&payload.azp!==clientId||Array.isArray(payload.aud)&&payload.aud.length>1&&payload.azp!==clientId)throw Error()
      return {subject:payload.sub,...typeof payload.email==='string'?{email:payload.email}:{},...typeof payload.name==='string'?{name:payload.name}:{}}
    }catch(error){if(error instanceof SubscriptionError)throw error;throw new SubscriptionError('INVALID_IDENTITY','无法验证返回的 ChatGPT 账户身份；未替换现有账户。')}
  }
  private async request(body:URLSearchParams,signal:AbortSignal){
    const config=await this.discovery();signal.throwIfAborted()
    let response:Response
    try{response=await this.fetcher(config.token_endpoint,{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded',accept:'application/json'},body,signal,redirect:'error'})}
    catch{if(signal.aborted)throw aborted();throw new SubscriptionError('NETWORK','无法连接 ChatGPT 授权服务，请稍后重试。',true)}
    if(!response.ok){
      let code='';try{const body=await response.json() as {error?:string|{code?:string}};code=typeof body.error==='string'?body.error:body.error?.code??''}catch{}
      const reauth=response.status===401||['invalid_grant','invalid_token','consent_required'].includes(code)
      throw new SubscriptionError(reauth?'REAUTH_REQUIRED':'AUTH_NETWORK',reauth?'授权未完成或已失效，请重新登录。':'授权服务暂时未接受请求，请稍后重试。',!reauth&&response.status>=500)
    }
    try{return await response.json() as Record<string,unknown>}catch{throw new SubscriptionError('INVALID_TOKEN_RESPONSE','授权服务返回的凭据格式无效。')}
  }
  private tokens(value:Record<string,unknown>,nonce?:string):PendingTokens{
    const now=Date.now(),expiry=value.expires_in
    if(typeof value.access_token!=='string'||!value.access_token||typeof value.refresh_token!=='string'||!value.refresh_token
      ||typeof value.id_token!=='string'||!value.id_token||typeof value.scope!=='string'||typeof value.token_type!=='string'||value.token_type.toLowerCase()!=='bearer'
      ||typeof expiry!=='number'||!Number.isFinite(expiry)||expiry<=0||!Number.isFinite(now+expiry*1000))throw new SubscriptionError('INVALID_TOKEN_RESPONSE','授权服务没有返回完整的可验证凭据。')
    const scopes=value.scope.trim().split(/\s+/).filter(Boolean)
    if(!scopes.includes(PLAN_SCOPE))throw new SubscriptionError('SHARING_NOT_GRANTED','此登录未授予 ChatGPT 订阅使用权限，未启用模型请求。')
    return {tokens:{accessToken:value.access_token,refreshToken:value.refresh_token,expiresAt:now+expiry*1000,
      ...typeof value.earliest_refresh_at==='string'||typeof value.earliest_refresh_at==='number'?{earliestRefreshAt:value.earliest_refresh_at}:{}},
      scopes,idToken:value.id_token,receivedAt:now,...nonce?{nonce}:{}}
  }
  async refresh(account:Account,signal:AbortSignal){
    if(!account.clientId||!account.tokens?.refreshToken)throw new SubscriptionError('REAUTH_REQUIRED','此账户需要重新登录。')
    return this.tokens(await this.request(new URLSearchParams({grant_type:'refresh_token',client_id:account.clientId,
      refresh_token:account.tokens.refreshToken,resource:RESOURCE}),signal))
  }
  async revoke(account:Account,signal:AbortSignal):Promise<boolean>{
    if(!account.tokens?.refreshToken||!account.clientId)return true
    try{const config=await this.discovery();if(!config.revocation_endpoint)return false
      const response=await this.fetcher(config.revocation_endpoint,{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},
        body:new URLSearchParams({token:account.tokens.refreshToken,token_type_hint:'refresh_token',client_id:account.clientId}),signal,redirect:'error'})
      return response.status===200
    }catch{return false}
  }
  async authorize(options:{account:Account;hostId:string;signal:AbortSignal;openBrowser:(url:string)=>Promise<void>;
    onRegistration:(id:string)=>Promise<void>;notify:(message:string)=>void;launch?:(value:{url:string;reopen:()=>Promise<void>}|null)=>void}){
    const config=await this.discovery(),state=fresh(),nonce=fresh(),verifier=fresh(),launchPath='/launch/'+fresh(),challenge=createHash('sha256').update(verifier).digest('base64url')
    let authorizationUrl:string|undefined
    let settle!:(value:{code:string;clientId:string})=>void,fail!:(error:Error)=>void
    const callback=new Promise<{code:string;clientId:string}>((resolve,reject)=>{settle=resolve;fail=reject})
    // Attach a rejection observer before the browser/network can race cancellation.
    void callback.catch(()=>{})
    const server=createServer((request,response)=>{
      let accepted=false
      try{
        const url=new URL(request.url??'','http://127.0.0.1')
        if(request.method==='GET'&&url.pathname===launchPath&&authorizationUrl&&!options.signal.aborted){
          response.writeHead(302,{location:authorizationUrl,'cache-control':'no-store','referrer-policy':'no-referrer'});response.end();return
        }
        if(request.method!=='GET'||url.pathname!=='/auth/callback'){response.writeHead(404);response.end();return}
        for(const key of ['state','code','client_id','error'])if(url.searchParams.getAll(key).length>1)throw Error()
        if(!equal(url.searchParams.get('state')??'',state))throw Error()
        if(url.searchParams.has('error')){fail(new SubscriptionError('DECLINED','未完成 ChatGPT 授权。'));response.writeHead(400);response.end('Authorization was not completed.');return}
        const code=url.searchParams.get('code'),clientId=url.searchParams.get('client_id')??options.account.clientId
        if(!code||!clientId||clientId==='dynamic_agent_client'||options.account.clientId&&clientId!==options.account.clientId)throw Error()
        settle({code,clientId});accepted=true
      }catch{/* A stray callback cannot cancel or complete the owning attempt. */}
      response.writeHead(accepted?200:400,{'content-type':'text/html; charset=utf-8','cache-control':'no-store'})
      response.end(accepted?'Authorization received. Return to DSH to check its final status.':'Invalid authorization callback.')
    })
    const abort=()=>{fail(aborted());server.closeAllConnections();server.close()}
    try{
      options.signal.throwIfAborted()
      await new Promise<void>((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',()=>{server.removeListener('error',reject);resolve()})})
      options.signal.addEventListener('abort',abort,{once:true});options.signal.throwIfAborted()
      const address=server.address();if(!address||typeof address==='string')throw Error('No callback port')
      const redirect='http://127.0.0.1:'+address.port+'/auth/callback',url=new URL(config.authorization_endpoint)
      url.search=new URLSearchParams({client_id:options.account.clientId??'dynamic_agent_client',ext_agent_host_id:options.hostId,response_type:'code',
        redirect_uri:redirect,scope:SCOPES,resource:RESOURCE,state,nonce,code_challenge_method:'S256',code_challenge:challenge,
        ...options.account.clientId?{}:{agent_name_hint:this.appName},...options.account.idToken?{id_token_hint:options.account.idToken}:{}}).toString()
      authorizationUrl=url.href
      options.launch?.({url:'http://127.0.0.1:'+address.port+launchPath,reopen:()=>options.openBrowser(url.href)})
      options.notify('请在系统浏览器中继续 ChatGPT 授权。')
      // The authorization URL can contain an ID-token hint. It is never a Remote value or a log message.
      try{await options.openBrowser(url.href)}catch{options.notify('无法自动打开浏览器。请复制本机安全登录入口，或点击重新打开浏览器。')}
      const returned=await callback;options.signal.throwIfAborted()
      await options.onRegistration(returned.clientId)
      const pending=this.tokens(await this.request(new URLSearchParams({grant_type:'authorization_code',client_id:returned.clientId,code:returned.code,
        code_verifier:verifier,redirect_uri:redirect,resource:RESOURCE}),options.signal),nonce)
      return {pending,clientId:returned.clientId}
    }finally{options.launch?.(null);authorizationUrl=undefined;options.signal.removeEventListener('abort',abort);server.closeAllConnections();await new Promise<void>(resolve=>server.close(()=>resolve()))}
  }
}
