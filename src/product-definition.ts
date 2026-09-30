/** Session-local product intent, projected from immutable Host tool receipts.
 * Definitions describe obligations, never certify geometry or grant permission.
 */
import {createHash} from 'node:crypto'
import type {Context} from '@deepseek-ai/cordis'
import {defineTool} from '@deepseek-ai/dsh-tools'
import {taskSources} from './task-sources.js'
import {projectDeliveryAudit} from './delivery-audit.js'
import {executionHistory,type ExecutionHistory} from './execution-history.js'

type Event = {type:string;seq?:number;data?:any}
type Binding = {verb:'geo_check_interfaces'|'test_controls';contract_sha256:string;check_id:string;case_id?:string}
type Requirement = {id:string;kind:'part'|'relation'|'control'|'dimension'|'detail'|'visual';
  description:string;subjects:string[];state:string;checks:Binding[];
  dimension?:{group:string;axis:number;expected_m:number;tolerance_m:number};
  members?:{group:string;expected_components:number};
  contact?:{source_group:string;target_group:string;max_distance:number;expected_points:number};
  control_values?:Record<string,number>;
  feature?:{family:string;purpose:string;attachment:string;controls:string[];construction:string;inspection:string}}
type Definition = {title:string;output:string;units:string;source_refs:string[];reviewed_through?:string;assumptions:string[];
  requirements:Requirement[];retired:{id:string;reason:string;source_ref:string}[]}
