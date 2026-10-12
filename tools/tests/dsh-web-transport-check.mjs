/** Public CDN redirects and network diagnostics, using real sockets with isolated routing. */
import assert from 'node:assert/strict';import fs from 'node:fs';import path from 'node:path';import http from 'node:http';
import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';
const cache=path.resolve(process.argv[2]),require=createRequire(path.join(cache,'node_modules/@deepseek-ai/dsh/lib/bin.js'));
const load=async n=>import(pathToFileURL(require.resolve(n)));
const {HttpFetchProvider}=await load('@deepseek-ai/dsh-web-fetch-http');
const transport=await load('@deepseek-ai/dsh-http-proxy');
const {resolvePublicAddresses}=await import(pathToFileURL(path.join(cache,'node_modules/@deepseek-ai/dsh-web-fetch-http/lib/types/network.js')));
const limits={maxResponseBytes:1024,maxBodyChars:1024,timeoutMs:2000,maxRedirects:2,userAgent:'DSH verification'};
const results=[],test=async(name,body)=>{await body();results.push({name,ok:true});console.log('PASS',name)};
let hits=0,cdnPort;const image=Buffer.from([255,216,255,1,2,3,255,217]);
const cdn=http.createServer((q,r)=>{hits++;assert.equal(q.headers.authorization,undefined);assert.equal(q.headers.cookie,undefined);r.writeHead(200,{'content-type':'image/jpeg'});r.end(image)});
const site=http.createServer((q,r)=>{const target=q.url==='/private'?`http://127.0.0.1:${cdnPort}/secret`:q.url==='/credentials'?`http://user:secret@cdn.fixture.test:${cdnPort}/image`:q.url==='/loop'?'/loop':q.url==='/scheme'?'file:///C:/private':`http://cdn.fixture.test:${cdnPort}/image`;r.writeHead(302,{location:target});r.end()});
const listen=s=>new Promise(r=>s.listen(0,'127.0.0.1',()=>r(s.address().port)));
const close=s=>new Promise(r=>{s.closeAllConnections();s.close(r)});
cdnPort=await listen(cdn);const sitePort=await listen(site),origin=`http://source.fixture.test:${sitePort}`;
const resolved=[];const provider=new HttpFetchProvider(limits,async host=>{assert(['source.fixture.test','cdn.fixture.test'].includes(host));resolved.push(host);return[{address:'127.0.0.1',family:4}]});
try{
 await test('cross-origin public CDN download validates each hop and records actual routes',async()=>{
  const r=await provider.download({url:origin+'/cdn'});assert.deepEqual(Buffer.from(r.bytes),image);assert.deepEqual(resolved,['source.fixture.test','cdn.fixture.test']);
  assert.deepEqual(r.network,[{origin,route:'direct',statusCode:302},{origin:`http://cdn.fixture.test:${cdnPort}`,route:'direct',statusCode:200}]);
 });
 await test('private, credentialed and non-HTTP redirects never contact the target',async()=>{
  const before=hits;for(const name of ['private','credentials','scheme'])await assert.rejects(provider.download({url:origin+'/'+name}),{code:name==='scheme'?'WEB_INVALID_URL':'WEB_BLOCKED_URL'});assert.equal(hits,before);
 });
 await test('redirect loops remain bounded',()=>assert.rejects(provider.download({url:origin+'/loop'}),{code:'WEB_REDIRECT_BLOCKED'}));
 await test('HTTPS downgrade is rejected before its next request',async()=>{
  const p=new HttpFetchProvider(limits);let calls=0,closed=0;
  p.requestOnce=async()=>{calls++;return{response:new Response(null,{status:302,headers:{location:'http://public.example/image'}}),network:{origin:'https://public.example',route:'direct'},close:async()=>{closed++}}};
  await assert.rejects(p.download({url:'https://public.example/image'}),{code:'WEB_REDIRECT_BLOCKED'});assert.equal(calls,1);assert.equal(closed,1);
 });
 await test('mixed public/private DNS answers are rejected as a whole',()=>assert.rejects(resolvePublicAddresses('public.example',new AbortController().signal,async()=>[{address:'1.1.1.1',family:4},{address:'127.0.0.1',family:4}]),{code:'WEB_BLOCKED_URL'}));
 await test('nested DNS cause becomes a useful error code without exposing arbitrary error text',async()=>{
  const p=new HttpFetchProvider(limits,async()=>{throw new TypeError('secret token=DO_NOT_LOG',{cause:Object.assign(new Error('another secret'),{code:'ENOTFOUND'})})});
  await assert.rejects(p.download({url:'https://public.example/image?token=DO_NOT_LOG'}),e=>e.code==='WEB_PROVIDER_ERROR'&&/ENOTFOUND/.test(e.message)&&/via direct/.test(e.message)&&!e.message.includes('DO_NOT_LOG')&&!e.message.includes('another secret'));
 });
 await test('failed authenticated proxy is diagnosed without credentials or silent direct fallback',async()=>{
  const sink=http.createServer();const port=await listen(sink);await close(sink);
  const proxy=`http://proxy-user:DO_NOT_LOG@127.0.0.1:${port}`;
  const dispose=await transport.installProxyFromEnvironment({get:key=>key==='HTTP_PROXY'||key==='HTTPS_PROXY'?{value:proxy,source:'fixture'}:undefined},()=>{});
  const before=hits;
  try{await assert.rejects(provider.download({url:origin+'/cdn'}),e=>e.code==='WEB_PROVIDER_ERROR'&&/via proxy http:\/\/127.0.0.1:/.test(e.message)&&/ECONNREFUSED/.test(e.message)&&!e.message.includes('DO_NOT_LOG')&&!e.message.includes('proxy-user'));assert.equal(hits,before)}finally{await dispose()}
 });
}finally{await close(site);await close(cdn)}
if(process.argv[3])fs.writeFileSync(process.argv[3],JSON.stringify({ok:true,results},null,2));
