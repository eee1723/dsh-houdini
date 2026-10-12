/** Compile the declared upstream source patch into an isolated exact DSH install. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {build} from 'esbuild';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const [sourceArg,targetArg,buildToolsArg,mode]=process.argv.slice(2);
const development=mode==='--development';
if(mode!==undefined&&!development)throw Error('Unknown build mode');
if(!sourceArg||!targetArg||!buildToolsArg)throw Error('usage: node tools/build-dsh-runtime-fixes.mjs <patched-source> <runtime-root> <build-tools>');
const source=path.resolve(sourceArg),target=path.resolve(targetArg),buildTools=path.resolve(buildToolsArg);
if(development&&!target.startsWith(path.join(root,'tools','out')+path.sep))throw Error('Development runtime must be under tools/out');
if(development)fs.rmSync(path.join(target,'.dsh-runtime-fixes.json'),{force:true});
const specification=path.join(root,'deployment/dsh-runtime-fixes');
const manifest=JSON.parse(fs.readFileSync(path.join(specification,'manifest.json'),'utf8'));
const sha=value=>createHash('sha256').update(value).digest('hex');
const patchSha256=sha(fs.readFileSync(path.join(specification,manifest.patch)));
if(patchSha256!==manifest.patchSha256)throw Error('Runtime source patch differs from its declared SHA-256');
const installed=JSON.parse(fs.readFileSync(path.join(target,'node_modules/@deepseek-ai/dsh/package.json'),'utf8'));
if(installed.version!==manifest.dshVersion)throw Error('Runtime patch requires the exact declared DSH version');
if(!development){
 const head=spawnSync('git',['rev-parse','HEAD'],{cwd:source,encoding:'utf8',windowsHide:true});
 if(head.status!==0||head.stdout.trim()!==manifest.commit)throw Error('Build source is not the pinned upstream commit');
 // New files produced by git apply must participate in the exact diff, too.
 const intent=spawnSync('git',['add','-N','--','packages'],{cwd:source,windowsHide:true});
 if(intent.status!==0)throw Error('Cannot include added source files in build identity');
 const diff=spawnSync('git',['diff','--binary','HEAD'],{cwd:source,windowsHide:true,maxBuffer:32*1024*1024});
 if(diff.status!==0||sha(diff.stdout)!==patchSha256)throw Error('Build source differs from the declared patch; no completion marker written');
}
function run(program,args,options={}){
 const r=spawnSync(program,args,{cwd:root,encoding:'utf8',windowsHide:true,...options});
 if(r.error)throw r.error;
 if(r.status!==0)throw Error(`${path.basename(program)} failed (${r.status}):\n${r.stdout??''}\n${r.stderr??''}`);
 return r.stdout??'';
}
const link=path.join(source,'node_modules');
if(!fs.existsSync(link))fs.symlinkSync(path.join(target,'node_modules'),link,'junction');
if(fs.realpathSync(link)!==fs.realpathSync(path.join(target,'node_modules')))throw Error('Source dependencies belong to a different runtime; use a fresh prepared source');
// Build-only dependencies live separately and are never copied into the release payload.
const sourceBuild=path.join(source,'.runtime-fix-build');fs.mkdirSync(sourceBuild,{recursive:true});
const linked=[];
function linkBuildPackage(name){
 const destination=path.join(target,'node_modules',name),origin=path.join(buildTools,'node_modules',name);
 if(fs.existsSync(destination))return;
 fs.mkdirSync(path.dirname(destination),{recursive:true});fs.symlinkSync(origin,destination,'junction');linked.push(destination);
}
for(const name of fs.readdirSync(path.join(buildTools,'node_modules'))){
 if(name.startsWith('.'))continue;
 if(name.startsWith('@'))for(const item of fs.readdirSync(path.join(buildTools,'node_modules',name)))linkBuildPackage(name+'/'+item);
 else linkBuildPackage(name);
}
const files={};
try{
 for(const pkg of manifest.hostPackages){
  const location=path.join(source,'packages',pkg.source),output=path.join(target,'node_modules/@deepseek-ai/dsh-'+pkg.name,'lib');
  const config=path.join(sourceBuild,pkg.name+'.json');
  fs.writeFileSync(config,JSON.stringify({compilerOptions:{target:'ES2024',module:'NodeNext',moduleResolution:'NodeNext',strict:true,skipLibCheck:true,
   allowImportingTsExtensions:true,rewriteRelativeImportExtensions:true,declaration:true,rootDir:path.join(location,'src'),outDir:path.join(output,'types'),types:['node'],
   typeRoots:[path.join(root,'node_modules/@types'),path.join(buildTools,'node_modules/@types')]},
   include:[...pkg.entries.map(e=>path.join(location,'src',e+'.ts')),path.join(location,'src/*.d.ts')]}));
  run(process.execPath,[path.join(root,'node_modules/typescript/bin/tsc'),'-p',config]);
  const result=await build({entryPoints:Object.fromEntries(pkg.entries.map(e=>[e,path.join(output,'types',e+'.js')])),outdir:output,format:'esm',platform:'node',target:'node24',
   bundle:true,splitting:true,packages:'external',chunkNames:'types-[hash]',metafile:true,logLevel:'warning'});
  for(const filename of Object.keys(result.metafile.outputs)){const full=path.resolve(root,filename);files[path.relative(target,full).replaceAll('\\','/')]=sha(fs.readFileSync(full));}
  for(const relative of pkg.assets??[]){
   const full=path.join(path.dirname(output),relative);fs.mkdirSync(path.dirname(full),{recursive:true});fs.copyFileSync(path.join(location,relative),full);
   files[path.relative(target,full).replaceAll('\\','/')]=sha(fs.readFileSync(full));
  }
  console.log('Compiled DSH fix:',pkg.name);
 }
 const tsdownRequire=createRequire(path.join(buildTools,'package.json'));
 for(const name of manifest.clientPackages){
  const config=path.join(sourceBuild,name+'.config.ts');
  const preset=pathToFileURL(path.join(source,'packages/client/tsdown.client.ts')).href;
  const entry=path.join(source,'packages/client',name,'src/client/index.ts');
  const output=path.join(target,'node_modules/@deepseek-ai/dsh-client-'+name,'lib');
  fs.writeFileSync(config,`import {clientBundle} from ${JSON.stringify(preset)};\nconst rows=clientBundle('@deepseek-ai/dsh-client-${name}',[])({env:{}});\nconst base=rows[rows.length-1];\nexport default {...base,inputOptions:{...base.inputOptions,onwarn(warning,handler){if(warning.code==='UNRESOLVED_IMPORT')throw new Error(warning.message);handler(warning)}},entry:{client:${JSON.stringify(entry)}},outDir:${JSON.stringify(output)}};\n`);
  run(process.execPath,[tsdownRequire.resolve('tsdown/run'),'--config',config],{cwd:source});
  // Locale namespaces are consumed through the installed declaration surface too.
  const locales=path.join(path.dirname(entry),'locales.ts');
  if(fs.existsSync(locales)){
   const config=path.join(sourceBuild,name+'-locales.json');
   fs.writeFileSync(config,JSON.stringify({compilerOptions:{target:'ES2024',module:'NodeNext',moduleResolution:'NodeNext',strict:true,skipLibCheck:true,
    declaration:true,emitDeclarationOnly:true,rootDir:path.dirname(locales),outDir:path.join(output,'types/client'),types:[]},files:[locales]}));
   run(process.execPath,[path.join(root,'node_modules/typescript/bin/tsc'),'-p',config]);
   const declaration=path.join(output,'types/client/locales.d.ts');files[path.relative(target,declaration).replaceAll('\\','/')]=sha(fs.readFileSync(declaration));
  }
  for(const filename of ['client.js','client.js.map']){const full=path.join(output,filename);files[path.relative(target,full).replaceAll('\\','/')]=sha(fs.readFileSync(full));}
  console.log('Compiled DSH client fix:',name);
 }
 const proof=path.join(target,'dsh-runtime-fixes');fs.mkdirSync(proof,{recursive:true});
 for(const name of ['manifest.json',manifest.patch])fs.copyFileSync(path.join(specification,name),path.join(proof,name));
 fs.copyFileSync(path.join(source,'LICENSE'),path.join(proof,'UPSTREAM-LICENSE'));
 if(!development)fs.writeFileSync(path.join(target,'.dsh-runtime-fixes.json'),JSON.stringify({schemaVersion:1,revision:manifest.revision,dshVersion:manifest.dshVersion,
  sourceCommit:manifest.commit,patchSha256,files},null,2)+'\n');
}finally{
 // These are only the junctions this build created, never package directories.
 for(const link of linked.reverse())if(fs.lstatSync(link).isSymbolicLink())fs.unlinkSync(link);
}
