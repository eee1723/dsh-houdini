/** Offline protocol/credential integration; never reads user credentials or requests inference. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const cache=path.resolve(process.argv[2]??(()=>{throw Error('Pass the prepared runtime root')})());
const require=createRequire(path.join(cache,'node_modules/@deepseek-ai/dsh/lib/bin.js'));
const load=async name=>import(pathToFileURL(require.resolve(name)));
const {generateKeyPair,exportJWK,SignJWT}=await load('jose');
const {openaiChatGPTOAuth:oauth}=await import(pathToFileURL(path.join(cache,'node_modules/@earendil-works/pi-ai/dist/auth/oauth/openai-chatgpt.js')));
const {Context}=await load('@deepseek-ai/cordis');
const {LocalCredentialProvider}=await load('@deepseek-ai/dsh-credentials-local');
const {AuthorizationService}=await load('@deepseek-ai/dsh-authorization');
const {credentialKey}=await load('@deepseek-ai/dsh-credentials');
const pi=await load('@deepseek-ai/dsh-llm-pi-ai');
const {default:LlmRuntime}=await load('@deepseek-ai/dsh-llm');
const pair=await generateKeyPair('RS256'),otherPair=await generateKeyPair('RS256');
const jwk={...await exportJWK(pair.publicKey),kid:'fixture-key',alg:'RS256',use:'sig'};
const originalFetch=globalThis.fetch,root=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-chatgpt-native-'));
const issuer='https://auth.openai.com',clientId='oaiapp_fixture',deviceId='2ccdf339-cf22-4f31-9ac2-3dcbb69ca893';
const accountKey=credentialKey('llm-pi-ai','openai'),registrationKey=credentialKey('llm-pi-ai-registration','openai');
let authorizeUrl,scenario={},requests=[],revocationCalls=0;
const resultRows=[];
const test=async(name,body)=>{scenario={};requests=[];revocationCalls=0;await body();resultRows.push(name);console.log('PASS',name)};
async function signed(extra={}) {
  let jwt=new SignJWT({nonce:authorizeUrl?.searchParams.get('nonce'),email:'fixture@example.invalid',name:'Fixture',...extra})
    .setProtectedHeader({alg:'RS256',kid:'fixture-key'}).setIssuer(scenario.issuer??issuer)
    .setAudience(scenario.audience??clientId).setSubject(scenario.subject??'fixture-subject').setIssuedAt().setExpirationTime(scenario.expired?'1 second ago':'5 minutes');
  return jwt.sign(scenario.badSignature?otherPair.privateKey:pair.privateKey);
}
globalThis.fetch=async(input,options={})=>{
  const url=String(input);requests.push({url,body:options.body});
  if(url.startsWith('http://127.0.0.1:'))return originalFetch(input,options);
  if(url.startsWith('https://api.openai.com/v1/responses')){assert(scenario.pendingInference);scenario.inferenceStarted();return new Promise((resolve,reject)=>{const abort=()=>{scenario.inferenceAborted=true;reject(new DOMException('Account signed out','AbortError'))};if(options.signal.aborted)abort();else options.signal.addEventListener('abort',abort,{once:true})})}
  assert(url.startsWith(issuer+'/'),'no test request may leave the fake issuer');
  if(url.endsWith('/.well-known/openid-configuration'))return Response.json({issuer,jwks_uri:scenario.badJwks?'https://untrusted.invalid/keys':issuer+'/.well-known/jwks.json',revocation_endpoint:issuer+'/api/accounts/oauth/revoke'});
  if(url.endsWith('/.well-known/jwks.json'))return Response.json({keys:[jwk]});
  if(url.endsWith('/api/accounts/oauth/revoke')){revocationCalls++;if(scenario.revokeNetwork)throw Error('fixture network unavailable');return new Response('',{status:scenario.revokeFailFirst&&revocationCalls===1?503:200})}
  if(url.endsWith('/api/accounts/oauth/token')){
    if(scenario.tokenError)return new Response('sensitive-body-must-not-escape',{status:401});
    const refreshing=options.body.get('grant_type')==='refresh_token';
    if(!refreshing){assert.equal(options.body.get('redirect_uri'),authorizeUrl.searchParams.get('redirect_uri'));assert.equal(options.body.get('client_id'),clientId)}
    return Response.json({access_token:'fixture-access',refresh_token:'fixture-refresh-rotated',expires_in:3600,token_type:'Bearer',
      ...(!scenario.omitScope?{scope:scenario.missingScope?'openid profile email':'openid profile email chatgpt.tokens.use.direct'}:{}),
      ...(!refreshing||scenario.refreshIdToken?{id_token:await signed(scenario.badNonce?{nonce:'wrong-nonce'}:{})}:{})});
  }
  throw Error('unexpected fake request');
};
function interaction(signal=new AbortController().signal) {
  return {signal,notify(event){if(event.type==='auth_url')authorizeUrl=new URL(event.url)},
    async prompt(){const callback=new URL(authorizeUrl.searchParams.get('redirect_uri'));callback.searchParams.set('state',scenario.badState?'wrong':authorizeUrl.searchParams.get('state'));callback.searchParams.set('code','fixture-code');
      if(!scenario.omitCallbackClient)callback.searchParams.set('client_id',scenario.changedClient?'oaiapp_other':clientId);return callback.href}};
}
const login=options=>oauth.login(interaction(),{getDeviceId:()=>deviceId,agentName:'DeepSeek Harness',...options});
const fibers=[];
async function harness(name){const ctx=new Context();let fiber=ctx.plugin(LocalCredentialProvider,{path:path.join(root,name,'.credentials.yaml'),watch:false});await fiber.await();fibers.push(fiber);fiber=ctx.plugin(AuthorizationService);await fiber.await();fibers.push(fiber);return ctx}
try{
  let credential;
  await test('new login validates RS256 identity, nonce and exact callback; no model request',async()=>{credential=await login();assert.equal(credential.identity.subject,'fixture-subject');assert.equal(credential.hostId,'urn:uuid:'+deviceId);assert.equal(authorizeUrl.searchParams.get('client_id'),'dynamic_agent_client');assert.equal(authorizeUrl.searchParams.get('agent_name_hint'),'DeepSeek Harness');assert(authorizeUrl.searchParams.get('code_challenge'));assert(!requests.some(r=>r.url.includes('/responses')))});
  for(const [name,flag]of [['wrong nonce','badNonce'],['wrong audience','audience'],['wrong issuer','issuer'],['expired token','expired'],['untrusted signature','badSignature'],['missing plan permission','missingScope'],['foreign JWKS endpoint','badJwks']])await test('rejects '+name,async()=>{scenario[flag]=flag==='audience'?'wrong-client':flag==='issuer'?'https://untrusted.invalid':true;await assert.rejects(login())});
  await test('invalid callback state is rejected before token exchange',async()=>{scenario.badState=true;await assert.rejects(login(),/state mismatch/);assert(!requests.some(r=>r.url.endsWith('/token')))});
  await test('real loopback callback ignores another state and accepts this attempt only',async()=>{const ui=interaction();let callbackTask;ui.prompt=()=>{callbackTask=(async()=>{const callback=new URL(authorizeUrl.searchParams.get('redirect_uri'));callback.search=new URLSearchParams({state:'wrong',code:'fixture-code',client_id:clientId});assert.equal((await originalFetch(callback)).status,400);callback.searchParams.set('state',authorizeUrl.searchParams.get('state'));assert.equal((await originalFetch(callback)).status,200);return callback.href})();return callbackTask};assert.equal((await oauth.login(ui,{getDeviceId:()=>deviceId})).identity.subject,'fixture-subject');await callbackTask});
  await test('cancellation retires the callback listener without exchanging credentials',async()=>{const stop=new AbortController(),ui=interaction(stop.signal);ui.notify=event=>{if(event.type==='auth_url'){authorizeUrl=new URL(event.url);stop.abort(Error('fixture cancelled'))}};ui.prompt=()=>Promise.reject(Error('fixture cancelled'));await assert.rejects(oauth.login(ui,{getDeviceId:()=>deviceId}),/cancelled/);assert(!requests.some(r=>r.url.endsWith('/token')));await new Promise(resolve=>setImmediate(resolve));await assert.rejects(originalFetch(authorizeUrl.searchParams.get('redirect_uri')))});
  await test('returning login reuses client and host, retains safe identity, sends only matching hint',async()=>{scenario.omitCallbackClient=true;const registration=await oauth.registration(credential);const next=await login({registration,credential});assert.equal(authorizeUrl.searchParams.get('client_id'),clientId);assert.equal(authorizeUrl.searchParams.has('agent_name_hint'),false);assert.equal(authorizeUrl.searchParams.get('id_token_hint'),credential.idToken);assert.equal(next.identity.subject,credential.identity.subject);assert(!JSON.stringify(registration).includes('fixture-refresh'))});
  await test('returning registration refuses another callback client or signed account',async()=>{const registration=await oauth.registration(credential);scenario.changedClient=true;await assert.rejects(login({registration}),/changed the selected/);scenario={subject:'different-subject'};await assert.rejects(login({registration}),/differs from the selected/)});
  await test('refresh keeps account mapping and identity when response omits ID token and scope',async()=>{scenario.omitScope=true;const next=await oauth.refresh(credential,new AbortController().signal);assert.equal(next.idToken,credential.idToken);assert.deepEqual(next.identity,credential.identity);assert.equal(next.clientId,credential.clientId);assert.equal(next.refresh,'fixture-refresh-rotated');assert.deepEqual(next.scopes,credential.scopes)});
  await test('refresh validates any new ID token and refuses an identity change',async()=>{scenario={refreshIdToken:true,subject:'different-subject'};await assert.rejects(oauth.refresh(credential,new AbortController().signal),/differs from the selected/)});
  await test('token exchange errors preserve structured HTTP status without exposing bodies',async()=>{scenario.tokenError=true;await assert.rejects(login(),error=>{assert(!String(error).includes('sensitive-body'));assert.equal(error.code,'AUTH');assert.equal(error.status,401);return true})});
  await test('remote revocation retries a server failure then confirms HTTP 200',async()=>{scenario.revokeFailFirst=true;assert.deepEqual(await oauth.revoke(credential,new AbortController().signal),{confirmed:true});assert.equal(revocationCalls,2);const request=requests.find(r=>r.url.endsWith('/revoke'));assert.equal(request.body.get('token'),credential.refresh);assert.equal(request.body.get('client_id'),clientId)});
  await test('remote revocation failure stays explicitly unconfirmed',async()=>{scenario.revokeNetwork=true;assert.deepEqual(await oauth.revoke(credential,new AbortController().signal),{confirmed:false});assert.equal(revocationCalls,3)});
  await test('native identity adoption is atomic and separate from account records',async()=>{const ctx=await harness('identity');const values=await Promise.all(Array.from({length:8},()=>pi.ensurePiAiInstallationId(ctx,'openai',{previousId:deviceId})));assert(values.every(v=>v===deviceId));assert.equal(await pi.ensurePiAiInstallationId(ctx,'openai',{previousId:'d94b266c-bc8a-4b7d-89c6-d968602c2a85'}),deviceId);assert.equal((await ctx.credentials.describeRecord(accountKey)).configured,false);await assert.rejects(pi.ensurePiAiInstallationId(ctx,'other',{previousId:'bad'}),/UUID/)});
  await test('native status is read-only and does not label legacy grants as verified accounts',async()=>{const ctx=await harness('status');await ctx.credentials.modifyRecord(accountKey,async()=>({kind:'grant',payload:{type:'oauth',access:'old',refresh:'old',expires:0,clientId}}));const before=requests.length;const value=await pi.describePiAiAccount(ctx,'openai');assert.equal(value.configured,true);assert.equal(value.account,undefined);assert.equal(requests.length,before);await ctx.credentials.modifyRecord(accountKey,async()=>({kind:'grant',payload:credential}));assert.equal((await pi.describePiAiAccount(ctx,'openai')).account.subject,'fixture-subject')});
  await test('native disconnect revokes and clears tokens while preserving registration and installation',async()=>{const ctx=await harness('logout');await pi.ensurePiAiInstallationId(ctx,'openai',{previousId:deviceId});await ctx.credentials.modifyRecord(accountKey,async()=>({kind:'grant',payload:credential}));const result=await pi.disconnectPiAiAccount(ctx,'openai');assert.deepEqual(result,{revocation:'confirmed',localCleared:true});assert.equal((await ctx.credentials.describeRecord(accountKey)).configured,false);const retained=await ctx.credentials.readRecord(registrationKey);assert.equal(retained.payload.clientId,clientId);assert(!JSON.stringify(retained).includes('fixture-refresh'));assert(!JSON.stringify(retained).includes(credential.idToken));assert.equal(await pi.ensurePiAiInstallationId(ctx,'openai'),deviceId)});
  await test('native logout preserves API keys and refuses deleting a concurrent replacement',async()=>{const ctx=await harness('races');await ctx.credentials.modifyRecord(accountKey,async()=>({kind:'api-key',key:'fixture-key'}));await assert.rejects(pi.disconnectPiAiAccount(ctx,'openai'),/API key was preserved/);assert.equal((await ctx.credentials.describeRecord(accountKey)).kind,'api-key');const observed={kind:'grant',payload:credential};await ctx.credentials.modifyRecord(accountKey,async()=>observed);await ctx.credentials.modifyRecord(accountKey,async()=>({kind:'api-key',key:'new-key'}));assert.equal(await ctx.credentials.deleteRecordIfCurrent(accountKey,observed),false);assert.equal((await ctx.credentials.describeRecord(accountKey)).kind,'api-key')});
  await test('actual DSH adapter offers OAuth and commits through the native authorization seam',async()=>{const ctx=await harness('flow');let fiber=ctx.plugin(LlmRuntime);await fiber.await();fibers.push(fiber);fiber=ctx.plugin(pi,{providers:{openai:{}}});await fiber.await();fibers.push(fiber);assert.deepEqual(ctx.authorization.describe(accountKey).methods.map(m=>m.id),['oauth','api-key']);await pi.ensurePiAiInstallationId(ctx,'openai',{previousId:deviceId});const ui=interaction();const result=await ctx.authorization.begin({key:accountKey,method:'oauth',interaction:{notify(n){if(n.url)authorizeUrl=new URL(n.url)},prompt:()=>ui.prompt()}});assert.equal(result.status,'authorized');assert.equal((await pi.describePiAiAccount(ctx,'openai')).account.subject,'fixture-subject')});
  await test('loaded account service coordinates admitted login commit before clearing it',async()=>{
    const ctx=await harness('admitted');let fiber=ctx.plugin(LlmRuntime);await fiber.await();fibers.push(fiber);fiber=ctx.plugin(pi,{providers:{openai:{}}});await fiber.await();fibers.push(fiber);
    const service=ctx.get('piAiAccounts');assert(service);await service.ensureInstallationId('openai',{previousId:deviceId});
    const store=ctx.get('credentials'),modify=store.modifyRecord.bind(store);let entered,release,held=false;const entry=new Promise(r=>entered=r),gate=new Promise(r=>release=r);
    store.modifyRecord=async(key,mutate)=>{if(key===accountKey&&!held){held=true;entered();await gate}return modify(key,mutate)};
    const ui=interaction();const attempt=ctx.authorization.begin({key:accountKey,method:'oauth',interaction:{notify(n){if(n.url)authorizeUrl=new URL(n.url)},prompt:()=>ui.prompt()}});
    await entry;const disconnect=service.disconnect('openai');await new Promise(r=>setImmediate(r));assert.equal((await service.describe('openai')).disconnecting,true);release();
    assert.equal((await attempt).status,'authorized');assert.equal((await disconnect).localCleared,true);assert.equal((await service.describe('openai')).configured,false);store.modifyRecord=modify;
  });
  await test('account sign-out aborts actual adapter inference through its existing signal',async()=>{
    const ctx=await harness('stream-cancel');let fiber=ctx.plugin(LlmRuntime);await fiber.await();fibers.push(fiber);fiber=ctx.plugin(pi,{providers:{openai:{transport:'sse'}}});await fiber.await();fibers.push(fiber);
    await ctx.credentials.modifyRecord(accountKey,async()=>({kind:'grant',payload:credential}));let entered;const entry=new Promise(r=>entered=r);scenario.pendingInference=true;scenario.inferenceStarted=entered;
    const stream=ctx.llm.stream({provider:'openai',model:'gpt-6.1-sol',messages:[{role:'user',content:[{type:'text',text:'offline fixture'}]}],tools:[]});
    const consuming=(async()=>{try{for await(const chunk of stream){void chunk}}catch{}})();
    await Promise.race([entry,new Promise((_,reject)=>setTimeout(()=>reject(Error('fixture inference did not reach fake transport')),3000))]);
    assert.equal((await ctx.get('piAiAccounts').disconnect('openai')).localCleared,true);await consuming;assert.equal(scenario.inferenceAborted,true);
  });
  console.log(JSON.stringify({ok:true,tests:resultRows.length,scope:'offline fake OIDC + exact native DSH/pi-ai + isolated credentials'}));
}finally{globalThis.fetch=originalFetch;for(const fiber of fibers.reverse())await fiber.dispose();assert.equal(path.dirname(path.resolve(root)),path.resolve(os.tmpdir()));assert(path.basename(root).startsWith('dsh-chatgpt-native-'));await fs.rm(root,{recursive:true,force:true})}
