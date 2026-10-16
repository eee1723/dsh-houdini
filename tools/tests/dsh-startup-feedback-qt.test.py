from pathlib import Path
import os
import sys
import time
import types
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QPlainTextEdit

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import dsh_bootstrap as bootstrap
import dsh_deployment as deployment
import dsh_ui_style

app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)
parent=QWidget()
folder=Path(os.environ['DSH_SUPPORT_QT_ROOT'])
lock=folder/'runtime.lock'
lease=deployment.FileLease(lock)
lease.record_owner({'hip_path':'E:/artist/Another Scene.hip','hip_is_new':False,'houdini_version':'21.0.440'})


class Store:
    root = folder
    trust = {}
    def activate(self,*args,**kwargs):
        assert kwargs['owner']['hip_path']=='E:/artist/Current Scene.hip'
        return deployment.FileLease(lock)


fake=types.ModuleType('hou')
fake.__dict__.update(applicationVersion=lambda:(22,0,368),applicationVersionString=lambda:'22.0.368',
    hipFile=types.SimpleNamespace(path=lambda:'E:/artist/Current Scene.hip',isNewFile=lambda:False),
    qt=types.SimpleNamespace(mainWindow=lambda:parent),ui=types.SimpleNamespace(setStatusMessage=lambda value:None))
try:
    with patch.dict(sys.modules,{'hou':fake}),patch.object(bootstrap,'_INITIALIZED',True),patch.object(bootstrap,'_PINNED','fixture'),\
         patch.object(bootstrap,'_ERROR',None),patch.object(bootstrap,'_CONTEXT',None),patch.object(bootstrap,'store',return_value=Store()),\
         patch('dsh_workbench.ensure',side_effect=lambda config:deployment.FileLease(lock)),\
         patch.object(bootstrap,'show_manager',side_effect=AssertionError('an occupancy error must not open an unrelated update panel')):
        bootstrap.open_workspace()
        deadline=time.monotonic()+5
        while bootstrap._BUSY:
            app.processEvents();time.sleep(.02)
            assert time.monotonic()<deadline
        window=bootstrap._PROBLEM_WINDOW
        assert window and window.isVisible()
        labels='\n'.join(widget.text() for widget in window.findChildren(QLabel))
        assert 'Another Scene.hip' in labels and '仅关闭插件面板不会释放占用' in labels
        assert not any(widget.isVisible() for widget in window.findChildren(QPlainTextEdit))
        app.processEvents()
        assert window.grab().save(str(folder/'occupied-window.png'))
        next(button for button in window.findChildren(QPushButton) if button.text()=='查看技术详情').click()
        assert any(widget.isVisible() for widget in window.findChildren(QPlainTextEdit))
        dsh_ui_style.clear_startup_problem()
        assert not window.isVisible(), 'retry must remove the old occupancy warning'
        app.processEvents()
    import dsh_install_ui
    import dsh_support_ui
    failures={'value':'latest startup failure'}
    captured=[]
    manager=dsh_install_ui.show(source_root=folder,parent=parent,startup_error='stale failure',startup_error_provider=lambda:failures['value'])
    with patch.object(dsh_support_ui,'show',side_effect=lambda **kwargs:captured.append(kwargs) or None):
        report_button=next(button for button in manager.findChildren(QPushButton) if '报告问题' in button.text())
        report_button.click()
        assert captured[-1]['startup_error']=='latest startup failure'
        failures['value']=None
        report_button.click()
        assert captured[-1]['startup_error'] is None
    manager.close();app.processEvents()
    import dsh_launcher
    source_hou=types.SimpleNamespace(isUIAvailable=lambda:True,qt=types.SimpleNamespace(mainWindow=lambda:parent))
    with patch.object(dsh_launcher,'hou',source_hou):
        dsh_launcher._startup_failure('连接地址已被另一个窗口占用。请保存并退出那个 Houdini 后重试。\n技术信息：bridge port conflict')
        window=dsh_launcher._PROBLEM_WINDOW
        assert window.isVisible()
        assert any('连接地址已被另一个窗口占用' in label.text() for label in window.findChildren(QLabel))
        window.close();app.processEvents()
    print('native startup feedback: managed occupancy names the window, explains switching, hides details and source conflicts are visible')
finally:
    lease.close()
    if bootstrap._TIMER is not None:bootstrap._TIMER.stop()
    parent.close()
