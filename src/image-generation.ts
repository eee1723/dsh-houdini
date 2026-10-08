/** Host image requests reuse DSH's configured routes, credential seam and attachments.
 * Managed destinations observe the selected Bridge; this module never calls HOM
 * directly, chooses a model, or introduces another provider registry. */
import fs from 'node:fs/promises'
import path from 'node:path'
import { createHash } from 'node:crypto'
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { attributionHeaders } from '@deepseek-ai/dsh-llm'
import { workspaceOf, HoudiniToolRuntime, type HoudiniConnection } from './tool-runtime.js'
import { imageOutputLocation, verifyManagedImageDirectory, type ImageOutputOptions } from './project-paths.js'
import { visualCapability } from './image-output.js'
import { IMAGE_TOOLS } from './tool-catalog.js'

const LIMIT = 64 * 1024 * 1024
const formats: Record<string, {format: string; mediaType: string}> = {
  '.png': {format:'png',mediaType:'image/png'}, '.jpg': {format:'jpeg',mediaType:'image/jpeg'},
  '.jpeg': {format:'jpeg',mediaType:'image/jpeg'}, '.webp': {format:'webp',mediaType:'image/webp'},
}
const hash = (data: Uint8Array) => createHash('sha256').update(data).digest('hex')
const service = (ctx:any, name:string) => ctx.get?.(name) ?? ctx[name]

async function isReservedFile(local:string, file:fs.FileHandle) {
  try {
    const [reserved,current]=await Promise.all([file.stat(),fs.lstat(local)])
    return current.isFile() && current.dev===reserved.dev && current.ino===reserved.ino
  } catch {return false}
}

function encodedType(data:Buffer) {
  if (data.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) return 'image/png'
  if (data[0]===255 && data[1]===216 && data[2]===255) return 'image/jpeg'
  if (data.toString('ascii',0,4)==='RIFF' && data.toString('ascii',8,12)==='WEBP') return 'image/webp'
  return null
}

function routes(ctx:any) {
  const llm = service(ctx,'llm'), settings = service(ctx,'settings')
  if (!llm || !settings) throw Error('DSH model/settings services are unavailable')
  const descriptors = settings.describe({redactSecrets:false})
  return llm.listConfigurableProviders().flatMap((entry:any) => {
    const descriptor = descriptors.find((d:any) => d.ns === entry.settingsNs)
    let profile = descriptor?.value
    for (const field of entry.settingsPath) profile = profile?.[field]
    // Only explicit OpenAI-compatible API routes. Catalog/OAuth defaults and
    // unrelated transports are not guessed from a provider or model name.
    if (!profile || !['openai-completions','openai-responses'].includes(profile.api) || !profile.baseURL) return []
    return [{provider:entry.provider,profile:structuredClone(profile)}]
  })
}

function endpoint(baseURL:string, operation:string) {
  const base = new URL(baseURL)
  if (!['https:','http:'].includes(base.protocol) || base.username || base.password || base.search || base.hash)
    throw Error('Image provider requires an HTTP(S) API base URL without embedded credentials, query or fragment')
  if (!base.pathname.endsWith('/')) base.pathname += '/'
  return new URL(`images/${operation}`,base)
}

/** Lists configured IDs, not a claim that a chat catalog certifies Images API support. */
export async function imageModels(ctx:any, query='image', provider?:string) {
  const result=[]
  for (const route of routes(ctx).filter((r:any) => !provider || r.provider === provider)) {
    const url=endpoint(route.profile.baseURL,'generations')
    const models = await service(ctx,'llm').listModels(route.provider)
    result.push({provider:route.provider,origin:url.origin,
      models:models.filter((m:any) => `${m.id} ${m.name ?? ''}`.toLowerCase().includes(query.toLowerCase()))
        .map((m:any) => ({id:m.id,name:m.name ?? m.id})),
      protocol:'openai-images',support:'unverified',
      note:'Configured model IDs; the provider must support the Images API. Use the exact user-selected model; no substitution.'})
  }
  return {routes:result,query,scope:'Configured API routes only; no network request, credential values or model inference.'}
}

async function credential(ctx:any, provider:string, profile:any) {
  const credentials=service(ctx,'credentials')
  if (!credentials) throw Error('DSH credential service is unavailable')
  if (!profile.apiKeyEnv) throw Error('This Images API route needs an explicit apiKeyEnv credential reference in DSH model settings; OAuth/adapter-private credentials are not reused')
  const value=(await credentials.resolve(profile.apiKeyEnv))?.value
  if (!value) throw Error('No API key configured for this image route; configure its credential in DSH model settings')
  if (value.trim() !== value || /[\r\n]/.test(value)) throw Error('Configured API key has invalid whitespace')
  return value
}

