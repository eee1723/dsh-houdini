import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

const source=fs.readFileSync(new URL('../../client.js',import.meta.url),'utf8')
const start=source.indexOf('    function readHoudiniCanonical('),end=source.indexOf('    // This is a last-observed fact')
const element=(type,props,...children)=>({type,props:props??{},children:children.flat()})
const {install,read}=vm.runInNewContext(source.slice(start,end)+'\n({install:installHoudiniToolResults,read:readHoudiniCanonical});',
  {React:{createElement:element}})
const entries=new Map(),factories=new Map(),listeners=new Map(),cleanups=[]
const nativeGallery=props=>({nativeGallery:props})
const builtin={name:'tool.call.images',component:nativeGallery,locale:'conversation'}
entries.set('tool.call.images',[builtin])
const slots={
  registerFactory(options,component){factories.set(options.name,{options,component})},
  register(options,component){const entry={...options,component};const list=entries.get(options.name)??[];list.push(entry);entries.set(options.name,list);
    return()=>{const index=list.indexOf(entry);if(index>=0)list.splice(index,1)}},
  entriesOfSlot:name=>entries.get(name)??[],
  subscribe(name,listener){listeners.set(name,listener);return()=>listeners.delete(name)},
  inject(name,install){const result=install();if(result&&typeof result.next==='function'){for(const dispose of result)cleanups.push(dispose)}else if(result)cleanups.push(result)},
}
install(slots)
assert.equal(entries.get('tool.call.images')[0],builtin,'the native read_image gallery retains its owner and registration')
const factory=factories.get('dsh-houdini-tool-result')
assert.deepEqual(Object.keys(factory.options.children),['dsh-houdini.tool.images'],'the Houdini factory must not redeclare DSH read_image child ownership')
assert.equal(entries.get('dsh-houdini.tool.images')[0].component,nativeGallery)
assert.equal(entries.get('dsh-houdini.tool.images')[0].locale,'conversation')
const view=entries.get('tool.call.toolview').find(entry=>entry.key==='houdini_exec')
assert(view,'unknown-tool text fallback must be replaced for actual Houdini image results')
const reference={attachmentId:'sha256:'+ 'a'.repeat(64),mediaType:'image/webp',width:480,height:320,bytes:7254,name:'check.png'}
const canonical={ok:false,requestReceipt:{status:'unknown_transport'},imageAttachments:[{from:'C:/own/check.png',attachment:reference},
  {from:'C:/own/failed.png',error:'channel unavailable'}]}
const block={kind:'tool-result',callId:'image',call:{name:'houdini_exec',argsRaw:'{"code":"render_view()"}'},
  meta:{canonical},content:[{type:'text',text:'Original unknown receipt; inspect before retrying.'}]}
const loadImage=()=>{throw Error('the view itself must not fetch or construct an image URL')}
let galleryProps,expanded=true
function renderFactorySlot(name,props){assert.equal(name,'dsh-houdini-tool-result');return factory.component({...props,
  renderSlot(slot,input){assert.equal(slot,'dsh-houdini.tool.images');galleryProps=input;return nativeGallery(input)}})}
function render(current=block,phase='result'){
  galleryProps=undefined
  return view.component({phase,block:current,toolName:'houdini_exec',loadImage,
    useDisclosure:()=>({expanded,toggle:()=>{expanded=!expanded}}),renderFactorySlot})
}
const tree=render()
assert.equal(galleryProps.loadImage,loadImage,'the current task authorized loader flows unchanged to native attachment presentation')
assert.equal(galleryProps.images[0].attachment,reference,'native references remain the canonical object, without path-to-URL conversion or copying')
assert.equal(galleryProps.images.length,1,'attachment errors are not fabricated as successful pictures')
assert.equal(tree.props['data-tool'],'houdini_exec')
assert(JSON.stringify(tree).includes('Original unknown receipt'))
assert(!JSON.stringify(tree).includes('成功'),'the client does not invent an execution or visual success verdict')
const fullArguments='{"code":"'+ 'x'.repeat(1200)+' COMPLETE_ORIGINAL_ARGUMENTS"}'
assert(JSON.stringify(render({...block,call:{...block.call,argsRaw:fullArguments}})).includes('COMPLETE_ORIGINAL_ARGUMENTS'),
  'the compact heading must not remove the original call arguments from the expanded record')
const nested={...block,meta:undefined,content:[{type:'text',text:JSON.stringify({kind:'dsh-houdini/execution-v1',tool:'houdini_exec',callId:'image',value:canonical})}]}
assert.equal(read(nested).requestReceipt.status,'unknown_transport')
render(nested);assert.equal(galleryProps.images[0].attachment.attachmentId,reference.attachmentId)
render({...nested,callId:'another'});assert.equal(galleryProps,undefined,'a log wrapper for another call does not supply image provenance')
render({...block,meta:undefined});assert.equal(galleryProps,undefined,'ordinary prose never infers attachment facts')
const aborted=render({...block,meta:undefined,content:[],isError:true,error:{code:'ABORTED',message:'call delivery stopped'}})
assert(JSON.stringify(aborted).includes('ABORTED'),'framework cancellation/error records remain visible even without canonical execution or text')
render(block,'start');assert.equal(galleryProps,undefined,'pre-execution rows never show a settled image')
expanded=false;render();assert.equal(galleryProps,undefined,'the disclosure controls actual gallery mounting')
const replacement=()=>({replacement:true});entries.set('tool.call.images',[{...builtin,component:replacement}]);listeners.get('tool.call.images')()
assert.equal(entries.get('dsh-houdini.tool.images').length,1)
assert.equal(entries.get('dsh-houdini.tool.images')[0].component,replacement,'native presentation reload replaces the mirror without stale component retention')
entries.set('tool.call.images',[]);listeners.get('tool.call.images')()
assert.equal(entries.get('dsh-houdini.tool.images').length,0)
for(const dispose of cleanups)dispose()
assert.equal(listeners.size,0)
console.log('Houdini tool images: canonical native/PTC references, authorized native gallery reuse, original errors, disclosure and provider lifecycle passed')
