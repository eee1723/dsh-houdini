// Owned loopback OpenAI HTTP fixture for the real Qt/DSH/HOM acceptance.
// Scripted answers test transport and UI, never model quality or semantic vision.
import fs from 'node:fs'
import http from 'node:http'
import {createHash} from 'node:crypto'
const config=JSON.parse(fs.readFileSync(process.env.DSH_SOURCE_GUI_CONFIG,'utf8'))
export const inject=['agents']
const write=(file,value)=>{fs.writeFileSync(file+'.tmp',JSON.stringify(value,null,2));fs.renameSync(file+'.tmp',file)}
export function apply(ctx) {
  const requests=[],forwarded=[],lost=[]
  const report=()=>write(config.providerEvidence,{scripted:true,semanticVision:'unverified',requests,forwarded,lost})
  ctx.on('agent/created',({agent})=>agent.ctx.tools.presentAs('both'))
  const proxy=http.createServer(async(req,res)=>{
    try {
      const chunks=[];for await(const chunk of req)chunks.push(chunk)
      const data=Buffer.concat(chunks),body=data.length?JSON.parse(data):{}
      const row={method:req.method,path:req.url,owner:body.owner_session,call:body.owner_call,request:body.request_ref}
      forwarded.push(row);report()
      const response=await fetch(config.actualBridge+req.url,{method:req.method,
        headers:Object.fromEntries(Object.entries(req.headers).filter(([name])=>!['host','connection','content-length'].includes(name))),
        ...(req.method==='POST'?{body:data}:{})})
      const bytes=Buffer.from(await response.arrayBuffer())
      if(req.url==='/exec'&&body.code?.includes('__gui_unknown_transport__')&&!lost.length) {
        const original=JSON.parse(bytes);lost.push({request:body.request_ref,call:body.owner_call,
          applied:original.ok===true,execution:original.execution});report();res.destroy();return
      }
      res.writeHead(response.status,{'content-type':response.headers.get('content-type')||'application/json'});res.end(bytes)
    }catch(error){res.writeHead(500);res.end(JSON.stringify({error:String(error)}))}
  })
  proxy.listen(config.bridgeProxyPort,'127.0.0.1')
  const provider=http.createServer(async(req,res)=>{
    try {
      if(req.url==='/v1/models'){res.setHeader('content-type','application/json');res.end(JSON.stringify({data:[{id:config.model}]}));return}
      if(req.url!=='/v1/chat/completions')throw Error('Unexpected fixture route '+req.url)
      let raw='';for await(const chunk of req)raw+=chunk
      const body=JSON.parse(raw),messages=body.messages??[]
      const text=content=>typeof content==='string'?content:(content??[]).filter(block=>block.type==='text').map(block=>block.text).join('\n')
      const user=messages.filter(message=>message.role==='user').map(message=>text(message.content)).findLast(value=>value.includes('GUI_CASE_'))||''
      const stage=/GUI_CASE_(\w+)/.exec(user)?.[1]||'TITLE'
      const tool=id=>messages.find(message=>message.role==='tool'&&message.tool_call_id===id)
      const imageParts=messages.flatMap(message=>Array.isArray(message.content)?message.content:[]).filter(block=>block.type==='image_url')
      const imageEvidence=imageParts.map(part=>{
        const match=/^data:([^;]+);base64,(.+)$/.exec(part.image_url?.url||'')
        if(!match)return{transport:'url',url:part.image_url?.url}
        const bytes=Buffer.from(match[2],'base64')
        const png=bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))
        let dimensions=png?{width:bytes.readUInt32BE(16),height:bytes.readUInt32BE(20)}:{}
        if(bytes.toString('ascii',0,4)==='RIFF'&&bytes.toString('ascii',8,12)==='WEBP') {
          for(let offset=12;offset+8<=bytes.length;){
            const kind=bytes.toString('ascii',offset,offset+4),length=bytes.readUInt32LE(offset+4),start=offset+8
            if(kind==='VP8X'&&length>=10)dimensions={width:1+bytes.readUIntLE(start+4,3),height:1+bytes.readUIntLE(start+7,3)}
            if(kind==='VP8 '&&length>=10)dimensions={width:bytes.readUInt16LE(start+6)&0x3fff,height:bytes.readUInt16LE(start+8)&0x3fff}
            if(kind==='VP8L'&&length>=5){const packed=bytes.readUInt32LE(start+1);dimensions={width:1+(packed&0x3fff),height:1+((packed>>>14)&0x3fff)}}
            offset=start+length+(length&1)
          }
        }
        return{transport:'base64',mediaType:match[1],bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),
          ...dimensions}
      })
      const row={ordinal:requests.length,stage,model:body.model,stream:body.stream===true,
        authorizationMatched:req.headers.authorization==='Bearer '+config.fixtureKey,messages,
        imageCount:imageParts.length,imageEvidence}
      requests.push(row);report()
      res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-cache'})
      const id='qt-http-'+requests.length
      const send=(delta,finish_reason=null)=>res.write('data: '+JSON.stringify({id,object:'chat.completion.chunk',created:1,model:config.model,
        choices:[{index:0,delta,finish_reason}]})+'\n\n')
      const finish=()=>{send({},'stop');res.end('data: [DONE]\n\n')}
      const emitTool=(callId,name,args)=>{send({role:'assistant'});send({tool_calls:[{index:0,id:callId,type:'function',function:{name,arguments:JSON.stringify(args)}}]});send({},'tool_calls');res.end('data: [DONE]\n\n')}
      if(stage==='BUILD'&&!tool('qt-build')){emitTool('qt-build','houdini_exec',{code:config.buildCode});return}
      if(stage==='DELIVER'&&!tool('qt-deliver')){emitTool('qt-deliver','run_code',{code:'return await tools.houdini_exec({code:'+JSON.stringify(config.deliveryCode)+'})',description:'Publish wrapped node entries'});return}
      if(stage==='NAVCHECK'&&!tool('qt-navcheck')){emitTool('qt-navcheck','houdini_inspect',{code:config.navigationCode});return}
      if(stage==='IMAGE'&&!tool('qt-image')){emitTool('qt-image','houdini_exec',{code:config.imageCode});return}
      if(stage==='UNKNOWN'&&!tool('qt-unknown')){emitTool('qt-unknown','houdini_exec',{code:config.unknownCode});return}
      if(stage==='UNKNOWN'&&!tool('qt-recover')) {
        const source=text(tool('qt-unknown')?.content),reference=/"request_ref"\s*:\s*"([a-f0-9.]+)"/.exec(source)?.[1]
        if(!reference)throw Error('Unknown operation must have an original receipt to recover')
        emitTool('qt-recover','houdini_request',{request_ref:reference});return
      }
      if(stage==='AFTER'&&!tool('qt-after')){emitTool('qt-after','houdini_inspect',{code:config.inspectCode});return}
      send({role:'assistant',content:'GUI_'+stage+'_STREAM '})
      if(stage==='STOP') {
        const timer=setInterval(()=>send({content:'working '}),200)
        const end=setTimeout(()=>{clearInterval(timer);finish()},30000)
        res.on('close',()=>{clearInterval(timer);clearTimeout(end);row.closedBeforeFinish=!res.writableEnded;report()});return
      }
      const delay=stage==='RECONNECT'?3500:300
      await new Promise(resolve=>setTimeout(resolve,delay))
      send({content:'GUI_'+stage+'_DONE'});finish()
    }catch(error){requests.push({failure:String(error.stack||error)});report();if(!res.headersSent)res.writeHead(500);res.end()}
  })
  provider.listen(config.providerPort,'127.0.0.1')
  ctx.effect(()=>()=>{provider.closeAllConnections();provider.close();proxy.closeAllConnections();proxy.close()})
}
