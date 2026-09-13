// Deterministic model boundary for the actual DSH/provider/worker composition.
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import {createHash} from 'node:crypto'
export const inject=['llm','agents']
export function apply(ctx) {
  let childRequests=0
  ctx.on('agent/disposed',({agent})=>{
    if(process.env.DSH_COMPONENT_EXPECT_REJECTION==='1'&&agent.session.header.parentSession){
      assert.equal(childRequests,0)
      fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'rejected.json'),JSON.stringify({rejected:true,childRequests}))
    }
  })
  class Fixture extends LlmAdapter {
    async resolveModel(provider,model){return {provider,id:model,name:'Component fixture',inputModalities:['text'],context:{contextWindow:500000}}}
    async *stream(options){
      const agent=ctx.agents.get(options.sessionId)
      let blocks=[]
      if(options.purpose||!agent){blocks=[{type:'text',text:'Component fixture'}]}
      else if(agent.session.header.parentSession){
        childRequests++
        assert(agent.session.header.cwd.startsWith(process.env.DSH_COMPONENT_TEST_WORKERS))
        assert(JSON.stringify(options.messages).includes('render_view is a Houdini verb called inside houdini_exec'),
          'Host execution facts must reach the child before its first model request')
        assert(agent.session.snapshotEvents().some(e=>e.type==='user/message'&&e.data.source?.plugin==='dsh-houdini'
          &&e.data.source.sections?.some(s=>s.name==='dsh-houdini:executor-binding')))
        const results=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'))
        for(const result of results){
          if(result.toolCallId==='outside-write')assert(result.isError, 'child wrote outside its workspace')
          else assert(!result.isError,JSON.stringify(result))
        }
        if(!results.length){
          blocks=[{type:'tool-call',id:'inside-write',name:'write',arguments:JSON.stringify({file_path:'local.txt',content:'local fixture'})},
            {type:'tool-call',id:'outside-write',name:'write',arguments:JSON.stringify({file_path:path.join(process.env.DSH_COMPONENT_TEST_OUT,'forbidden-'+agent.id+'.txt'),content:'must not be written'})}]
        }else if(!results.some(r=>r.toolCallId==='component-build')){
          assert(fs.existsSync(path.join(agent.session.header.cwd,'local.txt')))
          assert(!fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'forbidden-'+agent.id+'.txt')))
          const filename=path.join(agent.session.header.cwd,'part.dshcomponent')
          const code="g=tab_create('/obj','geo','component')\ns=tab_create(g,'subnet','part')\n"
            +"create_spare_parms(s,layout=[{'type':'float','name':'width','default':1}])\n"
            +"b=tab_create(s,'box','shape')\nset_parms(b,{'sizex':'ch(\"../width\")'})\n"
            +"detail=tab_create(s,'polybevel','bevel',inputs=[b])\nsop_set_output(detail,output_index=0)\n"
            +`__result__=component_export(s,${JSON.stringify(filename)},{'module_id':'part','revision':1,'units':'m','outputs':[0]})`
          blocks=[{type:'tool-call',id:'component-build',name:'houdini_exec',arguments:JSON.stringify({code})}]
        }else{
          assert(fs.existsSync(path.join(agent.session.header.cwd,'part.dshcomponent')))
          fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,agent.id+'.json'),JSON.stringify({child:agent.id,cwd:agent.session.header.cwd,passed:true}))
          blocks=[{type:'text',text:'Component candidate exported; assembly remains unverified.'}]
        }
      }else{
        const autoRelease=process.env.DSH_COMPONENT_EXPECT_AUTO_RELEASE==='1'
        const checked=agent.session.snapshotEvents().some(e=>e.type==='tool/call'&&e.data.name==='component_status')
        const called=agent.session.snapshotEvents().some(e=>e.type==='tool/call'&&e.data.name==='component_delegate')
        if(checked&&!called){
          const status=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId==='capacity')).at(-1)
          assert(status&&!status.isError,
            'read-only capacity must return a worker snapshot')
          assert(!fs.existsSync(process.env.DSH_COMPONENT_TEST_WORKERS),
            'capacity inspection must not start a worker or create its root')
        }
        const files=fs.readdirSync(process.env.DSH_COMPONENT_TEST_OUT).filter(f=>f.endsWith('.json')&&f!=='assembled.json')
        const assembly=agent.session.snapshotEvents().some(e=>e.type==='tool/call'&&e.data.name==='houdini_exec')
        if(autoRelease&&fs.existsSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'assembled.json'))){
          const status=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId==='release-status')).at(-1)
          if(!status)blocks=[{type:'tool-call',id:'release-status',name:'component_status',arguments:'{}'}]
          else{
            assert(!status.isError,JSON.stringify(status))
            const result=JSON.parse(status.content.find(c=>c.type==='text').text)
            assert.equal(result.occupied,0)
            assert.equal(result.children.length,2)
            assert(result.children.every(child=>child.workerStatus==='stopped'&&child.checkpoint==='saved'))
            fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'released.json'),JSON.stringify(result))
            blocks=[{type:'text',text:'Idle component workers released with saved checkpoints.'}]
          }
        }else if(files.length===2&&!assembly){
          let code="g=tab_create('/obj','geo','assembly')\nctrl=tab_create(g,'null','CTRL')\ncreate_spare_parms(ctrl,layout=[{'type':'float','name':'width','default':1}])\n"
          for(let i=0;i<files.length;i++){
            const info=JSON.parse(fs.readFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,files[i])))
            const artifact=path.join(info.cwd,'part.dshcomponent')
            const hash=createHash('sha256').update(fs.readFileSync(artifact)).digest('hex')
            code+=`component_import(g,${JSON.stringify(artifact)},'${hash}','part${i}',trusted=True)\n`
            code+=`set_parms(g.node('part${i}'),{'width':'ch("../CTRL/width")'})\n`
          }
          code+="offset=tab_create(g,'xform','offset',inputs=[g.node('part1')])\nset_parms(offset,{'tx':3})\n"
            +"out=tab_create(g,'merge','OUT',inputs=[g.node('part0'),offset])\nsop_set_output(out)\nverify_network(g,output=out)\n"
            +"report=test_controls(ctrl,out,[{'id':'shared_width','values':{'width':2},'expectations':[{'metric':'bounds_size','axis':0,'delta':[0.99,1.01]}]}])\n"
            +"assert report['restored'] and report['control_summary']['status']=='pass'\nscene_save()\n__result__={'assembly':True,'restored':report['restored']}"
          blocks=[{type:'tool-call',id:'assembly-build',name:'houdini_exec',arguments:JSON.stringify({code})}]
        }else if(assembly){
          const result=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId==='assembly-build')).at(-1)
          assert(result&&!result.isError,JSON.stringify(result))
          const stops=options.messages.flatMap(m=>m.content.filter(c=>c.type==='tool-result'&&c.toolCallId.startsWith('stop-child-')))
          if(autoRelease){
            fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'assembled.json'),JSON.stringify({passed:true}))
            blocks=[{type:'text',text:'Assembly saved; worker release pending idle-turn boundary.'}]
          }else if(stops.length===0){
            blocks=files.map((file,i)=>({type:'tool-call',id:'stop-child-'+i,name:'component_stop',
              arguments:JSON.stringify({childId:JSON.parse(fs.readFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,file))).child})}))
          }else{
            assert.equal(stops.length,2)
            assert(stops.every(r=>!r.isError),JSON.stringify(stops))
            fs.writeFileSync(path.join(process.env.DSH_COMPONENT_TEST_OUT,'assembled.json'),JSON.stringify({passed:true}))
            blocks=[{type:'text',text:'Two ordinary subnets assembled; shared control and recovery passed; both workers stopped.'}]
          }
        }else blocks=!checked?[{type:'tool-call',id:'capacity',name:'component_status',arguments:'{}'}]
          :called?[{type:'text',text:'Component work accepted; awaiting its result.'}]:[0,1].map(i=>({
          type:'tool-call',id:'delegate-'+i,name:'component_delegate',arguments:JSON.stringify({task:'Fixture part '+i+': create an ordinary subnet box in metres, publish output 0 and export part.dshcomponent. Do not create an HDA.'})}))
      }
      for(let index=0;index<blocks.length;index++){
        yield {type:'block-start',index,blockType:blocks[index].type}
        yield {type:'block-end',index,block:blocks[index]}
      }
      yield {type:'finish',reason:{kind:blocks.some(b=>b.type==='tool-call')?'tool-calls':'stop'}}
    }
  }
  ctx.llm.registerAdapter(['component-fixture'],new Fixture())
}