type Revision = {revision:number;base_revision:number;sha256:string;definition:Definition;change_reason:string;resolved_conflicts?:string[]}
type ExpectationChange = {id:string;fields:string[];revision:number;reason:string}
const sha = (value:unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex')
const hashPattern = /^[0-9a-f]{64}$/
function ordered(value:any):any {
  return Array.isArray(value)?value.map(ordered):value&&typeof value==='object'
    ?Object.fromEntries(Object.keys(value).sort().map(k=>[k,ordered(value[k])])):value
}
const kinds = ['part','relation','control','dimension','detail','visual']
const measurementGuide:Record<string,string>={
  part:'component_count on the final complete part group; a physical span or zero overlap does not count members',
  dimension:'physical_extent on the registered final group/axis with matching expected value and no looser tolerance',
  relation:'an explicit source_group/target_group interface for each required state; the measured method still does not certify arbitrary relation wording',
  control:'test_controls case with nonempty measurements; use check_id=test case id and omit case_id',
  detail:'numeric checks cannot mark detail quality measured; preserve actual construction and visual observations separately',
  visual:'numeric checks cannot mark semantic visual inspection measured; inspect the actual images',
}
const requiredText={type:'string',required:true} as const
const requiredTexts={type:'array',items:{type:'string'},required:true} as const
const requiredNumber={type:'number',required:true} as const
const requiredInteger={type:'integer',required:true} as const
const definitionSchema={type:'object',additionalProperties:false,properties:{
  title:requiredText,output:requiredText,units:requiredText,source_refs:requiredTexts,
  reviewed_through:{type:'string'},assumptions:requiredTexts,
  retired:{type:'array',required:true,items:{type:'object',additionalProperties:false,
    properties:{id:requiredText,reason:requiredText,source_ref:requiredText}}},
  requirements:{type:'array',required:true,items:{type:'object',additionalProperties:false,properties:{
    id:requiredText,kind:{type:'string',required:true,enum:['part','relation','control','dimension','detail','visual']},
    description:requiredText,subjects:requiredTexts,state:requiredText,
    checks:{type:'array',required:true,items:{type:'object',additionalProperties:false,properties:{
      verb:{type:'string',required:true,enum:['geo_check_interfaces','test_controls']},
      contract_sha256:requiredText,check_id:requiredText,case_id:{type:'string'}}}},
    dimension:{type:'object',additionalProperties:false,properties:{group:requiredText,axis:requiredInteger,expected_m:requiredNumber,tolerance_m:requiredNumber}},
    members:{type:'object',additionalProperties:false,properties:{group:requiredText,expected_components:requiredInteger}},
    contact:{type:'object',additionalProperties:false,properties:{source_group:requiredText,target_group:requiredText,max_distance:requiredNumber,expected_points:requiredInteger}},
    control_values:{type:'object',additionalProperties:true,description:'Actual named numeric control values for this required state.'},
    feature:{type:'object',additionalProperties:false,properties:{
      family:{type:'string',required:true,enum:['functional','assembly','support','edge','surface']},
      purpose:requiredText,attachment:requiredText,controls:requiredTexts,construction:requiredText,inspection:requiredText}},
  }}},
}} as const
const boundary = 'Author-declared obligations and historical measured coverage only. Missing declarations, source interpretation, visual quality and unobserved edits are not certified. No scene ownership, user authorization or whole-product acceptance is inferred.'
function text(value:unknown,label:string,max=1000):asserts value is string {
  if(typeof value!=='string'||!value.trim()||value.length>max) throw Error(`${label} must be nonempty text <= ${max} characters`)
}
function keys(value:any,allowed:string[],label:string) {
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!allowed.includes(k)))
    throw Error(`${label} supports only ${allowed.join(', ')}`)
}
function list(value:any,label:string,max:number,min=0):asserts value is any[] {
  if(!Array.isArray(value)||value.length<min||value.length>max) throw Error(`${label} needs ${min}..${max} entries`)
}
export function validateProductDefinition(value:any):Definition {
  keys(value,['title','output','units','source_refs','reviewed_through','assumptions','requirements','retired'],'definition')
  const missing:string[]=[]
  for(const key of ['title','output','units','source_refs','assumptions','requirements','retired'])
    if(value[key]===undefined) missing.push(`definition.${key}`)
  if(Array.isArray(value.requirements)) for(const [i,r] of value.requirements.entries()) {
    if(!r||typeof r!=='object'||Array.isArray(r)) continue
    for(const key of ['id','kind','description','subjects','state','checks'])
      if(r[key]===undefined) missing.push(`requirements[${i}].${key}`)
  }
  if(missing.length) throw Error(`Missing required product fields: ${missing.slice(0,24).join(', ')}${missing.length>24?` (+${missing.length-24} more)`:''}. Use state="default" only when applicable; unchecked checks=[] and no retired items retired=[] still need explicit fields. Read action="schema" for the complete shape.`)
  text(value.title,'title');text(value.output,'output',512);text(value.units,'units',200)
  if(!value.output.startsWith('/')) throw Error('output must be an explicit absolute SOP path')
  list(value.source_refs,'source_refs',64,1)
  if(value.source_refs.some((v:any)=>typeof v!=='string'||!hashPattern.test(v))) throw Error('source_refs require listed source SHA-256s')
  if(value.reviewed_through!==undefined&&(typeof value.reviewed_through!=='string'||!hashPattern.test(value.reviewed_through)))
    throw Error('reviewed_through requires a listed source SHA-256')
  list(value.assumptions,'assumptions',32);value.assumptions.forEach((v:any)=>text(v,'assumption'))
  list(value.requirements,'requirements',128,1)
  const ids=new Set<string>()
  const bindingErrors:string[]=[]
  for(const r of value.requirements) {
    keys(r,['id','kind','description','subjects','state','checks','dimension','members','contact','control_values','feature'],'requirement')
    text(r.id,'id',100);text(r.description,'description');text(r.state,'state',300)
    if(ids.has(r.id)||!kinds.includes(r.kind)) throw Error('requirements need unique ids and supported kinds')
    ids.add(r.id);list(r.subjects,'subjects',16,1);r.subjects.forEach((s:any)=>text(s,'subject',100))
    list(r.checks,'checks',8)
    if(r.members!==undefined){
      keys(r.members,['group','expected_components'],'members')
      text(r.members.group,'members group',100)
      if(r.kind!=='part'||!Number.isInteger(r.members.expected_components)||r.members.expected_components<1||r.members.expected_components>32)
        throw Error('members requires kind=part and expected_components=1..32')
    }
    if(r.contact!==undefined){
      keys(r.contact,['source_group','target_group','max_distance','expected_points'],'contact')
      text(r.contact.source_group,'contact source_group',100);text(r.contact.target_group,'contact target_group',100)
      if(r.kind!=='relation'||!Number.isFinite(r.contact.max_distance)||r.contact.max_distance<0
        ||!Number.isInteger(r.contact.expected_points)||r.contact.expected_points<1||r.contact.expected_points>512)
        throw Error('contact requires kind=relation, nonnegative SOP-local max_distance and expected_points=1..512')
    }
    if(r.dimension!==undefined){
      keys(r.dimension,['group','axis','expected_m','tolerance_m'],'dimension')
      const d=r.dimension
      if(r.kind!=='dimension'||!Number.isInteger(d.axis)||d.axis<0||d.axis>2
        ||!Number.isFinite(d.expected_m)||d.expected_m<=0||!Number.isFinite(d.tolerance_m)||d.tolerance_m<0||d.tolerance_m>=d.expected_m)
        throw Error('dimension requires a positive expected_m, valid tolerance_m and axis 0..2')
      text(d.group,'dimension group',100)
    }
    if(r.control_values!==undefined){
      if(!r.control_values||typeof r.control_values!=='object'||Array.isArray(r.control_values)
        ||Object.keys(r.control_values).length<1||Object.keys(r.control_values).length>8
        ||Object.entries(r.control_values).some(([k,v])=>!k||typeof v!=='number'||!Number.isFinite(v)))
        throw Error('control_values needs 1..8 named finite numeric expected state values')
    }
    if(r.feature!==undefined){
      const f=r.feature
      keys(f,['family','purpose','attachment','controls','construction','inspection'],'feature')
      if(r.kind!=='detail'||!['functional','assembly','support','edge','surface'].includes(f.family))throw Error(`requirement ${r.id}: detail feature family must be functional, assembly, support, edge or surface`)
      for(const field of ['purpose','attachment','construction','inspection'])text(f[field],'feature '+field)
      list(f.controls,'feature controls',8);f.controls.forEach((v:any)=>text(v,'feature control',100))
    }
    for(const c of r.checks) {
      keys(c,['verb','contract_sha256','check_id','case_id'],'check binding')
      if(!['geo_check_interfaces','test_controls'].includes(c.verb)||typeof c.contract_sha256!=='string'||!hashPattern.test(c.contract_sha256))
        throw Error('check binding requires supported verb and contract_sha256')
      text(c.check_id,'check_id',100)
      if(r.kind==='control'&&c.case_id!==undefined) bindingErrors.push(`${r.id}: control binding uses check_id as its case id; omit case_id`)
      if(c.verb==='test_controls' && r.kind!=='control' && (typeof c.case_id!=='string'||!c.case_id.trim()))
        bindingErrors.push(`${r.id}: test_controls interface binding requires case_id (baseline or exact test id)`)
      if(c.case_id!==undefined) text(c.case_id,'case_id',100)
      if(c.verb==='geo_check_interfaces'&&c.case_id!==undefined) throw Error('case_id requires test_controls')
    }
  }
  if(bindingErrors.length) throw Error(`Invalid check bindings: ${bindingErrors.slice(0,24).join('; ')}. Read action="review" evidence_index and copy the exact binding for the matching requirement and state. No revision was recorded.`)
  list(value.retired,'retired',128)
  for(const r of value.retired) {
    keys(r,['id','reason','source_ref'],'retired requirement');text(r.id,'retired id',100);text(r.reason,'retirement reason')
    if(ids.has(r.id)||!value.source_refs.includes(r.source_ref)) throw Error('retired ids must be unique, inactive and cite a definition source_ref')
    ids.add(r.id)
  }
  if(JSON.stringify(value).length>64000) throw Error('product definition exceeds 64000 characters; narrow descriptions, not obligations')
  return structuredClone(value)
}

