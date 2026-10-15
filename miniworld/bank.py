import argparse
import json
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

from interface.common import evidence, write_json
from . import timed, timed_often

INDEX='bank.json'
RANGES={'countries':(1,20),'size':(1.2,10.),'concentration':(.1,10.),'landmasses':(1,4),'climate':(.1,.9),'relief':(.3,2.),'density':(.4,2.5),'diversity':(0.,2.5),'diplomacy':(0.,1.),'ideology':(0.,1.)}
LIMIT=160
KNOBS=('concentration','landmasses','climate','relief','density','diversity','diplomacy','ideology')
MODELS=None


@timed
def draw(rng):
    countries=int(rng.integers(RANGES['countries'][0],RANGES['countries'][1]+1))
    size=float(np.exp(rng.uniform(*np.log(RANGES['size']))))
    states=int(min(LIMIT,max(countries,round(countries*size))))
    return {'states':states,'countries':countries,'size':size,
            'concentration':float(np.exp(rng.uniform(*np.log(RANGES['concentration'])))),
            'landmasses':int(min(states,rng.integers(RANGES['landmasses'][0],RANGES['landmasses'][1]+1))),
            'climate':float(rng.uniform(*RANGES['climate'])),'relief':float(rng.uniform(*RANGES['relief'])),
            'density':float(np.exp(rng.uniform(*np.log(RANGES['density'])))),'diversity':float(rng.uniform(*RANGES['diversity'])),
            'diplomacy':float(rng.uniform(*RANGES['diplomacy'])),'ideology':float(rng.uniform(*RANGES['ideology']))}


@timed
def ready(models):
    global MODELS
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(process)d %(message)s')
    MODELS=models


@timed
def one(directory,name,seed,knobs):
    from .build import build
    started=time.monotonic()
    build(MODELS,Path(directory)/'worlds'/name,seed,knobs)
    return {'name':name,'seed':seed,'knobs':knobs,'manifest':f'worlds/{name}/manifest.json','seconds':round(time.monotonic()-started,2)}


@timed
def create(directory,count,seed,workers):
    from .build import prepare
    if count<1 or workers<1: raise ValueError(evidence(count=count,workers=workers))
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=False)
    workers=min(workers,count)
    rng=np.random.default_rng(seed)
    jobs=[(f'world_{index:04d}',int(rng.integers(2**31)),draw(rng)) for index in range(count)]
    jobs.sort(key=lambda job:(-job[2]['states'],job[0]))
    started=time.monotonic()
    models=prepare()
    if workers==1:
        ready(models)
        worlds=[one(directory,*job) for job in jobs]
    else:
        with ProcessPoolExecutor(workers,initializer=ready,initargs=(models,)) as pool:
            worlds=list(pool.map(one,[str(directory)]*count,*zip(*jobs),buffersize=workers*2))
    worlds.sort(key=lambda world:world['name'])
    pending=directory/(INDEX+'.tmp')
    write_json(pending,{'seed':seed,'count':count,'workers':workers,'created':datetime.now(timezone.utc).isoformat(),
                                'seconds':round(time.monotonic()-started,1),'ranges':RANGES,'worlds':worlds})
    pending.replace(directory/INDEX)
    return directory/INDEX


@timed_often
def revision(path):
    path=Path(path).resolve()
    stat=path.stat()
    return path,stat.st_mtime_ns,stat.st_size


@lru_cache(maxsize=32)
@timed
def index(path,modified,size):
    found=json.loads(path.read_text(encoding='utf-8'))
    if not found['worlds'] or found['count']!=len(found['worlds']): raise ValueError(evidence(path=path,count=found['count']))
    return found


@lru_cache(maxsize=8)
@timed
def catalogue(revisions):
    found=[]
    for path,modified,size in revisions:
        for world in index(path,modified,size)['worlds']:
            target=(path.parent/world['manifest']).resolve()
            if not target.is_relative_to(path.parent) or not target.is_file(): raise ValueError(evidence(manifest=target,bank=path))
            found.append(target)
    if not found: raise ValueError(evidence(banks=revisions))
    return tuple(found)


@timed
def worlds(directories):
    return list(catalogue(tuple(revision(Path(directory)/INDEX) for directory in directories)))


@timed
def take(directories,rng):
    found=catalogue(tuple(revision(Path(directory)/INDEX) for directory in directories))
    return found[rng.randrange(len(found))]


@lru_cache(maxsize=128)
@timed
def loaded(path,modified,size):
    found=json.loads(path.read_text(encoding='utf-8'))
    if not found['countries'] or not found['states'] or any(name not in found['knobs'] for name in KNOBS):
        raise ValueError(evidence(manifest=path))
    mod=(path.parent/found['mod']).resolve()
    if not (mod/'.metadata/metadata.json').is_file(): raise FileNotFoundError(evidence(manifest=path,mod=mod))
    found['mod']=str(mod)
    return found


@timed_often
def manifest(path):
    return loaded(*revision(path))


@timed
def status(directory):
    found=index(*revision(Path(directory)/INDEX))
    knobs={name:[world['knobs'][name] for world in found['worlds']] for name in ('states',*RANGES)}
    return {'worlds':found['count'],'seed':found['seed'],'created':found['created'],'seconds':found['seconds'],'workers':found['workers'],
            'knobs':{name:{'min':min(values),'median':float(np.median(values)),'max':max(values)} for name,values in knobs.items()}}


@timed
def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--count',type=int,required=True)
    parser.add_argument('--seed',type=int,required=True)
    parser.add_argument('--workers',type=int,default=min(8,os.cpu_count() or 1))
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(process)d %(message)s')
    print(create(args.directory,args.count,args.seed,args.workers))


if __name__=='__main__':
    main()
