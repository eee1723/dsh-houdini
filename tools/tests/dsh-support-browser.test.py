from pathlib import Path
import base64
import json
import os
import sys
import time
import urllib.parse
import zipfile

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import dsh_webview
import dsh_web_auth

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)
folder = Path(os.environ['DSH_SUPPORT_TEST_ROOT'])
config = json.loads((folder/'browser.json').read_text())
auth = dsh_web_auth.shared_session(config['base'],str(folder/'host.log'),str(folder/'runtime.json'))
launch = auth.launch_url()
assert launch
dsh_webview.show_webview(session_id='support-selected',authenticated_url=launch,frontend_url=config['base'])
dsh_webview._window.move(12000,12000)
page = dsh_webview._view.page()
captured = []
page.profile().downloadRequested.connect(lambda request:captured.append(request))
destination = folder/'browser-report.zip'
QFileDialog.getSaveFileName = lambda *_args,**_kwargs:(str(destination),'')


def evaluate(code):
    output = []
    loop = QEventLoop()
    page.runJavaScript('encodeURIComponent(JSON.stringify((function(){'+code+'})()))',0,lambda value:(output.append(value),loop.quit()))
    QTimer.singleShot(5000,loop.quit)
    loop.exec()
    if not output or not output[0]:
        return None
    return json.loads(urllib.parse.unquote(output[0]))


def until(code,seconds=35):
    deadline = time.monotonic()+seconds
    while time.monotonic()<deadline:
        value = evaluate(code)
        if value:
            return value
        app.processEvents()
        time.sleep(.1)
    raise AssertionError('browser condition timeout: '+code+' state='+str(evaluate('return document.body.innerText.slice(-1800)')))


def ready(marker):
    until('return document.body.innerText.includes('+json.dumps(marker)+') && [...document.querySelectorAll("button")].some(b=>b.textContent==="报告问题"&&!b.disabled)')
    for attempt in range(40):
        evaluate("if(document.body.innerText.includes('预览版说明')){var button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='继续');if(button)button.click()}var later=[...document.querySelectorAll('button')].find(b=>['以后再说','稍后配置'].includes(b.textContent.trim()));if(later)later.click();return true")
        app.processEvents();time.sleep(.1)
    until("var button=[...document.querySelectorAll('button')].find(button=>button.textContent.trim()==='报告问题');if(!button)return false;var rect=button.getBoundingClientRect();return button.contains(document.elementFromPoint(rect.left+rect.width/2,rect.top+rect.height/2))")
    assert evaluate("return !document.querySelector('[data-houdini-connection]') && ![...document.querySelectorAll('button')].some(button=>button.textContent.trim()==='检查连接')")


def capture(filename):
    loop=QEventLoop()
    QTimer.singleShot(650,loop.quit)
    loop.exec()
    assert dsh_webview._window.grab().save(str(folder/filename))


