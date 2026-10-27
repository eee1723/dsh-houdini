import {randomUUID} from 'node:crypto'
import {mkdir} from 'node:fs/promises'
import {join} from 'node:path'
import {withFileLock} from '@deepseek-ai/dsh-atomic-write'
import {credentialKey,type CredentialProvider,type CredentialRecord} from '@deepseek-ai/dsh-credentials'
import type {Account,AccountState,Protector} from './types.js'
import {OWNER} from './types.js'
import {SubscriptionError} from './errors.js'

export const ACCOUNT_KEY=credentialKey(OWNER,'installation')
export const profileKey=(id:string)=>{if(!/^account-[0-9a-f-]{36}$/.test(id))throw new SubscriptionError('INVALID_INPUT','账户标识无效。');return credentialKey(OWNER,id)}
type Metadata={version:1;hostId:string;activeId?:string}

/** The native provider is the only writer; no SDK auth.json or environment fallback exists. */
export class AccountStore {
  constructor(private readonly credentials:CredentialProvider,readonly protector:Protector,readonly lockDirectory:string){}
  /** A public cross-process lock per account. Only a PID lock lives here;
   * credential and rotation receipts remain exclusively in the native store. */
  async withAccountLock<T>(id:string,operation:()=>Promise<T>,signal?:AbortSignal):Promise<T>{
    profileKey(id);signal?.throwIfAborted()
    await mkdir(this.lockDirectory,{recursive:true,mode:0o700})
    return withFileLock(join(this.lockDirectory,id),operation,{signal,waitMs:120000})
  }
  private async decode(record:CredentialRecord|undefined):Promise<unknown>{
    if(!record)return undefined
    if(record.kind!=='grant'||!record.payload||typeof record.payload!=='object')throw new SubscriptionError('STORE_INVALID','订阅账户记录无法读取；原记录已保留。')
    const envelope=record.payload as {version?:number;protection?:string;ciphertext?:string}
    if(envelope.version!==1||envelope.protection!==this.protector.id||typeof envelope.ciphertext!=='string')throw new SubscriptionError('STORE_INVALID','订阅账户保护格式不匹配；原记录已保留。')
    const bytes=await this.protector.unprotect(Buffer.from(envelope.ciphertext,'base64'))
    try{return JSON.parse(Buffer.from(bytes).toString('utf8')) as unknown}
    catch{throw new SubscriptionError('STORE_INVALID','订阅账户记录无法读取；原记录已保留。')}
    finally{bytes.fill(0)}
  }
  async encode(value:unknown):Promise<CredentialRecord>{
    const bytes=Buffer.from(JSON.stringify(value),'utf8')
    try{const ciphertext=await this.protector.protect(bytes);return {kind:'grant',payload:{version:1,protection:this.protector.id,ciphertext:Buffer.from(ciphertext).toString('base64')}}}
    finally{bytes.fill(0)}
  }
  async readAccount(id:string,fresh=false):Promise<Account|undefined>{
    // Native readers may be watch-backed caches. A declined native mutation
    // reconciles under its brief file lock and returns current state, with no write.
    const key=profileKey(id),record=fresh?await this.credentials.modifyRecord(key,async()=>undefined):await this.credentials.readRecord(key)
    const value=await this.decode(record) as Account|undefined
    if(value&&(value.id!==id||!Array.isArray(value.scopes)||!Number.isSafeInteger(value.revision)))throw new SubscriptionError('STORE_INVALID','账户记录格式无效；原记录已保留。')
    return value
  }
  async read():Promise<AccountState|undefined>{
    const meta=await this.decode(await this.credentials.readRecord(ACCOUNT_KEY)) as Metadata|undefined
    if(!meta)return undefined
    if(meta.version!==1||!/^urn:uuid:[0-9a-f-]{36}$/i.test(meta.hostId))throw new SubscriptionError('STORE_INVALID','安装身份记录无效；原记录已保留。')
    const accounts:Account[]=[]
    for(const entry of await this.credentials.listRecords())if(String(entry.key).startsWith(OWNER+'/account-')){
      const account=await this.readAccount(String(entry.key).slice(OWNER.length+1));if(account)accounts.push(account)
    }
    return {...meta,accounts}
  }
  async metadata(change:(value:Metadata)=>void){
    await this.credentials.modifyRecord(ACCOUNT_KEY,async current=>{
      const value=await this.decode(current) as Metadata|undefined??{version:1 as const,hostId:'urn:uuid:'+randomUUID()}
      change(value);return this.encode(value)
    })
  }
  async updateAccount(id:string,change:(value:Account|undefined)=>Account,signal?:AbortSignal):Promise<Account>{
    let result:Account|undefined
    await this.credentials.modifyRecord(profileKey(id),async record=>{
      signal?.throwIfAborted();const current=await this.decode(record) as Account|undefined
      result=change(current);const encoded=await this.encode(result);signal?.throwIfAborted();return encoded
    })
    return structuredClone(result!)
  }
  async ensure(){if(!await this.read())await this.metadata(()=>{});return (await this.read())!}
}

/** Windows per-user DPAPI, no plaintext fallback and no Houdini interpreter. */
export class WindowsDpapi implements Protector {
  readonly id='windows-dpapi-current-user-v1'
  private api?:Promise<{run:(bytes:Uint8Array,decrypt:boolean)=>Uint8Array}>
  private load(){return this.api??=(async()=>{
    if(process.platform!=='win32')throw new SubscriptionError('PROTECTION_UNAVAILABLE','本订阅插件当前需要 Windows 用户凭据保护；未写入明文凭据。')
    const {default:koffi}=await import('koffi')
    const blob=koffi.struct({cbData:'uint32',pbData:'void *'}),pointer=koffi.pointer(blob)
    const crypt=koffi.load('crypt32.dll'),kernel=koffi.load('kernel32.dll')
    const protect=crypt.func('__stdcall','CryptProtectData','int',[pointer,'str16',pointer,'void *','void *','uint32',koffi.out(pointer)])
    const unprotect=crypt.func('__stdcall','CryptUnprotectData','int',[pointer,'void *',pointer,'void *','void *','uint32',koffi.out(pointer)])
    const free=kernel.func('__stdcall','LocalFree','void *',['void *'])
    return {run(bytes:Uint8Array,decrypt:boolean){
      const input=Buffer.from(bytes),entropy=Buffer.from('dsh-chatgpt-subscription/v1'),output={cbData:0,pbData:null as unknown}
      try{
        const ok=(decrypt?unprotect:protect)({cbData:input.length,pbData:input},decrypt?null:'DSH ChatGPT subscription',{cbData:entropy.length,pbData:entropy},null,null,1,output)
        if(!ok)throw new SubscriptionError('PROTECTION_UNAVAILABLE','Windows 无法保护或读取此账户凭据；原记录已保留。')
        try{return Buffer.from(koffi.decode(output.pbData,'uint8',output.cbData) as Uint8Array)}finally{free(output.pbData)}
      }finally{input.fill(0)}
    }}
  })()}
  async protect(bytes:Uint8Array){return (await this.load()).run(bytes,false)}
  async unprotect(bytes:Uint8Array){return (await this.load()).run(bytes,true)}
}
