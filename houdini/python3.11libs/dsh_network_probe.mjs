// Short-lived diagnostics only: reuse the selected DSH's actual environment and transport.
import fs from 'node:fs'
import path from 'node:path'
import {createRequire} from 'node:module'
import {pathToFileURL} from 'node:url'
import {lookup} from 'node:dns/promises'

const require=createRequire(path.resolve(process.argv[2]))
const load=async name=>import(pathToFileURL(require.resolve(name)).href)
const redact=value=>{
  try {const url=new URL(value);return `${url.protocol}//${url.username||url.password?'redacted@':''}${url.host}`}
  catch {return '[无法解析的代理地址]'}
}
const request=JSON.parse(fs.readFileSync(0,'utf8'))
const report={schemaVersion:1,scope:'new_process_configuration',cwd:process.cwd()}
let dispose
try {
  const boot=await load('@deepseek-ai/dsh-app-boot')
  const {resolveDshHome}=await load('@deepseek-ai/dsh-home-paths')
  const environment=boot.loadLayeredEnv('dsh',process.cwd(),()=>{})
  report.home=resolveDshHome()
  report.envFile=path.join(report.home,'.env')
  report.runtime={node:process.version,dsh:require('@deepseek-ai/dsh/package.json').version}
  report.proxyEntries=[]
  for(const name of ['http_proxy','HTTP_PROXY','https_proxy','HTTPS_PROXY','all_proxy','ALL_PROXY','no_proxy','NO_PROXY']) {
    const entry=environment.get(name)
    if(entry?.value.trim())report.proxyEntries.push({name,source:entry.source,
      display:name.toLowerCase()==='no_proxy'?entry.value:redact(entry.value)})
  }
  const transport=await load('@deepseek-ai/dsh-http-proxy')
  report.proxyDiagnostics=[]
  dispose=await transport.installProxyFromEnvironment(environment,message=>report.proxyDiagnostics.push(message))
  const url=new URL(request.url)
  const route=transport.proxyRouteFor(url)
  report.route={proxied:route.proxied,proxy:route.proxied?redact(route.proxy):null}
  const bridgeUrl=new URL(request.bridgeUrl||'http://127.0.0.1:8765')
  report.bridgeRoute={url:bridgeUrl.origin,proxied:transport.proxyRouteFor(bridgeUrl).proxied,
    observed:'routing_only_no_bridge_request'}
  try {
  report.search={componentInstalled:!!require.resolve('@deepseek-ai/dsh-web-search-deepseek'),
      tested:false,note:'只核对配套搜索组件；未加载会话凭据或发起收费搜索，不能证明搜索可用'}
  } catch {report.search={componentInstalled:false,tested:false}}
  if(request.inspectOnly!==true) {
    const {HttpFetchProvider,DEFAULT_USER_AGENT}=await load('@deepseek-ai/dsh-web-fetch-http')
    const provider=new HttpFetchProvider({maxResponseBytes:5000000,maxBodyChars:100000,
      timeoutMs:15000,maxRedirects:5,userAgent:DEFAULT_USER_AGENT})
    const started=Date.now()
    try {
      const result=await provider.fetch({url:url.href},AbortSignal.timeout(20000))
      report.fetch={ok:result.statusCode>=200&&result.statusCode<300,url:url.href,
        status:result.statusCode,bodyKind:result.body.kind,bodyChars:result.body.content.length,
        truncated:result.truncated,elapsedMs:Date.now()-started}
    } catch(error) {
      report.fetch={ok:false,url:url.href,code:error.code||null,message:error.message,
        elapsedMs:Date.now()-started}
      if(error.code==='WEB_BLOCKED_URL') {
        try {report.fetch.resolvedAddresses=(await lookup(url.hostname,{all:true})).map(row=>row.address)}
        catch { /* The provider's original failure remains authoritative. */ }
      }
    }
  }
} catch(error) {
  report.error=String(error.message||error)
} finally {
  await dispose?.()
}
console.log('DSH_NETWORK_DIAGNOSTIC='+JSON.stringify(report))
