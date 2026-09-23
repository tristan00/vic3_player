import ctypes
from ctypes import wintypes

from PIL import Image

from ..common import timed

user32=ctypes.WinDLL('user32',use_last_error=True)
gdi32=ctypes.WinDLL('gdi32')
user32.PrintWindow.argtypes=[wintypes.HWND,wintypes.HDC,wintypes.UINT]


def window():
    found=[]
    proc=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def visit(hwnd,_):
        buffer=ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd,buffer,256)
        if buffer.value=='Victoria 3' and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(proc(visit),0)
    return found[0] if found else None


@timed
def shot(path):
    hwnd=window()
    if hwnd is None:
        raise RuntimeError('No visible Victoria 3 window to capture')
    rect=wintypes.RECT()
    user32.GetClientRect(hwnd,ctypes.byref(rect))
    width,height=rect.right,rect.bottom
    source=user32.GetDC(hwnd)
    memory=gdi32.CreateCompatibleDC(source)
    bitmap=gdi32.CreateCompatibleBitmap(source,width,height)
    gdi32.SelectObject(memory,bitmap)
    user32.PrintWindow(hwnd,memory,3)
    header=(ctypes.c_uint32*10)(40,width,(-height)&0xffffffff,0x200001,0,0,0,0,0,0)
    data=ctypes.create_string_buffer(width*height*4)
    gdi32.GetDIBits(memory,bitmap,0,height,data,header,0)
    Image.frombuffer('RGBA',(width,height),data,'raw','BGRA',0,1).convert('RGB').save(path)
    gdi32.DeleteObject(bitmap);gdi32.DeleteDC(memory);user32.ReleaseDC(hwnd,source)

