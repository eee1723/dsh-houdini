import fs from 'node:fs/promises'
import path from 'node:path'
import {pathToFileURL} from 'node:url'
const [log,task,modulePath]=process.argv.slice(2)
if(!log||!task||!modulePath)throw Error('Fixture log, task and explicit Playwright module are required')
const {chromium}=await import(pathToFileURL(modulePath))
const text=await fs.readFile(log,'utf8')
const match=[...text.matchAll(/dsh web:\s+(http:\/\/127\.0\.0\.1:\d+\/\?token=[^\s]+)/g)].at(-1)
if(!match)throw Error('No fixture auth URL')
const url=new URL(match[1])
const browser=await chromium.launch({channel:'msedge',headless:true})
let page
try{
  page=await browser.newPage({viewport:{width:1100,height:850}})
  page.on('pageerror',error=>console.error('PAGE ERROR: '+error.message))
  await page.goto(url.href)
  const onboarding=page.getByRole('button',{name:/^继续$|稍后配置|以后设置/})
  await onboarding.first().waitFor({timeout:8000}).catch(()=>{})
  if(await page.getByText('内测声明',{exact:true}).isVisible()) await page.getByRole('button',{name:'继续',exact:true}).click()
  const later=page.getByRole('button',{name:/稍后配置|以后设置/})
  await later.waitFor({timeout:5000}).catch(()=>{})
  if(await later.isVisible()) await later.click()
  const target=new URL(url.origin);target.searchParams.set('dsh-houdini-session',task)
  await page.goto(target.href)
  await later.waitFor({timeout:5000}).catch(()=>{})
  if(await later.isVisible()) await later.click()
  await page.getByRole('button',{name:'Houdini 执行端',exact:true}).click({timeout:25000})
  page.once('dialog',dialog=>dialog.accept())
  await page.getByRole('button',{name:'选择并绑定',exact:true}).click()
  await page.getByText('本任务已绑定所选 Houdini。未加载、保存或验证工程内容。',{exact:true}).waitFor({timeout:10000})
  await page.getByRole('button',{name:'刷新执行端',exact:true}).click()
  await page.getByText('本任务已绑定',{exact:true}).waitFor({timeout:10000})
  await page.screenshot({path:path.join(path.dirname(log),'picker-wide.png')})
  await page.setViewportSize({width:420,height:850})
  await page.screenshot({path:path.join(path.dirname(log),'picker-narrow.png')})
  console.log('PASS actual DSH browser task/picker/confirmation/bound state; screenshots in fixture directory')
}catch(error){
  if(page){await fs.writeFile(path.join(path.dirname(log),'picker-buttons.json'),JSON.stringify(await page.getByRole('button').allTextContents()));console.error((await page.locator('body').innerText()).slice(0,2200));await page.screenshot({path:path.join(path.dirname(log),'picker-failure.png')})}
  throw error
}finally{await browser.close()}
