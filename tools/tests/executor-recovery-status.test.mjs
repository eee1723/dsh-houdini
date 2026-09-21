import assert from 'node:assert/strict'
import {executorRecoveryStatus} from '../../lib/executor-controller.js'

const first='a'.repeat(32), second='b'.repeat(32)
const record=(executor_id,state='registered')=>({schema:1,executor_id,registration_id:'c'.repeat(32),runtime_id:'d'.repeat(32),
  installation:'C:/plugin',bridge_url:'http://127.0.0.1:12345',houdini_version:'21.0.440',pid:1,state,
  task_id:null,hip_path:'C:/project/test.hip'})

assert.equal(executorRecoveryStatus(undefined,[]).status,'unbound')
let value=executorRecoveryStatus(first,[record(first)])
assert.equal(value.status,'bound_available')
assert.equal(value.hipPath,'C:/project/test.hip')
value=executorRecoveryStatus(first,[record(first,'disconnected')])
assert.equal(value.status,'bound_disconnected')
assert.match(value.message,/不能直接迁移/)
value=executorRecoveryStatus(first,[record(second)])
assert.equal(value.status,'bound_missing')
assert.match(value.message,/跨进程恢复尚未实现/)
value=executorRecoveryStatus(undefined,[record(first)],new Error('two identities'))
assert.equal(value.status,'history_conflict')
assert.equal(value.detail,'two identities')
assert.match(value.message,/未发送live请求/)
console.log('executor recovery status: unbound, available, disconnected, missing and conflict passed')