async function outputTarget(ctx:any, exec:any, args:ImageGenerateArgs, connection?:HoudiniConnection) {
  const filesystem=service(ctx,'fs'), policyService=service(ctx,'sandboxPolicy')
  const cwd=workspaceOf(exec)
  if (!cwd || !filesystem || !policyService) throw Error('Image output requires a DSH session workspace, filesystem and file policy')
  const policy=policyService.resolve({session:exec.agent.session})
  if (policy.mode === 'read-only') throw Error('Current DSH file policy is read-only; image generation requires a writable output')
  const destination=await imageOutputLocation(args,connection ? async()=>{
    const {bridge}=await new HoudiniToolRuntime(ctx,connection).target(exec)
    return {value:await bridge.sceneContext(exec.signal),executorId:bridge.targetExecutorId}
  } : undefined)
  const filename=destination.filename
  if (filename.includes('$HIP')) throw Error('Pass the actual HIP directory from scene_info; Host paths do not expand $HIP')
  const target=await filesystem.resolve(filename,{cwd,signal:exec.signal})
  const local=filesystem.processPath(target)
  if (filesystem.processPathFromHostPath(local) !== local) throw Error('Image output currently requires a local/shared Host filesystem')
  if (policy.mode !== 'danger-full-access') {
    const root=await filesystem.resolve(policy.workspaceRoot,{signal:exec.signal})
    if (!filesystem.contains(root,target)) throw Error('Image output is outside the current DSH writable workspace. '
      + `Requested destination: ${local}; writable workspace: ${policy.workspaceRoot}. Align the workspace or choose an explicitly permitted destination before generating.`)
  }
  if (await filesystem.stat(target,exec.signal)) throw Error('Image output already exists; choose a new filename to preserve the existing image')
  destination.artifact.actual_path=local.replace(/\\/g,'/')
  return {local,filesystem,cwd,target,filename,artifact:destination.artifact}
}

async function bodyBytes(response:Response, limit=LIMIT):Promise<Buffer> {
  if (Number(response.headers.get('content-length') ?? 0) > limit) {
    await response.body?.cancel(); throw Error('Image response exceeds the supported byte limit')
  }
  const reader=response.body?.getReader()
  if (!reader) throw Error('Image provider returned an empty response')
  const chunks:Uint8Array[]=[]; let count=0
  try {
    while (true) {
      const {done,value}=await reader.read(); if (done) break
      count+=value.byteLength
      if (count>limit) throw Error('Image response exceeds the supported byte limit')
      chunks.push(value)
    }
  } finally {await reader.cancel().catch(()=>{}); reader.releaseLock()}
  return Buffer.concat(chunks)
}

export interface ImageGenerateArgs extends ImageOutputOptions {
  provider:string; model:string; prompt:string; references?:string[]
  size?:string; quality?:string; background?:string
}

