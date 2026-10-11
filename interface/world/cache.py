from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import logging
from pathlib import Path
import pickle
import random
import sys
import time
import traceback

import numpy as np
import psutil

from ..common import timed, timed_often
from ..runner.session import _spawn, process as owner
from .generate import generate
from .sampling import jobs
from .vanilla import boxes, rasters, vanilla


ROOT=Path(__file__).resolve().parents[2]
SOURCES=None


@timed_often
def publish(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2),encoding='utf-8')
    temporary.replace(path)


@timed
def checked(path):
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if Path(manifest['mod']).resolve()!=path.parent/'mod' or not (path.parent/'mod/map_data/provinces.png').is_file():
        raise ValueError(f'Cached world is missing its map or has moved: {path}')
    audit=json.loads((path.parent/'audit.json').read_text(encoding='utf-8'))
    if (not all(audit[name] for name in ('population_structure_preserved','culture_projection_matches','production_methods_match_projection')) or
            any(audit[name] for name in ('company_errors','ownership_errors','duplicate_buildings','coastal_templates_inland'))):
        raise ValueError(f'Cached world failed its generation audit: {path}')


@timed
def worlds(root):
    return sorted(root/name for name in json.loads((root/'index.json').read_text(encoding='utf-8'))['worlds'])


@timed
def configure(root,**settings):
    settings.update(seed=random.SystemRandom().randrange(10**12) if settings['seed'] is None else settings['seed'],game=str(Path(settings['game']).resolve()))
    jobs(settings)
    root.mkdir(parents=True)
    publish(root/'config.json',settings)
    publish(root/'index.json',{'worlds':[]})
    publish(root/'status.json',{'phase':'starting','target':settings['count'],'updated':time.time()})


@timed
def prepare_sources(root,game):
    folder=root/'sources'
    folder.mkdir()
    arrays=rasters(game)
    for name,array in arrays.items():
        np.save(folder/(name+'.npy'),array,allow_pickle=False)
    with open(folder/'definitions.pkl','wb') as handle:
        pickle.dump((vanilla(game),boxes(arrays['provinces'])),handle,pickle.HIGHEST_PROTOCOL)


@timed
def worker(root):
    global SOURCES
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    folder=Path(root)/'sources'
    with open(folder/'definitions.pkl','rb') as handle:
        data,bounds=pickle.load(handle)
    SOURCES=(data,{path.stem:np.load(path,mmap_mode='r',allow_pickle=False) for path in folder.glob('*.npy')},bounds)


@timed
def build_one(root,settings,job):
    started=time.monotonic()
    path=generate(root,settings['game'],SOURCES,settings['source_group_pool'],settings['country_pool'],**job)
    checked(path)
    return str(path.relative_to(root)),time.monotonic()-started


@timed
def build(root,workers):
    process=psutil.Process()
    settings=json.loads((root/'config.json').read_text(encoding='utf-8'))
    state={'pid':process.pid,'created':process.create_time(),'workers':workers,'started':time.time(),'updated':time.time(),
           'phase':'preparing sources','target':settings['count'],'completed':0,'world_seconds':0}
    publish(root/'status.json',state)
    try:
        prepare_sources(root,Path(settings['game'])/'game')
        state['phase']='building'
        publish(root/'status.json',state)
        complete=[]
        with ProcessPoolExecutor(workers,initializer=worker,initargs=(str(root),)) as pool:
            futures=[pool.submit(build_one,root,settings,job) for job in jobs(settings)]
            try:
                for future in as_completed(futures):
                    path,seconds=future.result()
                    complete.append(path)
                    publish(root/'index.json',{'worlds':sorted(complete)})
                    state.update(completed=len(complete),updated=time.time(),world_seconds=state['world_seconds']+seconds)
                    publish(root/'status.json',state)
                    print(f'{len(complete)}/{settings["count"]} {Path(path).parent.name} {seconds:.2f}s',flush=True)
            except BaseException:
                for future in futures:
                    future.cancel()
                pool.terminate_workers()
                raise
        state.update(phase='complete',updated=time.time())
    except BaseException as error:
        state.update(phase='failed',error=f'{type(error).__name__}: {error}',traceback=traceback.format_exc(),updated=time.time())
        raise
    finally:
        publish(root/'status.json',state)


@timed
def status(root):
    state=json.loads((root/'status.json').read_text(encoding='utf-8'))
    return dict(state,running=owner(state) is not None)


@timed
def launch(root,workers):
    process=_spawn([sys.executable,'-m','interface.world.cache',str(root),str(workers)],str(ROOT))
    return {'output':str(root),'pid':process.pid,'workers':workers,'log':str(root/'build.log')}


@timed
def main():
    root,workers=Path(sys.argv[1]),int(sys.argv[2])
    sys.stdout=sys.stderr=open(root/'build.log','a',encoding='utf-8',buffering=1)
    logging.basicConfig(stream=sys.stderr,level=logging.WARNING,format='%(asctime)s %(message)s')
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    build(root,workers)


if __name__=='__main__':
    main()
