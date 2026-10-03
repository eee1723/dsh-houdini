// Test-only stream interception: intentionally never calls next(), so even a
// configured paid route cannot reach its model adapter during this smoke.
import fs from 'node:fs';
export const inject=['llm'];
export function apply(ctx){
  const output=process.env.DSH_MODELING_TRIAL_SMOKE_OUT;
  if(!output)throw Error('Explicit isolated smoke output required');
  const requests=[];
  ctx.on('llm/stream',async function* (options){
    requests.push({sessionId:options.sessionId,purpose:options.purpose??null,
      provider:options.provider,model:options.model,messages:options.messages});
    fs.writeFileSync(output,JSON.stringify({networkRequests:0,requests},null,2));
    yield {type:'block-start',index:0,blockType:'text'};
    yield {type:'block-end',index:0,block:{type:'text',text:'Scripted isolated trial phase completed.'}};
    yield {type:'finish',reason:{kind:'stop'}};
  });
}
