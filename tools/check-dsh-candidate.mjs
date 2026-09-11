/** Read-only candidate API checks. No profile migration, model call or live restart.
 * Usage: node tools/check-dsh-candidate.mjs --candidate <npm-project> --plugin <unpacked-plugin>
 * Module import is diagnostic only; it never overrides npm peer admission.
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {collectRequestTelemetry} from './trace-session-lib.mjs';

const args=process.argv.slice(2);
const option=name=>args[args.indexOf(name)+1];
if (!args.includes('--candidate') || !args.includes('--plugin')) {
  throw Error('requires --candidate <npm-project> --plugin <unpacked-plugin>');
}
const candidate=path.resolve(option('--candidate'));
const plugin=path.resolve(option('--plugin'));
const require=createRequire(path.join(candidate,'package.json'));
// Do not let imported candidate packages resolve the user's real Harness home.
process.env.DSH_HOME=path.join(os.tmpdir(),'dsh-candidate-readonly-'+process.pid);
const load=async name=>import(pathToFileURL(require.resolve(name)).href);
const manifest=JSON.parse(fs.readFileSync(path.join(plugin,'package.json'),'utf8'));
const clean=error=>String(error).replace(/Bearer\s+\S+|([?&]token=)[^&\s]+/gi,'[redacted]');
const report={candidateVersion:require('@deepseek-ai/dsh/package.json').version,
  pluginVersion:manifest.version,checks:[],notTested:['live Houdini WebView','authenticated RPC','old-session migration','model behavior']};
const semver=require('semver');
for(const [name,range] of Object.entries(manifest.peerDependencies||{})) {
  try {
    const actual=require(name+'/package.json').version;
    report.checks.push({id:'peer:'+name,ok:semver.satisfies(actual,range),expected:range,actual});
  } catch(error) {report.checks.push({id:'peer:'+name,ok:false,error:clean(error)});}
}
try {
  const module=await import(pathToFileURL(path.join(plugin,manifest.main)).href);
  report.checks.push({id:'plugin-module-import',ok:module.name==='dsh-houdini',scope:'import only, not application startup'});
} catch(error) {report.checks.push({id:'plugin-module-import',ok:false,error:clean(error)});}
const persona=await load('@deepseek-ai/dsh-persona');
for(const preset of ['houdini','houdini-dev']) {
  const source=fs.readFileSync(path.join(plugin,'presets',preset,'agent.cordis.yml'),'utf8');
  // Parse only the persona row, never evaluate the other rows' !!js expressions.
  const yaml=require('js-yaml');
  const row=source.match(/^- id: persona\r?\n[\s\S]*?(?=^- id:|$(?![\s\S]))/m)?.[0];
  const config=row ? yaml.load(row)[0].config : null;
  const field=typeof config?.prefix==='string'?'prefix':typeof config?.text==='string'?'text':null;
  try {
    if(!field) throw Error('unrecognized persona config; inspect the preset explicitly');
    const parsed=persona.Config(config);
    if(parsed[field]!==config[field]) throw Error('persona content changed during schema validation');
    report.checks.push({id:'persona:'+preset,ok:true,field});
  } catch(error) {report.checks.push({id:'persona:'+preset,ok:false,field,error:clean(error)});}
}
const session=await load('@deepseek-ai/dsh-session');
report.sessionFormatVersion=session.SESSION_FORMAT_VERSION;
if(session.SESSION_FORMAT_VERSION===3) {
  const usage={inputTokens:10,outputTokens:2,cacheReadTokens:0,cacheWriteTokens:0,totalTokens:12};
  const result=collectRequestTelemetry([{seq:1,time:1000,type:'assistant/message',
    data:{turn:1,step:1,message:{role:'assistant',content:[]},stream:[],usage}}]);
  report.checks.push({id:'trace-v3-settled-usage',ok:result.requestCount===1,
    expectedRequests:1,observedRequests:result.requestCount,scope:'V3 settled usage fixture, not whole-format certification'});
}
const boot=await load('@deepseek-ai/dsh-app-boot');
for(const name of ['resolveProfileDir','initProfile','readProfileManifest','loadProfile','composeEntries']) {
  report.checks.push({id:'managed-boot-export:'+name,ok:typeof boot[name]==='function',scope:'export presence only'});
}
const slotFile=path.join(path.dirname(require.resolve('@deepseek-ai/dsh-client-ui-conversation/package.json')),
  'lib/types/client/contract/slots.d.ts');
if(fs.existsSync(slotFile)) {
  const slots=fs.readFileSync(slotFile,'utf8');
  for(const name of ['conversation.view','conversation.composer.dock']) {
    report.checks.push({id:'declared-client-slot:'+name,ok:slots.includes("'"+name+"'"),scope:'type contract only, not GUI acceptance'});
  }
}
report.compatible=report.checks.every(c=>c.ok);
report.promotePreferred=false;
console.log(JSON.stringify(report,null,2));
process.exitCode=report.compatible?0:1;
