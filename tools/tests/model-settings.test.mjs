import assert from 'node:assert/strict';
import {selectedModelSettings} from '../prepare-model-settings.mjs';
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
console.log('trial settings: selected provider/catalog preserved, missing route refused, unrelated settings excluded');
