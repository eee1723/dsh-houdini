/** Shared Host API routes and credentials remain owned by DSH model settings. */
export const hostService = (ctx:any,name:string) => ctx.get?.(name) ?? ctx[name]

/** The same provider/settings join as DSH's Models page, restricted to providers
 * that have a stored profile or a registered adapter. A chat protocol is not an
 * audio capability, so purpose-specific consumers diagnose unsupported routes. */
export function configuredProviders(ctx:any) {
  const llm=hostService(ctx,'llm'),settings=hostService(ctx,'settings')
  if (!llm || !settings) throw Error('DSH model/settings services are unavailable')
  const descriptors=settings.describe({redactSecrets:false})
  const registered=new Map<string,any>(llm.listProviders().map((entry:any)=>[entry.id,entry]))
  const declared=new Map<string,any>(llm.listConfigurableProviders().map((entry:any)=>[entry.provider,entry]))
  return [...new Set([...declared.keys(),...registered.keys()])].flatMap(provider=>{
    const entry=declared.get(provider),active=registered.get(provider)
    let profile=entry?descriptors.find((d:any)=>d.ns===entry.settingsNs)?.value:undefined
    for (const field of entry?.settingsPath??[]) profile=profile?.[field]
    const configured=Boolean(profile && typeof profile==='object' && !Array.isArray(profile))
    if (!configured && !active) return []
    return [{provider,displayName:entry?.displayName??active?.name??provider,
      registered:Boolean(active),configured,...(configured?{profile:structuredClone(profile)}:{}),
      ...(entry?.error?{error:entry.error}:{})}]
  })
}

export function configuredApiRoutes(ctx:any) {
  return configuredProviders(ctx).filter(route=>route.profile
    && ['openai-completions','openai-responses'].includes(route.profile.api) && route.profile.baseURL)
}

export function apiEndpoint(baseURL:string,operation:string,label='API') {
  const base=new URL(baseURL)
  if (!['https:','http:'].includes(base.protocol) || base.username || base.password || base.search || base.hash)
    throw Error(`${label} provider requires an HTTP(S) API base URL without embedded credentials, query or fragment`)
  if (!base.pathname.endsWith('/')) base.pathname+='/'
  return new URL(operation,base)
}

export async function apiCredential(ctx:any,profile:any,label:string) {
  const credentials=hostService(ctx,'credentials')
  if (!credentials) throw Error('DSH credential service is unavailable')
  if (!profile.apiKeyEnv) throw Error(`This ${label} API route needs an explicit apiKeyEnv credential reference in DSH model settings; OAuth/adapter-private credentials are not reused`)
  const value=(await credentials.resolve(profile.apiKeyEnv))?.value
  if (!value) throw Error(`No API key configured for this ${label.toLowerCase()} route; configure its credential in DSH model settings`)
  if (value.trim()!==value || /[\r\n]/.test(value)) throw Error('Configured API key has invalid whitespace')
  return value as string
}