export function productState(events:readonly Event[]):{current:Revision|null;conflicts:string[];candidates:Revision[];
    expectation_changes:ExpectationChange[];expectation_changes_omitted:number} {
  const calls=new Map<string,string>(),seen=new Set<string>(),conflicts:string[]=[],candidates:Revision[]=[]
  const changes:ExpectationChange[]=[];let omitted=0
  let current:Revision|null=null
  for(const e of events) {
    const d=e.data
    if(e.type==='tool/call') calls.set(d?.callId,d?.name)
    const id=d?.message?.source?.callId,row=d?.meta?.canonical?.product_definition
    if(e.type!=='tool/result'||calls.get(id)!=='houdini_product'||seen.has(id)||!row||d?.isError||d?.meta?.isError) continue
    seen.add(id)
    try {
      validateProductDefinition(row.definition)
      text(row.change_reason,'change_reason')
      if(!Number.isSafeInteger(row.revision)||row.revision!==row.base_revision+1||row.base_revision!==(current?.revision??0)
          ||row.sha256!==sha(row.definition)) throw Error('revision conflict')
      if(conflicts.length && JSON.stringify(row.resolved_conflicts)!==JSON.stringify(conflicts)) throw Error('unacknowledged revision conflict')
      for(const old of current?.definition.requirements??[]) {
        const next=row.definition.requirements.find((r:Requirement)=>r.id===old.id)
        if(!next) continue
        const fields=(['kind','subjects','state','dimension','members','contact','control_values'] as const)
          .filter(key=>JSON.stringify(ordered(old[key]))!==JSON.stringify(ordered(next[key])))
        if(fields.length) changes.push({id:old.id,fields,revision:row.revision,reason:row.change_reason})
      }
      if(changes.length>64) omitted+=changes.splice(0,changes.length-64).length
      current=row
      conflicts.splice(0);candidates.splice(0)
    } catch {
      conflicts.push(id)
      try {validateProductDefinition(row.definition);candidates.push(row)} catch { /* invalid history stays a conflict */ }
    }
  }
  return {current,conflicts,candidates,expectation_changes:changes,expectation_changes_omitted:omitted}
}

