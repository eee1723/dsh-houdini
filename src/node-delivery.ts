/** Node deliveries are references in ordinary DSH execution results, never a second ledger. */
import type {Context} from '@deepseek-ai/cordis'
import type {Agent} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-agent-preset-registry'
import type {} from '@deepseek-ai/dsh-session-query'
import {randomUUID} from 'node:crypto'
import {executionCall,executionResult,isHoudiniTool} from './dsh-adapter.js'
import type {SessionEvent} from './execution-history.js'
import type {ExecResult} from './bridge.js'
import {HoudiniToolRuntime,type HoudiniConnection} from './tool-runtime.js'
import {nodeDeliveryRows} from './node-delivery-record.js'

export {NODE_DELIVERY_KIND} from './node-delivery-record.js'
const ID=/^[0-9a-f]{32}$/
const object=(value:unknown):Record<string,any>|undefined =>
  value!==null&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,any>:undefined

/** The failed operation owns the useful cause; a Python stack belongs in diagnostics. */
function navigationFailure(result:ExecResult):Error {
  const failed=Array.isArray(result.verbs)
    ?result.verbs.map(object).find(verb=>verb?.ok===false&&typeof verb.error==='string'&&verb.error.trim()):undefined
  return new Error(failed?.error||result.error||'Houdini 未完成节点定位，请重试。')
}

export interface NodeDeliveryReference {
  id:string
  path:string
  label:string
  role:'control'|'output'|'node'
  type:string
  context?:string
  description?:string
}
export interface NodeDeliveryCoordinates {sessionId:string;eventSeq:number;index:number;callId?:string}
export interface RecordedNodeDelivery {
  reference:NodeDeliveryReference
  executorId:string
  hipPath:string
}

/** Only event coordinates come from the browser; the original result owns every target fact. */
export function nodeDeliveryCoordinates(input:unknown):NodeDeliveryCoordinates {
  const data=object(input)
  if(!data||Object.keys(data).some(key=>!['sessionId','eventSeq','index','callId'].includes(key))
    ||typeof data.sessionId!=='string'||!data.sessionId.trim()||data.sessionId.length>256
    ||!Number.isSafeInteger(data.eventSeq)||data.eventSeq<1
    ||!Number.isSafeInteger(data.index)||data.index<0
    ||(data.callId!==undefined&&(typeof data.callId!=='string'||!data.callId.trim()||data.callId.length>256)))
    throw new Error('Expected the selected sessionId and original node delivery eventSeq/index/callId coordinates')
  return data as unknown as NodeDeliveryCoordinates
}

/** Extract the same canonical execution facts for native and nested DSH calls. */
export function recordedNodeDelivery(event:SessionEvent,coordinates:NodeDeliveryCoordinates):RecordedNodeDelivery {
  const result=executionResult(event)
  const value=object(result?.value),execution=object(value?.execution)
  const operations=object(object(value?.outcome)?.operations)
  if(!result||result.isError||value?.ok!==true||Number(operations?.failed)>0
    ||(Array.isArray(value.verbs)&&value.verbs.some((verb:unknown)=>object(verb)?.ok===false)))
    throw new Error('Node delivery requires a successful original batch without failed operations')
  if(coordinates.callId!==undefined&&result.callId!==coordinates.callId)
    throw new Error('Node delivery call does not match the original event')
  if(execution?.owner_session!==coordinates.sessionId)
    throw new Error('Node delivery belongs to another task; open its original task')
  if(typeof execution.executor_id!=='string'||!ID.test(execution.executor_id)
    ||typeof execution.runtime_id!=='string'||!ID.test(execution.runtime_id)
    ||typeof execution.hip_path!=='string'||!execution.hip_path.trim()||execution.hip_is_new===true)
    throw new Error('Node delivery has no saved HIP and executor identity')
  const row=object(nodeDeliveryRows(value)[coordinates.index])
  if(!row||typeof row.id!=='string'||!ID.test(row.id)||typeof row.path!=='string'||!row.path.startsWith('/')
    ||typeof row.label!=='string'||!row.label.trim()||!['control','output','node'].includes(row.role)
    ||typeof row.type!=='string'||!row.type.trim()
    ||(row.description!==undefined&&(typeof row.description!=='string'||!row.description.trim()||row.description.length>200))
    ||(row.context!==undefined&&(typeof row.context!=='string'||!row.context.trim())))
    throw new Error('Node delivery not found at these original result coordinates')
  return {reference:row as unknown as NodeDeliveryReference,executorId:execution.executor_id,hipPath:execution.hip_path}
}

