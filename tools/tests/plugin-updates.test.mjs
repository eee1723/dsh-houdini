import assert from 'node:assert/strict'
import {PluginUpdates,validReleaseUpdate} from '../../lib/plugin-updates.js'
import {componentUpdate} from '../../lib/component-installation.js'

const repository='https://github.com/eee1723/dsh-houdini'
const host='0.2.1-rc.5'
const release=(version,changes={})=>({tag_name:'v'+version,html_url:repository+'/releases/tag/v'+version,
 draft:false,prerelease:false,assets:['release-manifest.json','dsh-houdini-'+version+'.tgz'].map(name=>({name,
 browser_download_url:repository+'/releases/download/v'+version+'/'+name})),...changes})
const manifest=(version,requiresDsh=host,changes={})=>({kind:'dsh-plugin-bundle',runtimeOwnership:'host',version,requiresDsh,
 file:'dsh-houdini-'+version+'.tgz',installUrl:repository+'/releases/download/v'+version+'/dsh-houdini-'+version+'.tgz',
 platform:{os:'win32',cpu:'x64'},...changes})
function fixture(releases,manifests,options={}) {
 const calls=[]
 const fetcher=async url=>{calls.push(url)
  if(url.startsWith('https://api.github.com/'))return Response.json(releases)
  const version=/\/v([^/]+)\//.exec(url)?.[1],value=manifests[version]
  if(value instanceof Error)throw value
  return value===undefined?new Response('missing',{status:404}):Response.json(value)
 }
 return {calls,service:new PluginUpdates({fetch:fetcher,version:'0.1.3',hostVersion:()=>host,platform:'win32',arch:'x64',...options})}
}

// Publication order and global latest do not decide what this user can install.
const f=fixture([release('0.1.9'),release('0.1.4'),release('0.1.8',{draft:true}),release('0.2.0-alpha.1',{prerelease:true})],
 {'0.1.9':manifest('0.1.9','0.2.2-alpha.2'),'0.1.4':manifest('0.1.4',host,{update:{summary:'改善工程连接。',urgency:'required',affectedVersions:'<0.1.0'}})})
const advised=await f.service.read()
assert.equal(advised.state,'available');assert.equal(advised.update.version,'0.1.4')
assert.equal(advised.update.urgency,'optional','a fix outside the installed version range is not mandatory')
assert.equal(advised.update.url,repository+'/releases/tag/v0.1.4')
assert(!f.calls.some(url=>url.includes('0.1.8')||url.includes('alpha')))
const count=f.calls.length;await f.service.read();assert.equal(f.calls.length,count,'background observations reuse the bounded Host cache')
await f.service.read({refresh:true});assert(f.calls.length>count,'explicit retry refreshes the facts')

const fix=fixture([release('0.1.4')],{'0.1.4':manifest('0.1.4',host,{update:{summary:'修复工程打开失败。',urgency:'recommended',affectedVersions:'0.1.3'}})})
assert.equal((await fix.service.read()).update.urgency,'recommended')
const repairs=fixture([release('0.1.6'),release('0.1.5')],{'0.1.6':manifest('0.1.6'),
 '0.1.5':manifest('0.1.5',host,{update:{summary:'修复当前版本的问题。',urgency:'required',affectedVersions:'0.1.3'}})})
assert.equal((await repairs.service.read()).update.version,'0.1.5','a later optional release does not erase a known applicable repair')
const mutable=[release('0.1.4')],notes={'0.1.4':manifest('0.1.4',host,{update:{summary:'修复工程打开失败。',urgency:'required',affectedVersions:'0.1.3'}})}
const retained=fixture(mutable,notes);const known=await retained.service.read();notes['0.1.4']=Error('offline')
const retry=await retained.service.read({refresh:true})
assert.equal(retry.state,'available');assert.equal(retry.update.urgency,'required');assert.equal(retry.checkedAt,known.checkedAt)
assert.match(retry.checkError,/上次检查/,'refresh failure preserves known advice while clearly marking stale facts')
const partialNotes={'0.1.6':manifest('0.1.6'),'0.1.5':manifest('0.1.5',host,{update:{summary:'修复当前版本的问题。',urgency:'required',affectedVersions:'0.1.3'}})}
const partial=fixture([release('0.1.6'),release('0.1.5')],partialNotes)
await partial.service.read();partialNotes['0.1.5']=Error('only one manifest is offline')
const partiallyRefreshed=await partial.service.read({refresh:true})
assert.equal(partiallyRefreshed.update.urgency,'required');assert.equal(partiallyRefreshed.update.version,'0.1.5')
assert.match(partiallyRefreshed.checkError,/上次检查/,'partial failures cannot erase a previously confirmed repair')
const firstPartial=await fixture([release('0.1.6'),release('0.1.5')],partialNotes).service.read()
assert.equal(firstPartial.state,'available');assert.match(firstPartial.checkError,/更新信息暂时无法读取/)
const incompatible=fixture([release('0.1.4')],{'0.1.4':manifest('0.1.4','0.2.2-alpha.2')})
const otherHost=await incompatible.service.read()
assert.equal(otherHost.state,'unavailable');assert.equal(otherHost.notesUrl,repository+'/releases');assert(!otherHost.update)
const failure=fixture([release('0.1.4')],{'0.1.4':Error('offline')})
const failed=await failure.service.read();assert.equal(failed.state,'unknown');assert(!failed.update)
await failure.service.read();assert.equal(failure.calls.length,2,'failed background checks do not retry on every render')
for(const changes of [{installUrl:'https://unrelated.example/plugin.tgz'},{version:'0.1.5'},
 {kind:'private-workbench'},{requiresDsh:'garbage'},{file:'old-workbench.zip'}]) {
 const invalid=fixture([release('0.1.4')],{'0.1.4':manifest('0.1.4',host,changes)})
 assert.equal((await invalid.service.read()).state,'unknown','malformed or foreign releases cannot become actionable updates')
}
const removed=fixture([release('0.1.4',{assets:[release('0.1.4').assets[0]]})],{'0.1.4':manifest('0.1.4')})
assert.equal((await removed.service.read()).state,'unknown','metadata without a downloadable package is not an available update')
const legacy=fixture([release('0.0.15',{assets:[{name:'release.json'}]})],{})
assert.equal((await legacy.service.read()).state,'current','old private-host packages never replace the standard plugin')
const unknown=fixture([],{}, {hostVersion:()=>{throw Error('unreadable host')}})
assert.equal((await unknown.service.read()).state,'unknown','unknown host identity is not called incompatible')
const abort=new AbortController();abort.abort()
await assert.rejects(f.service.read({},abort.signal),{name:'AbortError'})
await assert.rejects(f.service.read({url:'https://unrelated.example'}),/重新打开/)

