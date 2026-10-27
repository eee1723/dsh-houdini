/** SiWC-specific HTTP policy around public SDK encoders/decoder. The native
 * pi client factory exposes no log/tenant options, so it cannot isolate a
 * subscription request from OPENAI_* environment settings on its own. */
import OpenAI from 'openai'
import type {ResponseCreateParamsStreaming} from 'openai/resources/responses/responses'
import type {AssistantMessage,Model,SimpleStreamOptions,TranscriptContext} from '@earendil-works/pi-ai'
import type {OpenAIResponsesOptions} from '@earendil-works/pi-ai/api/openai-responses'
import {clampThinkingLevel} from '@earendil-works/pi-ai/models'
import {convertResponsesMessages,convertResponsesTools,processResponsesStream} from '@earendil-works/pi-ai/api/openai-responses-shared'
import {resolveTranscriptTools} from '@earendil-works/pi-ai/utils/transcript'
import {createAssistantMessageEventStream} from '@earendil-works/pi-ai/utils/event-stream'
import {attributionHeaders} from '@deepseek-ai/dsh-llm'
import type {Fetcher} from './types.js'

export function siwcPayload(raw:unknown){
  if(!raw||typeof raw!=='object')throw Error('Invalid SiWC request')
  const payload={...raw as Record<string,any>}
  for(const name of ['background','conversation','max_output_tokens','max_tool_calls','metadata','moderation','multi_agent','prompt',
    'prompt_cache_retention','prompt_cache_options','safety_identifier','temperature','top_logprobs','top_p','truncation','user','previous_response_id'])delete payload[name]
  payload.store=false;payload.stream=true
  if(!Array.isArray(payload.input))throw Error('SiWC requires complete array history')
  payload.input=payload.input.map((item:any)=>item?.role==='system'?{...item,role:'developer'}:item)
  if(Array.isArray(payload.tools)&&payload.tools.length){
    if(payload.tools.some((tool:any)=>!['function','custom','namespace'].includes(tool.type)))throw Error('SiWC does not support the requested hosted tool')
    payload.input=[{type:'additional_tools',tools:payload.tools},...payload.input];delete payload.tools
  }
  return payload
}
export function subscriptionStream(model:Model<'openai-responses'>,context:TranscriptContext,options:SimpleStreamOptions|OpenAIResponsesOptions|undefined,fetcher:Fetcher){
  const stream=createAssistantMessageEventStream()
  const output:AssistantMessage={role:'assistant',content:[],api:'openai-responses',provider:'openai',model:model.id,timestamp:Date.now(),
    usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'pending'}
  void (async()=>{
    try{
      if(!options?.apiKey)throw Error('Missing authorized subscription credential')
      // Explicit values override both ordinary Platform tenant defaults and
      // OPENAI_CUSTOM_HEADERS. Do not mutate process.env or another adapter.
      const headers=new Headers()
      for(const [key,value] of Object.entries({...model.headers,...options.headers,...attributionHeaders()}))if(typeof value==='string')headers.set(key,value)
      headers.delete('authorization');headers.delete('openai-organization');headers.delete('openai-project')
      const headerValues:Record<string,string>={};headers.forEach((value,key)=>{headerValues[key]=value})
      const client=new OpenAI({apiKey:options.apiKey,baseURL:'https://api.openai.com/v1',organization:null,project:null,logLevel:'warn',maxRetries:0,
        fetch:fetcher,fetchOptions:{redirect:'error'},defaultHeaders:{...headerValues,authorization:'Bearer '+options.apiKey,'openai-organization':null,'openai-project':null}})
      const toolOptions={supportsStrictMode:true,supportsOpenAIGrammarTools:false}
      const input=convertResponsesMessages(model,context,new Set(['openai']),{supportsMidConvoSystemMessages:true,supportsAdditionalTools:true,
        supportsToolSearch:false,toolOptions})
      // In the exact host SDK, initial declarations are requestTools; the
      // message converter retains subsequent additive transcript updates.
      const {requestTools}=resolveTranscriptTools(context.messages,true)
      const requested='reasoning' in options?options.reasoning:'reasoningEffort' in options?options.reasoningEffort:undefined
      const effort=requested?clampThinkingLevel(model,requested):undefined
      const params=siwcPayload({model:model.id,input,store:false,stream:true,
        ...requestTools.length?{tools:convertResponsesTools(requestTools,toolOptions)}:{},
        ...model.reasoning&&effort&&effort!=='off'?{reasoning:{effort:model.thinkingLevelMap?.[effort]??effort,summary:'auto'},include:['reasoning.encrypted_content']}: {}})
      const result=await client.responses.create(params as unknown as ResponseCreateParamsStreaming,{signal:options.signal,headers:{accept:'text/event-stream'}}).withResponse()
      const contentType=result.response.headers.get('content-type')?.split(';')[0]?.trim().toLowerCase()
      if(contentType&&contentType!=='text/event-stream')throw Error('Invalid subscription stream')
      let completed=false
      stream.push({type:'start',partial:output})
      await processResponsesStream(result.data,output,stream,model,{onProviderStreamEvent:event=>{
        if(event&&typeof event==='object'&&'type' in event&&event.type==='response.completed')completed=true
      }})
      options.signal?.throwIfAborted()
      if(!completed)throw Error('SiWC stream did not reach response.completed')
      if(output.stopReason==='pending'||output.stopReason==='error'||output.stopReason==='aborted')throw Error('Subscription response did not complete')
      stream.push({type:'done',reason:output.stopReason as 'stop'|'length'|'toolUse',message:output})
    }catch(error){
      output.stopReason=options?.signal?.aborted?'aborted':'error'
      // SDK/HTTP bodies can contain submitted context. Never forward them.
      const status=error instanceof OpenAI.APIError?error.status:undefined
      output.errorMessage=output.stopReason==='aborted'?'ChatGPT request cancelled':status===401?'ChatGPT authorization expired; reconnect this account':
        status===403?'This ChatGPT account cannot use the selected model':status===429?'ChatGPT subscription usage limit reached; review ChatGPT usage':
        'ChatGPT response failed or ended before response.completed'
      stream.push({type:'error',reason:output.stopReason,error:output})
    }finally{stream.end()}
  })()
  return stream
}
