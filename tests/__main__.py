import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE=Path(__file__).parent
ROOT=HERE.parent
SHARED=('DSN','psycopg','test_store','open_pool')


def run(modules):
    started=time.monotonic()
    done=subprocess.run([sys.executable,'-m','unittest',*modules],cwd=ROOT,capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(ROOT)})
    return modules,done.returncode,done.stderr,time.monotonic()-started


def main():
    started=time.monotonic()
    names=sorted(path.stem for path in HERE.glob('test_*.py'))
    database=[name for name in names if any(word in (HERE/f'{name}.py').read_text(encoding='utf-8') for word in SHARED)]
    jobs=[[f'tests.{name}' for name in database]]+[[f'tests.{name}'] for name in names if name not in database]
    with ThreadPoolExecutor(os.cpu_count()) as pool:
        results=list(pool.map(run,jobs))
    failed=[result for result in results if result[1]]
    for modules,_,output,_ in failed:
        print(' '.join(modules))
        print(output)
    ran=sum(int(line.split()[1]) for _,_,output,_ in results for line in output.splitlines() if line.startswith('Ran '))
    slowest=max(results,key=lambda result:result[3])
    print(f'{ran} tests in {time.monotonic()-started:.1f}s, slowest job {slowest[3]:.1f}s ({slowest[0][0]}{" ..." if len(slowest[0])>1 else ""}), {len(failed)} failed jobs')
    return 1 if failed else 0


if __name__=='__main__':
    sys.exit(main())
