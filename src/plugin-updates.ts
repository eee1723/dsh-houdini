/** Read-only release advice for the GitHub-distributed Houdini plugin. Installation
 * stays with DSH. This neither updates the Host nor grants version exemptions. */
import fs from 'node:fs/promises'
import semver from 'semver'
import {evaluatePluginCompatibility,getDshRuntimeVersion} from '@deepseek-ai/dsh-app-boot'

const REPOSITORY='https://github.com/eee1723/dsh-houdini'
const RELEASES='https://api.github.com/repos/eee1723/dsh-houdini/releases?per_page=100'
const CACHE_MS=12*60*60*1000

export interface PluginUpdateStatus {
  state:'current'|'available'|'unavailable'|'unknown'
  title:string
  message:string
  checkedAt:number|null
  currentVersion:string
  hostVersion:string|null
  update?:{version:string;url:string;installUrl:string;requiresDsh:string;summary:string;urgency:'optional'|'recommended'|'required'}
  details?:string
  checkError?:string
  attemptedAt?:number
  notesUrl?:string
}
type Release={tag_name:string;draft:boolean;prerelease:boolean;html_url:string;assets:{name:string;browser_download_url:string}[]}
type ReleaseUpdate={summary:string;urgency:'optional'|'recommended'|'required';affectedVersions?:string}
type Manifest={kind:string;version:string;requiresDsh:string;runtimeOwnership:string;file:string;installUrl:string;
  platform?:{os:string;cpu:string};update?:ReleaseUpdate}
type Options={fetch?:typeof fetch;now?:()=>number;version?:string;hostVersion?:()=>string;platform?:string;arch?:string}
class ReleaseRateLimit extends Error {}

/** Publication and consumption use the same rules, including pre-release
 * matching. A malformed mandatory-fix range cannot become an optional update. */
export function validReleaseUpdate(value:unknown):value is ReleaseUpdate {
  if(!value||typeof value!=='object'||Array.isArray(value))return false
  const note=value as ReleaseUpdate
  return typeof note.summary==='string'&&!!note.summary.trim()&&note.summary.length<=500
    &&['optional','recommended','required'].includes(note.urgency)
    &&(note.affectedVersions===undefined?note.urgency==='optional':
      typeof note.affectedVersions==='string'&&!!note.affectedVersions.trim()&&!!semver.validRange(note.affectedVersions))
}

async function json(response:Response,limit:number):Promise<unknown> {
  if(response.status===403&&response.headers.get('x-ratelimit-remaining')==='0')throw new ReleaseRateLimit('更新查询暂时受限。')
  if(!response.ok)throw Error('发布服务暂时不可用（'+response.status+'）。')
  if(Number(response.headers.get('content-length'))>limit)throw Error('更新信息超过读取范围。')
  const reader=response.body?.getReader()
  if(!reader)throw Error('没有收到更新信息。')
  const chunks:Uint8Array[]=[];let size=0
  try {
    for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength
      if(size>limit)throw Error('更新信息超过读取范围。');chunks.push(value)}
  }finally{await reader.cancel().catch(()=>{})}
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

/** Fixed publisher and immutable release assets; release prose is never executed
 * or used as an installation instruction. Old private-workbench releases lack
 * this standard-bundle manifest and are not candidates. */
