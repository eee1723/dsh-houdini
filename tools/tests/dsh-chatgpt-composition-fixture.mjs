// Fixture-only observation and synthetic credential inputs in the real Host.
// Production controller, native account service, settings and authorization stay intact.
import fs from 'node:fs'
import path from 'node:path'
import {createHash} from 'node:crypto'
import {createRequire} from 'node:module'
import {pathToFileURL} from 'node:url'
import assert from 'node:assert/strict'

const config=JSON.parse(fs.readFileSync(process.env.DSH_CHATGPT_COMPOSITION_CONFIG,'utf8'))
assert.equal(path.resolve(process.env.DSH_HOME),path.resolve(config.home),'fixture must use its own credentials/profile home')
const require=createRequire(config.binary)
const {credentialKey}=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-credentials')))
const accountKey=credentialKey('llm-pi-ai','openai'),otherKey=credentialKey('composition-fixture','untouched')
const write=(filename,value)=>{fs.writeFileSync(filename+'.tmp',JSON.stringify(value,null,2));fs.renameSync(filename+'.tmp',filename)}
const digest=filename=>fs.existsSync(filename)?createHash('sha256').update(fs.readFileSync(filename)).digest('hex'):null
const blockedExternal=[]
const catalogRequests=[]
let catalogFails=false
const accountModels=[
  {slug:'gpt-6.1-sol',display_name:'Account main model',description:'Synthetic account description',visibility:'list'},
  {slug:'gpt-4',display_name:'Hidden legacy model',visibility:'hide'},
  {slug:'gpt-6-luna',display_name:'Account quick model',visibility:'list'},
  {slug:'future-fixture-model',display_name:'Not yet installed',visibility:'list'},
]
const fetchOriginal=globalThis.fetch
globalThis.fetch=(input,init)=>{
  const url=new URL(typeof input==='string'||input instanceof URL?String(input):input.url)
  if(url.href==='https://api.openai.com/v1/models'&&(init?.method??'GET')==='GET'){
    assert.equal(new Headers(init?.headers??input?.headers).get('authorization'),'Bearer fixture','catalog uses the synthetic inference grant')
    catalogRequests.push({origin:url.origin,path:url.pathname,method:'GET'})
    return Promise.resolve(Response.json(catalogFails?{error:{message:'synthetic-private-provider-body'}}:{models:accountModels},{status:catalogFails?503:200}))
  }
  if(!['127.0.0.1','localhost','[::1]'].includes(url.hostname)){
    blockedExternal.push({origin:url.origin,method:init?.method??'GET'})
    throw Error('Fixture refuses external HTTP; no account or model request is permitted')
  }
  return fetchOriginal(input,init)
}
export const inject=['loader','houdiniFrontend','credentials','authorization','llm','settings','agentDefaultModel']
export function apply(ctx){
  ctx.effect(()=>{
    let stopped=false,busy=false,lastId
    const counts={describe:0,ensureInstallationId:0,disconnect:0,catalog:0}
    const native=ctx.get('piAiAccounts')
    const restore=[]
    if(native)for(const name of Object.keys(counts)){
      const original=native[name]
      if(typeof original!=='function')continue
      native[name]=function(...args){counts[name]++;return original.apply(this,args)}
      restore.push(()=>{native[name]=original})
    }
    const accountProfile=(field='value')=>{
      const entry=ctx.llm.listConfigurableProviders().find(row=>row.provider==='openai')
      let value=ctx.settings.describe({redactSecrets:true}).find(row=>row.ns===entry?.settingsNs)?.[field]
      for(const key of entry?.settingsPath??[])value=value?.[key]
      return value??null
    }
    const snapshot=async()=>({
      nativeService:Boolean(native),nativeMethods:Object.keys(counts).filter(name=>typeof native?.[name]==='function'),counts:{...counts},
      credential:await ctx.credentials.describeRecord(accountKey),other:await ctx.credentials.describeRecord(otherKey),
      credentialDigest:digest(path.join(config.home,'.credentials.yaml')),
      patchDigest:digest(path.join(config.home,'profiles/web/cordis.patch.yml')),
      defaultSelection:ctx.agentDefaultModel.currentSelection(),profile:accountProfile(),userProfile:accountProfile('user'),blockedExternal:[...blockedExternal],catalogRequests:[...catalogRequests],
      flow:ctx.authorization.describe(accountKey)?.methods.map(row=>row.id)??[],
    })
    queueMicrotask(async()=>{
      try{await ctx.loader.await();write(config.ready,{ok:true,...await snapshot()})}
      catch{write(config.ready,{ok:false,error:'Real Host composition did not become ready'})}
    })
    const timer=setInterval(async()=>{
      if(stopped||busy||!fs.existsSync(config.command))return
      let command
      try{command=JSON.parse(fs.readFileSync(config.command,'utf8'))}catch{return}
      if(command.id===lastId)return
      busy=true;lastId=command.id
      try{
        if(command.action==='seed-grant'){
          await ctx.credentials.modifyRecord(accountKey,async()=>({kind:'grant',payload:{type:'oauth',access:'fixture',refresh:'fixture',expires:Date.now()+600000}}))
          await ctx.credentials.modifyRecord(otherKey,async()=>({kind:'api-key',key:'synthetic-unrelated-record'}))
        }else if(command.action==='seed-api-key'){
          await ctx.credentials.modifyRecord(accountKey,async()=>({kind:'api-key',key:'synthetic-openai-api-record'}))
        }else if(command.action==='catalog-failure')catalogFails=true
        else if(command.action==='catalog-recover')catalogFails=false
        else if(command.action==='picker'){
          write(config.response+'.'+command.id,{id:command.id,ok:true,models:await ctx.llm.listModels('openai'),...await snapshot()});return
        }else if(command.action!=='snapshot')throw Error('Unknown fixture action')
        write(config.response+'.'+command.id,{id:command.id,ok:true,...await snapshot()})
      }catch(error){write(config.response+'.'+command.id,{id:command.id,ok:false,error:'Fixture observation or synthetic seed failed',diagnostic:String(error?.stack??error)})}
      finally{busy=false}
    },50)
    return ()=>{stopped=true;clearInterval(timer);for(const undo of restore)undo();globalThis.fetch=fetchOriginal}
  })
}
