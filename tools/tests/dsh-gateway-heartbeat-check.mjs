/** Exercise the exact prepared gateway over real loopback WebSockets.
 * node tools/tests/dsh-gateway-heartbeat-check.mjs <prepared-runtime-root>
 */
import assert from 'node:assert/strict'
import path from 'node:path'
import {createRequire} from 'node:module'
import {pathToFileURL} from 'node:url'
import {createServer} from 'node:http'
import {once} from 'node:events'

assert(process.argv[2], 'Pass the exact prepared runtime root')
const runtime=path.resolve(process.argv[2]),require=createRequire(path.join(runtime,'package.json'))
const load=async specifier=>import(pathToFileURL(require.resolve(specifier)))
const {Context}=await load('@deepseek-ai/cordis')
const {default:WebSocket}=await load('ws')
const {RemoteStreamMuxServer}=await import(pathToFileURL(path.join(runtime,'node_modules/@deepseek-ai/dsh-api-gateway/lib/types/stream-server.js')))
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms)),period=40

async function fixture(autoPong,body){
 const root=new Context(),fiber=root.plugin(()=>{});await fiber
 const peer={id:'heartbeat-fixture',ctx:fiber.ctx,principal:{kind:'owner'},interactions:'answer',
  signal:new AbortController().signal,dispose:()=>fiber.dispose()}
 const mux=new RemoteStreamMuxServer(async function*(_endpoint,_payload,_uplink,_peer,control){
  while(!control.signal.aborted){await pause(5);yield 'flowing'}
 },error=>({code:'internal',message:String(error),details:{}}),period,262144)
 const http=createServer();http.on('upgrade',(request,socket,head)=>mux.handleUpgrade(request,socket,head,peer))
 await new Promise(resolve=>http.listen(0,'127.0.0.1',resolve))
 const client=new WebSocket('ws://127.0.0.1:'+http.address().port,{autoPong})
 await once(client,'open');const server=[...mux.server.clients][0]
 try{await body(client,server)}finally{
  client.terminate();await mux.close();await new Promise(resolve=>http.close(resolve));await fiber.dispose()
 }
}
async function closes(client){
 let timer
 try{await Promise.race([once(client,'close'),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Unresponsive peer was retained')),period*12)})])}
 finally{clearTimeout(timer)}
}

await fixture(false,async(client,server)=>{
 let buffered=100000,pings=0,complete
 Object.defineProperty(server,'bufferedAmount',{configurable:true,get:()=>buffered})
 server.ping=(_data,_mask,callback)=>{pings++;complete=callback}
 // Model a single large frame still draining, so neither its write callback
 // nor the Ping queued behind it has completed. No fabricated Pong/inbound
 // message or completed application write can keep this connection alive.
 const draining=setInterval(()=>{buffered-=100},period/2)
 try{
  await pause(period*8)
  assert.equal(client.readyState,WebSocket.OPEN,'a draining frame is transport progress, not a dead peer')
  assert.equal(pings,1,'one pending Ping must not grow into a queue of heartbeats')
 }finally{clearInterval(draining)}
 await closes(client)
 complete?.(new Error('closed while queued'))
})
await fixture(true,async(client)=>{await pause(period*8);assert.equal(client.readyState,WebSocket.OPEN)})
await fixture(false,async(client)=>{await closes(client)})
await fixture(false,async(client)=>{
 client.send(JSON.stringify({type:'open',streamId:'flowing',endpoint:'fixture/follow',payload:{}}))
 let items=0;client.on('message',()=>items++)
 await closes(client)
 assert(items>0,'immediate writes alone must not manufacture peer liveness')
})
console.log('gateway heartbeat: progressing backpressure, single queued Ping, real stalls, healthy Pong and immediate-write counterexample passed')
