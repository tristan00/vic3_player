import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psutil

HERE=Path(__file__).parent
ROOT=HERE.parent
SHARED=('DSN','psycopg','test_store','open_pool')
GRAPH='test_entity_graph'
SHARE=.1
SINGLE={name:'1' for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')}


def run(modules):
    started=time.monotonic()
    done=subprocess.run([sys.executable,'-m','unittest',*modules],cwd=ROOT,capture_output=True,text=True,env={**os.environ,**SINGLE,'PYTHONPATH':str(ROOT)})
    return modules,done.returncode,done.stderr,time.monotonic()-started


def main():
    started=time.monotonic()
    cores=list(range(os.cpu_count()))[-max(1,int(os.cpu_count()*SHARE)):]
    runner=psutil.Process()
    runner.cpu_affinity(cores)
    runner.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    names=sorted(path.stem for path in HERE.glob('test_*.py'))
    first=[name for name in names if name.startswith(GRAPH) or any(word in (HERE/f'{name}.py').read_text(encoding='utf-8') for word in SHARED)]
    rest=[name for name in names if name not in first]
    parts=max(1,len(cores)-1)
    jobs=[[f'tests.{name}' for name in group] for group in (first,*(rest[part::parts] for part in range(parts))) if group]
    with ThreadPoolExecutor(len(cores)) as pool:
        results=list(pool.map(run,jobs))
    failed=[result for result in results if result[1]]
    for modules,_,output,_ in failed:
        print(' '.join(modules))
        print(output)
    ran=sum(int(line.split()[1]) for _,_,output,_ in results for line in output.splitlines() if line.startswith('Ran '))
    slowest=max(results,key=lambda result:result[3])
    print(f'{ran} tests in {time.monotonic()-started:.1f}s on {len(cores)} of {os.cpu_count()} cores, slowest job {slowest[3]:.1f}s ({slowest[0][0]}{" ..." if len(slowest[0])>1 else ""}), {len(failed)} failed jobs')
    return 1 if failed else 0


if __name__=='__main__':
    sys.exit(main())
