import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {runtimeFixInputs,runtimeFixKey} from '../runtime-fix-inputs.mjs';
import {resolvePython} from './python-runtime.mjs';

const root=path.resolve(import.meta.dirname,'../..');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'deployment/dsh-runtime-fixes/manifest.json')));
const inputs=runtimeFixInputs(root,manifest);
const python=spawnSync(resolvePython(),['-c',
  "import json,sys;sys.path.insert(0,'houdini/python3.11libs');import dsh_runtime_compat;print(json.dumps(dsh_runtime_compat.runtime_fix_inputs()))"],
  {cwd:root,encoding:'utf8',windowsHide:true});
assert.equal(python.status,0,python.stderr);
assert.deepEqual(JSON.parse(python.stdout),inputs,'builder and launcher must consume identical input identities');
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-runtime-inputs-'));
try {
  for(const name of manifest.inputFiles) {
    const file=path.join(dir,name);fs.mkdirSync(path.dirname(file),{recursive:true});
    fs.copyFileSync(path.join(root,name),file);
  }
  assert.equal(runtimeFixKey(runtimeFixInputs(dir,manifest)),runtimeFixKey(inputs));
  const lock=path.join(dir,'deployment/package-lock.json');
  const data=JSON.parse(fs.readFileSync(lock));data.packages['node_modules/fflate'].version='0.8.2';
  fs.writeFileSync(lock,JSON.stringify(data));
  assert.notEqual(runtimeFixKey(runtimeFixInputs(dir,manifest)),runtimeFixKey(inputs),
    'a changed dependency lock must select a new runtime even when the upstream patch is unchanged');
} finally {
  assert.equal(path.dirname(dir),fs.realpathSync(os.tmpdir()));
  fs.rmSync(dir,{recursive:true,force:true});
}
console.log('runtime inputs: Node/Python identity parity and dependency-only cache invalidation passed');
