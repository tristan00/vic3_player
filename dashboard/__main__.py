import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import socket
import subprocess
import sys
import time

from interface.common import DEFAULT_DATA
from interface.timing import timer

ROOT=Path(__file__).resolve().parents[1]
PORT=8790
LOG=DEFAULT_DATA/'dashboard.log'
WATCH=DEFAULT_DATA/'dashboard_watch.log'
QUICK=10
SLOWEST=60
often=timer('dashboard',level=logging.DEBUG)
timed=timer('dashboard')


@often
def sources():
    found={}
    for path in [path for folder in ('advisors','interface','loop','tuning') for path in (ROOT/folder).rglob('*.py')]+list((ROOT/'dashboard').glob('*.py')):
        try:
            found[path]=path.stat().st_mtime_ns
        except FileNotFoundError:
            found[path]=None
    return found


@timed
def serve(port):
    import uvicorn
    from .app import app
    uvicorn.run(app,host='127.0.0.1',port=port,log_level='warning')


@timed
def supervise(port):
    log=logging.getLogger('dashboard')
    socket.create_server(('127.0.0.1',port)).close()
    wait=1
    while True:
        seen=sources()
        started=time.monotonic()
        child=subprocess.Popen([sys.executable,'-m','dashboard','serve','--port',str(port)],cwd=ROOT,stdin=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        log.info('serving pid %d on http://127.0.0.1:%d',child.pid,port)
        try:
            while child.poll() is None and sources()==seen:
                time.sleep(1)
        finally:
            changed=child.poll() is None
            if changed:
                child.kill()
            child.wait()
        wait=1 if changed or time.monotonic()-started>=QUICK else min(wait*2,SLOWEST)
        log.info('server ended with %s after %.0fs; starting again in %ds',child.returncode,time.monotonic()-started,wait)
        time.sleep(wait)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',nargs='?',choices=('serve',))
    parser.add_argument('--port',type=int,default=PORT)
    arguments=parser.parse_args()
    serving=arguments.command=='serve'
    handler=RotatingFileHandler(LOG,maxBytes=8*2**20,backupCount=1,encoding='utf-8') if serving else logging.FileHandler(WATCH,encoding='utf-8')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',handlers=[handler,logging.StreamHandler()])
    if serving:
        serve(arguments.port)
    else:
        supervise(arguments.port)


if __name__=='__main__':
    main()
