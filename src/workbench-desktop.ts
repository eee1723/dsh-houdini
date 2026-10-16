import fs from 'node:fs/promises'
import path from 'node:path'

export async function desktopRequest(action:'presence'|'dialog',payload:unknown,signal:AbortSignal) {
  const location=process.env.DSH_HOUDINI_WORKBENCH_CONTEXT
  if(!location||!path.isAbsolute(location))throw new Error('请在独立工作台中使用此入口。')
  const context=JSON.parse(await fs.readFile(location,'utf8'))
  if(context.workbench!==true||typeof context.root!=='string'||!path.isAbsolute(context.root))throw new Error('工作台运行信息不可用，请重新打开工作台。')
  const descriptor=path.join(context.root,'workbench/desktop.json')
  if((await fs.stat(descriptor)).size>32768)throw new Error('工作台登记无效。')
  const record=JSON.parse(await fs.readFile(descriptor,'utf8'))
  if(record.schema!==1||!Number.isInteger(record.controlPort)||record.controlPort<1024||record.controlPort>65535
    ||typeof record.token!=='string'||!/^[0-9a-f]{64}$/.test(record.token)||typeof record.generation!=='string')throw new Error('工作台登记无效。')
  const response=await fetch('http://127.0.0.1:'+record.controlPort+'/projects/'+action,{method:'POST',
    headers:{'Content-Type':'application/json',Authorization:'Bearer '+record.token},body:JSON.stringify(payload),
    signal:AbortSignal.any([signal,AbortSignal.timeout(action==='presence'?20000:5000)]),redirect:'error'})
  const data=await response.json() as any
  if(!response.ok||data.generation!==record.generation||data.ok!==true)throw new Error(data.error||'工作台没有完成此操作。')
  return data.result
}