export function defineProduct(events:readonly Event[],definition:unknown,expectedRevision:number,reason:string,resolvedConflicts?:unknown):Revision {
  const state=productState(events)
  if((state.conflicts.length||resolvedConflicts!==undefined)&&JSON.stringify(resolvedConflicts)!==JSON.stringify(state.conflicts))
    throw Error('conflicting product revisions: read both definitions, merge obligations, then supply resolve_conflicts with the exact conflict call ids')
  if(!Number.isSafeInteger(expectedRevision)||expectedRevision!==(state.current?.revision??0)) throw Error(`expected_revision differs from current product revision ${state.current?.revision??0}; read first`)
  text(reason,'change_reason')
  const next=validateProductDefinition(definition)
  const sources=new Set(taskSources(events).filter(s=>s.kind!=='clarification_question').map(s=>s.source_ref))
  if(next.source_refs.some(ref=>!sources.has(ref))) throw Error('definition source_refs must cite current-session user material or clarification answers')
  if(next.reviewed_through!==undefined&&!sources.has(next.reviewed_through)) throw Error('reviewed_through must cite a current-session user source or clarification answer')
  const previous=[...(state.current?[state.current]:[]),...state.candidates]
  for(const old of previous.flatMap(row=>row.definition.requirements)) {
    if(!next.requirements.some(r=>r.id===old.id)&&!next.retired.some(r=>r.id===old.id))
      throw Error(`removed obligation ${old.id} needs a retained retirement reason and source_ref`)
  }
  for(const old of previous.flatMap(row=>row.definition.retired)) {
    if(!next.retired.some(r=>r.id===old.id)&&!next.requirements.some(r=>r.id===old.id))
      throw Error(`retain retirement ${old.id} or explicitly reactivate it`)
  }
  return {revision:expectedRevision+1,base_revision:expectedRevision,sha256:sha(next),definition:next,change_reason:reason,
    ...(state.conflicts.length?{resolved_conflicts:state.conflicts}:{})}
}

