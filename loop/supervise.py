from pathlib import Path
import re
import shutil
import sys
import time

import psutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from interface.common import DEFAULT_DATA
from interface.runner.session import _spawn

LAUNCH=ROOT/'loop'/'launch.cmd'
POLL=10
QUICK=600
QUICK_EXITS=3


def note(log,text):
    with open(log,'a',encoding='utf-8') as out:
        out.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {text}\n')


def running():
    return [p for p in psutil.process_iter(['name','cmdline']) if (p.info['name'] or '').lower()=='python.exe' and 'loop.run' in ' '.join(p.info['cmdline'] or [])]


def next_round():
    found=[int(m[1]) for path in DEFAULT_DATA.glob('collect_*.log') if (m:=re.fullmatch(r'collect_(\d+)\.log',path.name))]
    return f'collect_{max(found,default=0)+1}'


def launch(log,arguments):
    for world in (DEFAULT_DATA/'worlds').iterdir():
        shutil.rmtree(world)
    name=next_round()
    process=_spawn(['cmd.exe','/c',str(LAUNCH),name,*arguments],str(ROOT))
    note(log,f'LAUNCHED {name} as {process.pid} with {" ".join(arguments)}')


def main():
    arguments=sys.argv[1:]
    log=DEFAULT_DATA/'supervisor.log'
    note(log,f'SUPERVISOR STARTED as {psutil.Process().pid}')
    exits=[]
    while True:
        if not running():
            exits=[at for at in exits if time.time()-at<QUICK]+[time.time()]
            if len(exits)>QUICK_EXITS:
                note(log,f'BLOCKED: {len(exits)} rounds ended within {QUICK} s; not relaunching')
                return
            note(log,'ROUND DOWN')
            launch(log,arguments)
            time.sleep(60)
        time.sleep(POLL)


if __name__=='__main__':
    main()
