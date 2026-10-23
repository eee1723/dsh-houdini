"""ChatGPT settings in actual isolated H21/H22 Qt and DSH RPC.

The account replies are explicit synthetic UI fixtures. Protocol/credential
checks live in chatgpt-account.test.mjs and the pinned provider tests. This
exercise never logs into an account, calls a paid model or changes a user HIP.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('chatgpt_qt_driver', Path(__file__).with_name('dsh-source-webview.test.py'))
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
driver.__file__ = str(Path(__file__).resolve())
driver.HOST_FIXTURE = driver.HOST_FIXTURE.replace("'clientModules','agents'", "'clientModules','agents','houdiniFrontend'").replace(
    'await ctx.loader.await();', r"""await ctx.loader.await();
        const front=ctx.get('houdiniFrontend');
        const status={nativeFlowAvailable:true,credential:{stored:true,kind:'grant',writable:true},
          route:{configured:true,registered:true,writable:true,conflicts:[]},
          models:[{id:'fixture-model',name:'测试模型',inputModalities:['text','image'],contextWindow:262144,
            reasoning:{efforts:[{id:'low',name:'低'},{id:'high',name:'高'}]}}],
          defaultSelection:{provider:'existing-provider',model:'existing-model'},login:null};
        front.chatgptStatus=async()=>structuredClone(status);
        front.chatgptSelect=async(input)=>{status.defaultSelection={provider:'openai',...input};return structuredClone(status)};
        front.chatgptProbe=async(input)=>({ok:false,code:'RATE_LIMIT',message:'测试账户额度已用尽，请在 ChatGPT 设置查看用量。',model:input.model,elapsedMs:2});
        front.chatgptSignout=async()=>{status.credential={stored:false,kind:null,writable:true};return {...structuredClone(status),signout:{localCleared:true,revocation:'unconfirmed'}}};
        front.chatgptStart=async()=>{throw new Error('UI fixture refuses external login')};
        """)
driver.PAGE_ACCEPTANCE = r"""
(() => {
  if(window.__dshSourceAcceptance)return;
  const state=window.__dshSourceAcceptance={phase:'settings',done:false,facts:{layouts:[]}};
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const visible=el=>{if(!el)return false;const b=el.getBoundingClientRect();return b.width>0&&b.height>0&&getComputedStyle(el).visibility!=='hidden'};
  const wait=async(fn,label)=>{const end=Date.now()+30000;while(Date.now()<end){const v=fn();if(v)return v;await sleep(100)}throw Error('Timed out: '+label)};
  const check=(v,label)=>{if(!v)throw Error(label)};
  const button=name=>[...document.querySelectorAll('button,[role=menuitem]')].find(el=>visible(el)&&((el.textContent||'').trim()===name||el.getAttribute('aria-label')===name||el.getAttribute('title')===name||(el.getAttribute('role')==='menuitem'&&(el.textContent||'').trim().startsWith(name))));
  const panel=()=>document.querySelector('[data-houdini-chatgpt-settings]');
  const field=name=>panel()?.querySelector('[aria-label="'+name+'"]');
  const setValue=(input,value)=>{Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('change',{bubbles:true}))};
  async function capture(label,width){
    state.phase=label;state.resize={id:label,width,height:1080};
    await wait(()=>window.__dshChatGptResize===label,'Qt resize');await sleep(400);
    const box=panel().getBoundingClientRect(),controls=[...panel().querySelectorAll('input,select,button')].filter(visible).map(el=>{
      const b=el.getBoundingClientRect();return {label:el.textContent||el.getAttribute('aria-label'),left:b.left,right:b.right,width:b.width}});
    check(box.width>200,'usable content width');check(controls.every(c=>c.width>30&&c.left>=-1&&c.right<=innerWidth+1),'controls overflow viewport');
    state.facts.layouts.push({label,viewport:innerWidth,width:box.width,controls});
    state.capture=label;await wait(()=>window.__dshQtCapture===label,'Qt screenshot');
  }
  (async()=>{
    await wait(()=>window.__dshHoudiniSelection?.(),'native task selection');
    const onboarding=await wait(()=>button('继续')||button('稍后配置'),'onboarding');
    if((onboarding.textContent||'').trim()==='继续')onboarding.click();
    const account=await wait(()=>button('稍后配置')||[...document.querySelectorAll('[role=dialog]')].find(el=>visible(el)&&el.textContent.includes('添加 API Key')),'account onboarding');
    if(account.tagName==='BUTTON')account.click();else account.querySelector('button[aria-label="关闭"]').click();
    await wait(()=>![...document.querySelectorAll('[role=dialog]')].some(visible),'onboarding closed');
    (await wait(()=>button('账号菜单'),'account menu')).click();
    (await wait(()=>button('设置'),'settings entry')).click();
    (await wait(()=>button('ChatGPT 订阅'),'subscription entry')).click();
    await wait(()=>field('ChatGPT 模型')?.value==='fixture-model','RPC account catalog');
    check(panel().innerText.includes('授权已保存'),'stored credential distinction absent');
    check(panel().innerText.includes('existing-provider · existing-model'),'native default fact absent');
    setValue(field('ChatGPT 思考程度'),'high');await sleep(100);
    button('设为新对话默认').click();
    await wait(()=>panel().innerText.includes('已设为新对话的默认模型'),'selection action result');
    check(panel().innerText.includes('ChatGPT · fixture-model'),'new selection not reflected');
    button('测试模型连接').click();
    await wait(()=>panel().innerText.includes('这次模型请求未成功'),'quota error result');
    check(panel().querySelector('a[href="https://chatgpt.com/settings/usage"]'),'official usage action absent');
    await capture('chatgpt-wide',1440);
    await capture('chatgpt-narrow',760);
    button('断开连接').click();await wait(()=>button('确认断开本机授权'),'disconnect confirmation');button('确认断开本机授权').click();
    await wait(()=>panel().innerText.includes('服务端撤销尚未确认'),'unconfirmed revoke receipt');
    check(button('使用 ChatGPT 登录'),'reconnect action absent');
    check(!panel().innerText.includes('授权已保存'),'stored credential not invalidated');
    state.facts.syntheticAccount=true;state.facts.noCloudRequest=true;state.phase='done';state.ok=true;state.done=true;
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
            webview._view.page().runJavaScript('window.__dshChatGptResize='+json.dumps(request['id']), 0)

    def tick():
        if webview._view is None:
            timer.stop()
            return
        if not state['inflight']:
            state['inflight'] = True
            webview._view.page().runJavaScript('JSON.stringify(window.__dshSourceAcceptance?.resize||null)', 0, received)

    timer.timeout.connect(tick)
    timer.start(150)
    hou.session._dsh_chatgpt_resize = timer, state


if __name__ == '__main__':
    driver.main()
