import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'../..');
const target=process.argv[2]?path.resolve(process.argv[2]):root;
const require=createRequire(path.join(target,'package.json'));
const consumer=require.resolve('@deepseek-ai/libreoffice-kit');
const entry=createRequire(consumer).resolve('fflate');
const {zipSync,unzipSync,strToU8,strFromU8}=require(entry);
const zip=zipSync({'word/document.xml':strToU8('<document>round trip</document>')},{level:0});
assert.equal(strFromU8(unzipSync(zip)['word/document.xml']),'<document>round trip</document>');
const damaged=Buffer.from(zip);
const central=damaged.indexOf(Buffer.from([0x50,0x4b,0x01,0x02]));
assert(central>=0);
damaged.writeUInt32LE(0xffffffff,central+20);
const end=damaged.length-22;
const zip64=Buffer.alloc(56),locator=Buffer.alloc(20);
zip64.writeUInt32LE(0x06064b50,0);zip64.writeBigUInt64LE(44n,4);
zip64.writeUInt16LE(45,12);zip64.writeUInt16LE(45,14);
zip64.writeBigUInt64LE(1n,24);zip64.writeBigUInt64LE(1n,32);
zip64.writeBigUInt64LE(BigInt(end-central),40);zip64.writeBigUInt64LE(BigInt(central),48);
locator.writeUInt32LE(0x07064b50,0);locator.writeBigUInt64LE(BigInt(end),8);locator.writeUInt32LE(1,16);
const malformed=Buffer.concat([damaged.subarray(0,end),zip64,locator,damaged.subarray(end)]);
// A malformed ZIP64 must reject instead of hanging a document preview worker.
const result=spawnSync(process.execPath,['--input-type=commonjs','-e',
  "const {unzipSync}=require(process.argv[1]);try{unzipSync(Buffer.from(process.argv[2],'base64'));process.exit(2)}catch(error){if(!/zip/i.test(error.message))throw error}",
  entry,malformed.toString('base64')],{encoding:'utf8',timeout:5000,windowsHide:true});
assert.ifError(result.error);
assert.equal(result.status,0,result.stderr);
for(const name of ['package.json','deployment/package.json']) {
  const manifest=JSON.parse(fs.readFileSync(path.join(root,name)));
  assert.equal(manifest.overrides['@deepseek-ai/libreoffice-kit'].fflate,'0.8.3');
}
console.log('document dependency: actual consumer ZIP round trip and malformed ZIP64 rejection passed');
