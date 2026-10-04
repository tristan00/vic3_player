from pathlib import Path
import argparse
import json
import msvcrt
import re
import shutil
import sys
import time
import uuid

import psutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from interface.common import DEFAULT_DATA, timed
from interface.runner.session import _spawn
from loop.watch import roles, role

LAUNCH=ROOT/'loop'/'launch.cmd'
POLL=10
QUICK=600
QUICK_EXITS=3


@timed
def owner(pid,created):
    process=psutil.Process(int(pid))
    if process.create_time()!=float(created) or not process.is_running() or role(process.name(),process.cmdline())!='supervisor':
        raise RuntimeError('The supervising process is not running')
    return process


@timed
def start(arguments):
    if any(kind in ('supervisor','loop','game') and process.pid!=psutil.Process().pid for kind,process in roles()):
        raise RuntimeError('A supervisor or run is already active; stop it with python -m loop.stop')
    process=_spawn([sys.executable,'-m','loop.supervise',*arguments],str(ROOT))
    print(f'SUPERVISOR LAUNCHED pid {process.pid}; log {DEFAULT_DATA / "supervisor.log"}',flush=True)
    return process


def note(log,text):
    with open(log,'a',encoding='utf-8') as out:
        out.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {text}\n')


def running():
    return [process for kind,process in roles() if kind=='loop']


def next_round():
    found=[int(m[1]) for path in DEFAULT_DATA.glob('collect_*.log') if (m:=re.fullmatch(r'collect_(\d+)\.log',path.name))]
    return f'collect_{max(found,default=0)+1}'


def launch(log,arguments):
    for world in (DEFAULT_DATA/'worlds').glob('*'):
        shutil.rmtree(world)
    name=next_round()
    supervisor=psutil.Process()
    process=_spawn(['cmd.exe','/c',str(LAUNCH),name,*arguments,'--supervisor',str(supervisor.pid),repr(supervisor.create_time())],str(ROOT))
    note(log,f'LAUNCHED {name} as {process.pid} with {" ".join(arguments)}')


def main():
    arguments=sys.argv[1:]
    if '--no-supervisor' in arguments or '--supervisor' in arguments:
        raise ValueError('Supervision options belong to loop.run, not loop.supervise')
    with open(DEFAULT_DATA/'supervisor.lock','a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        monitor(arguments)


def monitor(arguments):
    log=DEFAULT_DATA/'supervisor.log'
    parser=argparse.ArgumentParser()
    parser.add_argument('--runs',type=int,required=True)
    parser.add_argument('--progress-file',type=Path)
    requested,_=parser.parse_known_args(arguments)
    checkpoint=requested.progress_file
    if checkpoint is None:
        checkpoint=DEFAULT_DATA/f'collection_{uuid.uuid4().hex}.json'
        save_progress(checkpoint,0)
        arguments=[*arguments,'--progress-file',str(checkpoint)]
    note(log,f'SUPERVISOR STARTED as {psutil.Process().pid}')
    exits=[]
    while True:
        if not running():
            if read_progress(checkpoint)>=requested.runs:
                note(log,f'COMPLETE: {requested.runs} runs; checkpoint {checkpoint}')
                return
            exits=[at for at in exits if time.time()-at<QUICK]+[time.time()]
            if len(exits)>QUICK_EXITS:
                note(log,f'BLOCKED: {len(exits)} rounds ended within {QUICK} s; not relaunching')
                return
            note(log,'ROUND DOWN')
            launch(log,arguments)
            time.sleep(60)
        time.sleep(POLL)


@timed
def read_progress(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))['completed']


@timed
def save_progress(path,completed):
    path=Path(path)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'completed':completed}),encoding='utf-8')
    temporary.replace(path)


if __name__=='__main__':
    main()
