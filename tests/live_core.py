import collections
import logging
import random
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from interface import GameInterface, record
from interface.actions import Executor
from interface.options import available
from interface.options.stored import Stored
from interface.recording.store import Store
from datetime import datetime, timezone

CORE=('build','switch_production_method','enact_law','cancel_enactment')


def universe(s,name):
    if name=='build':
        return [{'state':state,'building_type':kind} for state in s.states() for kind in s.keys('building_type')]
    if name=='switch_production_method':
        methods={}
        for kind,_,method in s.reference('building_production_method'):
            methods.setdefault(kind,[]).append(method)
        return [{'building':ident,'production_method':method} for ident,kind,_ in s.buildings() for method in methods.get(kind,())]
    if name=='enact_law':
        return [{'law':ident} for ident, in s.rows('law','law',country=s.player)]
    return []


def verdict(executor,name,combo):
    try:
        result=executor.run(name,check=True,**combo)
        return 'valid' if result['valid'] else (result['desc'][:80] or 'invalid')
    except LookupError:
        return 'no object'


def main(seed=0,per=40,budget=50):
    logging.basicConfig(level=logging.WARNING)
    game=GameInterface('actions');store=Store();store.begin_run(kind='attached',started_at=datetime.now(timezone.utc));executor=Executor(game);rng=random.Random(seed)
    started=time.monotonic()
    snapshot=Stored(store.connection,*record(game,store,'manual'))
    options=available(snapshot)
    for name in CORE:
        offered=options[name]
        verdicts=collections.Counter(verdict(executor,name,combo) for combo in rng.sample(offered,min(per,len(offered))))
        excluded=[combo for combo in universe(snapshot,name) if combo not in offered]
        missed=[combo for combo in rng.sample(excluded,min(per,len(excluded))) if verdict(executor,name,combo)=='valid']
        print(f'{name:26s} offered {len(offered):5d} valid {verdicts["valid"]}/{sum(verdicts.values())}  excluded {len(excluded):5d} missed {len(missed)}/{min(per,len(excluded))} {missed[:3]}')
        for reason,count in verdicts.most_common(6):
            if reason!='valid':
                print(f'    {count:3d} {reason}')
        if time.monotonic()-started>budget:
            break
    print(f'{time.monotonic()-started:.1f}s')


if __name__=='__main__':
    main(int(sys.argv[1]) if len(sys.argv)>1 else 0)
