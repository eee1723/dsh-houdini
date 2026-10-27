import assert from 'node:assert/strict'
import test from 'node:test'
import {fixture,wait} from './fixture.mjs'
import {WindowsDpapi} from '../lib/store.js'
import {testProtector} from './fixture.mjs'
import {SiwcProtocol} from '../lib/oauth.js'
import {SubscriptionAccounts} from '../lib/accounts.js'

test('SiWC native authorization, protected account directory, stable host/issued client and safe DTO',async()=>{
  const f=await fixture();try{
    assert.equal((await f.accounts.status()).accounts.length,0)
    assert.equal((await f.login()).status,'authorized')
    const first=await f.accounts.status(),id=first.activeAccountId
    assert.equal(first.accounts[0].sharing,true);assert.equal(first.accounts[0].identity.email,'fixture@example.invalid')
    assert(!JSON.stringify(first).includes('owned-access'));assert(!JSON.stringify([...f.ctx.credentials.records]).includes('owned-refresh'))
    const host=f.browsers[0].searchParams.get('ext_agent_host_id')
    assert.equal((await f.accounts.models()).length,2)
    assert.equal((await f.login({accountId:id})).status,'authorized')
    assert.equal(f.browsers[1].searchParams.get('client_id'),'issued-1')
    assert.equal(f.browsers[1].searchParams.get('ext_agent_host_id'),host)
    assert.equal(f.browsers[1].searchParams.has('agent_name_hint'),false)
    assert(f.browsers[1].searchParams.has('id_token_hint'))
    assert(!JSON.stringify(await f.accounts.status()).includes('id_token_hint'))
    await f.accounts.disconnect({accountId:id})
    const state=await f.store.read();assert.equal(state.accounts[0].clientId,'issued-1');assert.equal(state.accounts[0].tokens,undefined);assert.equal(state.hostId,host)
  }finally{await f.close()}
})
test('wrong nonce and absent plan permission never authorize or persist usable tokens',async()=>{
  for(const mode of ['wrong-nonce','no-plan','wrong-issuer','wrong-audience','wrong-signature']){const f=await fixture();try{f.mode(mode);const view=await f.login();assert.equal(view.status,'failed');const state=await f.store.read();assert.equal(state.activeId,undefined);assert.equal(state.accounts[0].tokens,undefined);assert.equal(state.accounts[0].clientId,'issued-1')}finally{await f.close()}}
})
test('cancel closes actual loopback listener and leaves registration/account disconnected',async()=>{
  const f=await fixture({holdBrowser:true});try{
    const attempt=await f.accounts.beginLogin({newAccount:true});await wait(()=>f.browsers.length)
    const result=await f.accounts.cancelLogin(attempt);assert.equal(result.status,'cancelled')
    await assert.rejects(fetch(f.browsers[0].searchParams.get('redirect_uri')))
    assert.equal((await f.accounts.status()).accounts[0].sharing,false)
  }finally{await f.close()}
})
test('concurrent expiry refresh rotates once and mismatched refreshed identity is never used',async()=>{
  const f=await fixture();try{
    await f.login();const id=(await f.accounts.status()).activeAccountId
    await f.store.updateAccount(id,account=>{account.tokens.expiresAt=Date.now()-1;return account})
    const values=await Promise.all([f.accounts.tokenFor(id,new AbortController().signal),f.accounts.tokenFor(id,new AbortController().signal)])
    assert.equal(f.refreshes(),1);assert.equal(values[0].accessToken,values[1].accessToken)
    // A separate protocol verifier forces the retrieval boundary to be tested.
    await f.store.updateAccount(id,account=>{account.tokens.expiresAt=Date.now()-1;return account})
    f.mode('wrong-subject');await assert.rejects(f.accounts.tokenFor(id,new AbortController().signal),/身份/)
    assert.equal((await f.store.readAccount(id)).status,'reauth_required');assert.equal((await f.store.readAccount(id)).pending,undefined)
    f.mode('normal');assert.equal((await f.login({accountId:id})).status,'authorized','invalid identity cannot trap the reconnect button in the same rejected checkpoint')
  }finally{await f.close()}
})
test('a JWKS outage after rotation preserves encrypted checkpoint and resumes without another refresh',async()=>{
  const f=await fixture();let resumed
  try{
    await f.login();const id=(await f.accounts.status()).activeAccountId
    await f.accounts.close()
    resumed=new SubscriptionAccounts(f.store,new SiwcProtocol(f.fetcher),f.ctx.authorization,async()=>{throw Error('No browser expected')},f.fetcher)
    await f.store.updateAccount(id,account=>{account.tokens.expiresAt=Date.now()-1;return account})
    f.mode('jwks-down');await assert.rejects(resumed.tokenFor(id,new AbortController().signal),/验证/)
    const pending=(await f.store.readAccount(id)).pending;assert(pending?.tokens.refreshToken);assert.equal(f.refreshes(),1)
    f.mode('normal');const result=await resumed.tokenFor(id,new AbortController().signal)
    assert.equal(result.accessToken,pending.tokens.accessToken);assert.equal(f.refreshes(),1);assert.equal((await f.store.readAccount(id)).pending,undefined)
  }finally{await resumed?.close();await f.close()}
})
test('safe launch link survives browser failure and expires on cancellation; raw hints never cross UI',async()=>{
  const f=await fixture({holdBrowser:true});try{
    f.browserFailure(true);const attempt=await f.accounts.beginLogin({newAccount:true})
    const view=await wait(()=>{const value=f.accounts.loginStatus(attempt);return value.launchUrl?value:null})
    assert.match(view.launchUrl,/^http:\/\/127\.0\.0\.1:\d+\/launch\/[A-Za-z0-9_-]+$/)
    assert(!JSON.stringify(view).includes('id_token_hint'))
    const redirect=await fetch(view.launchUrl,{redirect:'manual'});assert.equal(redirect.status,302);assert.equal(new URL(redirect.headers.get('location')).origin,'https://auth.openai.com')
    await f.accounts.cancelLogin(attempt);assert.equal(f.accounts.loginStatus(attempt).launchUrl,undefined);await assert.rejects(fetch(view.launchUrl))
  }finally{await f.close()}
})
test('cancellation before commit leaves tokens absent; native commit admission wins a late cancellation',async()=>{
  for(const admitted of [false,true]){
    let enter,release,wanted=false;const entered=new Promise(resolve=>enter=resolve),gate=new Promise(resolve=>release=resolve)
    const protector={...testProtector,async protect(bytes){const value=JSON.parse(Buffer.from(bytes).toString());
      if(value.status==='connected'){if(admitted)wanted=true;else{enter();await gate}}return testProtector.protect(bytes)}}
    const f=await fixture({protector});try{
      if(admitted)f.ctx.credentials.beforeWrite=async()=>{if(wanted){wanted=false;enter();await gate}}
      const attempt=await f.accounts.beginLogin({newAccount:true});await entered
      let settled=false;const cancellation=f.accounts.cancelLogin(attempt).then(value=>{settled=true;return value})
      await new Promise(resolve=>setTimeout(resolve,10));assert.equal(settled,!admitted)
      release();const value=await cancellation
      await new Promise(resolve=>setTimeout(resolve,10))
      assert.equal(value.status,admitted?'authorized':'cancelled');assert.equal((await f.accounts.status()).accounts[0].sharing,admitted)
    }finally{release();await f.close()}
  }
})
test('first plan notice acknowledgement and directory-read fact survive ordinary remounts',async()=>{
  const f=await fixture();try{
    await f.login();let status=await f.accounts.status();assert.equal(status.catalogRead,false);assert.equal(status.accounts[0].needsPlanNotice,true)
    await f.accounts.models();assert.equal((await f.accounts.status()).catalogRead,true)
    await f.accounts.acknowledgePlanNotice({accountId:status.activeAccountId});assert.equal((await f.accounts.status()).accounts[0].needsPlanNotice,false)
    await f.login({accountId:status.activeAccountId});assert.equal((await f.accounts.status()).accounts[0].needsPlanNotice,false)
  }finally{await f.close()}
})
test('multiple registrations remain distinct; logout of A cannot cancel B calls',async()=>{
  const f=await fixture();try{
    await f.login();const a=(await f.accounts.status()).activeAccountId
    await f.login();const b=(await f.accounts.status()).activeAccountId;assert.notEqual(a,b)
    const call=f.accounts.trackCall(b);await f.accounts.disconnect({accountId:a});assert.equal(call.signal.aborted,false);call.close()
    assert.equal((await f.accounts.status()).activeAccountId,b)
  }finally{await f.close()}
})
test('disconnect waits for the owning rotation and revokes the fresh canonical grant',async()=>{
  const f=await fixture();let release
  try{
    await f.login();const id=(await f.accounts.status()).activeAccountId
    await f.store.updateAccount(id,account=>{account.tokens.expiresAt=Date.now()-1;return account})
    let enter;const entered=new Promise(resolve=>enter=resolve),gate=new Promise(resolve=>release=resolve)
    f.tokenGate(async()=>{enter();await gate})
    const refresh=f.accounts.tokenFor(id,new AbortController().signal);await entered
    const logout=f.accounts.disconnect({accountId:id})
    await new Promise(resolve=>setTimeout(resolve,20));assert.equal(f.seen.some(row=>row.url.endsWith('/revoke')),false)
    release();const refreshed=await refresh;assert.equal((await logout).disconnected,true)
    const request=f.seen.find(row=>row.url.endsWith('/revoke'))
    assert.equal(new URLSearchParams(request.init.body).get('token'),refreshed.account.tokens.refreshToken)
    assert.equal((await f.store.readAccount(id)).status,'disconnected');assert.equal((await f.store.readAccount(id)).tokens,undefined)
  }finally{release?.();await f.close()}
})
test('real Windows DPAPI roundtrip never stores plaintext and wrong ciphertext fails',async()=>{
  const dpapi=new WindowsDpapi(),plain=Buffer.from('owned-unit-secret-not-an-account')
  if(process.platform!=='win32'){await assert.rejects(dpapi.protect(plain));return}
  const cipher=await dpapi.protect(plain);assert(!Buffer.from(cipher).includes(plain));assert.deepEqual(Buffer.from(await dpapi.unprotect(cipher)),plain)
  const invalid=Buffer.from(cipher);invalid[invalid.length-1]^=1;await assert.rejects(dpapi.unprotect(invalid))
})