export async function generateImage(ctx:any, exec:any, args:ImageGenerateArgs, request:typeof fetch=fetch,
  connection?:HoudiniConnection):Promise<any> {
  if (![args.provider,args.model,args.prompt].every(v=>typeof v==='string' && v.trim()))
    throw Error('provider, model and prompt must be nonempty')
  if (args.output !== undefined && (typeof args.output!=='string' || !args.output.trim())) throw Error('output must be nonempty when provided')
  if (args.references && (!Array.isArray(args.references) || args.references.length>16 || args.references.some(p=>typeof p!=='string' || !p.trim())))
    throw Error('references must contain up to 16 local image paths')
  const format=formats[path.extname(args.output ?? 'image.png').toLowerCase()]
  if (!format) throw Error('output must end in .png, .jpg, .jpeg or .webp')
  if (args.background === 'transparent' && format.format === 'jpeg') throw Error('Transparent images require PNG or WebP')
  const matching=routes(ctx).filter((r:any)=>r.provider===args.provider)
  if (matching.length!==1) throw Error('Image provider is not an unambiguous configured OpenAI-compatible API route; inspect image_models')
  const {profile}=matching[0]
  const edit=Boolean(args.references?.length), url=endpoint(profile.baseURL,edit?'edits':'generations')
  const attachments=service(ctx,'attachments')
  if (!attachments?.saveFile) throw Error('DSH image and verbatim file attachment services are required')
  const output=await outputTarget(ctx,exec,args,connection)
  const sourceImages=[]
  let total=0
  for (const filename of args.references ?? []) {
    const type=formats[path.extname(filename).toLowerCase()]
    if (!type) throw Error('Reference images must be local PNG/JPEG/WebP files')
    const target=await output.filesystem.resolve(filename,{cwd:output.cwd,signal:exec.signal})
    const bytes=await output.filesystem.readBytes(target,exec.signal,attachments.imageLimits.maxImageBytes)
    await attachments.validateImage({data:bytes,mediaType:type.mediaType,name:path.basename(filename)})
    total+=bytes.length
    if (total>LIMIT) throw Error('Reference image batch exceeds 64 MiB')
    sourceImages.push({path:target.displayPath,bytes:Buffer.from(bytes),mediaType:type.mediaType,sha256:hash(bytes)})
  }
  const key=await credential(ctx,args.provider,profile)
  const privateValues=[key,...Object.values(profile.headers ?? {}).filter((v):v is string=>typeof v==='string' && v.length>3)]
  const redact=(value:unknown)=>privateValues.reduce((text,secret)=>text.split(secret).join('[redacted]'),String(value)).slice(0,1500)
  const headers=new Headers(profile.headers ?? {})
  for (const [name,value] of Object.entries(attributionHeaders())) headers.set(name,value)
  headers.set('Authorization',`Bearer ${key}`)
  const params:Record<string,string|number>={model:args.model,prompt:args.prompt,n:1,output_format:format.format}
  for (const name of ['size','quality','background'] as const) if (args[name]) params[name]=args[name]!
  let body:string|FormData
  if (edit) {
    const form=new FormData()
    for (const [name,value] of Object.entries(params)) form.set(name,String(value))
    for (const input of sourceImages) form.append('image[]',new Blob([new Uint8Array(input.bytes)],{type:input.mediaType}),path.basename(input.path))
    headers.delete('Content-Type'); body=form
  } else {headers.set('Content-Type','application/json'); body=JSON.stringify(params)}
  const facts:any={provider:args.provider,model:args.model,operation:edit?'edit':'generate',
    requested:{size:args.size ?? null,quality:args.quality ?? null,background:args.background ?? null},
    sources:sourceImages.map(({bytes,...image})=>({...image,bytes:bytes.length})),output:output.local,artifact:output.artifact,
    semantic_status:'unverified'}
  // Reserve a new target before billing. Revalidate the canonical location after
  // making parents; DSH supplies the policy and filesystem identity, not the model.
  await fs.mkdir(path.dirname(output.local),{recursive:true})
  await verifyManagedImageDirectory(output.artifact)
  const actual=await output.filesystem.resolve(output.filename,{cwd:output.cwd,signal:exec.signal})
  if (actual.targetKey!==output.target.targetKey) throw Error('Image output location changed before the request')
  const file=await fs.open(output.local,'wx')
  let written=false, dispatched=false, generated=false
  try {
    exec.signal?.throwIfAborted()
    dispatched=true
    const signal=exec.signal ? AbortSignal.any([exec.signal,AbortSignal.timeout(600_000)]) : AbortSignal.timeout(600_000)
    const response=await request(url,{method:'POST',headers,body,signal,redirect:'error'})
    facts.request_id=response.headers.get('x-request-id')
    facts.http_status=response.status
    const data=await bodyBytes(response)
    if (!response.ok) {
      let info:any; try {info=JSON.parse(data.toString('utf8'))?.error} catch {}
      const message=redact(info?.message ?? response.statusText)
      return {...facts,ok:false,status:'provider_rejected',error:`Images API HTTP ${response.status}: ${message}`,retry:'No automatic retry was made.'}
    }
    const result=JSON.parse(data.toString('utf8'))
    const encoded=result.data?.[0]?.b64_json
    if (!Array.isArray(result.data) || result.data.length!==1 || typeof encoded!=='string' || !encoded.length
        || encoded.length%4!==0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded))
      throw Error('Expected one base64 image from the Images API; URL-only or other response protocols are unsupported')
    generated=true
    const bytes=Buffer.from(encoded,'base64')
    // Preserve billed bytes independently of preview admission and destination
    // I/O. DSH's verbatim file store does not resize or apply image-message caps.
    try {
      const recoveryFile=await attachments.saveFile({data:bytes,name:path.basename(output.local)})
      facts.recovery_file={attachment:recoveryFile,path:null}
      try {facts.recovery_file.path=attachments.fileHostPath(recoveryFile) ?? null} catch { /* ref remains recoverable */ }
    } catch {facts.recovery_error='Original attachment storage failed; the output path is attempted independently.'}
    if (encodedType(bytes)!==format.mediaType) throw Error('Provider image signature does not match the requested output format; use recovery_file when available to inspect the original response bytes')
    facts.bytes=bytes.length; facts.sha256=hash(bytes); facts.usage=result.usage ?? null
    // The paid response remains recoverable if a user moves a project folder or
    // replaces this reservation while the remote provider is still generating.
    await verifyManagedImageDirectory(output.artifact)
    const current=await output.filesystem.resolve(output.filename,{cwd:output.cwd,signal:exec.signal})
    if (current.targetKey!==output.target.targetKey || !await isReservedFile(output.local,file))
      throw Error('Image output location or reserved file changed during generation; inspect recovery_file for the original image')
    await file.writeFile(bytes); written=true; await file.sync()
    facts.revised_prompt=typeof result.data[0].revised_prompt==='string'?result.data[0].revised_prompt:null
    facts.provider_model=typeof result.model==='string'?result.model:null
    let attachment:any, attachment_error:string|undefined
    const capability=await visualCapability(exec,ctx)
    if (capability.status==='available') {
      try {attachment=await attachments.saveImage({data:bytes,mediaType:format.mediaType,name:path.basename(output.local)})}
      catch {attachment_error='Original image saved; native preview decoding, size policy or attachment storage failed. Inspect the original file with a suitable viewer; do not regenerate.'}
    } else attachment_error='Image saved; the current model route does not provide an available image-input channel. Visual inspection remains unverified.'
    const dimensions=attachment?.originalDimensions ?? (attachment?{width:attachment.width,height:attachment.height}:null)
    const expected=args.size?.match(/^(\d+)x(\d+)$/)
    const warnings=dimensions && expected && (dimensions.width!==Number(expected[1]) || dimensions.height!==Number(expected[2]))
      ? ['Provider output dimensions differ from the requested size. Use actual_dimensions when importing or resampling; no resize or repeat request was performed.'] : []
    return {...facts,ok:true,status:'saved',actual_dimensions:dimensions,warnings,
      ...(attachment?{attachment}:{}),...(attachment_error?{attachment_error}:{}),
      file_validation:attachment?'decoded_by_native_attachment':'format_signature_only',
      note:'Exact provider image saved. Inspect it before accepting its appearance or reference accuracy; generation is not COP processing or geometry verification.'}
  } catch(error) {
    const message=redact(error)
    return {...facts,ok:false,status:written?'saved':generated?'response_received':dispatched?'outcome_unknown':'not_sent',
      error:message,retry:dispatched?'No automatic retry. The provider may have processed or billed this request; inspect output/provider request status before resubmitting.':'Request not sent.'}
  } finally {
    // Delete only our unfilled reservation, never a replacement at the same path.
    const remove=!written && await isReservedFile(output.local,file)
    await file.close()
    if (remove) await fs.unlink(output.local).catch(()=>{})
  }
}

