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

SKIPPED={'pause','unpause','set_speed'}


def main(seed=0,per=5,budget=45):
    logging.basicConfig(level=logging.WARNING)
    game=GameInterface('actions');store=Store();store.begin_run(kind='attached',started_at=datetime.now(timezone.utc));rng=random.Random(seed)
    started=time.monotonic()
    options=available(Stored(store.connection,*record(game,store,'manual')))
    executor=Executor(game)
    totals=collections.Counter()
    for name,combos in options.items():
        if name in SKIPPED or time.monotonic()-started>budget:
            continue
        verdicts=[]
        for combo in rng.sample(combos,min(per,len(combos))):
            try:
                result=executor.run(name,check=True,**combo)
                verdicts.append('valid' if result['valid'] else result['desc'][:70] or 'invalid')
            except LookupError:
                verdicts.append('no object')
        valid=verdicts.count('valid')
        totals['sampled']+=len(verdicts);totals['valid']+=valid
        reason=collections.Counter(v for v in verdicts if v!='valid').most_common(1)
        print(f'{name:28s} {len(combos):6d} {valid}/{len(verdicts)} {reason[0][0] if reason else ""}')
    print(f"{totals['valid']}/{totals['sampled']} valid, {time.monotonic()-started:.1f}s")


if __name__=='__main__':
    main(int(sys.argv[1]) if len(sys.argv)>1 else 0)
