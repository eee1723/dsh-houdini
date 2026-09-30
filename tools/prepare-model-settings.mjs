/** Copy one explicitly selected provider/model configuration into a fresh trial.
 * Never copy credentials, other providers, personas, or unrelated user settings.
 */
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.resolve('@deepseek-ai/dsh-agent-presets'));
const yaml=require('js-yaml');

export function selectedModelSettings(source,provider,model){
  if(provider!=='deepseek-official')throw Error('Only the explicitly selected DeepSeek provider is supported');
  if(typeof model!=='string'||!model.trim())throw Error('Explicit model required');
  const settings=yaml.load(source);
  const config=settings?.['llm-deepseek'];
  if(!config||typeof config!=='object'||Array.isArray(config))throw Error('llm-deepseek settings are missing');
  const models=config.models;
  const selected=Array.isArray(models)?models.filter(row=>row?.id===model):[];
  if(selected.length!==1)throw Error('Selected model must have exactly one configured catalog entry; no default fallback');
  if(!Array.isArray(selected[0].inputModalities)||!selected[0].inputModalities.includes('text')
    ||selected[0].inputModalities.some(x=>!['text','image'].includes(x)))throw Error('Explicit text/image modalities required');
  const copied={...config,models:structuredClone(selected)};
  const hasInlineSecret=value=>value&&typeof value==='object'&&Object.entries(value).some(([k,v])=>
    /^(apiKey|token|password|secret|authorization)$/i.test(k)||hasInlineSecret(v));
  if(hasInlineSecret(copied))throw Error('Inline secrets must remain in the credential store');
  return {'llm-deepseek':copied};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const [source,home,provider,model]=process.argv.slice(2);
  if(!source||!home||!path.isAbsolute(home)||process.env.DSH_HOME!==home)throw Error('Explicit source and isolated DSH_HOME required');
  const value=selectedModelSettings(fs.readFileSync(source,'utf8'),provider,model);
  fs.mkdirSync(home,{recursive:true});
  fs.writeFileSync(path.join(home,'settings.yaml'),JSON.stringify(value,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({provider,model,inputModalities:value['llm-deepseek'].models[0].inputModalities,
    scope:'Selected provider configuration only; no credentials or other user settings copied'}));
}
