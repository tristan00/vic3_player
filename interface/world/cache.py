import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import logging
import msvcrt
from pathlib import Path
import pickle
import random
import sys
import time
import traceback

import numpy as np
import psutil

from ..common import DEFAULT_DATA, DEFAULT_GAME, timed, timed_often
from ..runner.session import _spawn
from .generate import generate
from .sampling import SLIDERS, world_size
from .vanilla import boxes, rasters, vanilla


ROOT=Path(__file__).resolve().parents[2]
DEFAULT_CACHE=DEFAULT_DATA/'world_cache'
MINIMUM=1000
SOURCES=None


@timed
def fingerprint(game):
    digest=hashlib.sha256()
    for path in sorted(path for path in (ROOT/'interface/world').glob('*.py') if path.name not in ('cache.py','__main__.py','__init__.py'))+[ROOT/'interface/script.py']:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    binary=Path(game)/'binaries/victoria3.exe'
    stat=binary.stat()
    digest.update(str((str(Path(game).resolve()),stat.st_size,stat.st_mtime_ns)).encode())
    return digest.hexdigest()


@timed_often
def publish(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2),encoding='utf-8')
    temporary.replace(path)


@timed_often
def jobs(seed,count):
    rng=random.Random(seed)
    seen=set()
    result=[]
    while len(result)<count:
        size=world_size(rng,[None]*len(SLIDERS))
        if size[0] not in seen:
            seen.add(size[0])
            result.append(size)
    return result


@timed_often
def manifest_path(root,size):
    return root/'worlds'/f'seed_{size[0]}_{size[1]}_{size[2]}'/'manifest.json'


@timed
def checked(path):
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if Path(manifest['mod']).resolve()!=path.parent/'mod' or not (path.parent/'mod/map_data/provinces.png').is_file():
        raise ValueError(f'Cached world is missing its map or has moved: {path}')
    if not any(c['country_type']!='decentralized' for c in manifest['countries']):
        raise ValueError(f'Cached world has no playable country: {path}')
    audit=json.loads((path.parent/'audit.json').read_text(encoding='utf-8'))
    if (not audit['population_structure_preserved'] or not audit['culture_projection_matches'] or not audit['production_methods_match_projection'] or
            any(audit[name] for name in ('company_errors','ownership_errors','duplicate_buildings','coastal_templates_inland'))):
        raise ValueError(f'Cached world failed its generation audit: {path}')
    return manifest['seed']


@timed
def prepare_sources(root,game):
    folder=root/'sources'
    folder.mkdir(exist_ok=True)
    if (folder/'ready').is_file():
        return
    source=Path(game)/'game'
    for name,array in rasters(source).items():
        np.save(folder/(name+'.npy'),array,allow_pickle=False)
    with open(folder/'definitions.pkl','wb') as handle:
        pickle.dump((vanilla(source),boxes(source)),handle,pickle.HIGHEST_PROTOCOL)
    (folder/'ready').touch()
    rasters.cache_clear()
    boxes.cache_clear()


@timed
def worker(root):
    global SOURCES
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    folder=Path(root)/'sources'
    with open(folder/'definitions.pkl','rb') as handle:
        data,bounds=pickle.load(handle)
    SOURCES=(data,{path.stem:np.load(path,mmap_mode='r',allow_pickle=False) for path in folder.glob('*.npy')},bounds)


@timed
def build_one(root,game,size):
    started=time.monotonic()
    path=generate(*size,game_dir=game,data_dir=root,source_data=SOURCES)
    checked(path)
    return str(path),time.monotonic()-started


