import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {spawn} from 'node:child_process'
import {once} from 'node:events'
import {pathToFileURL} from 'node:url'
import {processStarted,acquireDesktopLease} from '../../lib/desktop-process.js'

const directory=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-desktop-lease-'))
const root=path.join(directory,'home'),other=path.join(directory,'other-home')
const owned=[]
const occupied=error=>error.code==='EADDRINUSE'
let first,second
function childLease(root) {
  const source=`import {acquireDesktopLease} from ${JSON.stringify(pathToFileURL(path.resolve('lib/desktop-process.js')).href)};
const lease=await acquireDesktopLease(process.argv[1]);process.send({state:'acquired'});
process.on('message',async message=>{if(message==='close'){await lease.close();process.send({state:'closed'});process.disconnect()}});`
  const child=spawn(process.execPath,['--input-type=module','-e',source,root],{stdio:['ignore','ignore','pipe','ipc'],windowsHide:true})
  owned.push(child)
  return child
}
try {
  if(process.platform==='win32') {
    const birth=await processStarted(process.pid,'a-nonexistent-hfs-must-not-be-read')
    assert.match(birth,/^\d+$/)
    assert.equal(await processStarted(process.pid),birth,'birth identity is stable without launching an interpreter')
    const probe=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{windowsHide:true,stdio:'ignore'});owned.push(probe)
    const exited=once(probe,'exit')
    assert.match(await processStarted(probe.pid),/^\d+$/)
    probe.kill();await exited
    assert.equal(await processStarted(probe.pid),null,'an exited process does not remain alive through a cached birth time')
  }else assert.equal(await processStarted(process.pid),null,'unsupported birth observation is explicitly unknown')
  await assert.rejects(processStarted(0),/process id/)
  await assert.rejects(acquireDesktopLease('relative'),/absolute/)
  first=await acquireDesktopLease(root)
  await assert.rejects(acquireDesktopLease(root),occupied)
  await assert.rejects(acquireDesktopLease(root),occupied,'a failed acquisition cannot release the original owner')
  const alias=process.platform==='win32'?root.toUpperCase():path.join(root,'..',path.basename(root))
  await assert.rejects(acquireDesktopLease(alias),occupied,'canonical aliases share one OS lease')
  second=await acquireDesktopLease(other)
  await Promise.all([first.close(),first.close()]);first=undefined
  first=await acquireDesktopLease(root);await first.close();first=undefined
  const owner=childLease(root),message=await once(owner,'message')
  assert.equal(message[0].state,'acquired')
  await assert.rejects(acquireDesktopLease(root),occupied,'a different live process owns the same lease')
  const exit=once(owner,'exit');owner.kill();await exit
  first=await acquireDesktopLease(root)
  assert.deepEqual(await fs.readdir(root),[],'OS lifetime exclusion leaves no lock or PID artifact')
  await first.close();first=undefined
  console.log('Desktop process: OS birth identity, canonical-root mutual exclusion, foreign owner, crash release and idempotent close passed')
}finally{
  await first?.close();await second?.close()
  for(const child of owned)if(child.exitCode===null&&!child.killed){const exit=once(child,'exit');child.kill();await exit}
  assert.equal(path.dirname(directory),path.resolve(os.tmpdir()))
  assert.ok(path.basename(directory).startsWith('dsh-desktop-lease-'))
  await fs.rm(directory,{recursive:true,force:true})
}
