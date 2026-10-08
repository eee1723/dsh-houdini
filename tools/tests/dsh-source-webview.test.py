"""Source-mode acceptance in a fresh real Houdini GUI and its QtWebEngine.

Requires a built checkout and the exact preferred DSH npm cache. No model is
called, no Bridge is contacted, and no HIP is loaded, saved or modified. The
driver owns its temporary Host and GUI handles; it never restarts a live app.

python tools/tests/dsh-source-webview.test.py --runtime-cache <cache> \
    --houdini D:/houdini/bin/houdini.exe --houdini D:/Houdini22/bin/houdini.exe
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=True), encoding='utf-8')
    temporary.replace(path)


class GuiProcessJob:
    """Own only this test's GUI descendants; leave Chromium sandbox Jobs intact.

    No UI, memory, process-count or breakaway restrictions are applied. Windows
    10+ supports the nested Jobs created by the renderer sandbox. Explicit
    cleanup confirms zero active descendants before closing our final handle.
    """
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes

        class Basic(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount',
                        'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

        class Extended(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO), ('ProcessMemoryLimit', ctypes.c_size_t),
                        ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t),
                        ('PeakJobMemoryUsed', ctypes.c_size_t)]

        class Accounting(ctypes.Structure):
            _fields_ = [('TotalUserTime', ctypes.c_int64), ('TotalKernelTime', ctypes.c_int64),
                        ('ThisPeriodTotalUserTime', ctypes.c_int64), ('ThisPeriodTotalKernelTime', ctypes.c_int64),
                        ('TotalPageFaultCount', wintypes.DWORD), ('TotalProcesses', wintypes.DWORD),
                        ('ActiveProcesses', wintypes.DWORD), ('TotalTerminatedProcesses', wintypes.DWORD)]

        self.Accounting = Accounting
        kernel = self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        kernel.QueryInformationJobObject.restype = wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = kernel.CreateJobObjectW(None, None)
        self.cleanup = None
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE only
        if not self.handle or not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            if self.handle:
                kernel.CloseHandle(self.handle)
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, self.wintypes.HANDLE(int(process._handle))):
            error = self.ctypes.WinError(self.ctypes.get_last_error())
            process.kill()
            process.wait(timeout=20)
            raise error

    def active(self):
        info = self.Accounting()
        if not self.kernel.QueryInformationJobObject(self.handle, 1, self.ctypes.byref(info), self.ctypes.sizeof(info), None):
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        return info.ActiveProcesses

    def close(self):
        if self.handle is None:
            return self.cleanup
        try:
            forced = self.active() > 0
            if forced and not self.kernel.TerminateJobObject(self.handle, 1):
                raise self.ctypes.WinError(self.ctypes.get_last_error())
            deadline = time.monotonic()+10
            while self.active():
                if time.monotonic() >= deadline:
                    raise RuntimeError('Owned Houdini/renderer descendants did not terminate')
                time.sleep(.05)
            self.cleanup = {'activeProcesses': 0, 'terminatedRemainder': forced, 'limits': 'KILL_ON_JOB_CLOSE only'}
            return self.cleanup
        finally:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


# The real Host publishes known, explicitly artificial UI records. Human
# interaction goes through DSH's scoped Remote waterfall and its actual native
# approval/question components. It does not grant or execute any real action.
HOST_FIXTURE = r"""
import fs from 'node:fs';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(process.env.DSH_SOURCE_RUNTIME_BIN);
const {scopeTarget}=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-scope')));
const {createAssistantMessage}=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-llm')));
const config=JSON.parse(fs.readFileSync(process.env.DSH_SOURCE_GUI_CONFIG,'utf8'));
const {HOUDINI_TOOLS}=await import(config.toolCatalogUrl);
const write=(path,value)=>{fs.writeFileSync(path+'.tmp',JSON.stringify(value));fs.renameSync(path+'.tmp',path)};
export const inject=['loader','tools','agentPresets','clientModules','agents'];
export function apply(ctx) {
  ctx.effect(()=>{
    let stopped=false,busy=false,lastCommand;
    const lifetime=new AbortController();
    queueMicrotask(async()=>{
      try {
        await ctx.loader.await();
        const roster=await ctx.agentPresets.remoteExportList();
        const lease=await ctx.agentPresets.acquireScope('houdini');
        try {write(config.composition,{roster,tools:ctx.tools.schemas(lease.key).map(t=>t.name),expectedHoudiniTools:Object.keys(HOUDINI_TOOLS),
          graph:ctx.clientModules.graph(),rootEntries:[...ctx.loader.entries()].map(e=>({name:e.options.name,disabled:e.disabled}))});}
        finally {await lease[Symbol.asyncDispose]();}
      } catch(error) {write(config.composition,{error:String(error.stack||error)});}
    });
    const timer=setInterval(async()=>{
      if(stopped||busy||!fs.existsSync(config.command))return;
      let request;
      try {request=JSON.parse(fs.readFileSync(config.command,'utf8'));}catch{return;}
      if(request.id===lastCommand)return;
      const agent=ctx.agents.get(request.sessionId);
      if(!agent)return;
      busy=true;lastCommand=request.id;
      try {
        let result;
        if(request.action==='seed') {
          agent.session.append('turn/start',{turn:1});
          agent.session.append('user/message',{role:'user',source:{kind:'user'},content:[
            {type:'text',text:'Isolated Qt fixture: inspect Trace and native resources.'}]},{surfaceOp:'append'});
          agent.session.append('step/start',{turn:1,step:1});
          const canonical={ok:true,stdout:'',stderr:'',result:{fixture:true},
            execution:{runtime_id:'qt-fixture',sequence:1,observed_at:1,hip_dir:null,hip_is_new:true}};
          agent.session.append('tool/call',{turn:1,step:1,callId:'qt-inspect',name:'houdini_inspect',arguments:'{"code":"__result__ = scene_info()"}'});
          agent.session.append('tool/result',{turn:1,step:1,message:{role:'tool',source:{kind:'tool',callId:'qt-inspect'},
            content:[{type:'text',text:'Qt UI fixture; no HOM was executed.'}],isError:false},meta:{canonical}},{surfaceOp:'append'});
          agent.session.append('tool/call',{turn:1,step:1,callId:'qt-present',name:'present',arguments:JSON.stringify({files:[{path:config.resource}]})});
          agent.session.append('deliverables/presented',{turn:1,callId:'qt-present',files:[{path:config.resource,description:'Isolated Qt text resource'}]});
          agent.session.append('tool/result',{turn:1,step:1,message:{role:'tool',source:{kind:'tool',callId:'qt-present'},
            content:[{type:'text',text:'Fixture resource declared.'}],isError:false}},{surfaceOp:'append'});
          agent.session.append('assistant/message',{turn:1,step:1,stream:[],message:createAssistantMessage({source:{provider:'qt-fixture',model:'static-no-model'},content:[
            {type:'text',text:'Qt fixture complete. The declared text file is available below.'}]})},{surfaceOp:'append'});
          agent.session.append('step/end',{turn:1,step:1});
          agent.session.append('turn/end',{turn:1,reason:{kind:'completed'}});
          result={seeded:true};
        } else if(request.action==='approval') {
          result=await ctx.waterfall(scopeTarget(agent,agent),'approval/request',{
            agent,toolName:'isolated-ui-fixture',reason:'仅测试审批界面，不执行任何操作',signal:lifetime.signal},()=>Promise.resolve('unavailable'));
        } else if(request.action==='question') {
          result=await ctx.waterfall(scopeTarget(agent,agent),'user-questions/request',{
            agent,signal:lifetime.signal,questions:[{id:'qt-question',question:'内嵌页面中可以回答问题吗？',
              options:[{label:'可以回答'},{label:'稍后回答'}]}]},()=>Promise.resolve({answers:[]}));
        } else throw Error('Unknown fixture command');
        write(config.response,{id:request.id,ok:true,result});
      } catch(error) {write(config.response,{id:request.id,ok:false,error:String(error.stack||error)});}
      finally {busy=false;}
    },100);
    return ()=>{stopped=true;lifetime.abort();clearInterval(timer)};
  });
}
"""


# Runs inside the shipped QtWebEngine page. Every assertion observes the real
# DOM/native DSH stores; there is no Chrome driver or replacement renderer.
PAGE_ACCEPTANCE = r"""
(() => {
  if (window.__dshSourceAcceptance) return;
  const config=CONFIG_JSON;
  const state=window.__dshSourceAcceptance={phase:'selection',done:false,facts:{}};
  const visible=el=>{if(!el)return false;const box=el.getBoundingClientRect();return box.width>0&&box.height>0&&getComputedStyle(el).visibility!=='hidden'&&getComputedStyle(el).display!=='none'};
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const wait=async(fn,label)=>{const end=Date.now()+30000;while(Date.now()<end){const value=fn();if(value)return value;await sleep(100)}throw Error('Timed out: '+label)};
  const check=(condition,label)=>{if(!condition)throw Error(label)};
  const button=(name)=>[...document.querySelectorAll('button')].find(el=>visible(el)&&((el.textContent||'').trim()===name||el.getAttribute('aria-label')===name));
  const tab=name=>[...document.querySelectorAll('[role=tab]')].find(el=>visible(el)&&(el.textContent||'').trim()===name);
  const normalized=path=>String(path||'').replace(/\\/g,'/').replace(/\/+$/,'').toLowerCase();
  const response=id=>window.__dshSourceCommandResponse?.id===id?window.__dshSourceCommandResponse:null;
  async function command(action,waitForAnswer=true) {
    const id=action+'-'+Date.now();
    state.command={id,action,sessionId:state.facts.selection.sessionId};
    if(!waitForAnswer)return id;
    const answer=await wait(()=>response(id),action+' Host response');
    check(answer.ok,answer.error||action+' failed');return answer.result;
  }
  async function rpc(method,args) {
    const response=await fetch('/api/'+method,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({type:'client-request',rpcId:'qt-fixture-'+Date.now(),method,payload:{args}})});
    const wire=await response.json();check(response.ok&&wire.result?.ok,'RPC '+method+' failed');return wire.result.value;
  }
  async function checkModels(label) {
    state.phase=label;
    const model=await wait(()=>[...document.querySelectorAll('button')].find(el=>visible(el)&&/^(请选择模型|选择模型，当前 )/.test(el.getAttribute('aria-label')||'')),label+' model selector');
    check(!model.disabled,label+' model selector disabled');model.click();
    const menu=await wait(()=>[...document.querySelectorAll('[role=menu]')].find(el=>visible(el)&&el.getAttribute('aria-label')==='模型与推理等级'),label+' model menu');
    menu.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    await wait(()=>!visible(menu),label+' menu close');state.facts[label]=true;
  }
  (async()=>{
    state.facts.userAgent=navigator.userAgent;
    state.facts.css={colorMix:CSS.supports('color','color-mix(in srgb, red 50%, blue)'),has:CSS.supports('selector(:has(*))')};
    const selected=await wait(()=>window.__dshHoudiniSelection?.(), 'native DSH selection');
    check(normalized(selected.cwd)===normalized(config.workspace),'selected workspace differs');
    check(selected.agentPreset==='houdini','Houdini preset is not active');
    state.facts.selection=selected;
    await wait(()=>!new URL(location.href).searchParams.has('dsh-houdini-workspace'),'workspace intent consumed');
    check(!new URL(location.href).searchParams.has('token'),'launch token leaked to app URL');
    await wait(()=>document.documentElement.lang.startsWith('zh'),'fixture Host locale.preference=zh');
    state.facts.locale=document.documentElement.lang;
    const continueButton=button('继续');if(continueButton)continueButton.click();
    await wait(()=>button('稍后配置')||[...document.querySelectorAll('button')].some(el=>visible(el)&&/^(请选择模型|选择模型，当前 )/.test(el.getAttribute('aria-label')||'')),'account prompt or composer');
    const later=button('稍后配置');if(later)later.click();
    await checkModels('blankModel');
    state.phase='reopen';
    const before=await rpc('session/list',{_request:{}});
    const rows=value=>value.items.filter(row=>normalized(row.cwd)===normalized(config.workspace));
    check(rows(before).length===1,'initial workspace has duplicate tasks');
    await wait(()=>window.__dshQtReopened,'native WebView reopen');
    await wait(()=>!new URL(location.href).searchParams.has('dsh-houdini-workspace'),'reopen intent consumed');
    const after=await rpc('session/list',{_request:{}});
    check(rows(after).length===1,'reopen created a duplicate task');
    check(window.__dshHoudiniSelection().sessionId===selected.sessionId,'reopen replaced selection');
    state.facts.sameTaskOnReopen=true;
    state.phase='seed';await command('seed');
    await wait(()=>document.body.innerText.includes('Isolated Qt fixture: inspect Trace and native resources.'),'seeded conversation');
    await checkModels('conversationModel');
    const editor=await wait(()=>document.querySelector('[data-composer-input][contenteditable="true"]'),'native draft editor');
    editor.focus();document.execCommand('insertText',false,'Qt 验收未发送草稿');
    editor.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:'Qt 验收未发送草稿'}));
    await wait(()=>editor.innerText.includes('Qt 验收未发送草稿'),'draft input settled');
    const draft=editor.innerText;
    state.phase='caption-close';
    await wait(()=>window.__dshQtCaptionReopened,'native caption close and reopen');
    check(editor.innerText===draft,'caption close/reopen lost the draft');
    check(window.__dshHoudiniSelection().sessionId===selected.sessionId,'caption close/reopen replaced selection');
    state.facts.draftAfterCaptionClose=true;
    (await wait(()=>tab('执行记录'),'Trace tab')).click();
    await wait(()=>visible(document.querySelector('.dsh-trace')),'Trace visible');
    const traceRows=await wait(()=>{const rows=[...document.querySelectorAll('.tr-call-row')];
      return rows.some(el=>(el.getAttribute('aria-label')||'').includes('houdini_inspect'))?rows:null},'Trace consumes seeded Houdini call');
    check(traceRows.length===2,'Trace must show exactly the two seeded calls');state.facts.traceCalls=traceRows.length;
    await wait(()=>!visible(document.querySelector('[data-composer-seat]')),'Trace hides normal composer');
    state.facts.trace=true;state.phase='approval';
    const approvalId=await command('approval',false);
    const approval=await wait(()=>{const el=document.querySelector('[data-approval-key]');return visible(el)?el:null},'native approval takeover');
    check(!visible(editor),'normal draft visible during approval');
    const allow=[...approval.querySelectorAll('button')].find(el=>el.textContent.trim()==='允许一次');check(allow,'approval action absent');allow.click();
    const granted=await wait(()=>response(approvalId),'approval response');check(granted.ok&&granted.result==='allowed-once','approval was not answered');
    await wait(()=>!visible(document.querySelector('[data-composer-seat]')),'normal composer hidden after approval');
    state.facts.approval=true;state.phase='question';
    const questionId=await command('question',false);
    const question=await wait(()=>{const el=document.querySelector('[data-question-key]');return visible(el)?el:null},'native question takeover');
    const option=[...question.querySelectorAll('button[role=radio]')].find(el=>el.getAttribute('aria-label')==='可以回答');check(option,'question choice absent');option.click();
    const submit=await wait(()=>{const current=question.querySelector('[role=radio][aria-label="可以回答"]');
      const action=[...question.querySelectorAll('button')].find(el=>el.textContent.trim()==='提交');
      return current?.getAttribute('aria-checked')==='true'&&action&&!action.disabled?action:null},'selected answer and enabled submit');submit.click();
    const answered=await wait(()=>response(questionId),'question response');check(answered.ok&&answered.result?.answers?.[0]?.selected?.[0]==='可以回答','question was not answered');
    await wait(()=>!visible(document.querySelector('[data-composer-seat]')),'normal composer hidden after question');
    state.facts.question=true;
    tab('对话').click();await wait(()=>visible(editor),'composer restored');check(editor.innerText===draft,'draft was lost');state.facts.draftRestored=true;
    state.phase='resources';
    const image=new Image();image.src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l5cAAAAASUVORK5CYII=';
    await wait(()=>image.complete&&image.naturalWidth===1,'data URI PNG decoding');state.facts.dataImage=true;
    const resourceUrl=new URL('dsh-resource://file/session/'+encodeURIComponent(selected.sessionId)+'/plain.txt');
    check(resourceUrl.hostname==='file','file resource URL lost its authority');state.facts.resourceAuthority=true;
    const preview=await wait(()=>[...document.querySelectorAll('[data-presented-file] button')].find(el=>visible(el)&&(el.getAttribute('aria-label')||'').startsWith('在侧边栏预览 ')&&(el.getAttribute('aria-label')||'').includes('plain.txt')),'fixture text file card');
    preview.click();await wait(()=>document.body.innerText.includes('ISOLATED QT TEXT RESOURCE CONTENT'),'native DSH file resource read');state.facts.textResource=true;
    state.phase='complete';state.done=true;state.ok=true;
  })().catch(error=>{state.done=true;state.ok=false;state.error=String(error.stack||error)});
})();
"""


def start_gui_probe():
    """uiready entry in a fresh Houdini GUI; all network work is elsewhere."""
    import hou
    from hutil.Qt import QtCore
    from PySide6.QtWebEngineCore import QWebEnginePage
    config = json.loads(Path(os.environ['DSH_SOURCE_GUI_CONFIG']).read_text(encoding='utf-8'))
    sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
    import dsh_webview as webview
    assert hou.isUIAvailable(), 'acceptance requires actual Houdini GUI'
    initial_hip = {'path': hou.hipFile.path(), 'isNew': bool(hou.hipFile.isNewFile()),
                   'dirty': bool(hou.hipFile.hasUnsavedChanges())}
    assert initial_hip['isNew'] and not initial_hip['dirty'], 'fixture must start in a clean unsaved GUI scene'
    console, loads, renderer = [], [], []
    state = {'started': time.monotonic(), 'phase': 'page-load', 'injected': False,
             'inflight': False, 'command': None, 'response': None, 'finished': False, 'reopened': False,
             'captionClosed': False, 'captionReopened': False,
             'lastObserved': None, 'lastDiagnostic': 0, 'lastPoll': None, 'lastCallback': None,
             'emptyCallbacks': 0, 'injectionAck': False}
    output = Path(config['output'])

    class ProbePage(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):
            console.append({'level': str(level), 'message': str(message)[:1200],
                            'line': line, 'source': str(source).split('?')[0][-200:]})

    webview.QWebEnginePage = ProbePage
    webview.show_webview(workspace_dir=config['workspace'], authenticated_url=config['authenticatedUrl'], frontend_url=config['base'])
    webview._window.move(12000, 12000)
    webview._window.resize(1440, 1000)
    # Native ownership keeps this tool above Houdini while allowing another
    # application to cover the whole group. Qt hints alone cannot prove this.
    window = webview._window
    main = hou.qt.mainWindow()
    assert window.isWindow() and window.parentWidget() is main
    assert not window.windowFlags() & QtCore.Qt.WindowStaysOnTopHint
    assert window.windowFlags() & QtCore.Qt.WindowMinimizeButtonHint
    assert window.windowFlags() & QtCore.Qt.WindowCloseButtonHint
    assert window.windowFlags() & QtCore.Qt.WindowSystemMenuHint
    owner_facts = {'qtOwnedByHoudini': True, 'systemTopmost': False}
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        user = ctypes.WinDLL('user32', use_last_error=True)
        user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user.GetWindow.restype = wintypes.HWND
        user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user.GetWindowLongW.restype = ctypes.c_long
        user.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
        user.GetSystemMenu.restype = wintypes.HMENU
        user.GetMenuState.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
        user.GetMenuState.restype = wintypes.UINT
        user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.PostMessageW.restype = wintypes.BOOL
        native_owner = int(user.GetWindow(int(window.winId()), 4) or 0)
        native_topmost = bool(user.GetWindowLongW(int(window.winId()), -20) & 8)
        assert native_owner == int(main.winId()) and not native_topmost
        close_state = int(user.GetMenuState(user.GetSystemMenu(int(window.winId()), False), 0xF060, 0))
        assert close_state != 0xffffffff and not close_state & 3, 'native SC_CLOSE is missing or disabled'
        owner_facts.update(nativeOwnedByHoudini=True, systemTopmost=native_topmost, nativeCloseEnabled=True)
    page = webview._view.page()
    page.loadFinished.connect(lambda ok: loads.append(bool(ok)))
    page.renderProcessTerminated.connect(lambda status, code: renderer.append({'status': str(status), 'code': code}))
    timer = QtCore.QTimer(hou.qt.mainWindow())

    def finish(ok, detail):
        if state['finished']:
            return
        state['finished'] = True
        timer.stop()
        final_hip = {'path': hou.hipFile.path(), 'isNew': bool(hou.hipFile.isNewFile()),
                     'dirty': bool(hou.hipFile.hasUnsavedChanges())}
        hip_untouched = initial_hip == final_hip and not initial_hip['dirty'] and not final_hip['dirty']
        result = {'ok': ok and hip_untouched and not renderer and any(loads) and not any('ErrorMessageLevel' in entry.get('level', '') for entry in console), 'gui': True, 'houdini': hou.applicationVersionString(),
                  'phase': state['phase'], 'detail': detail, 'loads': loads, 'renderer': renderer,
                  'console': console[-60:], 'hipUntouched': hip_untouched,
                  'hipBefore': initial_hip, 'hipAfter': final_hip, 'lastObserved': state['lastObserved'],
                  'offTheRecord': page.profile().isOffTheRecord(), 'windowOwner': owner_facts,
                  'screenshot': 'pending'}
        # Preserve failure evidence even if the native render/grab path stalls.
        atomic_json(output, result)
        try:
            result['screenshot'] = 'saved' if webview._window.grab().save(str(output.with_suffix('.png'))) else 'save_failed'
        except Exception as error:
            result['screenshot'] = str(error)
        atomic_json(output, result)
        webview._dispose_webview()
        QtCore.QTimer.singleShot(100, hou.qt.mainWindow().close)

    def received(value):
        state['inflight'] = False
        state['lastCallback'] = round(time.monotonic()-state['started'], 2)
        if state['finished'] or not value:
            if not value:
                state['emptyCallbacks'] += 1
            return
        try:
            observed = json.loads(urllib.parse.unquote(value))
            state['lastObserved'] = observed
            if observed.get('navigationError'):
                finish(False, observed)
                return
            if (not state['injected'] and any(loads) and observed.get('ready') == 'complete'
                    and observed.get('selectionFunction') == 'function'
                    and urllib.parse.urlsplit(observed.get('href', '')).netloc == urllib.parse.urlsplit(config['base']).netloc):
                state['injected'] = True
                source = PAGE_ACCEPTANCE.replace('CONFIG_JSON', json.dumps({'workspace': config['workspace']}))
                page.runJavaScript(source, 0, lambda _value: state.update(injectionAck=True))
            probe = observed.get('probe')
            if not probe:
                return
            phase = probe.get('phase')
            if phase != state['phase']:
                state['phase'] = phase
                atomic_json(output.with_suffix('.progress.json'), {'phase': phase, 'elapsed': round(time.monotonic()-state['started'], 1)})
            if phase == 'reopen' and not state['reopened']:
                state['reopened'] = True
                webview.show_webview(workspace_dir=config['workspace'], frontend_url=config['base'])
                page.runJavaScript('window.__dshQtReopened=true', 0)
            if phase == 'caption-close' and not state['captionClosed']:
                state['captionClosed'] = True
                if os.name == 'nt':
                    # Use the native command issued by the caption X, rather
                    # than QWidget.close(), so the native close path is tested.
                    assert user.PostMessageW(int(window.winId()), 0x112, 0xF060, 0)
                else:
                    window.close()
            elif phase == 'caption-close' and not state['captionReopened']:
                assert not window.isVisible(), 'native caption command did not close the tool'
                assert webview._view.page() is page, 'close destroyed the current page'
                webview._load_finished(True)
                webview._retry_load()
                assert not window.isVisible(), 'background callback reopened a closed tool'
                webview.show_webview(frontend_url=config['base'])
                assert webview._window is window and webview._view.page() is page
                assert window.isVisible()
                state['captionReopened'] = True
                owner_facts.update(nativeCloseHides=True, samePageOnCloseReopen=True)
                page.runJavaScript('window.__dshQtCaptionReopened=true', 0)
            command = probe.get('command')
            if command and command['id'] != state['command']:
                state['command'] = command['id']
                atomic_json(config['command'], command)
            if probe.get('done'):
                finish(probe.get('ok') is True, probe)
        except Exception:
            finish(False, traceback.format_exc())

    def tick():
        elapsed = time.monotonic()-state['started']
        if elapsed-state['lastDiagnostic'] >= 2:
            state['lastDiagnostic'] = elapsed
            atomic_json(output.with_suffix('.diagnostics.json'), {
                'phase': state['phase'], 'elapsed': round(elapsed, 2), 'inflight': state['inflight'],
                'lastPoll': state['lastPoll'], 'lastCallback': state['lastCallback'],
                'emptyCallbacks': state['emptyCallbacks'], 'injected': state['injected'],
                'injectionAck': state['injectionAck'], 'loads': loads, 'renderer': renderer,
                'console': console[-60:], 'lastObserved': state['lastObserved'],
            })
        if renderer:
            finish(False, 'QtWebEngine renderer terminated; inspect native launch/DLL environment')
            return
        if elapsed > config['timeout']:
            finish(False, 'GUI acceptance timed out; no Chrome fallback')
            return
        response_path = Path(config['response'])
        if response_path.exists():
            response = json.loads(response_path.read_text(encoding='utf-8'))
            if response['id'] != state['response']:
                state['response'] = response['id']
                page.runJavaScript('window.__dshSourceCommandResponse='+json.dumps(response), 0)
        if state['inflight']:
            return
        state['inflight'] = True
        state['lastPoll'] = round(elapsed, 2)
        # ASCII-only PySide result transport avoids H21's Unicode conversion bug.
        page.runJavaScript("""encodeURIComponent(JSON.stringify({ready:document.readyState,hasBody:!!document.body,
          href:location.href,visibility:document.visibilityState,language:document.documentElement.lang,probe:window.__dshSourceAcceptance,
          selectionFunction:typeof window.__dshHoudiniSelection,selection:window.__dshHoudiniSelection?.(),
          navigationPending:new URL(location.href).searchParams.has('dsh-houdini-workspace'),
          navigationError:document.querySelector('#dsh-houdini-navigation[role=alert]')?.textContent,
          text:document.body?.innerText?.slice(0,8000),
          scripts:[...document.scripts].map(script=>script.src.split('?')[0]).filter(Boolean).slice(-25)}))""", 0, received)

    timer.timeout.connect(tick)
    timer.start(250)
    hou.session._dsh_source_acceptance = (timer, page, state)


def main():
    from houdini_test_environment import reexec_unpacked_test_cli
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-cache', type=Path, required=True)
    parser.add_argument('--houdini', type=Path, action='append', required=True)
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
    import dsh_managed_runtime as managed
    from dsh_web_auth import DshWebSession
    cache = args.runtime_cache.resolve(strict=True)
    binary = cache / 'node_modules/@deepseek-ai/dsh/lib/bin.js'
    preferred = json.loads((ROOT / 'dsh-runtime-compatibility.json').read_text(encoding='utf-8'))['preferredVersion']
    assert json.loads((binary.parent.parent / 'package.json').read_text(encoding='utf-8'))['version'] == preferred
    node = shutil.which('node')
    assert node, 'Node runtime unavailable'
    fixture = Path(tempfile.mkdtemp(prefix='dsh-source-qt-'))
    print('Actual Qt GUI evidence:', fixture, flush=True)
    for number, executable in enumerate(args.houdini):
        executable = executable.resolve(strict=True)
        run = fixture / str(number)
        run.mkdir()
        hython = executable.with_name('hython.exe')
        version_probe = subprocess.run([str(hython), '-c', "import hou;print('DSH_VERSION='+'.'.join(map(str,hou.applicationVersion()[:2])))"],
            cwd=launch_directory(hython), env=isolated_environment(run / 'version', executable=hython),
            capture_output=True, text=True, encoding='utf-8', errors='replace', check=True, timeout=60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        match = re.search(r'DSH_VERSION=(21\.0|22\.0)', version_probe.stdout)
        assert match, 'requires actual supported H21/H22 runtime'
        version = match[1]
        env = isolated_environment(run / 'host')
        subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'), str(binary), env['DSH_HOME'], str(ROOT)],
            cwd=ROOT, env=env, capture_output=True, check=True, timeout=60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        # The official locale plugin owns `locale.preference`; put the choice
        # in this freshly prepared profile's ordinary persisted patch. Do not
        # change the user's DSH home or fake navigator languages in the page.
        locale_patch = Path(env['DSH_HOME']) / 'profiles/web/cordis.patch.yml'
        assert locale_patch.is_file(), 'fresh DSH profile patch was not prepared'
        locale_patch.write_text('- id: locale\n  config:\n    preference: zh\n', encoding='utf-8')
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        bridge_reservation = socket.socket()
        bridge_reservation.bind(('127.0.0.1', 0))
        env['DSH_HOUDINI_BRIDGE_URL'] = 'http://127.0.0.1:'+str(bridge_reservation.getsockname()[1])
        env['DSH_HOUDINI_EXECUTOR_ID'] = uuid.uuid4().hex
        workspace = run / 'workspace'
        workspace.mkdir()
        resource = workspace / 'plain.txt'
        resource.write_text('ISOLATED QT TEXT RESOURCE CONTENT\n', encoding='utf-8')
        config = {'base': 'http://127.0.0.1:'+str(port), 'workspace': str(workspace), 'resource': str(resource),
                  'toolCatalogUrl': (ROOT / 'lib/tool-catalog.js').as_uri(),
                  'composition': str(run / 'composition.json'), 'command': str(run / 'command.json'),
                  'response': str(run / 'response.json'), 'output': str(run / 'result.json'), 'timeout': args.timeout}
        config_path = run / 'config.json'
        atomic_json(config_path, config)
        env['DSH_SOURCE_GUI_CONFIG'] = str(config_path)
        env['DSH_SOURCE_RUNTIME_BIN'] = str(binary)
        inspector = run / 'inspect.mjs'
        inspector.write_text(HOST_FIXTURE, encoding='utf-8')
        overlay = run / 'inspect.patch.yml'
        overlay.write_text('- insert:\n    - id: source-gui-inspector\n      name: '+inspector.as_uri()+'\n', encoding='utf-8')
        host_log = run / 'host.log'
        gui = None
        gui_job = None
        with host_log.open('wb') as host_output:
            host = managed.spawn_frontend([node, str(binary), 'web', '--patch', str(overlay), '--port', str(port), '--no-open'],
                node=node, cwd=run, env=env, stdout=host_output, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                deadline = time.monotonic()+60
                while not Path(config['composition']).exists():
                    assert host.poll() is None, 'Host exited: '+str(host_log)
                    assert time.monotonic() < deadline, 'Host composition timed out: '+str(host_log)
                    time.sleep(.2)
                composition = json.loads(Path(config['composition']).read_text(encoding='utf-8'))
                assert 'error' not in composition, composition
                presets = composition['roster']['presets']
                assert len(presets) == 1 and presets[0]['id'] == 'houdini' and presets[0]['isDefault'], composition
                assert sorted(name for name in composition['tools'] if name.startswith('houdini_')) == sorted(composition['expectedHoudiniTools']), composition
                assert any(row['name'] == 'dsh-houdini' and not row['disabled'] for row in composition['rootEntries']), composition
                auth = DshWebSession(config['base'], str(host_log), str(run / 'runtime.json'))
                deadline = time.monotonic()+10
                while auth.launch_url() is None:
                    assert host.poll() is None and time.monotonic() < deadline, 'Host did not announce its authenticated URL'
                    time.sleep(.1)
                auth.authorize(timeout=10)
                config['authenticatedUrl'] = auth.launch_url()
                atomic_json(config_path, config)
                gui_env = isolated_environment(run / 'gui', executable=executable, gui=True)
                gui_env['DSH_SOURCE_GUI_CONFIG'] = str(config_path)
                prefs = Path(gui_env['HOUDINI_USER_PREF_DIR'].replace('__HVER__', version))
                hook = prefs / ('python3.11libs' if version == '21.0' else 'python3.13libs') / 'uiready.py'
                hook.parent.mkdir(parents=True, exist_ok=True)
                hook.write_text("import importlib.util,traceback\ns=importlib.util.spec_from_file_location('source_gui_probe',"+repr(str(Path(__file__).resolve()))+")\nm=importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\ntry:\n m.start_gui_probe()\nexcept Exception:\n m.atomic_json("+repr(config['output'])+",{'ok':False,'phase':'uiready','error':traceback.format_exc()})\n", encoding='utf-8')
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = 0
                with (run / 'houdini.log').open('wb') as gui_output:
                    gui_job = GuiProcessJob()
                    # An independent kill-on-close Job owns only this GUI tree.
                    # No UI/memory limits, breakaway or Chromium sandbox flags.
                    gui = subprocess.Popen([str(executable), '-foreground', '-geometry=1440x1000+12000+12000'],
                        cwd=launch_directory(executable), env=gui_env, stdout=gui_output, stderr=subprocess.STDOUT,
                        startupinfo=startup, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    gui_job.assign(gui)
                    deadline = time.monotonic()+args.timeout+90
                    last_progress = None
                    while not Path(config['output']).exists():
                        assert gui.poll() is None, 'GUI exited before result: '+str(run)
                        assert host.poll() is None, 'Host exited during GUI verification: '+str(run)
                        assert time.monotonic() < deadline, 'GUI produced no result: '+str(run)
                        progress = Path(config['output']).with_suffix('.progress.json')
                        if progress.exists():
                            text = progress.read_text(encoding='utf-8')
                            if text != last_progress:
                                print(version, text, flush=True)
                                last_progress = text
                        time.sleep(.3)
                    exit_code = gui.wait(timeout=30)
                    result = json.loads(Path(config['output']).read_text(encoding='utf-8'))
                    print(version, json.dumps(result, ensure_ascii=True), flush=True)
                    assert result['ok'] and result['hipUntouched'] and result['offTheRecord'], 'GUI acceptance failed: '+str(run)
                    assert not result['renderer'] and any(result['loads']), 'Renderer crashed or no page load succeeded: '+str(run)
                    assert exit_code == 0, 'GUI shutdown failed: '+str(exit_code)
                    result['processExit'] = exit_code
                    atomic_json(config['output'], result)
            finally:
                try:
                    if gui_job is not None:
                        tree = gui_job.close()
                        if Path(config['output']).exists():
                            result = json.loads(Path(config['output']).read_text(encoding='utf-8'))
                            result['guiProcessTree'] = tree
                            atomic_json(config['output'], result)
                    if gui is not None:
                        gui.wait(timeout=20)
                finally:
                    managed.stop_owned(host)
                    host.wait(timeout=20)
                    bridge_reservation.close()
    print('Actual source QtWebEngine selection, model menus, Trace, interactions, draft and file resource checks passed', flush=True)


if __name__ == '__main__':
    main()