export interface HoudiniNodeDeliveryService {
  open(delivery:RecordedNodeDelivery,agent:Agent,signal:AbortSignal):Promise<unknown>
}
declare module '@deepseek-ai/cordis' {
  interface Context {houdiniNodeDelivery:HoudiniNodeDeliveryService}
}

/** Agent-local routing reuses the tool connection and its lifetime, for single and shared Hosts. */
export function installNodeDeliveryNavigation(ctx:Context,connection:HoudiniConnection):void {
  const runtime=new HoudiniToolRuntime(ctx,connection),lifetime=new AbortController()
  ctx.effect(()=>()=>lifetime.abort(new Error('Houdini node navigation service was unloaded')))
  ctx.provide('houdiniNodeDelivery',{
    async open(delivery,agent,signal) {
      if(agent.id!==agent.session.id)throw new Error('Node navigation requires the exact selected task')
      signal=AbortSignal.any([signal,lifetime.signal])
      signal.throwIfAborted()
      const {bridge,owner}=await runtime.target({agent,callId:'node-navigation-'+randomUUID(),signal})
      if(bridge.targetExecutorId!==delivery.executorId)
        throw new Error('Node delivery belongs to another Houdini executor; no navigation request sent')
      // UUID is the only locator. Historical labels, paths and node types never authorize a target.
      const result=await bridge.navigateNode({id:delivery.reference.id},delivery.hipPath,owner,signal)
      if(result.ok!==true||Number(object(object(result.outcome)?.operations)?.failed)>0
        ||(Array.isArray(result.verbs)&&result.verbs.some(verb=>object(verb)?.ok===false)))
        throw navigationFailure(result)
      return result.result
    },
  })
}

/** Authenticated root UI entry; the selected Agent scope supplies its own existing connection. */
export async function openDeliveredNode(ctx:Context,input:unknown,signal:AbortSignal):Promise<unknown> {
  const coordinates=nodeDeliveryCoordinates(input)
  signal.throwIfAborted()
  const agents=ctx.get('agents'),query=ctx.get('sessionQuery')
  if(!agents||!query)throw new Error('DSH task/history services unavailable; no navigation request sent')
  const agent=agents.get(coordinates.sessionId as Parameters<typeof agents.get>[0])
  if(!agent||agent.id!==coordinates.sessionId||agent.session.id!==coordinates.sessionId)
    throw new Error('Open the original node delivery task before navigating')
  const presets=ctx.get('agentPresets')
  const navigation=presets ? presets.serviceFor(agent,'houdiniNodeDelivery') : agent.ctx.get('houdiniNodeDelivery')
  if(!navigation)throw new Error('The selected task has no Houdini navigation service')
  const read=await query.readEvent({sessionId:coordinates.sessionId as Parameters<typeof query.readEvent>[0]['sessionId'],
    seq:coordinates.eventSeq as Parameters<typeof query.readEvent>[0]['seq'],before:0,after:0},signal)
  signal.throwIfAborted()
  if(read.session.id!==coordinates.sessionId||read.target.seq!==coordinates.eventSeq)
    throw new Error('DSH history did not return the requested task/event')
  const delivery=recordedNodeDelivery(read.target,coordinates)
  if(read.target.type==='tool/result') {
    const callId=executionResult(read.target)!.callId
    const call=agent.session.snapshotEvents().map(event=>executionCall(event)).find(item=>item?.callId===callId)
    if(!call||!isHoudiniTool(call.name))throw new Error('Node delivery is not a recorded Houdini tool result')
  }
  return navigation.open(delivery,agent,signal)
}
