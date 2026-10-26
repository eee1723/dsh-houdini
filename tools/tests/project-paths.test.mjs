import assert from 'node:assert/strict'
import os from 'node:os'
import path from 'node:path'
import {imageOutputLocation,projectDirectoryPath} from '../../lib/project-paths.js'

const root=path.resolve(os.tmpdir(),'dsh-project-path-contract')
for(const filename of ['atelier_v003.hip','repair_v003.hiplc','repair_v004.hipnc','项目.$F literal.hip']) {
  const hip=path.join(root,filename), stem=path.basename(filename,path.extname(filename))
  assert.equal(projectDirectoryPath(root,'render',hip),path.join(root,'dsh-artifacts/renders',stem))
  assert.equal(projectDirectoryPath(root,'visual_check',hip),path.join(root,'dsh-artifacts/checks/previews',stem))
  assert.equal(projectDirectoryPath(root,'execution_run',hip),path.join(root,'dsh-artifacts/checks/runs'))
  assert.equal(projectDirectoryPath(root,'texture',hip),path.join(root,'dsh-artifacts/textures'))
}
for(const hip of [undefined,'relative.hip'])
  assert.throws(()=>projectDirectoryPath(root,'render',hip),/named absolute HIP/)

// The copied HIP is its own explicit anchor. No history lookup or path search
// retargets isolated output to the source directory.
const copiedRoot=path.join(root,'run','inputs'), copiedHip=path.join(copiedRoot,'atelier_v003.hip')
assert.equal(projectDirectoryPath(copiedRoot,'render',copiedHip),path.join(copiedRoot,'dsh-artifacts/renders/atelier_v003'))
const original=projectDirectoryPath(root,'render',path.join(root,'atelier_v003.hip'))
assert.notEqual(projectDirectoryPath(root,'render',path.join(root,'atelier_v004.hip')),original)

// Explicit destinations remain caller intent and need no HIP observation.
const explicit=await imageOutputLocation({output:'dsh-artifacts/renders/old.png',output_policy:'explicit'},
  ()=>{throw Error('explicit output must not inspect Houdini')})
assert.equal(explicit.filename,'dsh-artifacts/renders/old.png')
assert.equal(explicit.artifact.managed_root,null)
console.log('Project directory HIP scopes passed')
