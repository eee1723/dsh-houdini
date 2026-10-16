import {isHoudiniSource} from './dsh-adapter.js'
import {sectionData} from './prompt-data.js'
import type {SessionEvent} from './execution-history.js'

export function lastRecoveryNotice(events:readonly SessionEvent[],target?:string) {
  for(let index=events.length-1;index>=0;index--) {
    const event=events[index]
    if(event.type!=='user/message'||!isHoudiniSource(event.data?.source))continue
    for(const section of [...(event.data.source.sections??[])].reverse()) {
      if(section.name!=='dsh-houdini:recovery-required')continue
      const value=sectionData(section)
      if(!value||value.executor_id!==target)continue
      return value.cleared===true?null:typeof value.reason==='string'?value:null
    }
  }
  return null
}
