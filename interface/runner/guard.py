import subprocess
import sys
import time

import psutil

LIMIT=50
SECONDS=6
INTERVAL=.5


def gpu_use():
    out=subprocess.check_output(['nvidia-smi','--query-gpu=utilization.gpu','--format=csv,noheader,nounits'],text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    return max(int(line) for line in out.split())


def watch(process,sample=gpu_use,limit=LIMIT,seconds=SECONDS,interval=INTERVAL,log=print):
    log(f'{time.strftime("%H:%M:%S")} guard started for game {process.pid}: kill above {limit}% GPU for {seconds}s')
    hot=None
    while process.is_running():
        use=sample()
        now=time.monotonic()
        hot=(hot or now) if use>limit else None
        if hot is not None and now-hot>=seconds:
            process.kill()
            log(f'{time.strftime("%H:%M:%S")} KILLED game {process.pid}: GPU at {use}%, above {limit}% for {now-hot:.1f}s')
            return True
        time.sleep(interval)
    log(f'{time.strftime("%H:%M:%S")} guard stopped: game {process.pid} exited')
    return False


if __name__=='__main__':
    pid,created,path=int(sys.argv[1]),float(sys.argv[2]),sys.argv[3]
    process=psutil.Process(pid)
    if abs(process.create_time()-created)>=.01:
        raise RuntimeError(f'Process {pid} is not the guarded game')
    with open(path,'a',encoding='utf-8') as out:
        watch(process,log=lambda line:(out.write(line+'\n'),out.flush()))
