/** Purpose-specific tutorial configuration; DSH owns settings and credentials.
 * These tools never receive a secret or configure a fake chat model. */
import {createHash} from 'node:crypto'
import {readFileSync} from 'node:fs'
import {apiEndpoint,configuredProviders,hostService} from './api-route.js'

export const VIDEO_ADAPTERS=[
  {id:'openai-transcriptions',label:'OpenAI 兼容文件转录',transport:'multipart-file',local:true},
  {id:'qwen-chat-asr',label:'千问音频 Chat',transport:'audio-chat-json',local:false},
  {id:'dashscope-asr',label:'DashScope 同步音频',transport:'dashscope-json',local:false},
] as const
export type VideoProtocol=typeof VIDEO_ADAPTERS[number]['id']
export type VideoSelection={provider:string;model:string;python:string;protocol:string;endpoint:string;
  authentication:'bearer'|'none';credentialRef:string;concurrency:number;requestsPerSecond:number}
export const VIDEO_DEFAULTS=JSON.parse(readFileSync(new URL('../skills/houdini-video-tutorial/scripts/transcription-policy.json',import.meta.url),'utf8')) as {concurrency:number;requestsPerSecond:number}
export const VIDEO_SETTINGS={section:'houdini-video',model_section:'models'}
const FIELDS={provider:'videoProvider',model:'videoModel',protocol:'videoProtocol',endpoint:'videoEndpoint',
  authentication:'videoAuthentication',concurrency:'videoConcurrency',requests_per_second:'videoRequestsPerSecond'} as const

export function videoSelection(ctx:any):VideoSelection {
  const value=hostService(ctx,'houdiniFrontend')?.videoSelection?.()??{}
  return {provider:value.provider??'',model:value.model??'',python:value.python??'',protocol:value.protocol??'',endpoint:value.endpoint??'',
    authentication:value.authentication??'bearer',credentialRef:value.credentialRef??'',
    concurrency:value.concurrency??VIDEO_DEFAULTS.concurrency,requestsPerSecond:value.requestsPerSecond??VIDEO_DEFAULTS.requestsPerSecond}
}
export function videoProtocol(value:string):VideoProtocol {
  if(!VIDEO_ADAPTERS.some(row=>row.id===value))throw Error('请明确选择已支持的文件转录协议：openai-transcriptions、qwen-chat-asr 或 dashscope-asr。实时/WebSocket 和异步任务接口需要各自适配器，不能仅替换模型 ID。')
  return value as VideoProtocol
}
export function tutorialEndpoint(value:string):URL {
  const endpoint=apiEndpoint(value,'','Transcription')
  // apiEndpoint normalizes bases with a trailing slash; a purpose endpoint is
  // already complete and must retain its original path exactly.
  endpoint.pathname=new URL(value).pathname
  if(endpoint.protocol!=='https:'&&!['127.0.0.1','[::1]','localhost'].includes(endpoint.hostname))
    throw Error('远程转录需要 HTTPS；本机服务可使用明确的 localhost/127.0.0.1 HTTP 地址。局域网明文服务需先提供 HTTPS，不能把音频或凭据无提示发往不安全地址。')
  return endpoint
}
export function customVideoCredential(endpoint:string,protocol:string) {
  return 'DSH_HOUDINI_ASR_'+createHash('sha256').update(new URL(endpoint).origin).digest('hex').slice(0,16).toUpperCase()+'_API_KEY'
}

