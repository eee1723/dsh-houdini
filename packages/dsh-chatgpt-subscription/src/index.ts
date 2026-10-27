import type {Context} from '@deepseek-ai/cordis'
import {spawn} from 'node:child_process'
import {Remote,TypertRemoteService} from '@deepseek-ai/dsh-typert-protocol'
import type {} from '@deepseek-ai/dsh-authorization'
import type {} from '@deepseek-ai/dsh-credentials'
import {AccountStore,WindowsDpapi} from './store.js'
import {SiwcProtocol} from './oauth.js'
import {SubscriptionAccounts} from './accounts.js'
import {SubscriptionAdapter} from './adapter.js'
import {PROVIDER} from './types.js'
import {SubscriptionError} from './errors.js'
import Schema from '@deepseek-ai/schemastery'
import {dshHomePath} from '@deepseek-ai/dsh-home-paths'
export * from './types.js'
export {SubscriptionAccounts,SubscriptionAdapter,AccountStore,WindowsDpapi,SiwcProtocol}
export const name='chatgpt-subscription'
export const inject=['llm','credentials','authorization']
export const Config=Schema.object({})
export class ChatgptSubscriptionController extends TypertRemoteService {
  constructor(ctx:Context,readonly accounts:SubscriptionAccounts){super(ctx,'chatgptSubscription')}
  @Remote status(){return this.accounts.status()}
  @Remote beginLogin(input:{accountId?:string;newAccount?:boolean}){return this.accounts.beginLogin(input)}
  @Remote loginStatus(input:{attemptId:string}){return this.accounts.loginStatus(input)}
  @Remote cancelLogin(input:{attemptId:string}){return this.accounts.cancelLogin(input)}
  @Remote reopenBrowser(input:{attemptId:string}){return this.accounts.reopenBrowser(input)}
  @Remote acknowledgePlanNotice(input:{accountId:string}){return this.accounts.acknowledgePlanNotice(input)}
  @Remote selectAccount(input:{accountId:string}){return this.accounts.selectAccount(input)}
  @Remote disconnect(input:{accountId:string}){return this.accounts.disconnect(input)}
  @Remote models(input:{refresh?:boolean},signal:AbortSignal){return this.accounts.models(input,signal)}
}
async function openBrowser(url:string){
  if(new URL(url).origin!=='https://auth.openai.com')throw new SubscriptionError('BROWSER_UNAVAILABLE','未打开非官方授权地址。')
  await new Promise<void>((resolve,reject)=>{
    const child=spawn('rundll32.exe',['url.dll,FileProtocolHandler',url],{windowsHide:true,shell:false,stdio:'ignore'})
    child.once('error',()=>reject(new SubscriptionError('BROWSER_UNAVAILABLE','无法打开系统浏览器，请检查默认浏览器。')))
    child.once('exit',code=>code===0?resolve():reject(new SubscriptionError('BROWSER_UNAVAILABLE','无法打开系统浏览器。')))
  })
}
/** No account files, network requests or default model changes occur at plugin startup. */
export function apply(ctx:Context){
  let registration:ReturnType<typeof ctx.llm.registerAdapter>|undefined
  const accounts=new SubscriptionAccounts(new AccountStore(ctx.credentials,new WindowsDpapi(),dshHomePath('dsh-chatgpt-subscription','account-locks')),new SiwcProtocol(),ctx.authorization,openBrowser,fetch,
    ()=>{registration?.replace([PROVIDER])})
  const adapter=new SubscriptionAdapter(accounts,ctx)
  registration=ctx.llm.registerAdapter([PROVIDER],adapter)
  new ChatgptSubscriptionController(ctx,accounts)
  ctx.effect(()=>async()=>{registration?.();await accounts.close()})
}