export function registerImageTools(ctx:Context, connection?:HoudiniConnection) {
  const output={schema:{type:'json' as const},render:(_args:unknown,value:any)=>[
    {type:'text' as const,text:JSON.stringify(Object.fromEntries(Object.entries(value).filter(([k])=>k!=='attachment')))},
    ...(value.recovery_file?.attachment?[{type:'file' as const,attachment:value.recovery_file.attachment}]:[]),
    ...(value.attachment?[{type:'image' as const,attachment:value.attachment}]:[])],
    presentationMeta:(_args:unknown,value:any)=>({canonical:value})}
  ctx.tools.register(defineTool({name:'image_models',description:IMAGE_TOOLS.image_models.purpose,
    parameters:{query:{type:'string',description:'Model ID/name substring, default image; empty lists all configured models.'},provider:{type:'string',description:'Optional configured provider route.'}},
    output,presentCall:()=>({card:'generic',kind:'read',title:IMAGE_TOOLS.image_models.label}),
    execute:async(args)=>imageModels(ctx,args.query,args.provider)}))
  ctx.tools.register(defineTool({name:'image_generate',description:IMAGE_TOOLS.image_generate.purpose+
    ' One OpenAI-compatible Images API request, without automatic retry or model fallback. Reference files are uploaded as images, not prompt URLs. Does not modify the Houdini scene; managed output reads its current project location. Inspect the returned image.',
    parameters:{provider:{type:'string',required:true},model:{type:'string',required:true,description:'Exact requested model ID; use image_models for configured routes.'},
      prompt:{type:'string',required:true},output:{type:'string',description:'Managed: optional PNG/JPEG/WebP basename, with a unique suffix added. Explicit: required chosen path, absolute or relative to the DSH workspace. Existing files are preserved.'},
      output_policy:{type:'string',enum:['managed','explicit'],description:'Default managed observes the current named HIP once and writes under its project directory. Explicit preserves the chosen destination and needs no Houdini connection.'},
      purpose:{type:'string',enum:['reference','texture'],description:'Default reference goes to dsh-reference/generated; texture goes to dsh-texture. This classifies the intended use, not image quality.'},
      references:{type:'array',items:{type:'string'},description:'Optional local reference paths, up to 16. Their actual pixels are uploaded using images/edits.'},
      size:{type:'string',description:'Provider-supported WIDTHxHEIGHT or auto.'},quality:{type:'string',description:'Provider-supported quality; omitted keeps its default.'},
      background:{type:'string',enum:['auto','opaque','transparent']}},output,
    presentCall:args=>({card:'generic',kind:'execute',title:`生成图片 · ${args.model}`,rawInput:args}),
    execute:(args,exec)=>generateImage(ctx,exec,args,fetch,connection)}))
}
