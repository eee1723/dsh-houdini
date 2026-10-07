"""Owned worker setup only; never import this as a production UI capability."""
import ctypes,os
from ctypes import wintypes as w


def _owned_welcome_handles():
    api=ctypes.WinDLL('user32',use_last_error=True)
    api.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    api.GetWindowThreadProcessId.restype=w.DWORD
    api.GetWindowTextLengthW.argtypes=[w.HWND];api.GetWindowTextLengthW.restype=ctypes.c_int
    api.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int];api.GetWindowTextW.restype=ctypes.c_int
    api.IsWindowVisible.argtypes=[w.HWND];api.IsWindowVisible.restype=w.BOOL
    callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    api.EnumWindows.argtypes=[callback_type,w.LPARAM];api.EnumWindows.restype=w.BOOL
    found=[];errors=[]
    @callback_type
    def visit(handle,_):
        owner=w.DWORD();api.GetWindowThreadProcessId(handle,ctypes.byref(owner))
        if owner.value!=os.getpid() or not api.IsWindowVisible(handle):return True
        length=api.GetWindowTextLengthW(handle)
        if not 0<length<256:return True
        title=ctypes.create_unicode_buffer(length+1);api.GetWindowTextW(handle,title,len(title))
        if title.value=='Python Callback Error':errors.append('Owned worker has a native Python Callback Error; setup does not hide it')
        elif title.value in ('Start Here','Anonymous Usage Statistics'):found.append({'handle':int(handle),'title':title.value})
        return True
    if not api.EnumWindows(visit,0):raise ctypes.WinError(ctypes.get_last_error())
    if errors:raise RuntimeError('; '.join(errors))
    return api,found


def dismiss_owned_start_here():
    api,handles=_owned_welcome_handles()
    api.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];api.PostMessageW.restype=w.BOOL
    for item in handles:
        if not api.PostMessageW(item['handle'],0x0010,0,0):raise ctypes.WinError(ctypes.get_last_error())  # WM_CLOSE
    return {'pid':os.getpid(),'exactTitles':['Start Here','Anonymous Usage Statistics'],'requestedClose':len(handles),
            'scope':'ordinary asynchronous WM_CLOSE to visible exact-title windows in this owned Houdini process only; no preferences, licence, foreign windows or HIP edits'}


def observe_owned_start_here():
    _,handles=_owned_welcome_handles()
    return {'pid':os.getpid(),'exactTitles':['Start Here','Anonymous Usage Statistics'],'visibleCount':len(handles)}