@timed
def build(root,game,count,workers,seed):
    root=Path(root).resolve()
    if count<MINIMUM or workers<1:
        raise ValueError(f'Use at least {MINIMUM} worlds and one worker')
    root.mkdir(parents=True,exist_ok=True)
    with open(root/'build.lock','a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        identity=fingerprint(game)
        config=root/'config.json'
        if config.is_file():
            settings=json.loads(config.read_text(encoding='utf-8'))
            if settings['fingerprint']!=identity or (seed is not None and seed!=settings['seed']):
                raise ValueError('Cache sources or seed changed; use a new cache directory')
        else:
            settings={'fingerprint':identity,'seed':seed if seed is not None else random.SystemRandom().randrange(10**12),'game':str(Path(game).resolve())}
            publish(config,settings)
        sizes=jobs(settings['seed'],count)
        complete=[]
        pending=[]
        for size in sizes:
            path=manifest_path(root,size)
            if path.exists():
                if checked(path)!=size[0]:
                    raise ValueError(f'Wrong cached world seed: {path}')
                complete.append(str(path.relative_to(root)))
            else:
                pending.append(size)
        state={'pid':psutil.Process().pid,'created':psutil.Process().create_time(),'target':count,'completed':len(complete),
               'workers':workers,'started':time.time(),'updated':time.time(),'phase':'preparing sources','world_seconds':0}
        publish(root/'index.json',{'fingerprint':identity,'worlds':complete})
        publish(root/'status.json',state)
        try:
            if pending:
                prepare_sources(root,game)
                state['phase']='building'
                publish(root/'status.json',state)
                with ProcessPoolExecutor(workers,initializer=worker,initargs=(str(root),)) as pool:
                    futures={pool.submit(build_one,root,game,size):size for size in pending}
                    try:
                        for future in as_completed(futures):
                            path,seconds=future.result()
                            complete.append(str(Path(path).relative_to(root)))
                            publish(root/'index.json',{'fingerprint':identity,'worlds':sorted(complete)})
                            state.update(completed=len(complete),updated=time.time(),world_seconds=state['world_seconds']+seconds)
                            publish(root/'status.json',state)
                            print(f'{len(complete)}/{count} {Path(path).parent.name} {seconds:.2f}s',flush=True)
                    except BaseException as error:
                        state.update(phase='failed',error=f'{type(error).__name__}: {error}',traceback=traceback.format_exc(),updated=time.time())
                        publish(root/'status.json',state)
                        for future in futures:
                            future.cancel()
                        raise
            state.update(phase='complete',updated=time.time())
            publish(root/'status.json',state)
        except BaseException as error:
            state.update(phase='failed',error=f'{type(error).__name__}: {error}',traceback=traceback.format_exc(),updated=time.time())
            publish(root/'status.json',state)
            raise


class Cached:
    @timed
    def __init__(self,root,rng,game=DEFAULT_GAME):
        self.root=Path(root).resolve()
        index=json.loads((self.root/'index.json').read_text(encoding='utf-8'))
        if index['fingerprint']!=fingerprint(game):
            raise ValueError('Cached worlds were generated from different sources; rebuild in a new directory')
        self.worlds=sorted({(self.root/path).resolve() for path in index['worlds']})
        if len(self.worlds)<MINIMUM:
            raise ValueError(f'World cache needs at least {MINIMUM} completed worlds; found {len(self.worlds)}')
        if any(not path.is_relative_to(self.root/'worlds') or not path.is_file() for path in self.worlds):
            raise ValueError('World cache contains missing or misplaced manifests')
        self.rng=rng

    @timed
    def take(self):
        world=self.rng.choice(self.worlds)
        checked(world)
        return world


@timed
def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('command',choices=('build','status'))
    parser.add_argument('--directory',type=Path,default=DEFAULT_CACHE)
    parser.add_argument('--game-dir',type=Path,default=DEFAULT_GAME)
    parser.add_argument('--count',type=int,default=MINIMUM)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--seed',type=int)
    parser.add_argument('--foreground',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args.command=='status':
        state=json.loads((args.directory/'status.json').read_text(encoding='utf-8'))
        state['running']=psutil.pid_exists(state['pid']) and psutil.Process(state['pid']).create_time()==state['created']
        print(json.dumps(state,indent=2))
        return
    if args.count<MINIMUM or args.workers<1:
        parser.error(f'Use at least {MINIMUM} worlds and one worker')
    if not args.foreground:
        args.directory.mkdir(parents=True,exist_ok=True)
        command=[sys.executable,'-m','interface.world.cache','build','--foreground','--directory',str(args.directory.resolve()),
                 '--game-dir',str(args.game_dir.resolve()),'--count',str(args.count),'--workers',str(args.workers)]
        if args.seed is not None:
            command+=['--seed',str(args.seed)]
        process=_spawn(command,str(ROOT))
        print(f'WORLD CACHE LAUNCHED pid {process.pid}; log {args.directory / "build.log"}',flush=True)
        return
    with open(args.directory/'build.log','a',encoding='utf-8',buffering=1) as log:
        sys.stdout=sys.stderr=log
        logging.basicConfig(stream=log,level=logging.WARNING,format='%(asctime)s %(message)s')
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        try:
            build(args.directory,args.game_dir,args.count,args.workers,args.seed)
        except BaseException:
            traceback.print_exc()
            raise


if __name__=='__main__':
    main()
