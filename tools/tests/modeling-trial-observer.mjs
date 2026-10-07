// Evidence-only observer for an explicitly isolated paid trial. It neither
// changes the LOOP request nor replaces the real provider stream.
import fs from 'node:fs';
export const inject=['llm'];
export function apply(ctx){
  const output=process.env.DSH_MODELING_TRIAL_OBSERVER_OUT;
  if(!output)throw Error('Explicit isolated trial observer output required');
  const modelInfo=process.env.DSH_MODELING_TRIAL_MODEL_INFO_OUT;
  const projectModel=async()=>{
    if(!modelInfo)return;
    let value;
    try{value={ok:true,scope:'Actual pinned Host ctx.llm.resolveModelInfo; no model inference',
      model:await ctx.llm.resolveModelInfo(process.env.DSH_MODELING_TRIAL_PROVIDER,process.env.DSH_MODELING_TRIAL_MODEL)};}
    catch(error){value={ok:false,errorType:error.name,errorCode:error.code??null};}
    fs.writeFileSync(modelInfo+'.tmp',JSON.stringify(value,null,2));fs.renameSync(modelInfo+'.tmp',modelInfo);
  };
  ctx.on('ready',projectModel);
  ctx.on('llm/adapters-updated',()=>{void projectModel();});
  let sequence=0;
  const write=value=>fs.appendFileSync(output,JSON.stringify(value)+'\n');
  ctx.on('llm/stream',async function* (options,next){
    const id=++sequence;
    const images=[];
    const tools=[];
    for(const [messageIndex,message] of options.messages.entries()){
      for(const block of message.content??[]){
        if(block.type==='image')images.push({messageIndex,role:message.role,
          attachment:block.attachment,offloaded:block.offloaded??false});
        if(block.type==='tool-call')tools.push({id:block.id,name:block.name});
      }
    }
    write({type:'request',sequence:id,at:new Date().toISOString(),sessionId:options.sessionId,
      provider:options.provider,model:options.model,purpose:options.purpose??null,
      messageCount:options.messages.length,images,tools,toolDefinitions:options.tools?.map(t=>t.name)??[]});
    try{
      for await(const chunk of next()){
        if(chunk.type==='block-end'&&chunk.block?.type==='text')write({type:'text',sequence:id,text:chunk.block.text});
        if(chunk.type==='block-end'&&chunk.block?.type==='tool-call')write({type:'tool-call',sequence:id,id:chunk.block.id,name:chunk.block.name});
        if(chunk.type==='finish')write({type:'finish',sequence:id,reason:chunk.reason,usage:chunk.usage});
        if(chunk.type==='usage')write({type:'usage',sequence:id,usage:chunk.usage});
        yield chunk;
      }
    }catch(error){
      write({type:'error',sequence:id,errorType:error.name,errorCode:error.code??null});
      throw error;
    }
  });
}