function observedItem(history:ExecutionHistory,check:any) {
  return history.results.get(check.source_call)?.evidence?.find((v:any)=>check.ledger_index!==null&&v.ledgerIndex===check.ledger_index
    &&v.verb===check.verb&&v.contract_sha256===check.contract_sha256&&v.output===check.output)
}
function bindingCoverage(history:ExecutionHistory,checks:any[],r:Requirement,b:Binding,output:string) {
  const check=checks.filter(c=>c.verb===b.verb&&c.contract_sha256===b.contract_sha256&&c.output===output).at(-1)
  if(!check) return {binding:b,status:'missing',reason:'no matching receipt on final output'}
  const base={binding:b,source_call:check.source_call,ledger_index:check.ledger_index,validity:check.validity,contract_status:check.status}
  if(check.validity!=='historical_observation_only') return {...base,status:'stale'}
  const item=observedItem(history,check)
  if(b.verb==='test_controls'&&item?.restored!==true)
    return {...base,status:item?.restored===false?'fail':'unverified',reason:'control restoration is not verified'}
  const row=b.verb==='geo_check_interfaces'?item?.results?.find((v:any)=>v.id===b.check_id)
    :r.kind==='control'?item?.results?.find((v:any)=>v.id===b.check_id)
    :b.case_id==='baseline'?item?.baseline_interfaces?.results?.find((v:any)=>v.id===b.check_id)
    :item?.results?.find((v:any)=>v.id===b.case_id)?.interfaces?.results?.find((v:any)=>v.id===b.check_id)
  if(r.control_values){
    const stateCase=b.verb==='test_controls'?item?.results?.find((v:any)=>v.id===(r.kind==='control'?b.check_id:b.case_id)):undefined
    if(!stateCase?.actual_values||Object.entries(r.control_values).some(([name,value])=>
      typeof stateCase.actual_values[name]!=='number'||Math.abs(stateCase.actual_values[name]-value)>Math.max(1e-12,Math.abs(value)*1e-9)))
      return {...base,status:'unverified',reason:'receipt does not establish the registered control state'}
  }
  if(!row) return {...base,status:check.status==='pass'?'missing':check.status,
    reason:item?.reason??'declared case/check not observed; inspect the enclosing contract result'}
  const method=row.method??'surface_proximity'
  if(r.members && (method!=='component_count'||row.target_group!==r.members.group
      ||row.expected_components!==r.members.expected_components))
    return {...base,status:'unverified',reason:'measurement does not match registered member group/count'}
  if(r.contact && (method!=='surface_proximity'||row.source_group!==r.contact.source_group
      ||row.target_group!==r.contact.target_group||row.expected_points!==r.contact.expected_points
      ||!Number.isFinite(row.tolerance)||row.tolerance>r.contact.max_distance+1e-12))
    return {...base,status:'unverified',reason:'measurement does not match registered contact groups/cardinality/tolerance'}
  if(row.status==='pass' && r.members && row.observed_components!==r.members.expected_components)
    return {...base,status:'unverified',reason:'passing receipt lacks the registered observed member count'}
  if(row.status==='pass' && r.contact && (!Number.isFinite(row.max_distance)||row.max_distance>r.contact.max_distance+1e-12))
    return {...base,status:'unverified',reason:'passing receipt lacks contact distances within the registered limit'}
  if(r.dimension){
    const d=r.dimension
    if(method!=='physical_extent'||row.target_group!==d.group||row.axis!==d.axis
        ||Math.abs(row.expected_mm/1000-d.expected_m)>Math.max(1e-12,d.expected_m*1e-9)
        ||!Number.isFinite(row.expected_mm)||!Number.isFinite(row.tolerance_mm)||row.tolerance_mm/1000>d.tolerance_m+1e-12)
      return {...base,status:'unverified',reason:'measurement group/axis/expected physical value/tolerance does not match the registered dimension'}
  }
  if(row.status!=='pass') return {...base,status:row.status??'unverified',reason:'declared case/check not observed passing'}
  const applicable=r.kind==='part'?method==='component_count':r.kind==='dimension'?method==='physical_extent'
    :r.kind==='relation'?!!row.source_group&&!!row.target_group
    :r.kind==='control'?b.verb==='test_controls'&&Array.isArray(row.measurements)&&row.measurements.length>0:false
  return {...base,status:applicable?'measured':'unverified',method,
    scope:row.scope??item?.scope??'selected measurements only',
    ...(applicable?{}:{reason:'measurement kind does not establish this obligation; visual/detail/source meaning needs review',
      required_evidence:measurementGuide[r.kind]})}
}

