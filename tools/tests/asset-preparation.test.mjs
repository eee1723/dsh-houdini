import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {planGlb,prepareGlb} from '../../skills/houdini-asset-integration/scripts/prepare-glb.mjs'

const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+p8AAAAASUVORK5CYII=','base64')
const buffer=Buffer.concat([Buffer.alloc(36),png])
const material={name:'material',pbrMetallicRoughness:{baseColorFactor:[.2,.3,.4,1],metallicFactor:.7,roughnessFactor:.8,baseColorTexture:{index:0,texCoord:1}},normalTexture:{index:0,scale:.5}}
const document={asset:{version:'2.0'},buffers:[{byteLength:buffer.length}],bufferViews:[{buffer:0,byteLength:36},{buffer:0,byteOffset:36,byteLength:png.length}],
  images:[{name:'user/image/name',bufferView:1,mimeType:'image/png'}],materials:[material],textures:[{source:0,sampler:0}],samplers:[{wrapS:33071}],
  accessors:[{bufferView:0,count:3,type:'VEC3',componentType:5126}],meshes:[{primitives:[{attributes:{POSITION:0},material:0}]}],
  scenes:[{nodes:[0]}],nodes:[{mesh:0,translation:[2,3,4]}],scene:0,extensionsUsed:['KHR_materials_ior']}
function glb(doc=document,bin=buffer){
  const json=Buffer.from(JSON.stringify(doc)),a=Buffer.concat([json,Buffer.alloc((-json.length>>>0)%4,32)]),b=Buffer.concat([bin,Buffer.alloc((-bin.length>>>0)%4)])
  const result=Buffer.alloc(12+8+a.length+8+b.length)
  result.writeUInt32LE(0x46546c67,0);result.writeUInt32LE(2,4);result.writeUInt32LE(result.length,8)
  result.writeUInt32LE(a.length,12);result.writeUInt32LE(0x4e4f534a,16);a.copy(result,20)
  result.writeUInt32LE(b.length,20+a.length);result.writeUInt32LE(0x004e4942,24+a.length);b.copy(result,28+a.length)
  return result
}
const bytes=glb(),original=Buffer.from(bytes),plan=planGlb(bytes)
assert.deepEqual(bytes,original)
for(const field of ['accessors','meshes','nodes','materials','textures','samplers','extensionsUsed'])assert.deepEqual(plan.document[field],document[field],field)
assert.deepEqual(plan.files.find(f=>f.name==='image-000.png').data,png)
assert.deepEqual(plan.files.find(f=>f.name==='scene.bin').data.subarray(0,buffer.length),buffer)
assert.equal(plan.document.images[0].uri,'image-000.png')
assert.equal(plan.document.images[0].bufferView,undefined)
assert.equal(plan.document.buffers[0].uri,'scene.bin')
assert.equal(plan.document.images[0].name,'user/image/name','user labels never become file paths')
assert.deepEqual(plan.summary.mesh_primitives,[{mesh:0,primitive:0,mode:4,vertices:3,triangles:1,material:0,texcoord_sets:[]}])
const indexed=structuredClone(document)
indexed.accessors[0].min=[-2,0,-1]
indexed.accessors[0].max=[1,3,4]
indexed.accessors.push({count:6,type:'SCALAR'},{count:3,type:'VEC2'},{count:5,type:'SCALAR'})
indexed.meshes[0].primitives=[
  {indices:1,attributes:{POSITION:0,TEXCOORD_0:2,TEXCOORD_1:2},material:0},
  {mode:1,indices:1,attributes:{POSITION:0}},
  {mode:5,indices:3,attributes:{POSITION:0}}
]
const inventory=planGlb(glb(indexed)).summary.mesh_primitives
for(const row of inventory)assert.deepEqual(row.position_bounds,{min:[-2,0,-1],max:[1,3,4]},
  'base mesh declarations stay local even when scene nodes have their own transform')
assert.deepEqual(inventory.map(({position_bounds,...row})=>row),[
  {mesh:0,primitive:0,mode:4,vertices:3,triangles:2,material:0,texcoord_sets:['TEXCOORD_0','TEXCOORD_1']},
  {mesh:0,primitive:1,mode:1,vertices:3,triangles:null,material:null,texcoord_sets:[]},
  {mesh:0,primitive:2,mode:5,vertices:3,triangles:3,material:null,texcoord_sets:[]}
])
const dataUri=structuredClone(document);dataUri.images=[{uri:'data:image/png;base64,'+png.toString('base64')}]
assert.deepEqual(planGlb(glb(dataUri)).files.find(f=>f.name==='image-000.png').data,png)
const external=structuredClone(document);external.images=[{uri:'https://example.invalid/image.png'}]
assert.throws(()=>planGlb(glb(external)),/Only embedded images/)
const escaped=structuredClone(document);escaped.bufferViews[1].byteLength=buffer.length+10
assert.throws(()=>planGlb(glb(escaped)),/Invalid embedded/)
const noBuffer=structuredClone(document);noBuffer.buffers=[]
assert.throws(()=>planGlb(glb(noBuffer)),/Invalid embedded/)
assert.throws(()=>planGlb(bytes.subarray(0,bytes.length-1)),/declared length/)
const root=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-asset-prepare-'))
try{
  const input=path.join(root,'source.glb'),output=path.join(root,'prepared');await fs.writeFile(input,bytes)
  const inspected=await prepareGlb(input,undefined,{inspect:true})
  assert.equal(inspected.planned_files.length,3);assert.deepEqual(await fs.readdir(root),['source.glb'])
  assert.deepEqual(inspected.mesh_primitives,plan.summary.mesh_primitives)
  const result=await prepareGlb(input,output)
  assert.equal(result.output_gltf,path.join(output,'scene.gltf').split(path.sep).join('/'))
  assert.deepEqual(JSON.parse(await fs.readFile(result.output_gltf,'utf8')).materials,[material])
  await assert.rejects(prepareGlb(input,output),/EEXIST/)
  assert.deepEqual(await fs.readFile(input),bytes)
}finally{await fs.rm(root,{recursive:true,force:true})}
console.log('GLB preparation: original BIN/geometry/materials preserved, image extraction, read-only inspection, malformed/external inputs and no-overwrite passed')
