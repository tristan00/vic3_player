from datetime import datetime, timezone
import logging
import math
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

import psutil

from interface.common import evidence, timed
from . import ACTIVE, VERSION
from . import weighting
from .data import prepare, verify
from .metrics import SPEC, loss
from .search import propose
from .space import Space
from .storage import digest, read, save, source_digest, write

LOG=logging.getLogger('tuning')
SECONDS=40


@timed
def stop(process):
    try:
        children=process.children(recursive=True)
        for child in reversed(children):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        process.kill()
        psutil.wait_procs([process,*children],timeout=5)
    except psutil.NoSuchProcess:
        pass


@timed
def execute(directory,request,seconds,memory_gb,heartbeat):
    if not 0<seconds<=SECONDS:
        raise ValueError(evidence(seconds=seconds,limit=SECONDS))
    request_path=directory/f"request_{request['trial']:05d}.json"
    output=directory/f"result_{request['trial']:05d}.json"
    request={**request,'output':str(output.resolve())}
    output.unlink(missing_ok=True)
    output.with_suffix('.progress.json').unlink(missing_ok=True)
    write(request_path,request)
    started=time.monotonic()
    started_at=time.time()
    environment={**os.environ,**{name:str(request['threads']) for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')}}
    with output.with_suffix('.stderr.log').open('w') as log:
        child=subprocess.Popen([sys.executable,'-m','tuning.worker','--request',str(request_path)],cwd=Path(__file__).resolve().parents[1],
                               stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=environment,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        process=psutil.Process(child.pid)
        created=process.create_time()
        peak=0
        state=None
        last_beat=-1.
        try:
            while child.poll() is None:
                elapsed=time.monotonic()-started
                try:
                    memory=process.memory_info().rss+sum(p.memory_info().rss for p in process.children(recursive=True) if p.is_running())
                    peak=max(peak,memory)
                except psutil.NoSuchProcess:
                    memory=0
                if elapsed>=seconds or memory>memory_gb*2**30:
                    state='time_limit' if elapsed>=seconds else 'memory_limit'
                    stop(process)
                    break
                if elapsed-last_beat>=1:
                    progress=output.with_suffix('.progress.json')
                    heartbeat({'trial':request['trial'],'pid':child.pid,'created':created,'seconds':elapsed,'memory_gb':memory/2**30,
                               'detail':read(progress) if progress.exists() else {'step':'starting'}})
                    last_beat=elapsed
                time.sleep(min(.05,max(0,seconds-(time.monotonic()-started))))
        finally:
            if child.poll() is None:
                stop(process)
            child.wait()
    elapsed=time.monotonic()-started
    if elapsed>seconds and state is None:
        state='time_limit'
    if state:
        result={'state':state,'error':f'{state}: {seconds}s / {memory_gb} GiB'}
    elif not output.is_file():
        result={'state':'failed','error':f'Worker exited {child.returncode} without a result; see {output.with_suffix(".stderr.log").name}'}
    else:
        result=read(output)
        if child.returncode and result['state']=='completed':
            result={'state':'failed','error':f'Worker exited {child.returncode} after writing a result'}
    progress_path=output.with_suffix('.progress.json')
    detail=read(progress_path) if progress_path.exists() else {}
    timings=dict(detail.get('timings',{}))
    interrupted=detail.get('step') if result['state']!='completed' else None
    if interrupted and 'step_started' in detail:
        timings[interrupted]=max(0,min(time.time(),started_at+seconds)-detail['step_started'])
    return {**result,'seconds':elapsed,'peak_memory_gb':peak/2**30,'timings':timings,'interrupted_step':interrupted}


@timed
def run_search(directory,data,manifest,model,settings,heartbeat):
    directory.mkdir(parents=True,exist_ok=True)
    space=Space(manifest['groups'][model])
    search={'version':VERSION,'model':model,'data':str(data.resolve()),'dataset_digest':digest(data/'dataset.json'),
            'source_digest':source_digest(),'metric':SPEC,'groups':space.groups,'parameters':space.parameters,'seconds_limit':SECONDS,**settings}
    config_path=directory/'search.json'
    if config_path.exists() and read(config_path)!=search:
        raise ValueError(evidence(path=config_path))
    write(config_path,search)
    history=[read(path) for path in sorted(directory.glob('trial_*.json'))]
    if [trial['trial'] for trial in history]!=list(range(len(history))):
        raise ValueError(evidence(trials=[trial['trial'] for trial in history]))
    for trial in history:
        if space.canonical(trial['config'])!=trial['config'] or (trial['state']=='completed' and not math.isfinite(trial['metrics']['score'])):
            raise ValueError(evidence(trial=trial['trial'],state=trial['state']))
    while len(history)<settings['trials']:
        number=len(history)
        weights=weighting.current(directory)
        config,proposal,trace=propose(space,history,settings['seed']+number,model,weights,settings['tuner'])
        save(directory/f'proposal_{number:05d}.pkl.gz',trace)
        trial={'trial':number,'config':config,'proposal':proposal,'state':'running','started_at':datetime.now(timezone.utc).isoformat()}
        request={'trial':number,'data':str(data.resolve()),'model':model,'config':config,'threads':settings['threads'],'seed':settings['seed'],'weighting':weights}
        def update(current):
            write(directory/'status.json',{'state':'running','phase':'tuning','current':{**trial,**current},'finished':len(history),
                                          'requested':settings['trials'],'updated':time.time(),'pid':os.getpid(),'created':psutil.Process().create_time()})
            heartbeat({'phase':'tuning','model':model,'current':current,'finished':len(history)})
        update({'seconds':0})
        result=execute(directory,request,SECONDS,settings['memory_gb'],update)
        found={**trial,**result}
        write(directory/f'trial_{number:05d}.json',found)
        history.append(found)
        LOG.info('%s trial %d %s score %s %.1fs',model,number,found['state'],found.get('metrics',{}).get('score'),found['seconds'])
    with weighting.locked(directory):
        return finish(directory,history,manifest,model,settings,search,space.groups,weighting.current(directory))


@timed
def finish(directory,history,manifest,model,settings,search,groups,weights):
    eligible=[trial for trial in history if trial['state']=='completed']
    if not eligible:
        raise RuntimeError(evidence(trials=len(history),states=sorted({trial['state'] for trial in history})))
    chosen=min(eligible,key=lambda trial:loss(trial['metrics'],weights['weights']))
    winner={**chosen,'metrics':{**chosen['metrics'],'score':loss(chosen['metrics'],weights['weights'])},
            'baseline':{**chosen['baseline'],'score':loss(chosen['baseline'],weights['weights'])},'ranking_weighting':weights}
    write(directory/'winner.json',winner)
    artifact=directory/f"result_{winner['trial']:05d}.model.pkl.gz"
    installed={'version':VERSION,'model':model,'config':winner['config'],'groups':groups,'trial':winner['trial'],'objective':manifest['objective'],
               'search':str(directory.resolve()),'dataset_digest':search['dataset_digest'],'source_digest':search['source_digest'],
               'validation':winner['metrics'],'installed_at':datetime.now(timezone.utc).isoformat(),
               'artifact':str(artifact.resolve()),'artifact_digest':digest(artifact),'threads':settings['threads'],'weighting':weights}
    write(directory/'deployment.json',installed)
    if settings['install']:
        write(ACTIVE/f'{model}.json',installed)
    write(directory/'status.json',{'state':'completed','phase':'completed','finished':len(history),'requested':settings['trials'],
                                  'current':None,'winner':winner['trial'],'installed':settings['install'],'updated':time.time()})
    return installed


@timed
def run(directory):
    settings=read(directory/'request.json')
    logging.basicConfig(filename=directory/'job.log',level=logging.INFO,format='%(asctime)s %(message)s')
    started=time.monotonic()
    def heartbeat(progress):
        write(directory/'status.json',{'state':'running','pid':os.getpid(),'created':psutil.Process().create_time(),
                                       'updated':time.time(),'seconds':time.monotonic()-started,**progress})
    try:
        heartbeat({'phase':'prepare'})
        data=Path(settings['data']) if settings['data'] else directory/'data'
        if not (data/'dataset.json').exists():
            prepare(data,settings['models'],settings['seed'],settings['points_per_run'],heartbeat)
        manifest=verify(data,settings['models'])
        for model in settings['models']:
            run_search(directory/model,data,manifest,model,settings,heartbeat)
        write(directory/'status.json',{'state':'completed','phase':'completed','updated':time.time(),'seconds':time.monotonic()-started})
    except Exception:
        error=traceback.format_exc()
        LOG.exception(evidence())
        for model in settings['models']:
            path=directory/model/'status.json'
            if path.exists() and read(path)['state']=='running':
                write(path,{**read(path),'state':'failed','error':error,'updated':time.time()})
        write(directory/'status.json',{'state':'failed','phase':'failed','error':error,'updated':time.time(),'seconds':time.monotonic()-started})
        raise


@timed
def work(directory):
    owner=psutil.Process()
    owner.cpu_affinity(owner.cpu_affinity()[:20])
    with (directory/'controller.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        try:
            run(directory)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
