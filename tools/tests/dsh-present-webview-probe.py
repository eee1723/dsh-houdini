"""Inspect an isolated DSH delivery in real Houdini QtWebEngine (no user HIP)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import urllib.parse

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_webview as webview

url = os.environ['DSH_PRESENT_WEBVIEW_URL']
session_id = os.environ['DSH_PRESENT_WEBVIEW_SESSION_ID']
output = Path(os.environ['DSH_PRESENT_WEBVIEW_RESULT'])
base = urllib.parse.urlsplit(url)
webview.FRONTEND_URL = f'{base.scheme}://{base.netloc}'
app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)
phase = 'load'
console = []

class ProbePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        console.append({'level': str(level), 'message': str(message)[:500], 'line': line,
                        'source': str(source).split('?')[0][-180:]})

webview.QWebEnginePage = ProbePage

def js(script):
    values = []
    loop = QEventLoop()
    # H21 PySide's callback conversion can crash on raw Unicode returned by
    # Chromium. Keep this diagnostic channel ASCII and decode after Qt returns.
    safe_script = 'encodeURIComponent(JSON.stringify((' + script + ')))'
    webview._view.page().runJavaScript(safe_script, 0, lambda value: (values.append(value), loop.quit()))
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    return json.loads(urllib.parse.unquote(values[0])) if values and values[0] else None

def tick(ms=400):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()

try:
    webview.show_webview(session_id=session_id, authenticated_url=url)
    deadline = time.monotonic() + 90
    state = None
    while time.monotonic() < deadline:
        tick()
        raw = js("""JSON.stringify({ready:document.readyState,
          cards:[...document.querySelectorAll('button[class*=cardPreview]')].map(b=>b.getAttribute('aria-label')),
          text:document.body?.innerText?.slice(0,12000),
          tokenInUrl:new URL(location.href).searchParams.has('token')})""")
        state = json.loads(raw) if raw else None
        if state and len(state['cards']) >= 4 and '最终 图片.png' in state['text']:
            break
    else:
        raise AssertionError('delivery cards did not appear: ' + str(state)[:1500])
    assert not state['tokenInUrl'], 'launch token reached the app URL'
    scheme = json.loads(js("""(()=>{const u=new URL('dsh-resource://file/session/example/plain.txt');
      const review=new URL('dsh-resource://changes-review/session/example/1/1');
      const ordinary=new URL('https://example.com/path');ordinary.hostname='example.org';
      return JSON.stringify({protocol:u.protocol,hostname:u.hostname,
        reviewHost:review.hostname,ordinaryHost:ordinary.hostname})})()"""))
    assert scheme == {'protocol': 'dsh-resource:', 'hostname': 'file',
                      'reviewHost': 'changes-review', 'ordinaryHost': 'example.org'}, scheme

    phase = 'text-preview'
    clicked = js("""(()=>{const row=[...document.querySelectorAll('[class*=nyYjTG_file]')]
      .find(el=>el.textContent.includes('plain.txt') && el.querySelector('button[class*=cardPreview]'));
      if(!row)return false;row.querySelector('button[class*=cardPreview]').click();return true})()""")
    assert clicked, 'text delivery preview button was absent'
    preview_deadline = time.monotonic() + 25
    while time.monotonic() < preview_deadline:
        tick()
        preview = js("document.body?.innerText?.includes('ASCII delivery preview')")
        if preview:
            break
    else:
        raise AssertionError('Sidebar did not show text source content')

    # Inspect the native menu without opening an application on the user's desktop.
    menu = json.loads(js("""(()=>{const row=[...document.querySelectorAll('[class*=nyYjTG_file]')]
      .find(el=>el.textContent.includes('plain.txt') && el.querySelector('button[class*=cardPreview]'));
      if(!row)return JSON.stringify({found:false});const buttons=[...row.querySelectorAll('button')];
      const b=buttons.at(-1);return JSON.stringify(b?{found:true,disabled:b.disabled,
        label:b.getAttribute('aria-label'),buttons:buttons.length}:{found:false})})()"""))
    assert menu and menu['found'], 'native-open menu control was absent'
    assert not menu['disabled'], 'Host native-open menu unexpectedly disabled'

    image_opened = js("""(()=>{const row=[...document.querySelectorAll('[class*=nyYjTG_file]')]
      .find(el=>el.textContent.includes('.png') && el.querySelector('button[class*=cardPreview]'));
      if(!row)return false;row.querySelector('button[class*=cardPreview]').click();return true})()""")
    assert image_opened, 'PNG delivery preview button was absent'
    image_deadline = time.monotonic() + 20
    while time.monotonic() < image_deadline:
        tick()
        image_ready = js("""(()=>{const img=document.querySelector('[data-image-preview] img');
          return !!img&&img.complete&&img.naturalWidth>0&&!img.hidden})()""")
        if image_ready:
            break
    else:
        raise AssertionError('Sidebar did not render PNG source bytes')

    external_opened = js("""(()=>{const row=[...document.querySelectorAll('[class*=nyYjTG_file]')]
      .find(el=>el.textContent.includes('final.txt') && el.querySelector('button[class*=cardPreview]'));
      if(!row)return false;row.querySelector('button[class*=cardPreview]').click();return true})()""")
    assert external_opened, 'outside-workspace delivery preview button was absent'
    external_deadline = time.monotonic() + 20
    while time.monotonic() < external_deadline:
        tick()
        external_ready = js("document.body?.innerText?.includes('outside HIP workspace')")
        if external_ready:
            break
    else:
        raise AssertionError('Sidebar did not read the outside-workspace absolute source path')
    if '.hip' in state['text']:
        hip_menu = json.loads(js("""(()=>{const row=[...document.querySelectorAll('[class*=nyYjTG_file]')]
          .find(el=>el.textContent.includes('.hip') && el.querySelector('button[class*=cardPreview]'));
          if(!row)return JSON.stringify({found:false});const buttons=[...row.querySelectorAll('button')];
          const b=buttons.at(-1);return JSON.stringify(b?{found:true,disabled:b.disabled}:{found:false})})()"""))
        assert hip_menu == {'found': True, 'disabled': False}, hip_menu
    phase = 'done'
    output.write_text(json.dumps({'ok': True, 'cards': state['cards'], 'textPreview': True,
                                  'imagePreview': True, 'externalPreview': True,
                                  'nativeMenu': menu, 'houdini': os.environ.get('HFS'),
                                  'console': console[-30:]}, ensure_ascii=False), encoding='utf-8')
    print('Qt WebView actual DSH delivery cards and Sidebar text preview passed; native menu:', menu)
except Exception as error:
    try:
        snapshot = js("""JSON.stringify({text:document.body?.innerText?.slice(0,10000),
          buttons:[...document.querySelectorAll('button[aria-label]')].map(b=>b.getAttribute('aria-label')).slice(-60),
          resources:[...document.querySelectorAll('[data-resource],[role=alert],[data-textpreview-state]')].map(e=>({state:e.getAttribute('data-textpreview-state'),url:e.getAttribute('data-textpreview-url'),text:e.textContent?.slice(0,400)})).slice(-20),
          moduleLoader:window.__ModuleLoader__?.mode,
          address:(()=>{let el=document.querySelector('[data-textpreview-state]');if(!el)return null;
            let key=Object.keys(el).find(k=>k.startsWith('__reactFiber'));let f=el[key];
            for(let i=0;i<25&&f;i++,f=f.return){const p=f.memoizedProps;if(p?.tab?.contentId)return p.tab.contentId;}
            return null})(),
          urlParser:(()=>{try{const u=new URL('dsh-resource://file/session/example/C%3A%2Fplain.txt');
            return {protocol:u.protocol,hostname:u.hostname}}catch(e){return String(e)}})(),
          scripts:performance.getEntriesByType('resource').map(e=>e.name).filter(x=>x.includes('/plugins/')).slice(-35)})""")
        detail = json.loads(snapshot) if snapshot else None
        opened = js("""(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='插件');
          if(!b)return false;b.click();return true})()""")
        if opened:
            tick(700)
            detail['pluginPage'] = js("document.body?.innerText?.slice(-9000)")
        webview._view.grab().save(str(output.with_suffix('.png')))
    except Exception as inspect_error:
        detail = {'inspectionError': str(inspect_error)}
    output.write_text(json.dumps({'ok': False, 'phase': phase, 'error': str(error),
                                  'detail': detail, 'console': console[-50:]}, ensure_ascii=False), encoding='utf-8')
    raise
finally:
    if webview._view is not None:
        assert webview._view.page().profile().isOffTheRecord()
    webview._dispose_webview()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
