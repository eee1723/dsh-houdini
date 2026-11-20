import {randomBytes} from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import {HoudiniBridge} from '../../lib/bridge.js'

export const fixtureToken = randomBytes(32).toString('hex')

export function pairedBridge(url, timeout, executorId, lifetime, target, token = fixtureToken) {
  return new HoudiniBridge(url, timeout, executorId, lifetime, target, async () => token)
}

export async function writeBridgeCredential(root, record, token) {
  const directory = path.join(root, 'credentials')
  await fs.mkdir(directory, {recursive:true})
  await fs.writeFile(path.join(directory, record.executor_id + '.json'), JSON.stringify({
    runtime_id:record.runtime_id, port:Number(new URL(record.bridge_url).port), token,
  }), {mode:0o600})
}