export function productCoverage(events:readonly Event[], facts:{history?:ExecutionHistory;audit?:any}={}) {
  const state=productState(events)
  if(!state.current) return {status:'not_defined',boundary}
  if(state.conflicts.length) return {status:'revision_conflict',conflicts:state.conflicts,boundary}
  const history=facts.history??executionHistory(events)
  const audit=facts.audit===undefined?projectDeliveryAudit(events,{fullChecks:true},history):facts.audit
  const definition=state.current.definition
  const sources=taskSources(events).filter(s=>s.kind!=='clarification_question')
  const reviewedIndex=definition.reviewed_through===undefined?-1:sources.findIndex(s=>s.source_ref===definition.reviewed_through)
  const unreconciled_sources=sources.filter((s,i)=>i>reviewedIndex&&!definition.source_refs.includes(s.source_ref))
    .map(s=>({source_ref:s.source_ref,kind:s.kind,event_seq:s.event_seq}))
  const requirements=definition.requirements.map(r=> {
    const evidence=r.checks.map(b=>bindingCoverage(history,audit?.checks??[],r,b,definition.output))
    const status=!evidence.length?'missing':evidence.every(e=>e.status==='measured')?'measured'
      :evidence.some(e=>e.status==='fail')?'fail':evidence.some(e=>e.status==='stale')?'stale':'unverified'
    return {id:r.id,kind:r.kind,description:r.description,subjects:r.subjects,state:r.state,status,evidence,
      ...(r.dimension?{dimension:r.dimension}:{}),...(r.members?{members:r.members}:{}),...(r.contact?{contact:r.contact}:{}),
      ...(r.control_values?{control_values:r.control_values}:{}),...(r.feature?{feature:r.feature}:{})}
  })
  const numeric=requirements.filter(r=>!['detail','visual'].includes(r.kind))
  const planningGaps=requirements.filter(r=>(r.kind==='part'&&!r.members)||(r.kind==='dimension'&&!r.dimension)
    ||(r.kind==='detail'&&!r.feature)).map(r=>({id:r.id,missing:r.kind==='part'?'members':r.kind==='dimension'?'dimension':'feature'}))
  const workflow={
    persistence:audit?.delivery??{status:'no_current_save_receipt'},
    stages:{definition:{status:'declared',requirements:requirements.length,unreconciled_sources:unreconciled_sources.length},
      expectation_plan:{status:planningGaps.length?'incomplete':'declared',gaps:planningGaps},
      numerical_checks:{status:!numeric.length?'not_applicable':numeric.every(r=>r.status==='measured')?'recorded':'incomplete',
        pending:numeric.filter(r=>r.status!=='measured').map(r=>({id:r.id,status:r.status}))},
      detail_and_visual:{status:'requires_semantic_review',requirements:requirements.filter(r=>['detail','visual'].includes(r.kind)).map(r=>r.id)}},
    expectation_changes:state.expectation_changes,expectation_changes_omitted:state.expectation_changes_omitted,
    completion:{status:'not_certified',reason:'Persistence, numeric evidence and semantic acceptance are separate. Saving is always allowed; no stage grants whole-product acceptance.'},

  }
  return {status:'declared_coverage_only',revision:state.current.revision,sha256:state.current.sha256,
    output:definition.output,requirements,unresolved:requirements.filter(r=>r.status!=='measured').length,
    retired:definition.retired,unreconciled_sources,workflow,
    detail_plan:{declared:definition.requirements.filter(r=>r.kind==='detail').length,
      with_design:definition.requirements.filter(r=>r.kind==='detail'&&r.feature).length,
      boundary:'Design purposes and attachments are author plans, not evidence that the detail exists or is visually correct.'},
    source_review:'unverified',visual_semantics:'unverified',boundary}
}

