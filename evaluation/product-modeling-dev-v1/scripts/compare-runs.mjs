/** Compare registered conditions without turning honest incompleteness into quality. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const fixed=['caseId','inputSha256','model','modelVersion','houdiniVersion','toolBuildSha256','budget','viewProtocol'];
const median=values=>{if(!values.length)return null;const s=[...values].sort((a,b)=>a-b),i=Math.floor(s.length/2);return s.length%2?s[i]:(s[i-1]+s[i])/2};
export function compareRuns(rows){
  if(!Array.isArray(rows)||rows.length<2)throw Error('at least two registered runs required');
  const ids=new Set(),pairs=new Map();
  for(const row of rows){
    if(!row||typeof row.runId!=='string'||!row.runId||ids.has(row.runId))throw Error('unique runId required');
    ids.add(row.runId);
    if(!['baseline','candidate'].includes(row.condition))throw Error('condition must be baseline/candidate');
    for(const field of fixed)if(typeof row[field]!=='string'||!row[field])throw Error('missing fixed field '+field);
    if(!/^[0-9a-f]{64}$/.test(row.inputSha256)||!/^[0-9a-f]{64}$/.test(row.toolBuildSha256))throw Error('exact input/tool SHA-256 required');
    if(!['complete','partial','failed','unverified'].includes(row.quality))throw Error('independent quality judgement required, including unverified');
    if(!['complete','partial','failed','unclear'].includes(row.agentClaim))throw Error('agentClaim required');
    if(typeof row.evidence!=='string'||!row.evidence)throw Error('evidence locator required');
    for(const field of ['wallTimeSeconds','tokens','toolCalls'])if(row[field]!==null&&(!Number.isFinite(row[field])||row[field]<0))throw Error(field+' must be measured nonnegative or null');
    const key=row.caseId;const group=pairs.get(key)??[];group.push(row);pairs.set(key,group);
  }
  for(const [key,group] of pairs){
    if(new Set(group.map(r=>r.condition)).size!==2)throw Error(key+' needs both conditions, including failed/unfinished runs');
    for(const field of fixed)if(new Set(group.map(r=>r[field])).size!==1)throw Error(key+' comparison confounded by '+field);
  }
  const conditions=Object.fromEntries(['baseline','candidate'].map(condition=>{
    const runs=rows.filter(r=>r.condition===condition);
    return [condition,{runs:runs.length,
      quality:{complete:runs.filter(r=>r.quality==='complete').length,partial:runs.filter(r=>r.quality==='partial').length,
        failed:runs.filter(r=>r.quality==='failed').length,unverified:runs.filter(r=>r.quality==='unverified').length},
      reporting:{confirmed_overclaim:runs.filter(r=>r.agentClaim==='complete'&&['partial','failed'].includes(r.quality)).length,
        unsupported_complete:runs.filter(r=>r.agentClaim==='complete'&&r.quality==='unverified').length,
        acknowledged_incomplete:runs.filter(r=>['partial','failed'].includes(r.agentClaim)&&r.quality!=='complete').length,
        unclear_claim:runs.filter(r=>r.agentClaim==='unclear').length},
      medianSeconds:median(runs.map(r=>r.wallTimeSeconds).filter(v=>v!==null)),
      medianTokens:median(runs.map(r=>r.tokens).filter(v=>v!==null)),
      medianCalls:median(runs.map(r=>r.toolCalls).filter(v=>v!==null)),
      missingUsage:runs.filter(r=>r.tokens===null).length}];
  }));
  return {conditions,cases:pairs.size,runs:rows.map(r=>({runId:r.runId,condition:r.condition,evidence:r.evidence})),
    generalization:'unverified',scope:'Registered development runs only; independent quality and report accuracy are separate. No automatic geometry/visual judgement, no causal or unseen-task claim from small samples.'};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const [input,out]=process.argv.slice(2);
  if(!input||!out)throw Error('usage: node compare-runs.mjs <registered-runs.json> <new-report.json>');
  fs.writeFileSync(out,JSON.stringify(compareRuns(JSON.parse(fs.readFileSync(input,'utf8'))),null,2)+'\n',{flag:'wx'});
}
