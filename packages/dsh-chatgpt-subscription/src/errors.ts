export class SubscriptionError extends Error {
  constructor(readonly code:string,message:string,readonly retryable=false){super(message);this.name='SubscriptionError'}
}
export function safeFailure(error:unknown){
  return error instanceof SubscriptionError?{code:error.code,message:error.message}:{code:'FAILED',message:'操作未完成，请稍后重试。'}
}
export const aborted=()=>new SubscriptionError('CANCELLED','操作已取消。')
