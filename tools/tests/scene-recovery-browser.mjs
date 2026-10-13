import fs from 'node:fs/promises'
import path from 'node:path'
import assert from 'node:assert/strict'
import {pathToFileURL} from 'node:url'
const [log,task,modulePath]=process.argv.slice(2)
const phase=process.env.DSH_RECOVERY_PHASE||'resume'
const dirtyChoice=phase==='resume'?process.env.DSH_RECOVERY_DIRTY_CHOICE||'':''
const originalChoice=phase==='resume'?process.env.DSH_RECOVERY_ORIGINAL_CHOICE||'':''
const {chromium}=await import(pathToFileURL(modulePath))
const content=await fs.readFile(log,'utf8')
const match=[...content.matchAll(/dsh web:\s+(http:\/\/127\.0\.0\.1:\d+\/\?token=[^\s]+)/g)].at(-1)
if(!match)throw Error('No fixture authentication URL')
const url=new URL(match[1]),browser=await chromium.launch({channel:'msedge',headless:true})
let page
const errors=[],repairRequests=[]
try{
 page=await browser.newPage({viewport:{width:1100,height:850}})
 await page.emulateMedia({colorScheme:'dark'})
 page.on('pageerror',error=>errors.push(String(error)))
 page.on('request',request=>{if(request.url().includes('houdiniFrontend/recoverTask'))repairRequests.push(request.url())})
 await page.goto(url.href)
 const later=page.getByRole('button',{name:/稍后配置|以后设置/})
 await page.getByRole('button',{name:'继续',exact:true}).waitFor({timeout:5000}).catch(()=>{})
 if(await page.getByRole('button',{name:'继续',exact:true}).isVisible())await page.getByRole('button',{name:'继续',exact:true}).click()
 await later.waitFor({timeout:3000}).catch(()=>{});if(await later.isVisible())await later.click()
 const target=new URL(url.origin);target.searchParams.set('dsh-houdini-session',task)
 await page.goto(target.href)
 await later.waitFor({timeout:3000}).catch(()=>{});if(await later.isVisible())await later.click()
 await page.waitForFunction(id=>window.__dshHoudiniSelection?.()?.sessionId===id,task,{timeout:30000})
 if(await page.getByRole('button',{name:'继续',exact:true}).isVisible())await page.getByRole('button',{name:'继续',exact:true}).click()
 if(await later.isVisible())await later.click()
 const selected=await page.evaluate(()=>window.__dshHoudiniSelection())
 assert.equal(selected.agentPreset,'houdini')
 const repairButtons=page.getByRole('button',{name:/检查工程接续|恢复此任务的工程连接|重新打开保存文件并恢复/})
 assert.equal(await repairButtons.count(),0,'ordinary continuation must not depend on a repair control')
 const composer=page.locator('[data-composer-input][contenteditable="true"]')
 await composer.waitFor({state:'visible',timeout:15000})
 await composer.fill('继续')
 await composer.press('Enter')
 if(dirtyChoice||(originalChoice&&originalChoice!=='auto')){
  const question=page.locator('[data-question-key]')
  await question.waitFor({state:'visible',timeout:20000})
  const choice=originalChoice?(originalChoice==='keep'?'保留当前工程':'放弃当前修改，打开原工程继续')
    :dirtyChoice==='keep'?'保留当前修改，继续讨论':'放弃未保存修改，从保存点继续'
  if(originalChoice){const detail=await question.innerText();assert(detail.includes('other.hip')&&detail.includes('project.hip'))}
  assert.equal(await question.getByText(/^1\s*\/\s*1$/).count(),0,'single questions have no redundant pager')
  await page.screenshot({path:path.join(path.dirname(log),'recovery-question.png')})
  await question.screenshot({path:path.join(path.dirname(log),'recovery-question-card.png')})
  await page.setViewportSize({width:420,height:850})
  await page.screenshot({path:path.join(path.dirname(log),'recovery-question-narrow.png')})
  assert(await question.evaluate(el=>el.scrollWidth<=el.clientWidth),'question must wrap long paths without horizontal overflow')
  await page.setViewportSize({width:1100,height:850})
  await question.getByText(choice,{exact:true}).click()
  await question.getByRole('button',{name:/提交|完成|确认|发送/}).click()
  await question.waitFor({state:'detached',timeout:15000})
 }
 const completion=phase==='save'?'Fixture complete':dirtyChoice==='keep'||originalChoice==='keep'?'Fixture kept the unsaved scene and continued the conversation without live tools.':'Fixture resumed through the normal conversation.'
 await page.getByText(completion,{exact:true}).waitFor({timeout:45000})
 const finalSelection=await page.evaluate(()=>window.__dshHoudiniSelection())
 assert.equal(finalSelection.sessionId,task,'recovery must preserve the selected conversation')
 if(process.env.DSH_RECOVERY_SAVE_AS==='1')assert.equal(path.resolve(finalSelection.cwd).toLowerCase(),path.resolve(path.dirname(log),'saved-as').toLowerCase(),'selected frontend task must expose the actual new directory')
 assert.equal(await page.locator('[data-question-key]').count(),0,'no unresolved recovery decision remains')
 assert.deepEqual(repairRequests,[],'the browser must never call a recovery RPC')
 assert.deepEqual(errors,[],'the ordinary conversation must remain usable')
 await page.screenshot({path:path.join(path.dirname(log),'recovery-wide.png')})
 await page.setViewportSize({width:420,height:850})
 await page.screenshot({path:path.join(path.dirname(log),'recovery-narrow.png')})
 await fs.writeFile(path.join(path.dirname(log),phase+'-browser.json'),JSON.stringify({ok:true,selected,finalSelection,prompt:'继续',dirtyChoice,originalChoice,repairRequests,errors},null,2))
 console.log('PASS actual selected DSH task -> ordinary 继续 prompt -> '+(dirtyChoice?'native '+dirtyChoice+' conversation choice':'automatic saved-scene recovery'))
}catch(error){
 if(page){console.error((await page.locator('body').innerText()).slice(-3500));await page.screenshot({path:path.join(path.dirname(log),'recovery-failure.png')})}
 throw error
}finally{await browser.close()}
