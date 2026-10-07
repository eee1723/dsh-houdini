import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {nextDeliveryCall} from './modeling-trial-scripted.mjs';
const delivery={hip:'Z:/owned/final.hip',image:'Z:/owned/native-ui.png',source:'Z:/owned/brief.md'};
const control={id:randomUUID().replaceAll('-',''),path:'/obj/actual_container/actual_control',role:'control'};
const target='ui:returned-reference-'+randomUUID();
const messages=[],events=[];
const settle=(step,result,verbs=[])=>{
  const callId='delivery-smoke-'+step;
  messages.push({role:'tool',toolCallId:callId,content:[{type:'text',text:'native tool content'}]});
  events.push({type:'tool/result',data:{message:{source:{callId}},meta:{canonical:{ok:true,result,verbs}}}});
};
const args=()=>JSON.parse(nextDeliveryCall(messages,events,delivery).arguments);
assert.match(args().code,/tab_create\(/);
assert.match(args().code,/present_nodes\(/);
settle(0,{kind:'houdini/node-delivery-v1',nodes:[{role:'node',id:'different'},control]},[{verb:'scene_save',ok:true,result:{path:delivery.hip}}]);
const focus=args().code;
assert(focus.includes(control.id),'use the returned persisted control id');
assert(focus.includes('expected_hip='+JSON.stringify(delivery.hip)),'bind navigation to the saved actual HIP');
settle(1,{focused:{path:control.path},saved:{path:delivery.hip}});
assert.equal(nextDeliveryCall(messages,events,delivery).name,'houdini_ui_list');
settle(2,{surfaces:[
  {kind:'pane',pane_type:'Parm',current_node:'/obj/other',supported:true,target:'unrelated'},
  {kind:'pane',pane_type:'Parm',current_node:control.path,supported:false,target:'unsupported'},
  {kind:'pane',pane_type:'Parm',current_node:control.path,supported:true,target},
]});
assert.deepEqual(args(),{target,path:delivery.image,output_policy:'explicit'},'exact observed surface; no private/resizing arguments');
settle(3,{fresh:true,file_status:'passed',path:delivery.image});
assert.deepEqual(args(),{file_path:delivery.image});
settle(4,{ok:true});
assert.deepEqual(args().files.map(f=>f.path),[delivery.hip,delivery.source,delivery.image]);
settle(5,{ok:true});
assert.equal(nextDeliveryCall(messages,events,delivery),null);
assert.throws(()=>nextDeliveryCall(messages.slice(0,3),events.filter(e=>e.data.message.source.callId!=='delivery-smoke-2'),delivery),/canonical native receipt/);
const unsupported=[...events.slice(0,2),{type:'tool/result',data:{message:{source:{callId:'delivery-smoke-2'}},meta:{canonical:{ok:true,result:{surfaces:[]}}}}}];
assert.throws(()=>nextDeliveryCall(messages.slice(0,3),unsupported,delivery),/No supported visible ParameterEditor/);
assert.throws(()=>nextDeliveryCall([{role:'tool',toolCallId:'delivery-smoke-0',isError:true}],events,delivery),/tool failed/);
console.log('PASS native carrier chains persisted entry, exact observed target and image facts; failures do not fabricate delivery');
