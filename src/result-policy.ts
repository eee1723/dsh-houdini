import {readFileSync} from 'node:fs'

export const RESULT_DETAIL_POLICY=JSON.parse(readFileSync(new URL('../houdini/result-detail-policy.json',import.meta.url),'utf8'))
if(RESULT_DETAIL_POLICY.schemaVersion!==1||['maxArchiveBytes','detailThresholdChars','maxPresentationBytes','maxModelTextBytes','loadWarningPreviewBytes'].some(key=>
  !Number.isSafeInteger(RESULT_DETAIL_POLICY[key])||RESULT_DETAIL_POLICY[key]<=0)||RESULT_DETAIL_POLICY.loadWarningPreviewBytes<128)
  throw Error('Unsupported result detail policy')

export const DETAIL_THRESHOLD:number=RESULT_DETAIL_POLICY.detailThresholdChars
export const MAX_PRESENTATION_BYTES:number=RESULT_DETAIL_POLICY.maxPresentationBytes
export const MAX_MODEL_TEXT_BYTES:number=RESULT_DETAIL_POLICY.maxModelTextBytes
