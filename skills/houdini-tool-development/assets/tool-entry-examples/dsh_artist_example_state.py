"""Nodeless SOP viewer-state example: report the XZ-plane point under a click.

This is an interaction/source example, not a geometry picking or modeling tool.
It does not create nodes, change selection, edit parameters or write files.
"""
import hou

STATE_NAME = 'dsh_artist_example::plane_inspect'


class State:
    def __init__(self, state_name, scene_viewer):
        self.scene_viewer = scene_viewer

    def onEnter(self, kwargs):
        self.scene_viewer.setPromptMessage('左键读取 XZ 平面坐标；切换工具退出。场景保持不变。')

    def onGenerate(self, kwargs):
        self.onEnter(kwargs)

    def onResume(self, kwargs):
        self.onEnter(kwargs)

    def onInterrupt(self, kwargs):
        self.scene_viewer.clearPromptMessage()

    def onMouseEvent(self, kwargs):
        event = kwargs['ui_event']
        if event.reason() != hou.uiEventReason.Start or not event.device().isLeftButton():
            return False
        origin, direction = event.ray()
        if abs(direction[1]) < 1e-8:
            self.scene_viewer.setPromptMessage('视线与 XZ 平面平行，请旋转视图后再试。')
            return True
        distance = -origin[1] / direction[1]
        if distance < 0:
            self.scene_viewer.setPromptMessage('XZ 平面在视线后方，请旋转视图后再试。')
            return True
        point = origin + direction * distance
        self.scene_viewer.setPromptMessage('XZ 平面坐标：({:.3f}, 0, {:.3f})；左键重新读取。'.format(point[0], point[2]))
        return True

    def onExit(self, kwargs):
        self.scene_viewer.clearPromptMessage()


def createViewerStateTemplate():
    template = hou.ViewerStateTemplate(STATE_NAME, 'Inspect XZ Plane', hou.sopNodeTypeCategory())
    template.bindFactory(State)
    template.bindIcon('SOP_null')
    return template


def enter_from_shelf(kwargs):
    viewer = kwargs.get('pane')
    if not isinstance(viewer, hou.SceneViewer):
        viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if viewer is None:
        raise hou.Error('请先打开 Scene View，再运行工具。')
    if viewer.pwd().childTypeCategory() != hou.sopNodeTypeCategory():
        raise hou.Error('请先进入 Geometry 的 SOP 网络，再运行平面坐标工具。')
    viewer.setCurrentState(STATE_NAME, generate=hou.stateGenerateMode.Insert)