/** Optional requirement facts; they do not prescribe the next operation. */
export function productNotice(events:readonly Event[],coverage=productCoverage(events)) {
  if(coverage.status==='not_defined') return null
  const pending=coverage.requirements?.filter(r=>r.status!=='measured')??[]
  return {status:coverage.status,revision:coverage.revision,output:coverage.output,
    conflicts:coverage.conflicts,unresolved:coverage.unresolved,total:coverage.requirements?.length??0,
    pending:pending.slice(0,8).map(r=>({id:r.id,kind:r.kind,status:r.status,description:r.description.slice(0,160),state:r.state.slice(0,100)})),
    pending_omitted:Math.max(0,pending.length-8),retired_count:coverage.retired?.length??0,
    unreconciled_source_count:coverage.unreconciled_sources?.length??0,
    read:'houdini_product(action="read")',boundary}
}

/** Bounded receipt navigation, not automatic binding or acceptance. */
function evidenceIndex(history:ExecutionHistory,audit:any,output:string|undefined) {
  const rows:any[]=[];let total=0
  for(const check of [...(audit?.checks??[])].reverse()) {
    if(check.output!==output||typeof check.contract_sha256!=='string'||!hashPattern.test(check.contract_sha256)) continue
    const item=observedItem(history,check)
    const add=(row:any,caseId?:string,control=false,values?:unknown)=>{
      if(!row||typeof row.id!=='string') return
      total++
      if(rows.length>=32) return
      const facts=Object.fromEntries(['method','source_group','target_group','expected_components','observed_components',
        'expected_mm','tolerance_mm','axis','expected_points','tolerance','max_distance','max_overlap_volume'].filter(k=>row[k]!==undefined).map(k=>[k,row[k]]))
      rows.push({binding:{verb:check.verb,contract_sha256:check.contract_sha256,check_id:row.id,...(caseId?{case_id:caseId}:{})},
        kind:control?'control_case':'interface',status:row.status,validity:check.validity,source_call:check.source_call,
        ledger_index:check.ledger_index,...facts,...(values?{control_values:values}:{})})
    }
    if(check.verb==='geo_check_interfaces') for(const row of item?.results??[]) add(row)
    else {
      for(const row of item?.baseline_interfaces?.results??[]) add(row,'baseline')
      for(const trial of item?.results??[]) {
        add(trial,undefined,true,trial.actual_values)
        for(const row of trial.interfaces?.results??[]) add(row,trial.id,false,trial.actual_values)
      }
    }
  }
  return {rows,omitted:Math.max(0,total-rows.length),scope:'Recent final-output receipt locators only. Select the matching obligation/state/method; entries are not automatically bound. Full historical results remain available through result_ref.'}
}

