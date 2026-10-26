/** Prepare an unmodified official Host for isolated development, never for distribution. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const args=process.argv.slice(2);
if(args.some(arg=>arg!=='--json'))throw Error('usage: npm run runtime:prepare [-- --json]; this prepares a development fixture, not a distributable runtime');
const source=path.join(root,'deployment');
const manifest=JSON.parse(fs.readFileSync(path.join(source,'package.json'),'utf8'));
const policy=JSON.parse(fs.readFileSync(path.join(root,'dsh-runtime-compatibility.json'),'utf8'));
const version=manifest.dependencies?.['@deepseek-ai/dsh'];
if(version!==policy.preferredVersion)throw Error('Official Host fixture differs from the tested plugin compatibility target');
const digest=createHash('sha256');
for(const name of ['package.json','package-lock.json'])digest.update(name).update(fs.readFileSync(path.join(source,name)));
const inputsSha256=digest.digest('hex');
const target=path.join(root,'.npm-cache','_npx','dsh-houdini-official-'+version+'-'+inputsSha256.slice(0,16));
const marker=path.join(target,'.dsh-official-host.json');
const bin=path.join(target,'node_modules','@deepseek-ai','dsh','lib','bin.js');
if(!fs.existsSync(marker)) {
  if(fs.existsSync(target)&&fs.readdirSync(target).length)throw Error('Incomplete official Host fixture exists; preserve and inspect it: '+target);
  fs.mkdirSync(target,{recursive:true});
  for(const name of ['package.json','package-lock.json'])fs.copyFileSync(path.join(source,name),path.join(target,name));
  const npm=process.env.npm_execpath??path.join(path.dirname(process.execPath),'node_modules','npm','bin','npm-cli.js');
  if(!fs.existsSync(npm))throw Error('Run this preparation through npm or select a Node installation containing npm');
  const result=spawnSync(process.execPath,[npm,'ci','--omit=dev','--ignore-scripts','--no-audit','--no-fund',
    '--registry=https://registry.npmjs.org','--cache='+path.join(root,'.npm-cache')],
    {cwd:target,stdio:args.includes('--json')?['ignore','ignore','inherit']:'inherit',windowsHide:true});
  if(result.error)throw result.error;
  if(result.status!==0)throw Error('Official npm fixture installation failed with exit '+result.status);
  fs.writeFileSync(marker,JSON.stringify({schemaVersion:1,runtimeOwnership:'development-fixture',dshVersion:version,inputsSha256},null,2)+'\n');
}
const record=JSON.parse(fs.readFileSync(marker,'utf8'));
const installed=JSON.parse(fs.readFileSync(path.join(target,'node_modules','@deepseek-ai','dsh','package.json'),'utf8'));
if(record.runtimeOwnership!=='development-fixture'||record.dshVersion!==version||record.inputsSha256!==inputsSha256
  ||installed.version!==version||!fs.existsSync(bin))throw Error('Official Host fixture identity differs from its npm lock; preserve it and prepare a new fixture');
const prepared={runtime:target,bin,dshVersion:version,home:path.join(target,'test-home')};
if(args.includes('--json'))console.log(JSON.stringify(prepared));
else {
  console.log('Official development Host:',bin);
  console.log('Set an explicit disposable DSH_HOME before running it. The plugin package contains no DSH runtime.');
}
