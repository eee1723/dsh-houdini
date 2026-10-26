import fs from 'node:fs';import path from 'node:path';import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
import {randomUUID} from 'node:crypto';
import {nativeSessionSelector} from './browser-selection.mjs';
const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const {chromium}=await import(pathToFileURL(config.playwright));
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
let page;const errors=[];let sessions,renameResult;
try{
 const context=await browser.newContext({viewport:{width:1440,height:1050},colorScheme:'dark'});
 await context.addCookies(config.cookies);
 page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
 const rpc=(method,args)=>page.request.post(new URL('api/'+method,config.base).href,{data:{type:'client-request',rpcId:randomUUID(),method,payload:{args}}});
 const renamed=await rpc('session/rename',{request:{sessionId:config.sessionId,title:'Network reference verification'}});
 renameResult=await renamed.json();assert(renamed.ok()&&renameResult.result?.ok,JSON.stringify(renameResult));
 sessions=await (await rpc('session/list',{_request:{}})).json();
 const url=new URL(config.base);url.searchParams.set('dsh-houdini-workspace',config.workspace);url.searchParams.set('dsh-houdini-request','network-real-flow-check');
 await page.goto(url.href);
 const proceed=page.getByRole('button',{name:'继续',exact:true});
 const later=page.getByRole('button',{name:'稍后配置',exact:true});
 for(let i=0;i<2;i++){
  try{await Promise.race([proceed.waitFor({state:'visible',timeout:3000}),later.waitFor({state:'visible',timeout:3000})]);}
  catch(error){if(error.name!=='TimeoutError')throw error;break;}
  if(await proceed.isVisible()){
   await proceed.click();await proceed.waitFor({state:'hidden',timeout:5000});
  }else if(await later.isVisible()){
   await later.click();await later.waitFor({state:'hidden',timeout:5000});
  }
 }
 const entry=page.getByText('Network reference verification',{exact:true});
 if(!await entry.first().isVisible())await page.getByText('未分组',{exact:true}).click();
 await entry.first().waitFor({state:'visible',timeout:15000});await entry.first().click();
 await page.waitForSelector(nativeSessionSelector(config.sessionId),{timeout:30000});
 await page.getByRole('button',{name:/已完成.*用时/}).click();
 await page.getByRole('button',{name:/^(?=.*已调用工具)(?=.*执行了命令).*运行了代码等$/}).click();
 const failure=page.locator('[data-tool="pwsh"][data-state="error"]').filter({hasText:/退出码 7|exit code 7/});
 await failure.first().waitFor({timeout:15000});
 assert.equal(await failure.count(),1,'collapsed foreground failure must show actual exit code');
 const diagnostic=page.locator('[data-tool="pwsh"][data-diagnostic="true"]').filter({hasText:/有诊断输出（退出码 0）|Diagnostic output \(exit code 0\)/});
 await diagnostic.first().waitFor({timeout:15000});
 assert((await diagnostic.count())>=2,'nonterminating errors and stderr warnings must have a visible diagnostic cue');
 assert.equal(await diagnostic.filter({has:page.locator('[data-state="error"]')}).count(),0);
 assert.equal(await page.locator('[data-tool="pwsh"][data-state="error"]').filter({hasText:/退出码 99|exit code 99/}).count(),0,'stdout cannot forge process status');
 const nested=page.locator('[data-tool="pwsh"][data-state="error"]').filter({hasText:/退出码 9|exit code 9/});
 // Nested calls may initially be collapsed inside run_code; the persisted root is still visible.
 await page.screenshot({path:path.join(config.output,'network-workflow-chat.png'),fullPage:true});
 assert.equal(await page.locator('[data-approval-key]').count(),0,'workflow must not request escalation');
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(config.output,'browser-report.json'),JSON.stringify({ok:true,sessionId:config.sessionId,
  exit7Visible:true,exit0Diagnostics:await diagnostic.count(),nestedExitRows:await nested.count(),approvalRequests:0,errors},null,2));
 console.log('Actual browser: selected network task, collapsed exit 7, no escalation UI, no page errors');
}catch(error){
 fs.writeFileSync(path.join(config.output,'browser-failure.json'),JSON.stringify({error:String(error),errors,
  body:page?await page.locator('body').innerText():null,buttons:page?await page.getByRole('button').allTextContents():[],url:page?.url(),renameResult,sessions},null,2));
 if(page)await page.screenshot({path:path.join(config.output,'browser-failure.png'),fullPage:true});
 throw error;
}finally{await browser.close()}
