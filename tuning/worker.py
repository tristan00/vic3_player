import argparse
import logging
import os
from pathlib import Path
import time
import threading
import traceback
import psutil

from .storage import read, write
from interface.timing import COLUMNS, RECORDER


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',required=True,type=Path)
    args=parser.parse_args()
    request=read(args.request)
    output=Path(request['output'])
    threads=request['threads']
    owner=psutil.Process()
    owner.cpu_affinity(owner.cpu_affinity()[:20])
    if not 1<=threads<=20:
        raise ValueError('Training must use between 1 and 20 threads')
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        os.environ[name]=str(threads)
    logging.basicConfig(filename=output.with_suffix('.log'),level=logging.INFO,format='%(asctime)s %(message)s')
    started=time.monotonic()
    finished=threading.Event()
    def timings():
        cpu=owner.cpu_times()
        io=owner.io_counters()
        write(output.with_suffix('.timings.json'),{'seconds':time.monotonic()-started,
              'cpu_seconds':cpu.user+cpu.system,'rss_bytes':owner.memory_info().rss,'threads':owner.num_threads(),
              'read_bytes':io.read_bytes,'write_bytes':io.write_bytes,
              'functions':[dict(zip(COLUMNS,row)) for row in RECORDER.totals()]})
    def monitor():
        while not finished.wait(2):
            timings()
    recorder=threading.Thread(target=monitor,daemon=True)
    recorder.start()
    try:
        import psycopg
        from interface.recording.store import DSN
        from .evaluate import evaluate
        from .space import Space
        directory=Path(request['data'])
        manifest=read(directory/'dataset.json')
        config=Space(manifest['groups'][request['model']]).canonical(request['config'])
        progress=output.with_suffix('.progress.json')
        logging.getLogger('tuning').info('worker imports and configuration %.3fs',time.monotonic()-started)
        with psycopg.connect(DSN,connect_timeout=5) as connection:
            connection.execute('set transaction isolation level repeatable read read only')
            connection.execute('set local max_parallel_workers_per_gather=0')
            result=evaluate(connection,directory,manifest,request['model'],config,threads,request['seed'],progress,output,request['weighting']['weights'])
        write(output,{'state':'completed',**result,'seconds':time.monotonic()-started})
    except Exception:
        write(output,{'state':'failed','error':traceback.format_exc(),'seconds':time.monotonic()-started})
        raise
    finally:
        finished.set()
        recorder.join()
        timings()


if __name__=='__main__':
    main()
