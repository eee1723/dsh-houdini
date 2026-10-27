import {Context} from '@deepseek-ai/cordis'
import {CredentialProvider} from '@deepseek-ai/dsh-credentials'
import {AuthorizationService} from '@deepseek-ai/dsh-authorization'
import {randomBytes,createCipheriv,createDecipheriv,createHash} from 'node:crypto'
import {generateKeyPair,exportJWK,SignJWT} from 'jose'
import {AccountStore} from '../lib/store.js'
import {SiwcProtocol} from '../lib/oauth.js'
import {SubscriptionAccounts} from '../lib/accounts.js'
import {getBuiltinModels} from '@earendil-works/pi-ai/providers/all'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

class MemoryCredentials extends CredentialProvider {
  records=new Map();tail=Promise.resolve()
  constructor(ctx){super(ctx)}
  async resolve(){return undefined}async describe(){return{configured:false,writable:true}}async set(){throw Error('No ref writes')}async unset(){}
  async readRecord(key){return structuredClone(this.records.get(key))}
  async describeRecord(key){const value=this.records.get(key);return{configured:!!value,writable:true,...value?{kind:value.kind}:{}}}
  async listRecords(){return [...this.records].map(([key,value])=>({key,kind:value.kind}))}
  async modifyRecord(key,fn){const task=this.tail.then(async()=>{const next=await fn(structuredClone(this.records.get(key)));if(next!==undefined){await this.beforeWrite?.(key,next);this.records.set(key,structuredClone(next));this.notifyRecordUpdated(key)}return structuredClone(this.records.get(key))});this.tail=task.catch(()=>{});return task}
  async deleteRecord(key){await this.modifyRecord(key,()=>undefined);this.records.delete(key);this.notifyRecordUpdated(key)}
}
const privateKey=randomBytes(32)
export const testProtector={id:'test-memory-aes-gcm-only',async protect(value){const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',privateKey,iv),body=Buffer.concat([cipher.update(value),cipher.final()]);return Buffer.concat([iv,cipher.getAuthTag(),body])},async unprotect(value){const data=Buffer.from(value),cipher=createDecipheriv('aes-256-gcm',privateKey,data.subarray(0,12));cipher.setAuthTag(data.subarray(12,28));return Buffer.concat([cipher.update(data.subarray(28)),cipher.final()])}}
export const model=getBuiltinModels('openai').find(row=>row.api==='openai-responses'&&row.input.includes('image'))
assert(model)
export const wait=async read=>{for(let n=0;n<300;n++){const value=await read();if(value)return value;await new Promise(resolve=>setTimeout(resolve,10))}throw Error('fixture wait timed out')}
export async function fixture(options={}){
  const ctx=new Context(),cf=ctx.plugin(options.credentialPlugin??{apply(c){new MemoryCredentials(c)}},options.credentialConfig??{});await cf.await()
  const af=ctx.plugin(AuthorizationService);await af.await()
  const pair=await generateKeyPair('RS256'),other=await generateKeyPair('RS256'),jwk=await exportJWK(pair.publicKey);jwk.kid='owned-test-key'
  const seen=[],browsers=[];let issued=0,refreshes=0,mode='normal',responseBody,catalog,tokenGate,revokeGate,nonce,clientId,hold=!!options.holdBrowser,browserFailure=false
  const fetcher=async(input,init={})=>{
    const url=String(input);seen.push({url,init})
    if(url.endsWith('/.well-known/openid-configuration'))return Response.json({issuer:'https://auth.openai.com',authorization_endpoint:'https://auth.openai.com/api/accounts/authorize',token_endpoint:'https://auth.openai.com/api/accounts/oauth/token',jwks_uri:'https://auth.openai.com/keys',revocation_endpoint:'https://auth.openai.com/revoke'})
    if(url.endsWith('/keys')){if(mode==='jwks-down')return new Response('unavailable',{status:503});return Response.json({keys:[jwk]})}
    if(url.endsWith('/oauth/token')){
      const form=new URLSearchParams(init.body),refresh=form.get('grant_type')==='refresh_token'
      if(refresh){refreshes++;await tokenGate?.()}
      else assert.equal(createHash('sha256').update(form.get('code_verifier')).digest('base64url'),browsers.at(-1).searchParams.get('code_challenge'))
      const idToken=await new SignJWT({sub:mode==='wrong-subject'?'different':'owned-subject-'+clientId,email:'fixture@example.invalid',...!refresh?{nonce:mode==='wrong-nonce'?'invalid':nonce}:{}})
        .setProtectedHeader({alg:'RS256',kid:jwk.kid}).setIssuer(mode==='wrong-issuer'?'https://wrong.invalid':'https://auth.openai.com').setAudience(mode==='wrong-audience'?'wrong-client':clientId).setIssuedAt().setExpirationTime('1h').sign(mode==='wrong-signature'?other.privateKey:pair.privateKey)
      return Response.json({access_token:'owned-access-'+(++issued),refresh_token:'owned-refresh-'+issued,token_type:'Bearer',expires_in:3600,id_token:idToken,
        scope:mode==='no-plan'?'openid profile email':'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'})
    }
    if(url.endsWith('/revoke')){await revokeGate?.();return new Response('',{status:200})}
    if(url==='https://api.openai.com/v1/models')return Response.json({models:catalog??[{slug:model.id,display_name:'Owned model',visibility:'list'},{slug:'unknown-capabilities',display_name:'Unresolved model',visibility:'list'},{slug:'hidden',display_name:'Hidden',visibility:'hidden'}]})
    if(url==='https://api.openai.com/v1/responses'){
      if(responseBody)return responseBody(input,init)
      const body=JSON.parse(init.body);assert.equal(body.stream,true);assert.equal(body.store,false)
      const message={id:'msg_owned',type:'message',role:'assistant',status:'completed',content:[{type:'output_text',text:'Owned completed response',annotations:[]}]}
      const values=[{type:'response.created',response:{id:'resp_owned',model:body.model,status:'in_progress'}},
        {type:'response.output_item.added',output_index:0,item:{...message,status:'in_progress',content:[]}},
        {type:'response.content_part.added',output_index:0,content_index:0,part:{type:'output_text',text:'',annotations:[]}},
        {type:'response.output_text.delta',output_index:0,content_index:0,delta:'Owned completed response'},
        {type:'response.output_text.done',output_index:0,content_index:0,text:'Owned completed response'},
        {type:'response.output_item.done',output_index:0,item:message},
        {type:mode==='incomplete'?'response.incomplete':'response.completed',response:{id:'resp_owned',model:body.model,status:mode==='incomplete'?'incomplete':'completed',output:[message],usage:{input_tokens:2,output_tokens:3,total_tokens:5,input_tokens_details:{cached_tokens:0},output_tokens_details:{reasoning_tokens:0}}}}]
      return new Response(values.map(value=>'data: '+JSON.stringify(value)+'\n\n').join('')+'data: [DONE]\n\n',{headers:{'content-type':'text/event-stream'}})
    }
    throw Error('Unexpected URL; real network is forbidden: '+url)
  }
  const openBrowser=async value=>{
    const url=new URL(value);browsers.push(url);nonce=url.searchParams.get('nonce');clientId=url.searchParams.get('client_id')==='dynamic_agent_client'?'issued-'+browsers.length:url.searchParams.get('client_id')
    if(browserFailure)throw Error('owned browser failure')
    if(hold)return
    const callback=new URL(url.searchParams.get('redirect_uri'));callback.search=new URLSearchParams({state:url.searchParams.get('state'),code:'owned-one-time-code',client_id:clientId}).toString()
    const response=await fetch(callback);assert.equal(response.status,200)
  }
  const lockDirectory=options.lockDirectory??await fs.mkdtemp(path.join(os.tmpdir(),'dsh-subscription-lock-test-'))
  const store=new AccountStore(ctx.credentials,options.protector??testProtector,lockDirectory)
  const accounts=new SubscriptionAccounts(store,new SiwcProtocol(fetcher),ctx.authorization,openBrowser,fetcher)
  return{ctx,store,accounts,fetcher,seen,browsers,mode:value=>{mode=value},response:value=>{responseBody=value},refreshes:()=>refreshes,
    holdBrowser:value=>{hold=value},browserFailure:value=>{browserFailure=value},
    catalog:value=>{catalog=value},
    tokenGate:value=>{tokenGate=value},
    revokeGate:value=>{revokeGate=value},
    async login(input={newAccount:true}){const attempt=await accounts.beginLogin(input);return await wait(async()=>{const value=accounts.loginStatus(attempt);return value.status!=='pending'?value:null})},
    async close(){await accounts.close();await af.dispose();await cf.dispose();if(!options.lockDirectory)await fs.rm(lockDirectory,{recursive:true,force:true})}}
}