export function registerProductTool(ctx:Context) {
  ctx.tools.register(defineTool({
    name:'houdini_product',
    description:'Optionally maintain a session-local product definition for complex tasks. Review returns requirement coverage, save facts and recent check bindings. Host-only, no HOM or scene edits. Definitions never certify completion or grant ownership. Use schema first; source_refs come from houdini_query(source_ref="index"). Revisions require the current expected_revision and a change reason. Retain removed obligations with explicit retirement reasons and source references.',
    parameters:{action:{type:'string',enum:['schema','define','read','review'],required:true},definition:definitionSchema,
      expected_revision:{type:'number'},change_reason:{type:'string'},resolve_conflicts:{type:'json',description:'Only after read reports conflicts: exact conflict call-id list, acknowledging the definitions merged in this revision.'}},
    output:{schema:{type:'object',properties:{product_definition:{type:'json'},result:{type:'json'}},additionalProperties:false},
      render:(_args,value)=>[{type:'text' as const,text:JSON.stringify(value)}],
      presentationMeta:(_args,value)=>({canonical:value})},
    presentCall:args=>({card:'generic',title:'Houdini product definition',kind:args.action==='define'?'edit':'read',rawInput:args}),
    async execute(args,exec) {
      if(args.action!=='define'&&[args.definition,args.expected_revision,args.change_reason,args.resolve_conflicts].some(v=>v!==undefined))
        throw Error('definition/expected_revision/change_reason require action=define')
      if(args.action==='schema') return {result:{schema_version:1,max_requirements:128,boundary,
        define_arguments:{action:'define',expected_revision:'0 initially; otherwise current revision from read',change_reason:'required nonempty reason',definition:'object below'},
        required_definition_fields:['title','output','units','source_refs','assumptions','requirements','retired'],
        required_requirement_fields:['id','kind','description','subjects','state','checks'],
        feature_families:['functional','assembly','support','edge','surface'],
        measurement_mapping:measurementGuide,
        definition:{title:'Product',output:'/obj/product/OUT_ASSET',units:'meters; dimensions cited in mm',
          source_refs:['SHA-256 from source_ref=index'],assumptions:[],retired:[],requirements:[
          {id:'hinge_closed',kind:'relation',description:'Lid remains attached to base',subjects:['lid','base'],state:'baseline: opening=0',checks:[]}]},
        check_binding:{verb:'geo_check_interfaces or test_controls',contract_sha256:'exact receipt hash',check_id:'exact interface id or control case id',
          case_id:'test_controls relation: baseline or exact test case id; omit for control kind'},
        binding_examples:{
          direct_interface:{verb:'geo_check_interfaces',contract_sha256:'COPY_RECEIPT_HASH',check_id:'contact'},
          control_requirement:{verb:'test_controls',contract_sha256:'COPY_RECEIPT_HASH',check_id:'maximum_travel'},
          interface_at_control_state:{verb:'test_controls',contract_sha256:'COPY_RECEIPT_HASH',check_id:'contact',case_id:'maximum_travel'},
          baseline_interface:{verb:'test_controls',contract_sha256:'COPY_RECEIPT_HASH',check_id:'contact',case_id:'baseline'}},
        kinds,reviewed_through:'Optional last reviewed user/clarification source SHA-256; acknowledges reviewing preceding sources, never semantic correctness or authorization.',
        optional_requirement_fields:{dimension:{group:'final_part',axis:0,expected_m:0.12,tolerance_m:0.0001},
          members:{group:'final_members',expected_components:4},
          contact:{source_group:'foot_vertices',target_group:'receiver',max_distance:0.00005,expected_points:4},
          control_values:{travel:0.03},feature:{family:'support',purpose:'stiffen an attachment',attachment:'named mounting surface',
            controls:['wall_thickness'],construction:'surface-attached gusset source',inspection:'foot contact plus local side view'}},
        notes:'List each required state separately. Record source-based member/dimension/contact expectations when relevant; contact max_distance is in explicit final SOP-local units. Empty checks preserve pending obligations. Review separates persistence, expectation planning, numerical checks and semantic review; it never authorizes completion. Expectation revisions remain disclosed. Visual/detail obligations remain unverified by numeric measurements. Define sequentially with native direct calls; nested/Code Mode definitions are rejected.'}}
      const session=exec.agent?.session as any
      if(!session?.snapshotEvents) throw Error('product definition requires a current durable session')
      const events=session.snapshotEvents()
      const history=executionHistory(events)
      const audit=projectDeliveryAudit(events,{fullChecks:true},history)
      const coverage=productCoverage(events,{history,audit})
      if(args.action==='read') return {result:JSON.parse(JSON.stringify({...productState(events),coverage}))}
      if(args.action==='review') {
        return {result:JSON.parse(JSON.stringify({status:coverage.status,revision:coverage.revision,output:coverage.output,
          workflow:coverage.workflow??{
            persistence:(audit as any)?.delivery??{status:'no_current_save_receipt'},
            stages:{definition:{status:coverage.status}},completion:{status:'not_certified'},
            boundary:'No consistent requirement definition is recorded.'},
          evidence_index:evidenceIndex(history,audit,coverage.output),boundary}))}
      }
      if(args.action!=='define') throw Error('unknown product action')
      if(exec.parent!==undefined) throw Error('Product definitions require a direct native houdini_product call. Nested/Code Mode does not persist canonical definition receipts in this DSH version; use native/both tool presentation. No definition was recorded.')
      return {product_definition:defineProduct(events,args.definition,args.expected_revision!,args.change_reason!,args.resolve_conflicts)}
    },
  }))
}