/** Explicit protocol, never a provider/model-name guess. */
export function resolveVideoRoute(ctx:any,selection:VideoSelection,override:{provider?:string;model?:string;protocol?:string}={}) {
  const protocol=videoProtocol(override.protocol??selection.protocol),model=override.model??selection.model
  if(!model||!/^[A-Za-z0-9_.:/-]{1,160}$/.test(model))throw Error('请填写服务商公布的准确转录模型 ID；它不需要加入聊天模型目录。')
  const provider=override.provider??selection.provider
  let endpoint:URL,credentialRef='',displayName='自定义转录服务',settingsSource:{ns:string;revision:number}|undefined
  if(provider) {
    const rows=configuredProviders(ctx).filter(row=>row.provider===provider)
    if(rows.length!==1||!rows[0].profile)throw Error('已选 DSH 服务商不存在或不明确；请重新选择已有服务商，或单独配置转录地址。')
    const row=rows[0],profile=row.profile
    const baseURL=profile.baseURL??row.defaultBaseURL
    if(!baseURL)
      throw Error('此聊天服务商没有明确的可复用音频 API 基址；请单独配置转录端点，不修改聊天模型。')
    if(profile.headers&&Object.keys(profile.headers).length)throw Error('此服务商使用额外请求头；当前转录适配器不支持该认证/头协议。请使用受支持端点，不能静默忽略请求头。')
    if(protocol==='dashscope-asr') {
      const base=apiEndpoint(baseURL,'')
      if(!['/compatible-mode/v1/','/api/v1/'].includes(base.pathname))throw Error('DashScope 需要明确的原生音频地址；不能从中转站路径推断原生接口。')
      endpoint=tutorialEndpoint(apiEndpoint(baseURL,'/api/v1/services/aigc/multimodal-generation/generation').href)
    }else endpoint=tutorialEndpoint(apiEndpoint(baseURL,protocol==='qwen-chat-asr'?'chat/completions':'audio/transcriptions').href)
    credentialRef=profile.apiKeyEnv??'';displayName=row.displayName;settingsSource=row.settingsSource
  }else {
    if(!selection.endpoint)throw Error('尚未选择转录服务。让 Agent 帮你配置已有服务商，或官方/中转/本机的完整转录端点。')
    endpoint=tutorialEndpoint(selection.endpoint)
    // Origin changes get a different native reference. An agent cannot send
    // another provider's saved key to a newly configured relay by accident.
    credentialRef=customVideoCredential(endpoint.href,protocol)
  }
  const authentication=selection.authentication
  if(!['bearer','none'].includes(authentication))throw Error('未支持的转录认证方式。')
  if(authentication==='none')credentialRef=''
  if(authentication==='bearer'&&!/^[A-Za-z_][A-Za-z0-9_]*$/.test(credentialRef))throw Error('此服务商没有可复用的 API-key 引用；可单独配置转录端点后安全录入密钥。OAuth 聊天授权不能代替语音 API-key。')
  return {provider:provider||null,displayName,model,protocol,endpoint:endpoint.href,origin:endpoint.origin,authentication,credentialRef,
    ...(settingsSource?{settingsSource}:{}),
    dataLocation:['127.0.0.1','[::1]','localhost'].includes(endpoint.hostname)?'loopback':'network',support:'unverified' as const}
}

export async function videoConfiguration(ctx:any) {
  const selected=videoSelection(ctx),diagnostics:string[]=[],providers=[]
  // Read settings identity in the same synchronous turn as the selection.
  // A credential-presence lookup may yield while another actor changes it.
  const settings=hostService(ctx,'settings')
  const descriptor=settings?.describe({redactSecrets:true}).find((row:any)=>row.ns==='houdini-frontend')
  const revision=descriptor?.revision,writable=Boolean(descriptor&&settings?.writable!==false&&descriptor.writable!==false)
  let displayedEndpoint=''
  if(selected.endpoint)try {displayedEndpoint=tutorialEndpoint(selected.endpoint).href}catch{displayedEndpoint='[端点未接受，请重新配置；原值不回显]'}
  const {credentialRef:_reference,...selectionView}=selected
  const safeSelected={...selectionView,endpoint:displayedEndpoint,
    authentication:['bearer','none'].includes(selected.authentication)?selected.authentication:'[认证方式未接受]'}
  try {for(const row of configuredProviders(ctx))providers.push({provider:row.provider,display_name:row.displayName})}
  catch(error){diagnostics.push((error as Error).message)}
  let service:any=null
  try {
    const route=resolveVideoRoute(ctx,selected)
    const credential=route.authentication==='none'?{configured:true,writable:false,required:false}:
      {...await hostService(ctx,'credentials').describe(route.credentialRef),required:true}
    service={...route,credential}
    if(!credential.configured)diagnostics.push('服务地址已配置；请在教程视频状态页点击「安全录入密钥」，不要粘贴到聊天。')
  }catch(error){diagnostics.push((error as Error).message)}
  return {selected:safeSelected,service,routes:providers,adapters:VIDEO_ADAPTERS.map(row=>({...row})),defaults:{concurrency:selected.concurrency,requestsPerSecond:selected.requestsPerSecond},
    diagnostics,revision,writable,settings:VIDEO_SETTINGS,
    setup:{tool:'video_configure',message:'请帮我配置教程分析：先检查当前状态，只问缺少的非秘密信息；API key 请让我在原生安全输入框录入。'},
    scope:'这里只读配置/凭据是否存在，未调用音频服务；正确地址、已存密钥或聊天模型目录均不证明转录可用。'}
}

