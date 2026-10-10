"""Actual tutorial settings in isolated Houdini QtWebEngine; no cloud or HIP edits.

Reuses the source WebView acceptance driver's exact DSH composition, fresh
preferences, authentication, native page and owned process cleanup. Only this
test's page interaction and artificial API route differ.

python tools/tests/dsh-video-settings.test.py --runtime-cache <cache> \
    --houdini D:/Houdini22/bin/houdini.exe
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

DRIVER_PATH = Path(__file__).with_name('dsh-source-webview.test.py')
spec = importlib.util.spec_from_file_location('source_webview_driver', DRIVER_PATH)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)

# The generic driver's uiready hook must import this configured entry, not run
# the original source-surface scenario. No existing test or user file is edited.
driver.__file__ = str(Path(__file__).resolve())

# This fixture starts the Host outside Houdini. Give it the same explicit HFS
# as the owned GUI under test so the automatic Python choice reflects the
# product's ordinary Houdini-launched Host rather than this test's shell.
original_environment = driver.isolated_environment
houdini_install = None


def isolated_environment(*args, **kwargs):
    global houdini_install
    if kwargs.get('executable'):
        houdini_install = Path(kwargs['executable']).resolve().parent.parent
    env = original_environment(*args, **kwargs)
    if houdini_install:
        env['HFS'] = str(houdini_install)
    return env


driver.isolated_environment = isolated_environment


def report(*values, **options):
    if values and str(values[0]).startswith('Actual source QtWebEngine composition,'):
        values = ('Actual Qt tutorial settings: registration, editable fields, save/reopen, local dependencies and wide/narrow layout passed. No cloud request or HIP change.',)
    print(*values, **options)


driver.print = report
driver.HOST_FIXTURE = driver.HOST_FIXTURE.replace(
    "'clientModules','agents'", "'clientModules','agents','settings'").replace(
    'await ctx.loader.await();', """await ctx.loader.await();
        const routeSettings=ctx.settings.describe().find(row=>row.ns==='llm-pi-ai');
        await ctx.settings.mutate(routeSettings.ns,[{op:'set',path:['providers','fixture-video-ui'],value:{
          api:'openai-completions',baseURL:'http://127.0.0.1:9/v1/',apiKeyEnv:'DSH_VIDEO_UI_UNSET_KEY',
          models:[{id:'fixture-chat-catalog',name:'Fixture chat catalog',input:['text']}] }},
          {op:'set',path:['providers','openai'],value:{apiKeyEnv:'DSH_VIDEO_UI_UNSET_OPENAI_KEY'}},
          {op:'set',path:['providers','anthropic'],value:{apiKeyEnv:'DSH_VIDEO_UI_UNSET_ANTHROPIC_KEY'}}],routeSettings.revision);
        """)

driver.PAGE_ACCEPTANCE = r"""
(() => {
  if(window.__dshSourceAcceptance)return;
  const config=CONFIG_JSON;
  const state=window.__dshSourceAcceptance={phase:'settings-open',done:false,facts:{layouts:[]}};
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const visible=el=>{if(!el)return false;const b=el.getBoundingClientRect();return b.width>0&&b.height>0&&getComputedStyle(el).visibility!=='hidden'};
  const wait=async(fn,label)=>{const end=Date.now()+30000;while(Date.now()<end){const v=fn();if(v)return v;await sleep(100)}throw Error('Timed out: '+label)};
  const check=(v,label)=>{if(!v)throw Error(label)};
  const button=name=>[...document.querySelectorAll('button')].find(el=>visible(el)&&((el.textContent||'').trim()===name||el.getAttribute('aria-label')===name||el.getAttribute('title')===name));
  const panel=()=>document.querySelector('[data-houdini-video-settings]');
  const field=name=>[...panel().querySelectorAll('label')].find(el=>el.querySelector('strong')?.textContent===name)?.querySelector('input,select');
  function setValue(input,value){
    Object.getOwnPropertyDescriptor(input.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(input,value);
    input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}));
  }
  async function openAdvanced(){
    if(!panel().querySelector('details').open)panel().querySelector('summary').click();
    await wait(()=>panel().querySelector('details').open&&visible(field('Python 程序')),'advanced settings expanded');
  }
  async function capture(label,width){
    state.phase=label;state.resize={id:label,width,height:1000};
    await wait(()=>window.__dshVideoResize===label,'native Qt resize '+label);
    await openAdvanced();
    await sleep(400);
    const section=panel(),box=section.getBoundingClientRect();
    const controls=[...section.querySelectorAll('input,select,button')].filter(visible).map(el=>{
      const r=el.getBoundingClientRect();return{tag:el.tagName,label:el.textContent||el.placeholder||'',left:r.left,right:r.right,width:r.width,disabled:el.disabled};});
    check(box.width>200,'settings content has usable width');
    check(controls.every(c=>c.width>30&&c.left>=-1&&c.right<=innerWidth+1),'settings controls overflow viewport');
    const first=field('转录服务供应商'),r=first.getBoundingClientRect();
    check(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===first,'tutorial form is covered by another dialog');
    state.facts.layouts.push({label,viewport:innerWidth,contentWidth:box.width,controls});
    state.capture=label;await wait(()=>window.__dshQtCapture===label,'native screenshot '+label);
  }
  (async()=>{
    await wait(()=>window.__dshHoudiniSelection?.(),'native task selection');
    const onboarding=await wait(()=>button('继续')||button('稍后配置'),'native first-use prompt');
    if((onboarding.textContent||'').trim()==='继续')onboarding.click();
    const later=await wait(()=>button('稍后配置'),'native account prompt');later.click();
    await wait(()=>!button('稍后配置'),'account prompt dismissed');
    const settings=await wait(()=>button('设置'),'native settings entry');settings.click();
    const tutorial=await wait(()=>button('教程视频'),'registered tutorial settings section');tutorial.click();
    await wait(()=>panel()&&field('转录服务供应商')&&!field('转录服务供应商').disabled,'editable tutorial form');
    await wait(()=>[...field('转录服务供应商').options].some(o=>o.value==='fixture-video-ui'),'configured provider discovery');
    const configuredProviders=[...field('转录服务供应商').options].map(o=>o.value);
    check(configuredProviders.includes('openai')&&configuredProviders.includes('anthropic'),'catalog-only and non-OpenAI configured providers must remain visible');
    state.facts.providers=configuredProviders;
    check(![...panel().querySelectorAll('input')].some(i=>i.type==='password'),'tutorial page must not duplicate credential storage');
    state.phase='settings-edit';
    setValue(field('转录服务供应商'),'fixture-video-ui');await sleep(150);
    check(field('转录模型 ID').tagName==='SELECT','configured transcription models must use a dropdown');
    check([...field('转录模型 ID').options].some(o=>o.value==='fixture-chat-catalog'),'exact configured model catalog missing');
    setValue(field('转录模型 ID'),'fixture-chat-catalog');await sleep(150);
    const saveCatalog=await wait(()=>{const b=button('保存设置');return b&&!b.disabled?b:null},'catalog save enabled');saveCatalog.click();
    await wait(()=>panel().innerText.includes('已保存。'),'catalog selection persisted');
    const nativeModels=await wait(()=>button('模型'),'native model settings section');nativeModels.click();
    await wait(()=>!panel(),'catalog form unmounted');button('教程视频').click();
    await wait(()=>panel()&&field('转录模型 ID').value==='fixture-chat-catalog','saved configured model after reopen');
    setValue(field('转录服务供应商'),'anthropic');await sleep(150);
    check(field('转录模型 ID').value==='','changing provider must clear the previous provider model');
    check(panel().innerText.includes('尚无可复用的 OpenAI 兼容音频 API 地址'),'unsupported provider must explain its configuration');
    setValue(field('转录服务供应商'),'fixture-video-ui');await sleep(150);
    setValue(field('转录模型 ID'),'__dsh_other_transcription_model__');await sleep(150);
    await wait(()=>field('其他转录模型 ID'),'audio-only model ID supplement');
    setValue(field('其他转录模型 ID'),'fixture-asr-ui');await sleep(150);
    await openAdvanced();
    setValue(field('Python 程序'),'');await sleep(150);
    const save=await wait(()=>{const b=button('保存设置');return b&&!b.disabled?b:null},'save enabled');save.click();
    await wait(()=>panel().innerText.includes('已保存。'),'real settings mutation accepted');
    state.facts.saved=true;
    // Unmount the contribution and read a fresh form snapshot through the
    // native section navigation; do not inspect React's private state.
    const models=await wait(()=>button('模型'),'native model settings section');models.click();
    await wait(()=>!panel(),'tutorial form unmounted');button('教程视频').click();
    await wait(()=>panel()&&field('其他转录模型 ID')?.value==='fixture-asr-ui','saved audio-only model after reopen');
    check(field('转录服务供应商').value==='fixture-video-ui','provider did not survive reopening');
    await openAdvanced();
    check(field('Python 程序').value==='','automatic Python did not survive reopening');
    state.facts.reopened={provider:field('转录服务供应商').value,model:field('其他转录模型 ID').value,python:field('Python 程序').value};
    state.phase='local-dependencies';button('检查本机依赖').click();
    await wait(()=>panel().querySelectorAll('details li').length===3,'local dependency results');
    state.facts.dependencies=[...panel().querySelectorAll('details li')].map(el=>el.textContent);
    state.facts.dependencyPaths=[...panel().querySelectorAll('details li')].map(el=>({name:el.textContent.split('：')[0],path:el.title}));
    check(state.facts.dependencies.some(s=>/^Python：Python 3\./.test(s)),'actual Python version missing');
    check(state.facts.dependencies.some(s=>/^FFmpeg：ffmpeg version/.test(s)),'actual private FFmpeg version missing');
    check(state.facts.dependencies.some(s=>/^ffprobe：ffprobe version/.test(s)),'actual private ffprobe version missing');
    check(state.facts.dependencyPaths.filter(row=>row.name!=='Python').every(row=>/runtime[\\/]video[\\/]ffmpeg[\\/]bin[\\/]ff(?:mpeg|probe)\.exe$/.test(row.path)), 'media dependencies must come from the plugin private directory');
    await capture('video-settings-wide',1440);
    await capture('video-settings-narrow',760);
    state.facts.noAudioUploaded=true;state.facts.cloudEndpoint='unreachable fixture route; diagnostics are local';
    state.phase='done';state.ok=true;state.done=true;
  })().catch(error=>{state.error=String(error.stack||error);state.ok=false;state.done=true});
})();
"""


atomic_json = driver.atomic_json


def start_gui_probe():
    driver.start_gui_probe()
    import hou
    from hutil.Qt import QtCore
    import dsh_webview as webview
    state = {'inflight': False, 'last': None}
    timer = QtCore.QTimer(hou.qt.mainWindow())

    def received(value):
        state['inflight'] = False
        if not value or webview._window is None:
            return
        request = json.loads(value)
        if request and request['id'] != state['last']:
            state['last'] = request['id']
            webview._window.resize(request['width'], request['height'])
            webview._view.page().runJavaScript('window.__dshVideoResize='+json.dumps(request['id']), 0)

    def tick():
        if webview._view is None:
            timer.stop()
            return
        if not state['inflight']:
            state['inflight'] = True
            webview._view.page().runJavaScript('JSON.stringify(window.__dshSourceAcceptance?.resize||null)', 0, received)

    timer.timeout.connect(tick)
    timer.start(150)
    hou.session._dsh_video_settings_resize = timer, state


if __name__ == '__main__':
    driver.main()
