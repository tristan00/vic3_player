import argparse
import math
from datetime import datetime, timezone
from pathlib import Path
import sys

from interface.common import evidence
from interface.runner.session import _spawn
from . import ROOT
from .storage import read, write
from .weighting import initialize, normalize


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['start','resume','work','status'])
    parser.add_argument('--directory',type=Path)
    parser.add_argument('--data',type=Path)
    parser.add_argument('--models',nargs='+',choices=['histogram','row'],default=['histogram','row'])
    parser.add_argument('--trials',type=int,default=400)
    parser.add_argument('--points-per-run',type=int,default=12)
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--memory-gb',type=float,default=6.)
    parser.add_argument('--seed',type=int,default=19)
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--differentiation-weight',type=float)
    parser.add_argument('--reward-weight',type=float)
    args=parser.parse_args()
    directory=args.directory or ROOT/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if args.command=='start':
        if args.differentiation_weight is None or args.reward_weight is None:
            parser.error(evidence(differentiation_weight=args.differentiation_weight,reward_weight=args.reward_weight))
        weights=normalize({'differentiation':args.differentiation_weight,'reward':args.reward_weight})
        if min(args.trials,args.points_per_run,args.threads,args.memory_gb)<=0 or args.threads>20 or not math.isfinite(args.memory_gb):
            raise ValueError(evidence(trials=args.trials,points_per_run=args.points_per_run,threads=args.threads,memory_gb=args.memory_gb))
        directory.mkdir(parents=True,exist_ok=False)
        write(directory/'request.json',{'data':str(args.data.resolve()) if args.data else None,'models':list(dict.fromkeys(args.models)),
              'trials':args.trials,'points_per_run':args.points_per_run,'threads':args.threads,'memory_gb':args.memory_gb,'seed':args.seed,'install':args.install,'initial_weights':weights})
        for model in dict.fromkeys(args.models):
            initialize(directory/model,weights)
    if args.command in ('start','resume'):
        if args.command=='resume':
            from interface.runner.session import process
            status=read(directory/'status.json')
            if process(status) is not None:
                raise ValueError(evidence(directory=directory,pid=process(status).pid))
            for model in read(directory/'request.json')['models']:
                path=directory/model/'status.json'
                if path.exists():
                    current=read(path).get('current')
                    if current:
                        orphan=process(current)
                        if orphan is not None:
                            from .job import stop
                            stop(orphan)
        process=_spawn([sys.executable,'-m','tuning','work','--directory',str(directory.resolve())],Path(__file__).resolve().parents[1])
        print(f'Tuning launched: pid {process.pid}, directory {directory.resolve()}')
    elif args.command=='work':
        from .job import work
        work(directory)
    else:
        print(read(directory/'status.json'))


if __name__=='__main__':
    main()
