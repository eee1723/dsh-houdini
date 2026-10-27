import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import {Context} from '@deepseek-ai/cordis'
import LocalCredentials from '@deepseek-ai/dsh-credentials-local'
import {AccountStore,WindowsDpapi} from '../lib/store.js'

test('real official credentials-local and DPAPI retain accounts across restart without rewriting foreign entries',async()=>{
  if(process.platform!=='win32')return
  const folder=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-subscription-persistence-')),file=path.join(folder,'owned.credentials.yaml')
  const original='# owned native persistence fixture\nversion: 1\nrefs:\n  OWNED_OTHER_KEY: owned-other-value\nrecords:\n  unrelated/account:\n    kind: grant\n    payload:\n      keep: owned-foreign-value\n'
  await fs.writeFile(file,original,{mode:0o600})
  let fiber
  try{
    const first=new Context();fiber=first.plugin(LocalCredentials,{path:file,watch:false});await fiber.await()
    const store=new AccountStore(first.credentials,new WindowsDpapi(),path.join(folder,'locks')),state=await store.ensure(),id='account-11111111-1111-4111-8111-111111111111'
    await store.updateAccount(id,()=>({id,label:'Owned persistence',clientId:'issued-owned',identity:{subject:'owned-subject',email:'owned@example.invalid'},
      status:'connected',scopes:['chatgpt.tokens.use.direct'],tokens:{accessToken:'owned-private-access',refreshToken:'owned-private-refresh',expiresAt:Date.now()+3600000},revision:1,connectionRevision:1}))
    await store.metadata(meta=>{meta.activeId=id})
    const disk=await fs.readFile(file,'utf8');assert(!disk.includes('owned-private-access'));assert(!disk.includes('owned@example.invalid'))
    assert(disk.includes('OWNED_OTHER_KEY: owned-other-value'));assert(disk.includes('keep: owned-foreign-value'));assert(disk.startsWith('# owned native persistence fixture'))
    await fiber.dispose();fiber=null
    const next=new Context();fiber=next.plugin(LocalCredentials,{path:file,watch:false});await fiber.await()
    const restored=await new AccountStore(next.credentials,new WindowsDpapi(),path.join(folder,'locks')).read()
    assert.equal(restored.hostId,state.hostId);assert.equal(restored.activeId,id);assert.equal(restored.accounts[0].tokens.refreshToken,'owned-private-refresh')
    assert.equal((await next.credentials.readRecord('unrelated/account')).payload.keep,'owned-foreign-value')
  }finally{await fiber?.dispose();await fs.rm(folder,{recursive:true,force:true})}
})
