import type {SessionEvent} from './execution-history.js'

export type PromptSectionData={name:string;text:string}
export function sectionData(section?:PromptSectionData):any {
  if(!section) return null
  try {return JSON.parse(section.text.slice(section.text.indexOf('\n')+1))}
  catch {return null}
}
export function lastEvent(events:readonly SessionEvent[],predicate:(event:SessionEvent)=>boolean) {
  for(let i=events.length-1;i>=0;i--) if(predicate(events[i])) return events[i]
}
/** Escape string tokens before DSH expands template variables; keep JSON structure. */
export function literalData(text:string):string {
  return text.replace(/"(?:\\.|[^"\\])*"/g,token=>token.replace(/\{/g,'\\u007b').replace(/\}/g,'\\u007d'))
}
