import fs from 'node:fs'
import vm from 'node:vm'
import assert from 'node:assert/strict'

const source=fs.readFileSync('client.js','utf8')
const fragment=source.slice(source.indexOf('    function createSupportReporter('),source.indexOf('    function apply('))
const hooks=[],effects=[],requests=[],downloads=[]
let cursor=0,sessionId='task-a',generation={id:1},respond
const React={Fragment:'fragment',createElement:(tag,props,...children)=>typeof tag==='function'?tag({...props,children:children.flat(Infinity)}):({tag,props:props??{},children:children.flat(Infinity)}),
  useRef(value){const index=cursor++;return hooks[index]??(hooks[index]={current:value})},
  useState(value){const index=cursor++;if(!(index in hooks))hooks[index]=value;return [hooks[index],next=>hooks[index]=next]},
  useSyncExternalStore:(_subscribe,get)=>get(),useEffect(callback,deps){const index=cursor++;
    if(!hooks[index]||deps.some((value,key)=>value!==hooks[index].deps[key])){
      hooks[index]?.dispose?.();hooks[index]={deps};effects.push(()=>hooks[index].dispose=callback())
    }
  }}
const ui={Button:'button',Checkbox:props=>React.createElement('label',{},props.label,React.createElement('input',{
  type:'checkbox',checked:props.checked,onChange:event=>props.onChange(event.target.checked)})),
  Modal:props=>props.open?React.createElement('div',{'aria-label':props.title},
    React.createElement('button',{'aria-label':props.closeLabel,onClick:props.onClose},'header-close'),props.children,props.footer):null}
const context={React,ui,document:{createElement:()=>({click(){downloads.push(this.download)},remove(){}})},
  AbortController,setTimeout:()=>1,clearTimeout(){},atob,Uint8Array,Blob,URL:{createObjectURL:()=> 'blob:fixture',revokeObjectURL(){}}}
vm.createContext(context)
vm.runInContext(fragment+'\nthis.factory=createSupportReporter;',context)
const component=context.factory({generation:{subscribe:()=>()=>{},getSnapshot:()=>generation},rpc:{call:async(channel,endpoint,payload,signal)=>{
  requests.push({channel,endpoint,payload,signal});return new Promise(resolve=>respond=resolve)
}}})
function render(runEffects=true){cursor=0;const tree=component({sessionId});if(runEffects)while(effects.length)effects.shift()();return tree}
function nodes(tree){return tree&&typeof tree==='object'?[tree,...tree.children.flatMap(nodes)]:[]}
function button(label){return nodes(render()).find(node=>node.tag==='button'&&node.children.includes(label))}
function open(){button('报告问题').props.onClick();render()}
const report={filename:'fixture.zip',reportId:'report-a',archiveBase64:'',summary:'summary',issuesUrl:'https://github.com/eee1723/dsh-houdini/issues/new',
  files:[{name:'manifest.json',label:'报告信息',description:'收集范围',text:'task-a evidence'}]}
render();open()
assert.equal(button('保存报告').props.disabled,false,'save is available before preview')
let promise=button('保存报告').props.onClick()
assert.equal(requests.at(-1).payload.args.input.sessionId,'task-a')
assert.equal(requests.at(-1).payload.args.input.includeContent,false)
assert.equal(requests.length,1)
await button('正在整理并保存…').props.onClick()
assert.equal(requests.length,1,'rapid clicks do not duplicate collection')
respond({ok:true,value:report});await promise
assert.equal(downloads.length,1,'first save collects and downloads without preview')
assert(!nodes(render()).some(node=>node.tag==='pre'),'saving does not force technical details open')
const beforePreview=requests.length
await button('查看报告内容').props.onClick()
assert.equal(requests.length,beforePreview,'preview reuses the exact saved report')
assert(!nodes(render()).some(node=>node.tag==='pre'),'all detail sections start collapsed')
let disclosure=nodes(render()).find(node=>node.tag==='button'&&node.props['aria-expanded']===false)
disclosure.props.onClick()
assert(nodes(render()).some(node=>node.tag==='pre'&&node.children.includes('task-a evidence')))
button('收起详情').props.onClick()
assert(!nodes(render()).some(node=>node.tag==='pre'))
button('返回填写').props.onClick()
nodes(render()).find(node=>node.tag==='input').props.onChange({target:{checked:false}})
assert.equal(button('保存报告').props.disabled,false,'scope edits do not introduce a preview prerequisite')
promise=button('保存报告').props.onClick()
const oldSignal=requests.at(-1).signal
sessionId='task-b';render();assert(oldSignal.aborted)
respond({ok:true,value:report});await promise
assert.equal(downloads.length,1,'late response cannot save another task')
assert(!button('保存报告'),'late response must not reopen the previous report')
open();promise=button('查看报告内容').props.onClick();respond({ok:true,value:report});await promise
sessionId='task-c'
const immediate=render(false)
const immediateSave=nodes(immediate).find(node=>node.tag==='button'&&node.children.includes('保存报告'))
promise=immediateSave.props.onClick()
assert.equal(requests.at(-1).payload.args.input.sessionId,'task-c','before effects, save must collect the new task instead of downloading old bytes')
assert.equal(downloads.length,1)
render();respond({ok:true,value:report});await promise
assert.equal(downloads.length,1)
open();promise=button('保存报告').props.onClick()
const reconnectSignal=requests.at(-1).signal
generation={id:2};render();assert(reconnectSignal.aborted)
respond({ok:true,value:report});await promise
assert.equal(downloads.length,1)
open();promise=button('保存报告').props.onClick()
const closeSignal=requests.at(-1).signal
button('header-close').props.onClick();assert(closeSignal.aborted)
respond({ok:true,value:report});await promise
assert.equal(downloads.length,1)
open();promise=button('保存报告').props.onClick();respond({ok:false,error:{message:'fixture failure'}});await promise
assert.equal(button('保存报告').props.disabled,false,'failure leaves a usable retry action')
assert.equal(downloads.length,1)
console.log('support UI: one-click save, cached optional preview, collapse, rapid clicks, stale task/reconnect/close, edited scope and failure retry passed')