try:
    ready('SELECTED_PRIVATE_CONTENT')
    capture('workspace-no-connection-banner.png')
    evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='报告问题').click();return true")
    until("return !!document.querySelector('[aria-label=\"报告问题\"] textarea')")
    until("var panel=document.querySelector('[aria-label=\"报告问题\"]');var rect=panel.getBoundingClientRect();var hit=document.elementFromPoint(rect.left+40,rect.top+40);return rect.width>500&&rect.height>400&&panel.contains(hit)",5)
    assert evaluate("return [...document.querySelectorAll('button')].some(b=>b.textContent==='保存报告'&&!b.disabled)")
    assert evaluate("return !document.querySelector('[aria-label=\"报告问题\"] pre')")
    capture('support-form.png')
    text = evaluate("return document.querySelector('[aria-label=\"报告问题\"]').innerText")
    assert 'PRIVATE_LAUNCH_TOKEN' not in text and 'SELECTED_PRIVATE_CONTENT' not in text and 'OTHER_PRIVATE_CONTENT' not in text
    evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='保存报告').click();return true")
    deadline = time.monotonic()+20
    while time.monotonic()<deadline and (not captured or not captured[-1].isFinished()):
        app.processEvents();time.sleep(.05)
    assert captured and captured[-1].state()==captured[-1].DownloadState.DownloadCompleted
    with zipfile.ZipFile(destination) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['session']['id']=='support-selected',manifest
        timeline = archive.read('timeline.jsonl').decode()
        assert 'CHECKPOINT_UNAVAILABLE' in timeline and 'PRIVATE_LAUNCH_TOKEN' not in timeline
    assert evaluate("return !document.querySelector('[aria-label=\"报告问题\"] pre')"), 'direct save must leave raw logs hidden'
    evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='查看报告内容').click();return true")
    until("return document.querySelectorAll('.dsh-support-file').length>0")
    assert evaluate("return !document.querySelector('.dsh-support-file-body')")
    evaluate("[...document.querySelectorAll('.dsh-support-file>button')].find(b=>b.textContent.includes('当前运行记录')).click();return true")
    until("return !!document.querySelector('.dsh-support-file-body pre')")
    assert evaluate("var text=document.querySelector('.dsh-support-file-body pre');text.scrollTop=text.scrollHeight;return text.scrollHeight>text.clientHeight"), 'long details must scroll within their reader'
    evaluate("var body=document.querySelector('.dsh-support-content>div:last-child');body.scrollTop=body.scrollHeight;return true")
    assert evaluate("var close=document.querySelector('[aria-label=\"关闭报告窗口\"]');var save=[...document.querySelectorAll('button')].find(b=>b.textContent==='保存报告');var collapse=[...document.querySelectorAll('button')].find(b=>b.textContent==='收起详情');return [close,save,collapse].every(b=>{var rect=b.getBoundingClientRect();return rect.top>=0&&rect.bottom<=innerHeight&&b.contains(document.elementFromPoint(rect.left+rect.width/2,rect.top+rect.height/2))})"), 'close/save/collapse must remain reachable at the bottom'
    capture('browser-report.png')
    evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='收起详情').click();return true")
    assert evaluate("return !document.querySelector('.dsh-support-file-body pre')")
    dsh_webview._window.resize(640,560)
    until("return innerWidth<=640&&innerHeight<=560")
    until("var close=document.querySelector('[aria-label=\"关闭报告窗口\"]');var save=[...document.querySelectorAll('button')].find(b=>b.textContent==='保存报告');return [close,save].every(b=>{var rect=b.getBoundingClientRect();return rect.top>=0&&rect.bottom<=innerHeight})")
    capture('support-narrow.png')
    dsh_webview._window.resize(1200,800)
    until("return innerWidth>=1100")
    evaluate("document.querySelector('[aria-label=\"关闭报告窗口\"]').click();return true")
    destination = folder/'native-session-export.zip'
    evaluate("var menu=document.querySelector('[aria-label=\"更多操作\"]');menu.click();return true")
    until("return [...document.querySelectorAll('[role=menuitem],button')].some(b=>b.textContent.includes('下载 Session 日志'))")
    before=len(captured)
    evaluate("[...document.querySelectorAll('[role=menuitem],button')].find(b=>b.textContent.includes('下载 Session 日志')).click();return true")
    deadline = time.monotonic()+20
    while time.monotonic()<deadline and (len(captured)<=before or not captured[-1].isFinished()):
        app.processEvents();time.sleep(.05)
    assert len(captured)>before and captured[-1].state()==captured[-1].DownloadState.DownloadCompleted
    with zipfile.ZipFile(destination) as archive:
        text = '\n'.join(archive.read(name).decode('utf-8') for name in archive.namelist() if name.endswith('.jsonl'))
        assert 'SELECTED_PRIVATE_CONTENT' in text and 'OTHER_PRIVATE_CONTENT' not in text
    dsh_webview.show_webview(session_id='support-other',authenticated_url=launch,frontend_url=config['base'])
    ready('OTHER_PRIVATE_CONTENT')
    evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='报告问题').click();return true")
    until("return !!document.querySelector('[aria-label=\"报告问题\"] textarea')")
    evaluate("var box=[...document.querySelectorAll('[aria-label=\"报告问题\"] input')].at(-1);box.click();return true")
    destination=folder/'other-session-report.zip'
    before=len(captured)
    evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='保存报告').click();return true")
    deadline=time.monotonic()+20
    while time.monotonic()<deadline and (len(captured)<=before or not captured[-1].isFinished()):
        app.processEvents();time.sleep(.05)
    assert len(captured)>before and captured[-1].state()==captured[-1].DownloadState.DownloadCompleted
    with zipfile.ZipFile(destination) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        assert manifest['session']['id']=='support-other' and manifest['content_included']
        text=archive.read('session-content.jsonl').decode()
        assert 'OTHER_PRIVATE_CONTENT' in text and 'SELECTED_PRIVATE_CONTENT' not in text
    print(json.dumps({'ok':True,'selected_session':'support-selected','support_archive':True,'native_export':True}),flush=True)
finally:
    dsh_webview._dispose_webview()
