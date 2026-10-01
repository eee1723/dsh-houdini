// Actual DSH browser module delivery and selection; no model or HOM requests.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {pathToFileURL} from 'node:url'
const [modulePath,configFile]=process.argv.slice(2)
const {chromium}=await import(pathToFileURL(modulePath).href)
const config=JSON.parse(fs.readFileSync(configFile,'utf8'))
const browser=await chromium.launch({headless:true,executablePath:config.browser})
const errors=[]
try {
  const context=await browser.newContext({viewport:{width:1440,height:1000}})
  await context.addCookies(config.cookies)
  const page=await context.newPage()
  page.on('pageerror',error=>errors.push(String(error)))
  const first=new URL(config.base)
  first.searchParams.set('dsh-houdini-workspace',config.first)
  first.searchParams.set('dsh-houdini-request','dsh-houdini-browser-first')
  await page.goto(first.href)
  await page.waitForFunction(expected=>window.__dshHoudiniSelection?.()?.cwd.replace(/\\/g,'/')===expected.replace(/\\/g,'/'),config.first,{timeout:30000})
  const firstSelection=await page.evaluate(()=>window.__dshHoudiniSelection())
  // Same intent path that Qt sends into a loaded page. Ordinary input is not
  // a competing navigation and must not restore the old selected workspace.
  await page.evaluate(next=>{
    const url=new URL(location.href)
    url.searchParams.set('dsh-houdini-workspace',next)
    url.searchParams.set('dsh-houdini-request','dsh-houdini-browser-second')
    history.replaceState(history.state,'',url)
    dispatchEvent(new Event('pointerdown'));dispatchEvent(new KeyboardEvent('keydown',{key:'x'}))
    dispatchEvent(new Event('dsh-houdini-open-workspace'))
  },config.second)
  await page.waitForFunction(expected=>window.__dshHoudiniSelection?.()?.cwd.replace(/\\/g,'/')===expected.replace(/\\/g,'/'),config.second,{timeout:30000})
  const secondSelection=await page.evaluate(()=>window.__dshHoudiniSelection())
  assert.notEqual(firstSelection.sessionId,secondSelection.sessionId)
  assert.equal(secondSelection.agentPreset,'houdini')
  const disclaimer=page.getByRole('button',{name:'继续',exact:true})
  if(await disclaimer.isVisible())await disclaimer.click()
  fs.writeFileSync(config.seedFile,secondSelection.sessionId)
  await page.getByText('Isolated UI fixture: inspect Trace and tool documentation.',{exact:true}).waitFor({timeout:15000})
  // This owned profile has no account. Use DSH's own "configure later" path.
  await page.getByRole('button',{name:'稍后配置',exact:true}).click({timeout:15000})
  const traceTab=page.getByRole('tab',{name:'Houdini Trace',exact:true})
  await traceTab.click()
  await page.getByRole('navigation',{name:'Trace 看板'}).waitFor()
  const traceText=await page.locator('body').innerText()
  for(const label of ['执行过程','提示词与上下文','工具','技能','分析']) {
    assert.ok(traceText.includes(label),'missing Trace section '+label)
  }
  await page.screenshot({path:path.join(config.output,'browser-trace.png')})
  await page.getByRole('tab',{name:'Houdini 工具',exact:true}).click()
  const toolsText=await page.locator('body').innerText()
  for(const name of ['houdini_inspect','houdini_exec','houdini_request','houdini_resource','houdini_capabilities',
      'houdini_job_submit','houdini_job_status','houdini_job_cancel']) {
    assert.ok(toolsText.includes(name),'missing tool documentation '+name)
  }
  await page.screenshot({path:path.join(config.output,'browser-tools.png')})
  await page.screenshot({path:path.join(config.output,'browser-navigation.png')})
  fs.writeFileSync(path.join(config.output,'browser-review.json'),JSON.stringify({firstSelection,secondSelection,errors,title:await page.title(),traceText,toolsText},null,2))
  await page.waitForFunction(()=>!new URL(location.href).searchParams.has('dsh-houdini-workspace'),null,{timeout:5000})
  assert.deepEqual(errors,[],'browser module failed')
  console.log('Actual browser: workspaces selected and confirmed; Trace and eight tool docs visible')
} finally {await browser.close()}
