/** Plugin-owned runtime facts, never a second DSH home or profile. */
import path from 'node:path'
import {dshHomePath} from '@deepseek-ai/dsh-home-paths'

export function desktopPaths() {
  const root=dshHomePath('dsh-houdini')
  return {root,descriptor:path.join(root,'desktop.json'),
    launches:path.join(root,'launches'),registry:path.resolve(process.env.DSH_HOUDINI_EXECUTOR_REGISTRY||path.join(root,'executors'))}
}
