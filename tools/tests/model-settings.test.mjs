import assert from 'node:assert/strict';
import {selectedModelSettings,selectedCredentials} from '../prepare-model-settings.mjs';
const text=JSON.stringify({'agent-default-model':{provider:'other'},'unrelated':{token:'do-not-copy'},
  'llm-deepseek':{protocol:'messages',models:[{id:'deepseek-v4-flash',inputModalities:['text','image']},
    {id:'other',inputModalities:['text']}]}});
const result=selectedModelSettings(text,'deepseek-official','deepseek-v4-flash');
assert.deepEqual(Object.keys(result),['llm-deepseek']);
assert.equal(result['llm-deepseek'].models.length,1);
assert.deepEqual(result['llm-deepseek'].models[0].inputModalities,['text','image']);
assert(!JSON.stringify(result).includes('do-not-copy'));
assert.throws(()=>selectedModelSettings(text,'other','deepseek-v4-flash'),/provider/);
assert.throws(()=>selectedModelSettings(text,'deepseek-official','unknown'),/catalog entry/);
assert.throws(()=>selectedModelSettings('{"llm-deepseek":{"models":[{"id":"m"}]}}','deepseek-official','m'),/modalities/);
assert.throws(()=>selectedModelSettings(JSON.stringify({'llm-deepseek':{models:[{id:'m',inputModalities:['text','image']}],headers:{Authorization:'secret'}}}),
  'deepseek-official','m'),/Inline secrets/);
const defaults={models:[{id:'deepseek-flash',name:'Pinned Flash',inputModalities:['text','image']}]};
assert.equal(selectedModelSettings('- id: ui-theme\n  config: {preference: dark}', 'deepseek-official','deepseek-flash',defaults)['llm-deepseek'].models[0].name,'Pinned Flash');
assert.equal(selectedModelSettings('- id: llm-deepseek\n  config: {maxTokens: 4000}', 'deepseek-official','deepseek-flash',defaults)['llm-deepseek'].maxTokens,4000);
assert.throws(()=>selectedModelSettings('- id: llm-deepseek\n  config: {apiKey: secret}', 'deepseek-official','deepseek-flash',defaults),/Inline secrets/);
assert.deepEqual(selectedCredentials(JSON.stringify({version:1,refs:{DEEPSEEK_API_KEY:'selected',OTHER:'not-selected'},records:{browser:'not-selected'}}),'DEEPSEEK_API_KEY'),{version:1,refs:{DEEPSEEK_API_KEY:'selected'},records:{}});
assert.throws(()=>selectedCredentials('{"version":1,"refs":{}}','DEEPSEEK_API_KEY'),/missing/);
const pi=JSON.stringify({'llm-pi-ai':{providers:{selected:{api:'openai-completions',apiKeyEnv:'SELECTED_KEY',
  models:[{id:'m',inputModalities:['text','image']},{id:'other',inputModalities:['text']}]},
  unrelated:{apiKey:'do-not-copy',models:[]}}}});
const piResult=selectedModelSettings(pi,'selected','m');
assert.deepEqual(Object.keys(piResult),['llm-pi-ai']);
assert.deepEqual(Object.keys(piResult['llm-pi-ai'].providers),['selected']);
assert.equal(piResult['llm-pi-ai'].providers.selected.models.length,1);
assert.deepEqual(piResult['llm-pi-ai'].providers.selected.models[0].input,['text','image']);
assert.equal(piResult['llm-pi-ai'].providers.selected.models[0].inputModalities,undefined);
assert(!JSON.stringify(piResult).includes('do-not-copy'));
assert.throws(()=>selectedModelSettings(pi,'missing','m'),/provider/);
assert.throws(()=>selectedModelSettings(pi,'selected','missing'),/catalog entry/);
const modernPi=JSON.stringify({'llm-pi-ai':{providers:{p:{apiKeyEnv:'K',models:[{id:'m',input:['text','image']}]}}}});
assert.deepEqual(selectedModelSettings(modernPi,'p','m')['llm-pi-ai'].providers.p.models[0].input,['text','image']);
assert.throws(()=>selectedModelSettings(JSON.stringify({'llm-pi-ai':{providers:{p:{apiKeyEnv:'K',
 models:[{id:'m',input:['text'],inputModalities:['text','image']}]}}}}),'p','m'),/conflicting/);
assert.throws(()=>selectedModelSettings(JSON.stringify({'llm-pi-ai':{providers:{p:{apiKeyEnv:'K',
  models:[{id:'m',inputModalities:['text']}],headers:{Authorization:'secret'}}}}}),'p','m'),/Inline secrets/);
console.log('trial settings: selected provider/catalog preserved, missing route refused, unrelated settings excluded');