export class PluginUpdates {
  private readonly fetcher:typeof fetch
  private readonly now:()=>number
  private readonly hostVersion:()=>string
  private readonly platform:string
  private readonly arch:string
  private readonly version:Promise<string>
  private cached?:PluginUpdateStatus
  private pending?:Promise<PluginUpdateStatus>
  constructor(options:Options={}) {
    this.fetcher=options.fetch??fetch;this.now=options.now??Date.now
    this.hostVersion=options.hostVersion??getDshRuntimeVersion
    this.platform=options.platform??process.platform;this.arch=options.arch??process.arch
    this.version=options.version?Promise.resolve(options.version):fs.readFile(new URL('../package.json',import.meta.url),'utf8')
      .then(text=>JSON.parse(text).version as string)
  }
  async read(input:unknown={},signal?:AbortSignal):Promise<PluginUpdateStatus> {
    if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).some(key=>key!=='refresh')
      ||'refresh' in input&&typeof input.refresh!=='boolean')throw Error('请重新打开插件更新。')
    signal?.throwIfAborted()
    const age=this.cached?this.now()-(this.cached.attemptedAt??this.cached.checkedAt!):Infinity
    if(!(input as {refresh?:boolean}).refresh&&this.cached&&age>=0&&age<(this.cached.state==='unknown'||this.cached.checkError?60000:CACHE_MS))return this.cached
    // One shared, bounded lookup per Host; closing a view does not cancel another
    // view's lookup. Consumers discard replies from old connection generations.
    if(!this.pending){const pending=this.check();this.pending=pending
      void pending.finally(()=>{if(this.pending===pending)this.pending=undefined}).catch(()=>{})}
    const result=await this.pending;signal?.throwIfAborted();return result
  }
  private async check():Promise<PluginUpdateStatus> {
    const version=await this.version
    let hostVersion:string|null=null
    const base:{currentVersion:string;hostVersion:string|null;checkedAt:number}={currentVersion:version,hostVersion,checkedAt:this.now()}
    try {
      hostVersion=this.hostVersion();base.hostVersion=hostVersion
      if(!semver.valid(hostVersion)||!semver.valid(version))throw Error('暂时无法确认正在使用的版本。')
      const signal=AbortSignal.timeout(12000)
      const request=(url:string,limit:number)=>this.fetcher(url,{signal,headers:{Accept:'application/vnd.github+json'}}).then(r=>json(r,limit))
      let raw:unknown,partial=false
      try {raw=await request(RELEASES,2_000_000)}catch(error) {
        if(!(error instanceof ReleaseRateLimit))throw error
        // GitHub's public latest full-release redirect does not need an API
        // quota. It proves only this release, never all historical candidates.
        const latest=await this.fetcher(REPOSITORY+'/releases/latest',{method:'HEAD',signal})
        const tag=latest.url.startsWith(REPOSITORY+'/releases/tag/')?latest.url.slice((REPOSITORY+'/releases/tag/').length):''
        const v=tag.startsWith('v')?tag.slice(1):''
        if(!latest.ok||!semver.valid(v)||semver.prerelease(v)!==null)throw Error('暂时无法确认正式更新。')
        const prefix=REPOSITORY+'/releases/download/'+tag+'/'
        raw=[{tag_name:tag,html_url:latest.url,draft:false,prerelease:false,
          assets:['release-manifest.json','dsh-houdini-'+v+'.tgz'].map(name=>({name,browser_download_url:prefix+name}))}]
        partial=true
      }
      if(!Array.isArray(raw))throw Error('发布服务没有返回版本列表。')
      const releases=(raw as Release[]).filter(r=>r&&r.draft===false&&r.prerelease===false
        &&typeof r.tag_name==='string'&&r.tag_name.startsWith('v')&&semver.valid(r.tag_name.slice(1))
        &&semver.prerelease(r.tag_name.slice(1))===null&&semver.gt(r.tag_name.slice(1),version)
        &&r.html_url===REPOSITORY+'/releases/tag/'+r.tag_name&&Array.isArray(r.assets))
        .sort((a,b)=>semver.rcompare(a.tag_name.slice(1),b.tag_name.slice(1)))
      let incompatible=false,failed=partial||releases.length>20
      const candidates:NonNullable<PluginUpdateStatus['update']>[]=[]
      for(const release of releases.slice(0,20)) {
        const asset=release.assets.find(a=>a.name==='release-manifest.json')
        if(!asset)continue
        const prefix=REPOSITORY+'/releases/download/'+release.tag_name+'/'
        if(asset.browser_download_url!==prefix+'release-manifest.json'){failed=true;continue}
        let m:Manifest
        try {m=await request(asset.browser_download_url,32768) as Manifest}catch{failed=true;continue}
        if(!m||m.kind!=='dsh-plugin-bundle'||m.runtimeOwnership!=='host'||m.version!==release.tag_name.slice(1)
          ||m.file!=='dsh-houdini-'+m.version+'.tgz'||m.installUrl!==prefix+m.file
          ||!release.assets.some(a=>a.name===m.file&&a.browser_download_url===m.installUrl)
          ||typeof m.requiresDsh!=='string'||!semver.validRange(m.requiresDsh)){failed=true;continue}
        if(m.platform&&(m.platform.os!==this.platform||m.platform.cpu!==this.arch))continue
        // Legacy standard bundles were explicitly Windows x64, even before
        // their release manifest included that fact.
        if(!m.platform&&(this.platform!=='win32'||this.arch!=='x64'))continue
        if(evaluatePluginCompatibility({name:'dsh-houdini',version:m.version,engines:{dsh:m.requiresDsh}},{},hostVersion)){
          incompatible=true;continue
        }
        if(partial){const packageHead=await this.fetcher(m.installUrl,{method:'HEAD',signal})
          if(!packageHead.ok)continue}
        const note=m.update
        if(note!==undefined&&!validReleaseUpdate(note)){failed=true;continue}
        const summary=note&&typeof note.summary==='string'&&note.summary.trim()&&note.summary.length<=500?note.summary:
          '此版本有功能改进。你可以先查看更新说明，再决定是否更新。'
        const affected=note?.affectedVersions&&semver.validRange(note.affectedVersions)
          &&semver.satisfies(version,note.affectedVersions,{includePrerelease:true})
        const urgency=affected&&['recommended','required'].includes(note?.urgency??'')?note!.urgency:'optional'
        candidates.push({version:m.version,url:release.html_url,installUrl:m.installUrl,requiresDsh:m.requiresDsh,summary,urgency})
      }
      // A later optional release does not prove that it contains an earlier
      // required fix. Prefer an explicitly applicable repair, then version.
      const priority={required:2,recommended:1,optional:0}
      candidates.sort((a,b)=>priority[b.urgency]-priority[a.urgency]||semver.rcompare(a.version,b.version))
      if(candidates.length){const update=candidates[0]
        if(failed&&this.cached?.state==='available'&&this.cached.update
          &&priority[this.cached.update.urgency]>priority[update.urgency])return this.failure({...base,state:'unknown',
            title:'暂时无法确认更新',message:'部分更新信息暂时无法读取。可以稍后再试。'})
        const result:PluginUpdateStatus={...base,state:'available',title:update.urgency==='required'?'请更新 Houdini 插件':
          update.urgency==='recommended'?'建议更新 Houdini 插件':'Houdini 插件有更新',message:update.summary,update,
          ...(failed?{checkError:'其他更新信息暂时无法读取，以下更新已确认可用。',attemptedAt:this.now()}:{})}
        this.cached=result;return result}
      if(failed)return this.failure({...base,state:'unknown',title:'暂时无法完整检查更新',
        message:'部分更新信息暂时无法读取。可以稍后重试，或先查看版本说明。',notesUrl:REPOSITORY+'/releases'})
      const result:PluginUpdateStatus={...base,state:incompatible?'unavailable':'current',
        title:incompatible?'新版暂不适合当前 DSH':'暂时没有适合当前环境的新版本',
        message:incompatible?
          '暂时没有适合当前 DSH 的插件更新。可以查看版本说明，了解支持范围。':'可以继续使用当前版本。',
        ...(incompatible?{notesUrl:REPOSITORY+'/releases'}:{})}
      this.cached=result
      return result
    }catch(error){const result:PluginUpdateStatus={...base,hostVersion,state:'unknown',title:'暂时无法检查更新',
      message:'未能取得更新信息，可以稍后重试。',notesUrl:REPOSITORY+'/releases',details:String(error instanceof Error?error.message:error)}
      return this.failure(result)}
  }
  private failure(result:PluginUpdateStatus):PluginUpdateStatus {
    if(this.cached&&this.cached.state!=='unknown'&&this.cached.hostVersion===result.hostVersion){
      this.cached={...this.cached,checkError:'暂时无法刷新，以下为上次检查结果。',attemptedAt:this.now(),details:result.details}
    }else this.cached=result
    return this.cached
  }
}
