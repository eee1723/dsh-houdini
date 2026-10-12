/** Native Windows system routing, with isolated settings snapshots and local servers; no registry edits. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import os from 'node:os';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const cache=path.resolve(process.argv[2]);
const require=createRequire(path.join(cache,'node_modules/@deepseek-ai/dsh/lib/bin.js'));
const load=async name=>import(pathToFileURL(require.resolve(name)));
const transport=await load('@deepseek-ai/dsh-http-proxy');
const {createWindowsProxySource,windowsBypasses,windowsProxyFor}=await import(pathToFileURL(path.join(cache,'node_modules/@deepseek-ai/dsh-http-proxy/lib/types/windows.js')));
const {readWindowsProxySettings}=await import(pathToFileURL(path.join(cache,'node_modules/@deepseek-ai/dsh-http-proxy/lib/types/windows-native.js')));
const {fetch:undiciFetch}=require('undici');
const results=[];
const test=async(name,body)=>{await body();results.push({name,ok:true});console.log('PASS',name)};
const listen=server=>new Promise(resolve=>server.listen(0,'0.0.0.0',()=>resolve(server.address().port)));
const stop=server=>new Promise(resolve=>{server.closeAllConnections();server.close(resolve)});
const host=Object.values(os.networkInterfaces()).flat().find(v=>v&&v.family==='IPv4'&&!v.internal&&!v.address.startsWith('198.18.'))?.address;
assert(host,'a local non-loopback interface is needed for same-origin route switching');
const hits={direct:0,a:0,b:0};
let holdHit;
const origin=http.createServer((_q,r)=>{hits.direct++;r.end('DIRECT')});
const a=http.createServer((q,r)=>{hits.a++;r.writeHead(200,{'content-type':'text/html'});
 if(q.url.includes('/hold')){holdHit?.();setTimeout(()=>r.end('PROXY-A'),250)}else r.end('PROXY-A')});
const b=http.createServer((_q,r)=>{hits.b++;r.end('PROXY-B')});
const [port,pa,pb]=await Promise.all([listen(origin),listen(a),listen(b)]);
const url=new URL(`http://${host}:${port}/probe`),proxyA=`http://127.0.0.1:${pa}`,proxyB=`http://127.0.0.1:${pb}`;
let settings={autoDetect:false,autoConfigUrl:'',proxy:'',bypass:''};
const source=createWindowsProxySource(()=>({...settings}));
const dispose=await transport.installProxyFromEnvironment({get:()=>undefined},()=>{}, {systemProxy:source});
const get=async(target=url,options={})=>{const r=await fetch(target,{signal:AbortSignal.timeout(6000),...options});return r.text()};
const pac=http.createServer((q,r)=>{
 r.writeHead(200,{'content-type':'application/x-ns-proxy-autoconfig'});
 if(q.url==='/invalid')r.end('not a valid PAC script');
 else if(q.url.startsWith('/slow'))setTimeout(()=>r.end('function FindProxyForURL(url, host) { return "DIRECT"; }'),350);
 else r.end(`function FindProxyForURL(url, host) { if(url.indexOf('/direct')>=0) return 'DIRECT'; return 'PROXY 127.0.0.1:${pa}'; }`);
});const pacPort=await listen(pac);
try{
 await test('reads actual current Windows configuration without copying addresses into the environment',async()=>{
  const native=readWindowsProxySettings();assert.equal(typeof native.autoDetect,'boolean');assert.equal(typeof native.proxy,'string');
  assert.equal(transport.proxyConfiguration().source,'windows');assert.deepEqual(transport.proxyEnvironmentForChild(),{});
 });
 await test('same process and destination follow direct, proxy A, proxy B, then direct',async()=>{
  assert.equal(await get(),'DIRECT');settings.proxy=proxyA;assert.equal(await get(),'PROXY-A');
  settings.proxy=proxyB;assert.equal(await get(),'PROXY-B');settings.proxy='';assert.equal(await get(),'DIRECT');
 });
 await test('captured route does not drift when the OS setting changes before dispatch',async()=>{
  settings.proxy=proxyA;const frozen=await transport.proxyRouteFor(url);assert(frozen.proxied);
  settings.proxy=proxyB;const response=await undiciFetch(url,{dispatcher:frozen.dispatcher});assert.equal(await response.text(),'PROXY-A');assert.equal(await get(),'PROXY-B');
 });
 await test('Windows bypass patterns and protocol-specific proxy values are respected',async()=>{
  settings={...settings,proxy:proxyA,bypass:host};assert.equal(await get(),'DIRECT');
  assert(windowsBypasses('<local>',new URL('http://intranet/')));
  assert(windowsBypasses('*.example.test;10.*',new URL('https://child.example.test')));
  assert(!windowsBypasses('*.example.test',new URL('https://example.test.attacker.test')));
  assert.equal(windowsProxyFor(new URL('https://example.test'),'http=127.0.0.1:1;https=127.0.0.1:2',''),'http://127.0.0.1:2');
  assert.throws(()=>windowsProxyFor(url,'socks=127.0.0.1:1',''),/SOCKS/);
 });
 await test('loopback stays direct while a system proxy is active',async()=>{
  settings={...settings,proxy:proxyA,bypass:''};assert.equal(await get(new URL(`http://127.0.0.1:${port}/`)),'DIRECT');
  assert.equal((await transport.proxyRouteFor(new URL(`http://127.0.0.1:${port}/`))).proxied,false);
 });
 await test('a double-slash URL path cannot masquerade as a different destination for proxy routing',async()=>{
  settings.proxy=proxyA;
  assert.equal(await get(new URL(`http://${host}:${port}//127.0.0.1/looks-local`)),'PROXY-A');
 });
 await test('a stopped explicit system proxy fails without sending the request directly',async()=>{
  settings.proxy='http://127.0.0.1:1';const before=hits.direct;
  await assert.rejects(get());assert.equal(hits.direct,before);
 });
 await test('explicit environment configuration overrides system routing and disposal restores it',async()=>{
  settings.proxy=proxyB;
  const nested=await transport.installProxyFromEnvironment({get:n=>n==='HTTPS_PROXY'||n==='HTTP_PROXY'?{value:proxyA}:undefined},()=>{});
  try{assert.equal(await get(),'PROXY-A');assert.equal(transport.proxyConfiguration().source,'environment')}
  finally{await nested()}
  assert.equal(await get(),'PROXY-B');
  const direct=await transport.installProxyFromEnvironment({get:n=>n==='NO_PROXY'?{value:'*'}:undefined},()=>{});
  try{assert.equal(await get(),'DIRECT')}finally{await direct()}
  assert.equal(await get(),'PROXY-B');
 });
 await test('web fetch and binary download consume the same captured system route',async()=>{
  settings.proxy=proxyA;
  const {HttpFetchProvider}=await load('@deepseek-ai/dsh-web-fetch-http');
  const provider=new HttpFetchProvider({maxResponseBytes:10000,maxBodyChars:10000,timeoutMs:3000,maxRedirects:2,userAgent:'test'});
  const target='http://unresolvable-system-test.example/probe';
  assert.match((await provider.fetch({url:target})).body.content,/PROXY-A/);
  assert.equal(Buffer.from((await provider.download({url:target})).bytes).toString(),'PROXY-A');
  await assert.rejects(provider.fetch({url:`http://127.0.0.1:${port}/`}),{code:'WEB_BLOCKED_URL'});
 });
 await test('disposing an override restores route facts before old responses finish draining',async()=>{
  settings.proxy=proxyB;
  const nested=await transport.installProxyFromEnvironment({get:n=>n==='HTTP_PROXY'?{value:proxyA}:undefined},()=>{});
  const received=new Promise(resolve=>{holdHit=resolve});
  const pending=get(new URL(`http://${host}:${port}/hold`));await received;
  const closing=nested();
  const restored=await transport.proxyRouteFor(url);assert(restored.proxied);assert.equal(restored.proxy,proxyB);
  assert.equal(await get(),'PROXY-B');assert.equal(await pending,'PROXY-A');await closing;
 });
 await test('native Windows PAC chooses direct or proxy for each full URL',async()=>{
  settings={autoDetect:false,autoConfigUrl:`http://127.0.0.1:${pacPort}/route.pac`,proxy:'',bypass:''};
  assert.equal(await get(new URL(`http://${host}:${port}/direct`)),'DIRECT');
  assert.equal(await get(),'PROXY-A');
 });
 await test('invalid PAC is reported without falling back to direct',async()=>{
  settings.autoConfigUrl=`http://127.0.0.1:${pacPort}/invalid`;
  const before=hits.direct;await assert.rejects(transport.proxyRouteFor(url),/PAC\/WPAD/);assert.equal(hits.direct,before);
 });
 await test('cancelled PAC lookup settles promptly and sends no model HTTP request',async()=>{
  settings.autoConfigUrl=`http://127.0.0.1:${pacPort}/slow-route`;
  const before=hits.direct,start=Date.now();
  await assert.rejects(transport.proxyRouteFor(url,AbortSignal.timeout(40)),{name:'TimeoutError'});
  assert(Date.now()-start<250);
  settings.autoConfigUrl=`http://127.0.0.1:${pacPort}/slow-fetch`;
  await assert.rejects(get(url,{signal:AbortSignal.timeout(40)}),{name:'TimeoutError'});
  await new Promise(resolve=>setTimeout(resolve,850));assert.equal(hits.direct,before);
 });
}finally{await dispose();await Promise.all([stop(origin),stop(a),stop(b),stop(pac)])}
if(process.argv[3])fs.writeFileSync(process.argv[3],JSON.stringify({ok:true,results},null,2));
