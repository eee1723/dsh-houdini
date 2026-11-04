#!/usr/bin/env node
/** Externalize a self-contained glTF 2 container without interpreting/remeshing
 * its geometry. Native Houdini importers remain the geometry/material consumer. */
import fs from 'node:fs/promises'
import path from 'node:path'
import {createHash} from 'node:crypto'
import {fileURLToPath} from 'node:url'

const extensions={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp'}
const integer=value=>Number.isSafeInteger(value)&&value>=0
const hash=bytes=>createHash('sha256').update(bytes).digest('hex')

export function planGlb(bytes) {
  if(!Buffer.isBuffer(bytes)||bytes.length<20||bytes.readUInt32LE(0)!==0x46546c67||bytes.readUInt32LE(4)!==2)
    throw Error('Expected a glTF 2 binary container (.glb)')
  if(bytes.readUInt32LE(8)!==bytes.length)throw Error('GLB declared length does not match the file')
  let json,bin
  for(let offset=12;offset<bytes.length;){
    if(offset+8>bytes.length)throw Error('Incomplete GLB chunk header')
    const length=bytes.readUInt32LE(offset),type=bytes.readUInt32LE(offset+4);offset+=8
    if(length%4||offset+length>bytes.length)throw Error('Invalid GLB chunk length/alignment')
    const data=bytes.subarray(offset,offset+length);offset+=length
    if(type===0x4e4f534a){if(json)throw Error('Duplicate GLB JSON chunk');json=data}
    else if(type===0x004e4942){if(bin)throw Error('Duplicate GLB BIN chunk');bin=data}
    else throw Error('Unsupported GLB chunk type: '+type)
  }
  if(!json)throw Error('GLB has no JSON chunk')
  const document=JSON.parse(json.toString('utf8').trim())
  if(document?.asset?.version!=='2.0')throw Error('Expected glTF asset.version 2.0')
  const buffers=document.buffers??[],files=[]
  if(buffers.length>1||buffers.some(buffer=>buffer.uri!==undefined))
    throw Error('Only a self-contained GLB is supported; external buffers require an explicit dependency-aware importer')
  if(buffers.length){
    if(!bin||!integer(buffers[0].byteLength)||buffers[0].byteLength>bin.length)throw Error('GLB binary buffer is missing or incomplete')
    files.push({name:'scene.bin',data:bin})
    document.buffers=[{...buffers[0],uri:'scene.bin'}]
  }
  const imageFacts=[]
  document.images=(document.images??[]).map((original,index)=>{
    let data,mime=original.mimeType
    if(original.bufferView!==undefined){
      if(original.uri!==undefined)throw Error('Image cannot declare both bufferView and uri')
      const view=document.bufferViews?.[original.bufferView],offset=view?.byteOffset??0
      if(!integer(original.bufferView)||!view||view.buffer!==0||!buffers.length||!bin||!integer(offset)||!integer(view.byteLength)
        ||offset+view.byteLength>buffers[0]?.byteLength)throw Error('Invalid embedded image buffer view at image '+index)
      data=bin.subarray(offset,offset+view.byteLength)
    }else{
      const match=typeof original.uri==='string'&&original.uri.match(/^data:(image\/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/]*={0,2})$/)
      if(!match)throw Error('Only embedded images are supported; external image at index '+index)
      mime=match[1];data=Buffer.from(match[2],'base64')
      if(data.toString('base64').replace(/=+$/,'')!==match[2].replace(/=+$/,''))throw Error('Invalid base64 image '+index)
    }
    const extension=extensions[mime]
    if(!extension||!data.length)throw Error('Unsupported/empty embedded image at index '+index+': '+mime)
    const name='image-'+String(index).padStart(3,'0')+extension
    files.push({name,data});imageFacts.push({index,mime,file:name,bytes:data.length,sha256:hash(data)})
    const {bufferView:_,uri:__,...metadata}=original
    return {...metadata,uri:name}
  })
  const output=Buffer.from(JSON.stringify(document,null,2)+'\n')
  files.push({name:'scene.gltf',data:output})
  return {document,files,summary:{source_sha256:hash(bytes),source_bytes:bytes.length,
    images:imageFacts,materials:document.materials??[],textures:document.textures??[],
    scenes:document.scenes??[],nodes:document.nodes??[],extensions_used:document.extensionsUsed??[],
    mesh_count:document.meshes?.length??0,
    scope:'Container/resource preparation only. Original BIN bytes, accessors, mesh topology, node transforms, material factors, texture indices, samplers and extensions are preserved. No geometry evaluation, texture conversion, appearance verification or network access.'}}
}

export async function prepareGlb(input,output,{inspect=false}={}) {
  const source=path.resolve(input),bytes=await fs.readFile(source),plan=planGlb(bytes)
  if(inspect)return {ok:true,source,...plan.summary,planned_files:plan.files.map(f=>({file:f.name,bytes:f.data.length}))}
  if(!output)throw Error('--out requires a new output directory')
  const destination=path.resolve(output)
  await fs.mkdir(destination) // Exclusive directory; existing assets are never overwritten.
  for(const file of plan.files)await fs.writeFile(path.join(destination,file.name),file.data,{flag:'wx'})
  return {ok:true,source,...plan.summary,output_gltf:path.join(destination,'scene.gltf'),
    files:plan.files.map(file=>({path:path.join(destination,file.name),bytes:file.data.length,sha256:hash(file.data)}))}
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const args=process.argv.slice(2)
  if(args.includes('--help'))console.log('node prepare-glb.mjs --input <asset.glb> [--inspect | --out <new-directory>]\nOffline preparation of embedded PNG/JPEG/WebP images and the original binary buffer; no generation, remesh or file overwrite.')
  else try{
    let input,output,inspect=false
    for(let i=0;i<args.length;i++){
      if(args[i]==='--input')input=args[++i]
      else if(args[i]==='--out')output=args[++i]
      else if(args[i]==='--inspect')inspect=true
      else throw Error('Unknown argument: '+args[i])
    }
    if(!input||inspect&&output)throw Error('Use --input with either --inspect or --out')
    console.log(JSON.stringify(await prepareGlb(input,output,{inspect})))
  }catch(error){console.error(JSON.stringify({ok:false,error:String(error)}));process.exitCode=1}
}