// Only the observed API-quota condition uses GitHub's stable latest redirect;
// it still needs a valid compatible manifest and an existing package.
function rateFixture({latest='0.1.4',packageStatus=200,remaining='0',requiresDsh=host}={}) {
 const calls=[]
 const responseUrl=(url)=>{const r=new Response(null,{status:200});Object.defineProperty(r,'url',{value:url});return r}
 const fetcher=async(url,options)=>{calls.push({url,method:options?.method??'GET'})
  if(url.startsWith('https://api.github.com/'))return new Response('quota',{status:403,headers:{'x-ratelimit-remaining':remaining}})
  if(url.endsWith('/releases/latest'))return responseUrl(repository+'/releases/tag/v'+latest)
  if(url.endsWith('/release-manifest.json'))return Response.json(manifest(latest,requiresDsh))
  if(url.endsWith('.tgz'))return new Response(null,{status:packageStatus})
  throw Error('unexpected endpoint')
 }
 return {calls,service:new PluginUpdates({fetch:fetcher,version:'0.1.3',hostVersion:()=>host,platform:'win32',arch:'x64'})}
}
const quota=rateFixture(),quotaResult=await quota.service.read()
assert.equal(quotaResult.state,'available');assert.equal(quotaResult.update.version,'0.1.4')
assert.match(quotaResult.checkError,/已确认可用/)
assert.equal(quota.calls.find(c=>c.url.endsWith('.tgz')).method,'HEAD','fallback proves the package without downloading it')
assert.equal((await rateFixture({latest:'0.2.0-alpha.1'}).service.read()).state,'unknown','a prerelease-looking redirect is never recommended')
assert.equal((await rateFixture({requiresDsh:'0.2.2-alpha.2'}).service.read()).state,'unknown','a partial lookup cannot claim that no older compatible update exists')
assert.equal((await rateFixture({packageStatus:404}).service.read()).state,'unknown')
const other403=rateFixture({remaining:'30'})
assert.equal((await other403.service.read()).state,'unknown');assert.equal(other403.calls.length,1,'unexplained 403 does not invent a fallback condition')
for(const affectedVersions of ['', 'not-a-range']) {
 const malformed={summary:'请更新。',urgency:'required',affectedVersions}
 assert.equal(validReleaseUpdate(malformed),false)
 assert.equal((await fixture([release('0.1.4')],{'0.1.4':manifest('0.1.4',host,{update:malformed})}).service.read()).state,'unknown')
}

// Installed and loaded are independent; no build difference grants scene access.
const current='a'.repeat(16),old='b'.repeat(16)
assert.equal(componentUpdate({helper:{id:old,version:'0.1.3'}},current,false).state,'install')
assert.equal(componentUpdate({helper:{id:old,version:'0.1.3'}},current,true).state,'restart')
assert.equal(componentUpdate({helper:{id:current,version:'0.1.4'}},current,true).state,'current')
assert.equal(componentUpdate({},current,true).state,'unknown','an old helper without loaded identity does not prove that reopening alone will work')
assert.equal(componentUpdate({helper:{id:old,version:'0.1.3'}},current,null).state,'unknown')
assert.equal(componentUpdate({helper:{id:old,version:'0.1.3'}},current,true,false).state,'unknown',
 'an updated Package in another installation cannot promise that reopening this window loads it')
console.log('Plugin update advice: compatible target selection, explicit affected versions, unavailable/unknown separation, cache and actual loaded component states passed')
