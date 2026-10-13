/** Prepare a patched runtime separately; never rewrite a running DSH installation. */
import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';import {createHash,randomUUID} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const specification=path.join(root,'deployment/dsh-runtime-fixes');
const manifest=JSON.parse(fs.readFileSync(path.join(specification,'manifest.json'),'utf8'));
const patch=path.join(specification,manifest.patch),patchSha256=createHash('sha256').update(fs.readFileSync(patch)).digest('hex');
if(patchSha256!==manifest.patchSha256)throw Error('Runtime source patch differs from its declared SHA-256');
const args=process.argv.slice(2);const apply=args.indexOf('--apply-to');
if(args.length && (apply!==0||args.length!==2))throw Error('usage: npm run runtime:prepare, or --apply-to <new release app directory>');
const target=apply===0?path.resolve(args[1]):path.join(root,'.npm-cache/_npx/dsh-houdini-'+patchSha256.slice(0,12));
const marker=path.join(target,'.dsh-runtime-fixes.json');
const hash=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
if(fs.existsSync(marker)){
 const data=JSON.parse(fs.readFileSync(marker,'utf8'));
 const required=manifest.hostPackages.flatMap(p=>[...p.entries.map(e=>`node_modules/@deepseek-ai/dsh-${p.name}/lib/${e}.js`),...(p.assets??[]).map(a=>`node_modules/@deepseek-ai/dsh-${p.name}/${a}`)])
  .concat(manifest.clientPackages.map(pkg=>`node_modules/@deepseek-ai/dsh-${pkg.name}/lib/client.js`));
 if(data.patchSha256!==patchSha256||data.dshVersion!==manifest.dshVersion||!data.files||!required.every(name=>name in data.files)||!Object.entries(data.files).every(([name,value])=>fs.existsSync(path.join(target,name))&&hash(path.join(target,name))===value))throw Error('Prepared runtime integrity mismatch; preserve it and build in a new revision directory');
 console.log('Verified prepared runtime:',path.join(target,'node_modules/@deepseek-ai/dsh/lib/bin.js'));process.exit(0);
}
function run(program,argv,cwd=root){const r=spawnSync(program,argv,{cwd,stdio:'inherit',windowsHide:true});if(r.error)throw r.error;if(r.status!==0)throw Error(`${program} failed with exit ${r.status}`);}
const npm=path.join(path.dirname(process.execPath),'node_modules/npm/bin/npm-cli.js');
if(!fs.existsSync(npm))throw Error('The selected Node must include its npm CLI');
const work=path.join(root,'tools/out/runtime-fixes',patchSha256.slice(0,12)+'-'+randomUUID().slice(0,8));fs.mkdirSync(work,{recursive:true});
if(apply!==0){
 if(fs.existsSync(target)&&fs.readdirSync(target).length)throw Error('Incomplete runtime directory exists: '+target+'; preserve it and inspect before retrying');
 fs.mkdirSync(target,{recursive:true});
 for(const name of ['package.json','package-lock.json'])fs.copyFileSync(path.join(root,'deployment',name),path.join(target,name));
 run(process.execPath,[npm,'ci','--omit=dev','--ignore-scripts','--no-audit','--no-fund'],target);
}
const source=path.join(work,'source');
run('git',['clone','--filter=blob:none','--no-checkout','--depth','1','--branch',manifest.tag,manifest.repository,source]);
run('git',['sparse-checkout','init','--cone'],source);
run('git',['sparse-checkout','set',...new Set([...manifest.hostPackages,...manifest.clientPackages].map(pkg=>'packages/'+pkg.source)),'packages/client/modules','packages/client/web','docs','scripts'],source);
run('git',['checkout'],source);
const commit=spawnSync('git',['rev-parse','HEAD'],{cwd:source,encoding:'utf8',windowsHide:true});
if(commit.status!==0||commit.stdout.trim()!==manifest.commit)throw Error('Upstream tag did not resolve to the pinned source commit');
run('git',['apply','--check',patch],source);run('git',['apply',patch],source);
const buildTools=path.join(work,'build-tools');fs.mkdirSync(buildTools);
fs.copyFileSync(path.join(specification,'build-package.json'),path.join(buildTools,'package.json'));
fs.copyFileSync(path.join(specification,'build-package-lock.json'),path.join(buildTools,'package-lock.json'));
run(process.execPath,[npm,'ci','--ignore-scripts','--no-audit','--no-fund'],buildTools);
run(process.execPath,[path.join(root,'tools/build-dsh-runtime-fixes.mjs'),source,target,buildTools]);
console.log('Prepared runtime:',path.join(target,'node_modules/@deepseek-ai/dsh/lib/bin.js'));
console.log('Existing Host and Houdini processes were not restarted.');
