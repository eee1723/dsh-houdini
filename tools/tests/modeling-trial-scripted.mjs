// Test-only stream interception: intentionally never calls next(), so even a
// configured paid route cannot reach its model adapter during this smoke.
import fs from 'node:fs';
export const inject=['llm','agents'];
export function nextDeliveryCall(messages,events,delivery){
  const completed=new Set(messages.filter(m=>m.role==='tool').map(m=>m.toolCallId));
  const names=['houdini_exec','houdini_exec','houdini_ui_list','houdini_ui_screenshot','read_image','present'];
  const index=names.findIndex((_,i)=>!completed.has('delivery-smoke-'+i));
  if(index<0)return null;
  for(const message of messages)if(message.role==='tool'&&String(message.toolCallId).startsWith('delivery-smoke-')&&message.isError)
    throw Error('A real carrier tool failed; no downstream success is fabricated');
  const actual=step=>{
    const event=events.findLast(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='delivery-smoke-'+step);
    const value=event?.data?.meta?.canonical;
    if(value?.ok!==true)throw Error('Successful canonical native receipt is required for step '+step);
    return value;
  };
  let args;
  if(index===0)args={code:"g=tab_create('/obj','geo','carrier_delivery')\nb=tab_create(g,'box','shape',parms={'sizex':1.2,'sizey':0.4,'sizez':0.8})\no=tab_create(g,'null','OUT',inputs=[b])\nsop_set_output(o)\n__result__=present_nodes([{'node':g.path(),'label':'Smoke Container','role':'node'},{'node':b.path(),'label':'Smoke Controls','role':'control'},{'node':o.path(),'label':'Smoke Output','role':'output'}])\nscene_save(expected_path="+JSON.stringify(delivery.hip)+")"};
  if(index===1){
    const original=actual(0),control=original.result?.nodes?.find(n=>n.role==='control');
    const saved=original.verbs?.find(v=>v.verb==='scene_save'&&v.ok)?.result;
    if(!control?.id||!saved?.path)throw Error('Actual saved control entry is missing');
    args={code:"focused=focus_node("+JSON.stringify({id:control.id})+",expected_hip="+JSON.stringify(saved.path)+")\n__result__={'focused':focused,'saved':scene_save(expected_path="+JSON.stringify(saved.path)+")}"};
  }
  if(index===2)args={};
  if(index===3){
    const control=actual(0).result.nodes.find(n=>n.role==='control');
    const matches=actual(2).result.surfaces?.filter(s=>s.supported===true&&s.kind==='pane'&&s.pane_type==='Parm'&&s.current_node===control.path);
    if(!matches?.length)throw Error('No supported visible ParameterEditor for the actual control node');
    args={target:matches[0].target,path:delivery.image,output_policy:'explicit'};
  }
  if(index===4){const shot=actual(3).result;if(!shot.fresh||shot.file_status!=='passed')throw Error('Native UI image did not finish');args={file_path:shot.path};}
  if(index===5)args={files:[{path:actual(0).verbs.find(v=>v.verb==='scene_save'&&v.ok).result.path,description:'Owned saved smoke HIP'},
    {path:delivery.source,description:'Owned smoke source text'},
    {path:actual(3).result.path,description:'Actual visible ParameterEditor capture'}]};
  return {type:'tool-call',id:'delivery-smoke-'+index,name:names[index],arguments:JSON.stringify(args)};
}
export function apply(ctx){
  const output=process.env.DSH_MODELING_TRIAL_SMOKE_OUT;
  if(!output)throw Error('Explicit isolated smoke output required');
  const requests=[];
  const delivery=process.env.DSH_MODELING_TRIAL_DELIVERY_SMOKE
    ?JSON.parse(process.env.DSH_MODELING_TRIAL_DELIVERY_SMOKE):null;
  ctx.on('llm/stream',async function* (options){
    requests.push({sessionId:options.sessionId,purpose:options.purpose??null,
      provider:options.provider,model:options.model,messages:options.messages});
    fs.writeFileSync(output,JSON.stringify({networkRequests:0,requests},null,2));
    if(delivery&&!options.purpose){
      const events=ctx.agents.get(options.sessionId).session.snapshotEvents();
      const block=nextDeliveryCall(options.messages,events,delivery);
      if(block){
        yield {type:'block-start',index:0,blockType:'tool-call'};
        yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'tool-calls'}};return;
      }
    }
    yield {type:'block-start',index:0,blockType:'text'};
    yield {type:'block-end',index:0,block:{type:'text',text:'Scripted isolated trial phase completed.'}};
    yield {type:'finish',reason:{kind:'stop'}};
  });
}
