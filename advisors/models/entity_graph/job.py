import argparse
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
import traceback

from interface.common import timed, timed_often
from interface.runner.session import _spawn


@timed_often
def record(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2),encoding='utf-8')
    temporary.replace(path)


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('launch','run'))
    parser.add_argument('--output',type=Path,required=True)
    args,command=parser.parse_known_args()
    while command and command[0]=='--':
        command=command[1:]
    args.output.mkdir(parents=True,exist_ok=True)
    if args.mode=='launch':
        process=_spawn([sys.executable,'-m',__spec__.name,'run','--output',str(args.output.resolve()),'--',*command],Path.cwd())
        result={'pid':process.pid,'created':process.create_time()}
        record(args.output/'process.json',result)
        print(json.dumps(result))
        return
    started=time.monotonic()
    status={'command':command,'state':'running','started':time.time()}
    record(args.output/'job.json',status)
    with (args.output/'worker.log').open('w',encoding='utf-8') as log:
        try:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            status.update(state='complete' if result.returncode==0 else 'failed',exit_code=result.returncode)
        except Exception:
            traceback.print_exc(file=log)
            status.update(state='failed')
    status['seconds']=time.monotonic()-started
    record(args.output/'job.json',status)


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    main()
