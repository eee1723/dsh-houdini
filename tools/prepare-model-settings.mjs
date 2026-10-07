/** Copy one explicitly selected provider/model configuration into a fresh trial.
 * Copies only the explicitly selected credential reference; never other providers,
 * account records, personas, or unrelated user settings.
 */
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
const require=createRequire(import.meta.resolve('@deepseek-ai/dsh-agent-preset'));
const yaml=require('js-yaml');

export function selectedModelSettings(source,provider,model,defaults){
  if(typeof provider!=='string'||!provider.trim())throw Error('Explicit provider required');
  if(typeof model!=='string'||!model.trim())throw Error('Explicit model required');
  const settings=yaml.load(source);
  const hasInlineSecret=value=>value&&typeof value==='object'&&Object.entries(value).some(([k,v])=>
    /^(apiKey|token|password|secret|authorization)$/i.test(k)||hasInlineSecret(v));
  if(provider!=='deepseek-official'){
    const config=Array.isArray(settings)
      ? Object.assign({},...settings.filter(row=>row?.id==='llm-pi-ai'&&!row.disabled).map(row=>row.config??{}))
      : settings?.['llm-pi-ai'];
    const route=config?.providers?.[provider];
    if(!route||typeof route!=='object'||Array.isArray(route))throw Error('Selected provider is missing from llm-pi-ai settings');
    const selected=Array.isArray(route.models)?route.models.filter(row=>row?.id===model):[];
    if(selected.length!==1)throw Error('Selected model must have exactly one configured catalog entry; no default fallback');
    const entry=selected[0];
    if(entry.input!==undefined&&entry.inputModalities!==undefined
      &&JSON.stringify([...entry.input].sort())!==JSON.stringify([...entry.inputModalities].sort()))
      throw Error('Selected PI model has conflicting input and older inputModalities declarations');
    const input=entry.input??entry.inputModalities;
    if(!Array.isArray(input)||!input.includes('text')||input.some(x=>!['text','image'].includes(x)))
      throw Error('Explicit text/image modalities required');
    if(typeof route.apiKeyEnv!=='string'||!route.apiKeyEnv.trim())throw Error('Selected provider must name a credential reference');
    // Pinned PI configuration accepts `input`; inputModalities is a resolver
    // output. Translate only this observed older, explicit user declaration.
    const configured=structuredClone(entry);configured.input=[...input];delete configured.inputModalities;
    const copied={...config,providers:{[provider]:{...route,models:[configured]}}};
    if(hasInlineSecret(copied))throw Error('Inline secrets must remain in the credential store');
    return {'llm-pi-ai':copied};
  }
  // DSH 0.2 migrated settings to the profile patch. Take only this provider's
  // explicit overrides; its default catalog must come from the pinned runtime.
  const config=Array.isArray(settings)
    ? Object.assign({},...settings.filter(row=>row?.id==='llm-deepseek').map(row=>row.config??{}))
    : settings?.['llm-deepseek'];
  if(!config||typeof config!=='object'||Array.isArray(config))throw Error('llm-deepseek settings are missing');
  const models=config.models??defaults?.models;
  const selected=Array.isArray(models)?models.filter(row=>row?.id===model):[];
  if(selected.length!==1)throw Error('Selected model must have exactly one configured catalog entry; no default fallback');
  if(!Array.isArray(selected[0].inputModalities)||!selected[0].inputModalities.includes('text')
    ||selected[0].inputModalities.some(x=>!['text','image'].includes(x)))throw Error('Explicit text/image modalities required');
  const copied={...config,models:structuredClone(selected)};
  if(hasInlineSecret(copied))throw Error('Inline secrets must remain in the credential store');
  return {'llm-deepseek':copied};
}

export function selectedCredentials(source,reference){
  const parsed=yaml.load(source);
  if(parsed?.version!==1||!Object.hasOwn(parsed.refs??{},reference))throw Error('Selected credential reference is missing');
  return {version:1,refs:{[reference]:parsed.refs[reference]},records:{}};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const [source,home,provider,model,dsh,credentials]=process.argv.slice(2);
  if(!source||!home||!path.isAbsolute(home)||process.env.DSH_HOME!==home)throw Error('Explicit source and isolated DSH_HOME required');
  const runtime=dsh&&provider==='deepseek-official'?await import(pathToFileURL(createRequire(dsh).resolve('@deepseek-ai/dsh-llm-deepseek-api-key'))):undefined;
  const defaults=runtime?.resolveAdapterOptions({});
  const value=selectedModelSettings(fs.readFileSync(source,'utf8'),provider,model,defaults);
  const resolved=runtime?.resolveAdapterOptions(value['llm-deepseek']);
  fs.mkdirSync(home,{recursive:true});
  const id=provider==='deepseek-official'?'llm-deepseek':'llm-pi-ai';
  const selectedRoute=id==='llm-deepseek'?value[id]:value[id].providers[provider];
  fs.writeFileSync(path.join(home,'selected-model.patch.yml'),yaml.dump([{id,config:value[id]}]),{flag:'wx'});
  if(credentials){
    const copied=selectedCredentials(fs.readFileSync(credentials,'utf8'),resolved?.apiKeyEnv??selectedRoute.apiKeyEnv??'DEEPSEEK_API_KEY');
    fs.writeFileSync(path.join(home,'.credentials.yaml'),yaml.dump(copied),{flag:'wx',mode:0o600});
  }
  console.log(JSON.stringify({provider,model,catalogName:selectedRoute.models[0].name??model,
    inputModalities:id==='llm-deepseek'?selectedRoute.models[0].inputModalities:selectedRoute.models[0].input,
    baseURL:resolved?.baseURL??selectedRoute.baseURL,
    scope:'Selected provider configuration and credential reference only; no other provider or browser credentials copied'}));
}
