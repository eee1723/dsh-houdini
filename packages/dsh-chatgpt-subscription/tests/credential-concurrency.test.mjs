import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import {spawn} from 'node:child_process'
import {once} from 'node:events'
import {randomUUID} from 'node:crypto'
import {Context} from '@deepseek-ai/cordis'
import LocalCredentials from '@deepseek-ai/dsh-credentials-local'
import {credentialRef} from '@deepseek-ai/dsh-credentials'
import {AccountStore} from '../lib/store.js'
import {SubscriptionAccounts} from '../lib/accounts.js'
import {fixture,testProtector} from './fixture.mjs'

test('refresh serializes only its account while both native credential providers can write unrelated records',async()=>{
  const folder=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-subscription-concurrency-')),file=path.join(folder,'owned.credentials.yaml'),lockDirectory=path.join(folder,'account-locks')
  const f=await fixture({credentialPlugin:LocalCredentials,credentialConfig:{path:file,watch:false},lockDirectory})
  const second=new Context(),fiber=second.plugin(LocalCredentials,{path:file,watch:false});await fiber.await()
  const store=new AccountStore(second.credentials,testProtector,lockDirectory)
  const other=new SubscriptionAccounts(store,f.accounts.protocol,f.ctx.authorization,async()=>{throw Error('No browser expected')},f.fetcher)
  let release=()=>{}
  try{
    await f.login();const id=(await f.accounts.status()).activeAccountId
    await f.store.updateAccount(id,row=>{row.tokens.expiresAt=Date.now()-1;return row})
    let enter;const entered=new Promise(resolve=>enter=resolve),gate=new Promise(resolve=>release=resolve)
    f.tokenGate(async()=>{enter();await gate})
    const first=f.accounts.tokenFor(id,new AbortController().signal);await entered
    const contender=other.tokenFor(id,new AbortController().signal)
    let closed=false;const closing=f.accounts.close().then(()=>{closed=true})
    const unrelated=Promise.all([
      f.ctx.credentials.set(credentialRef('OWNED_OTHER_PROVIDER_KEY'),'owned-dummy-value'),
      second.credentials.modifyRecord('unrelated-provider/account',()=>({kind:'grant',payload:{owned:true}})),
    ])
    let timer
    try{await Promise.race([unrelated,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Unrelated native writers blocked behind subscription network')),2500)})])}
    finally{clearTimeout(timer)}
    assert.equal(closed,false,'close still drains the admitted rotation')
    assert.equal(f.refreshes(),1,'another native provider/account manager must not rotate the same token')
    assert.equal(await fs.stat(file+'.lock').then(()=>true,error=>{if(error.code==='ENOENT')return false;throw error}),false)
    assert.equal(await fs.stat(path.join(lockDirectory,id)+'.lock').then(()=>true),true)
    release();const[a,b]=await Promise.all([first,contender,closing])
    assert.equal(a.accessToken,b.accessToken);assert.equal(f.refreshes(),1)
    assert.equal((await store.readAccount(id)).tokens.accessToken,a.accessToken)
    assert.equal((await second.credentials.readRecord('unrelated-provider/account')).payload.owned,true)
  }finally{release();await other.close();await f.close();await fiber.dispose();await fs.rm(folder,{recursive:true,force:true})}
})

test('the account lock excludes another OS process without storing another credential copy',async()=>{
  const folder=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-subscription-process-lock-')),id='account-'+randomUUID()
  const store=new AccountStore({},testProtector,folder)
  const source=new URL('../lib/store.js',import.meta.url).href
  const code=`import{AccountStore}from ${JSON.stringify(source)};const store=new AccountStore({}, {}, ${JSON.stringify(folder)});await store.withAccountLock(${JSON.stringify(id)},async()=>{process.stdout.write('LOCK_HELD\\n');await new Promise(resolve=>process.stdin.once('data',resolve))});`
  const child=spawn(process.execPath,['--input-type=module','-e',code],{stdio:['pipe','pipe','pipe'],env:{...process.env,DSH_HOME:folder}})
  const ended=once(child,'exit');let errorText='',entered=false
  child.stderr.on('data',data=>errorText+=data)
  try{
    await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Child lock timeout '+errorText)),5000);child.stdout.on('data',data=>{if(String(data).includes('LOCK_HELD')){clearTimeout(timer);resolve()}});child.once('error',error=>{clearTimeout(timer);reject(error)})})
    await assert.rejects(store.withAccountLock(id,async()=>{entered=true},AbortSignal.timeout(120)),error=>error.name==='TimeoutError'||error.name==='AbortError')
    assert.equal(entered,false)
    const lock=await fs.readFile(path.join(folder,id)+'.lock','utf8');assert(lock.includes(String(child.pid)));assert(!lock.includes('token'))
    child.stdin.end('release\n');assert.equal((await ended)[0],0,errorText)
    await store.withAccountLock(id,async()=>{entered=true});assert.equal(entered,true)
    assert.deepEqual(await fs.readdir(folder),[],'only a transient PID lock exists; no account/token replica')
  }finally{if(child.exitCode===null){child.kill();await ended}await fs.rm(folder,{recursive:true,force:true})}
})

test('an old prepared connection is rejected from the fresh native record before refreshing a replacement',async()=>{
  const folder=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-subscription-fresh-generation-')),file=path.join(folder,'owned.credentials.yaml'),lockDirectory=path.join(folder,'account-locks')
  const f=await fixture({credentialPlugin:LocalCredentials,credentialConfig:{path:file,watch:false},lockDirectory})
  const second=new Context(),fiber=second.plugin(LocalCredentials,{path:file,watch:false});await fiber.await()
  const store=new AccountStore(second.credentials,testProtector,lockDirectory)
  try{
    await f.login();const{account,generation}=await f.accounts.selection(),id=account.id
    await store.withAccountLock(id,()=>store.updateAccount(id,row=>{row.revision++;row.connectionRevision++;row.tokens.expiresAt=Date.now()-1;row.tokens.accessToken='owned-reconnected-token';return row}))
    const replacement=await store.readAccount(id)
    assert.equal((await f.store.readAccount(id)).connectionRevision,generation.connectionRevision,'first native reader remains cached')
    await assert.rejects(f.accounts.tokenFor(id,new AbortController().signal,generation),error=>error.code==='ACCOUNT_CHANGED')
    assert.equal(f.refreshes(),0,'an old prepared call must never rotate the replacement connection')
    assert.deepEqual(await store.readAccount(id,true),replacement)
  }finally{await f.close();await fiber.dispose();await fs.rm(folder,{recursive:true,force:true})}
})