export async function configureVideo(ctx:any,input:Record<string,unknown>) {
  if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).some(key=>!Object.hasOwn(FIELDS,key)&&key!=='expected_revision'))
    throw Error('配置只接受非秘密的服务地址、协议、模型和调度参数；密钥必须在原生凭据输入框录入。')
  if(input.provider&&input.endpoint)throw Error('请选择沿用已有服务商或独立转录端点，不能同时指定两份地址来源。')
  const before=videoSelection(ctx),next={...before},patch:Record<string,unknown>={}
  for(const [field,value] of Object.entries(input)) {
    if(field==='expected_revision')continue
    if(field==='concurrency') {if(!Number.isInteger(value)||Number(value)<1||Number(value)>64)throw Error('并发应为 1..64；默认 2，先用短段确认额度。');next.concurrency=Number(value)}
    else if(field==='requests_per_second') {if(typeof value!=='number'||!Number.isFinite(value)||value<=0||value>100)throw Error('请求速率应大于 0 且不超过 100。');next.requestsPerSecond=value}
    else {if(typeof value!=='string'||value.length>2048)throw Error('配置字段必须是有限长度文字。');(next as any)[field]=value.trim()}
    patch[(FIELDS as any)[field]]=typeof value==='string'?value.trim():value
  }
  const sourceChanged=(typeof input.endpoint==='string'&&input.endpoint.trim()!==before.endpoint)
    ||(typeof input.provider==='string'&&input.provider.trim()!==before.provider)
  if(sourceChanged) {
    // A new service is not evidence that the old model, wire protocol or
    // unauthenticated mode works there. Explicit values from this choice win.
    if(!Object.hasOwn(input,'model')){next.model='';patch.videoModel=''}
    if(!Object.hasOwn(input,'protocol')){next.protocol='';patch.videoProtocol=''}
    if(!Object.hasOwn(input,'authentication')){next.authentication='bearer';patch.videoAuthentication='bearer'}
  }
  if(Object.hasOwn(input,'endpoint')&&next.endpoint){next.provider='';patch.videoProvider=''}
  if(Object.hasOwn(input,'provider')&&next.provider){next.endpoint='';patch.videoEndpoint=''}
  if(next.provider||next.authentication==='none')patch.videoCredentialRef=''
  if(next.protocol)videoProtocol(next.protocol)
  if(next.endpoint)tutorialEndpoint(next.endpoint)
  if(next.model&&!/^[A-Za-z0-9_.:/-]{1,160}$/.test(next.model))throw Error('转录模型 ID 格式无效。')
  if(!['bearer','none'].includes(next.authentication))throw Error('认证只支持 bearer 或 none。')
  // Store one explicit native reference, never its secret value. Keeping it in
  // the Config also lets DSH's own credential surfaces describe this route.
  if(next.endpoint&&next.protocol)patch.videoCredentialRef=next.authentication==='none'?'':customVideoCredential(tutorialEndpoint(next.endpoint).href,next.protocol)
  const settings=hostService(ctx,'settings')
  const current=settings?.describe({redactSecrets:true}).find((row:any)=>row.ns==='houdini-frontend')
  if(!current||settings.writable===false||current.writable===false)throw Error('Houdini 教程设置当前不可写；请先确认本插件已经启用。')
  const revision=input.expected_revision??current.revision
  if(revision!==undefined&&!Number.isSafeInteger(revision))throw Error('无效的设置版本。')
  await settings.update('houdini-frontend',patch,revision)
  return {...await videoConfiguration(ctx),changed_fields:Object.keys(patch),
    next_action:'若缺密钥，在设置→教程视频点击安全录入；先获准上传一个短片试转录，再按实际额度调整并发。已有任务的原服务身份和结果不被本次设置修改。'}
}
