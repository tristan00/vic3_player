import ctypes
from fnmatch import fnmatchcase
from ctypes import wintypes
import logging
import msvcrt
import os
import re
import threading
import time

from ..common import timed, timed_often

kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.CreateFileW.restype=wintypes.HANDLE
kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]

POLL=.05
WINDOW=16<<20
TRACE=256
SETTLE=1
FATAL=(b"You can't add new commands while the console is still running commands",)
STAMP=re.compile(rb'^\[(\d\d:\d\d:\d\d)\]')
INVALID=wintypes.HANDLE(-1).value


@timed_often
def shared_read(path,offset):
    handle=kernel.CreateFileW(str(path),0x80000000,7,None,3,0x80,None)
    if handle==INVALID:
        raise FileNotFoundError(path)
    with os.fdopen(msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY),'rb') as stream:
        stream.seek(offset)
        return stream.read()


def rotation(path):
    return int(path.stem.partition('.')[2] or 0)


class LogTail:
    @timed_often
    def __init__(self,directory,store,since=''):
        self.directory=directory
        self.since=since.encode()
        self.fatal=None
        self.died=None
        self.grown=time.monotonic()
        self.store=store
        self.lock=threading.Lock()
        self.buffer=bytearray()
        self.total=0
        self.lost=0
        self.known=None
        self.offset=0
        self.last=b''
        self.unsettled=None
        self.thread=None
        self.stopped=threading.Event()
        store.parent.mkdir(parents=True,exist_ok=True)
        store.write_bytes(b'')

    @timed_often
    def files(self):
        found={}
        for name in os.listdir(self.directory):
            if not fnmatchcase(name,'debug*.log'):
                continue
            path=self.directory/name
            try:
                stat=os.stat(path)
            except FileNotFoundError:
                continue
            found[rotation(path)]=(path,stat.st_ino,stat.st_size)
        return found

    @timed_often
    def rotated(self,files):
        return {ident for index,(_,ident,_) in files.items() if index}

    @timed_often
    def continues(self,path,size):
        return size>=self.offset and shared_read(path,self.offset-len(self.last))[:len(self.last)]==self.last

    @timed_often
    def step(self):
        with self.lock:
            files=self.files()
            if 0 not in files:
                return
            active,_,size=files[0]
            data=shared_read(active,self.offset-len(self.last))
            chunks=[]
            if self.known is None:
                chunks=[shared_read(files[index][0],0) for index in sorted(files,reverse=True) if index]
                self.known=self.rotated(files)
            else:
                fresh=sorted((index for index,(_,ident,_) in files.items() if index and ident not in self.known),reverse=True)
                if fresh and files[fresh[-1]][2]==size:
                    return
                if fresh or data[:len(self.last)]!=self.last:
                    if fresh and self.continues(*files[fresh[0]][::2]):
                        chunks=[shared_read(files[index][0],self.offset if index==fresh[0] else 0) for index in fresh]
                    elif self.unsettled is None or time.monotonic()-self.unsettled<SETTLE:
                        self.unsettled=self.unsettled or time.monotonic()
                        return
                    else:
                        self.lost+=1
                        logging.getLogger('interface').warning('debug log rotated past the tail %d times',self.lost)
                    self.unsettled=None
                    self.known=self.rotated(files)
                    self.offset=0
                    self.last=b''
                    data=shared_read(active,0)
            data=data[len(self.last):]
            self.offset+=len(data)
            self.last=(self.last+data)[-TRACE:]
            added=b''.join(chunk if chunk.endswith(b'\n') or not chunk else chunk+b'\n' for chunk in chunks)+data
            if added:
                self.grown=time.monotonic()
                self.scan(added)
                with open(self.store,'ab') as stream:
                    stream.write(added)
                self.buffer+=added
                self.total+=len(added)
                if len(self.buffer)>WINDOW:
                    cut=self.buffer.find(b'\n',len(self.buffer)-WINDOW)+1
                    del self.buffer[:cut]

    @timed_often
    def scan(self,added):
        for line in added.splitlines():
            stamp=STAMP.match(line)
            if stamp and stamp[1]>=self.since and any(marker in line for marker in FATAL):
                self.fatal=line.decode('utf-8','replace')

    @timed_often
    def quiet(self):
        return time.monotonic()-self.grown

    @timed_often
    def poll(self):
        try:
            self.step()
        except (PermissionError,FileNotFoundError):
            pass

    def run(self):
        while not self.stopped.wait(POLL):
            try:
                self.poll()
            except Exception as error:
                self.died=error
                return

    @timed_often
    def close(self):
        self.stopped.set()
        if self.thread is not None:
            self.thread.join()

    @timed
    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True,name='debug-log-tail')
        self.thread.start()

    @timed_often
    def text(self):
        return self.after(0)

    @timed_often
    def mark(self):
        self.after(self.total)
        return self.total

    @timed_often
    def after(self,mark):
        if self.thread is None:
            self.start()
        if self.died:
            raise RuntimeError('The debug log tail thread stopped') from self.died
        self.poll()
        with self.lock:
            data=bytes(self.buffer[max(0,len(self.buffer)-(self.total-mark)):])
        return data.decode('utf-8','replace')
