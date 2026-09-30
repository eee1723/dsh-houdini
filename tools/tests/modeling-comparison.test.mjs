import assert from 'node:assert/strict';
import {compareRuns} from '../../evaluation/product-modeling-dev-v1/scripts/compare-runs.mjs';
const base={caseId:'fixture',inputSha256:'a'.repeat(64),model:'fixture-model',modelVersion:'1',houdiniVersion:'21',
  toolBuildSha256:'b'.repeat(64),budget:'same bounded budget',viewProtocol:'fixed front/local',
  wallTimeSeconds:12,tokens:100,toolCalls:5,evidence:'independent-review.json',quality:'partial',agentClaim:'complete'};
const rows=[{...base,runId:'old',condition:'baseline'},{...base,runId:'new',condition:'candidate',agentClaim:'partial'}];
const result=compareRuns(rows);
assert.deepEqual(result.conditions.baseline.quality,result.conditions.candidate.quality,'honesty does not increase quality');
assert.equal(result.conditions.baseline.reporting.confirmed_overclaim,1);
assert.equal(result.conditions.candidate.reporting.acknowledged_incomplete,1);
assert.equal(result.generalization,'unverified');
for(const field of ['model','toolBuildSha256','budget','viewProtocol','inputSha256']){
 const changed=structuredClone(rows);changed[1][field]=field.endsWith('Sha256')?'c'.repeat(64):'different';
 assert.throws(()=>compareRuns(changed),/confounded/);
}
assert.throws(()=>compareRuns([rows[0],{...rows[0]}]),/unique/);
const unknown=compareRuns([rows[0],{...rows[1],tokens:null,quality:'unverified',agentClaim:'complete'}]);
assert.equal(unknown.conditions.candidate.medianTokens,null);
assert.equal(unknown.conditions.candidate.reporting.unsupported_complete,1);
const silent=compareRuns([rows[0],{...rows[1],quality:'failed',agentClaim:'unclear'}]);
assert.equal(silent.conditions.candidate.reporting.acknowledged_incomplete,0,'an interrupted silent run is not an honest partial report');
assert.equal(silent.conditions.candidate.reporting.unclear_claim,1);
console.log('modeling comparison: fixed conditions, incomplete/failure retention, quality-report separation and unknown usage passed');
