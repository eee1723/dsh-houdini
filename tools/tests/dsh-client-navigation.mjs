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
  const context=await browser.newContext({viewport:{width:1440,height:1000},colorScheme:"dark"})
  // Houdini's Chromium 108 lacks toSorted. Exercise the delivered DSH client
  // with that real runtime gap and the same generated asset WebView injects.
  await context.addInitScript({content:'delete Array.prototype.toSorted;\n'
    +fs.readFileSync(new URL('../../houdini/python3.11libs/dsh_iterator_polyfill.js',import.meta.url),'utf8')})
  await context.addCookies(config.cookies)
  // Exercise the shipped approval/question components and their native pending
  // interaction registry. Expose only their existing local request constructors
  // inside this owned browser fixture; no Host actions or model calls occur.
  const interactionFixtures = new Set()
  await context.route('**/*', async route => {
    if (route.request().resourceType() !== 'script') return route.continue()
    const response = await route.fetch()
    let body = await response.text()
    if (body.includes('id: "@deepseek-ai/dsh-client-ui-approval"')) {
      const marker = 'const registerPendingInteraction = ctx.uiSession.registerPendingInteraction(() => 0);'
      assert.ok(body.includes(marker), 'exact DSH approval registry changed')
      body = body.replace(marker, marker + `
        window.__dshFixtureApproval = (sessionId, request) => {
          const pending = new PendingApproval(sessionId, request);
          const remove = registerPendingInteraction(pending, async () => pending.delegate());
          return pending.result.finally(remove);
        };`)
      interactionFixtures.add('approval')
    }
    if (body.includes('id: "@deepseek-ai/dsh-client-ui-user-questions"')) {
      const marker = 'const cards = new QuestionCards(ctx.uiSession.registerPendingInteraction((pending) => pending.kind === "plan-review" ? 2 : 1));'
      assert.ok(body.includes(marker), 'exact DSH question registry changed')
      body = body.replace(marker, marker + `
        window.__dshFixtureQuestions = (sessionId, questions) => {
          const card = cards.ensure(sessionId, questions);
          const controller = new AbortController();
          const waterfall = createWaterfallRequest(undefined, controller.signal,
            channel => card.pending.detachWaterfall(channel));
          card.pending.attachWaterfall(waterfall.channel);
          return waterfall.result.finally(() => { controller.abort(); card.remove(); });
        };`)
      interactionFixtures.add('questions')
    }
    await route.fulfill({response, body})
  })
  const page=await context.newPage()
  page.on('pageerror',error=>{errors.push(String(error));console.error('PAGE ERROR: '+error)})
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
  // This owned profile has no account. Use DSH's own "configure later" path.
  await page.getByRole('button',{name:'稍后配置',exact:true}).click({timeout:15000})
  const modelButton=page.getByRole('button',{name:/^(请选择模型|选择模型，当前 )/})
  async function checkModelSelector(label) {
    await modelButton.waitFor({state:'visible',timeout:15000})
    assert.equal(await modelButton.isEnabled(),true,label+' model selector must remain usable')
    await modelButton.click()
    await page.getByRole('menu',{name:'模型与推理等级',exact:true}).waitFor({state:'visible'})
    await page.keyboard.press('Escape')
    return modelButton.getAttribute('aria-label')
  }
  // The original navigation test only inspected a nonempty conversation.
  // A blank workspace must expose DSH's model selector before its first message.
  const blankModel=await checkModelSelector('blank')
  assert.equal(await page.getByRole('button',{name:'Houdini 执行端',exact:true}).count(),0,
    'an ordinary Host must not show shared-executor binding controls')
  await page.screenshot({path:path.join(config.output,'browser-blank.png')})
  await page.setViewportSize({width:800,height:600})
  await checkModelSelector('blank narrow')
  await page.screenshot({path:path.join(config.output,'browser-blank-narrow.png')})
  await page.setViewportSize({width:1440,height:1000})
  fs.writeFileSync(config.seedFile,secondSelection.sessionId)
  await page.getByText('Isolated UI fixture: inspect Trace and tool documentation.',{exact:true}).waitFor({timeout:15000})
  const conversationModel=await checkModelSelector('nonempty')
  const composer = page.locator('[data-composer-input][contenteditable="true"]')
  await composer.fill('保留这段未发送的草稿')
  const traceTab=page.getByRole('tab',{name:'执行记录',exact:true})
  await traceTab.click()
  await page.getByRole('navigation',{name:'Trace 看板'}).waitFor()
  const traceText=await page.locator('body').innerText()
  for(const label of ['执行记录','能力资料','高级诊断']) {
    assert.ok(traceText.includes(label),'missing Trace section '+label)
  }
  assert.equal(await page.locator('[data-composer-seat]').isVisible(), false, 'Trace hides the normal composer and todo dock when no interaction is pending')
  assert.equal(await page.locator('.dsh-houdini-watermark').count(),0)
  const traceBounds=await page.locator('.dsh-trace').boundingBox()
  assert.ok(traceBounds.height>700 && traceBounds.y+traceBounds.height<=1001,'Trace fills the available viewport')
  await page.screenshot({path:path.join(config.output,'browser-trace.png')})
  await page.getByRole('button',{name:'需要关注',exact:true}).click()
  await page.getByRole('button',{name:/调用 #.*检查有警告/}).click()
  await page.locator('.tr-attention-warning').getByText('夹具：输出存在属性警告',{exact:true}).waitFor()
  assert.match(await page.locator('.tr-detail').innerText(),/\/obj\/asset\/OUT/)
  assert.match(await page.locator('.tr-detail').innerText(),/后续修复不会改写历史记录/)
  await page.screenshot({path:path.join(config.output,'browser-trace-attention.png')})
  assert.deepEqual([...interactionFixtures].sort(), ['approval','questions'])
  await page.evaluate(sessionId => {
    window.__dshFixtureApproval(sessionId, {toolName:'fixture',reason:'隔离审批可见性检查'})
      .then(value => { window.__dshFixtureApprovalResult = value })
  }, secondSelection.sessionId)
  const approval = page.locator('[data-approval-key]')
  await approval.waitFor({state:'visible'})
  assert.equal(await composer.isVisible(),false,'Trace still hides the ordinary draft during approval')
  await approval.getByRole('button',{name:'允许一次',exact:true}).click()
  await page.waitForFunction(()=>window.__dshFixtureApprovalResult === 'allowed-once')
  await approval.waitFor({state:'detached'})
  assert.equal(await page.locator('[data-composer-seat]').isVisible(),false,'settling approval keeps Trace free of the input bar')
  await page.evaluate(sessionId => {
    window.__dshFixtureQuestions(sessionId, [{id:'trace-question',header:'隔离澄清检查',question:'Trace 中仍能回答问题吗？',
      options:[{label:'可以回答',description:'只完成本地交互夹具'},{label:'稍后回答',description:'不执行任何操作'}]}])
      .then(value => { window.__dshFixtureQuestionResult = value })
  }, secondSelection.sessionId)
  const question = page.locator('[data-question-key]')
  await question.waitFor({state:'visible'})
  await question.getByText('可以回答',{exact:true}).click()
  await question.getByRole('button',{name:/提交|完成|确认|发送/}).click()
  await page.waitForFunction(()=>window.__dshFixtureQuestionResult !== undefined)
  assert.equal((await page.evaluate(()=>window.__dshFixtureQuestionResult)).answers[0].selected[0], '可以回答')
  await question.waitFor({state:'detached'})
  assert.equal(await page.locator('[data-composer-seat]').isVisible(),false,'settling clarification keeps the normal composer hidden')
  const darkBackground=await page.locator('.dsh-trace').evaluate(el=>getComputedStyle(el).backgroundColor)
  await page.emulateMedia({colorScheme:'light'})
  await page.waitForFunction(previous=>getComputedStyle(document.querySelector('.dsh-trace')).backgroundColor!==previous,darkBackground)
  await page.screenshot({path:path.join(config.output,'browser-trace-light.png')})
  await page.emulateMedia({colorScheme:'dark'})
  await page.waitForFunction(previous=>getComputedStyle(document.querySelector('.dsh-trace')).backgroundColor===previous,darkBackground)

  await page.setViewportSize({width:800,height:600})
  await page.screenshot({path:path.join(config.output,'browser-trace-narrow.png')})
  assert.equal(await page.locator('[data-composer-seat]').isVisible(),false)
  await page.getByRole('tab',{name:'对话',exact:true}).click()
  assert.equal(await composer.isVisible(),true,'leaving Trace restores the composer')
  assert.equal(await composer.innerText(),'保留这段未发送的草稿','view changes preserve the native draft')
  await traceTab.click()
  await page.setViewportSize({width:1440,height:1000})
  assert.equal(await page.getByRole('tab',{name:'Houdini 工具',exact:true}).count(),0,
    'Houdini tool information belongs to the single Trace entry')
  await page.getByRole('navigation',{name:'Trace 看板'}).getByRole('button',{name:'能力资料',exact:true}).click()
  const toolsText=await page.locator('body').innerText()
  for(const name of ['houdini_inspect','houdini_exec','houdini_request','houdini_resource','houdini_capabilities',
      'houdini_job_submit','houdini_job_status','houdini_job_cancel']) {
    assert.ok(toolsText.includes(name),'missing tool documentation '+name)
  }
  for(const label of ['当前包提供 8 个工具','本任务已用 2 个','本任务调用 3 次']) {
    assert.ok(toolsText.includes(label),'missing task usage statistic '+label)
  }
  await page.screenshot({path:path.join(config.output,'browser-tools.png')})
  await page.getByRole('button',{name:'动词目录',exact:true}).click()
  const verbViews=[]
  for(const [group,name] of [[/^节点与网络 /,'tab_create'],[/^参数与动画 /,'set_parms'],[/^渲染与模拟 /,'render_view']]) {
    await page.getByRole('button',{name:group}).click()
    const content=await page.locator('body').innerText()
    assert.ok(content.includes(name),'missing verb '+name)
    verbViews.push(content)
  }
  const verbsText=verbViews.join('\n')
  await page.screenshot({path:path.join(config.output,'browser-navigation.png')})
  await page.getByRole('navigation',{name:'Trace 看板'}).getByRole('button',{name:'高级诊断',exact:true}).click()
  await page.screenshot({path:path.join(config.output,'browser-diagnostics.png')})
  fs.writeFileSync(path.join(config.output,'browser-review.json'),JSON.stringify({firstSelection,secondSelection,blankModel,conversationModel,errors,title:await page.title(),traceText,toolsText,verbsText},null,2))
  await page.waitForFunction(()=>!new URL(location.href).searchParams.has('dsh-houdini-workspace'),null,{timeout:5000})
  assert.deepEqual(errors,[],'browser module failed')
  console.log('Actual browser: workspace selection, model menus with Chromium 108 API gap, Trace tools/verbs, native approval/clarification and draft restoration passed')
} finally {await browser.close()}
