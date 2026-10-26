import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {evaluatePluginCompatibility,readPluginMeta} from '@deepseek-ai/dsh-app-boot';
import {pathToFileURL} from 'node:url';

const root=path.resolve(import.meta.dirname,'../..');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
const policy=JSON.parse(fs.readFileSync(path.join(root,'dsh-runtime-compatibility.json'),'utf8'));
const fixture=JSON.parse(fs.readFileSync(path.join(root,'deployment/package.json'),'utf8'));
assert.equal(manifest.engines.dsh,policy.preferredVersion);
assert.equal(fixture.dependencies['@deepseek-ai/dsh'],policy.preferredVersion);
assert.equal(policy.runtimeOwnership,'host');
assert.equal(policy.runtimeFixes,undefined);
assert.ok(manifest.files.includes('runtime/video'),'formal plugin packaging retains the source-complete tutorial media resources');
assert.equal(evaluatePluginCompatibility(manifest,{},policy.preferredVersion),undefined,
  'the official host must admit the plugin using its ordinary compatibility check');
assert.ok(evaluatePluginCompatibility(manifest,{},'0.2.0-rc.2'),
  'an unqualified host is rejected by the official check, without replacing its runtime');
assert.equal(Object.keys(manifest.dependencies??{}).some(name=>name==='@deepseek-ai/dsh'||name.startsWith('@deepseek-ai/dsh-')),false,
  'host packages belong to peer/development requirements, never bundled plugin dependencies');
for(const name of ['@deepseek-ai/dsh-home-paths','@deepseek-ai/dsh-typert-protocol','@deepseek-ai/schemastery'])
  assert.ok(manifest.peerDependencies[name],`the official resolver can supply runtime import ${name}`);
const meta=readPluginMeta('dsh-houdini',pathToFileURL(root+path.sep));
assert.equal(meta.title.en,'DSH Houdini');
assert.equal(meta.title.zh,'DSH Houdini');
assert.ok(meta.description.en&&meta.description.zh);
assert.match(meta.icon,/^data:image\/png;base64,/);
const npm=process.env.npm_execpath??path.join(path.dirname(process.execPath),'node_modules/npm/bin/npm-cli.js');
const packed=spawnSync(process.execPath,[npm,'pack','--dry-run','--ignore-scripts','--json','--cache='+path.join(root,'.npm-cache')],{cwd:root,encoding:'utf8',windowsHide:true});
assert.ifError(packed.error);
assert.equal(packed.status,0,packed.stderr);
const files=JSON.parse(packed.stdout)[0].files.map(row=>row.path);
assert.ok(files.includes('lib/frontend-host.js'));
assert.ok(files.includes('presets/houdini/cordis.patch.yml'));
for(const file of ['assets/dsh-houdini-plugin.png','locale/en.json','locale/zh.json'])assert.ok(files.includes(file),'package omits '+file);
assert.ok(fs.statSync(path.join(root,'assets/dsh-houdini-plugin.png')).size<=256*1024,'official icon size limit');
assert.equal(files.some(file=>/^(deployment\/|node_modules\/|\.npm-cache\/)/.test(file)),false,
  'the distributable bundle must not carry a private DSH install, lock or core patch');
assert.equal(files.some(file=>/runtime-fix|prepare-dsh-runtime|build-dsh-runtime|shared-host\.cordis|dsh-profile\.requirements/.test(file)),false);
console.log('Official host compatibility admission and runtime-free Desktop plugin package verified');
