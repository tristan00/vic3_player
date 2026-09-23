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


def valid(executor,name,combos,rng,tries=30):
    for combo in rng.sample(combos,min(tries,len(combos))):
        try:
            if executor.run(name,check=True,**combo)['valid']:
                return combo
        except LookupError:
            pass
    return None


def plays_of(snapshot):
    return {ident:(initiator,target) for ident,initiator,target in snapshot.rows('diplomatic_play','diplomatic_play,initiator,target')}


def main(seed=0,budget=50):
    logging.basicConfig(level=logging.WARNING)
    game=GameInterface('actions');store=Store();store.begin_run(kind='attached',started_at=datetime.now(timezone.utc));executor=Executor(game);rng=random.Random(seed)
    started=time.monotonic()
    snapshot=Stored(store.connection,*record(game,store,'manual'))
    options=available(snapshot)
    combo=None
    for name in ('start_play_country','start_play_state'):
        combo=valid(executor,name,options[name],rng)
        if combo:
            break
    print('play',name,combo)
    if combo is None:
        return 1
    before=plays_of(snapshot)
    print(executor.run(name,**combo))
    snapshot=Stored(store.connection,*record(game,store,'manual'))
    started_play=[ident for ident,(initiator,_) in plays_of(snapshot).items() if ident not in before and initiator==snapshot.player]
    print('started',started_play)
    options=available(snapshot)
    for army in options['mobilize']:
        print('mobilize',army,executor.run('mobilize',**army))
    while time.monotonic()-started<budget:
        executor.run('unpause');time.sleep(4);executor.run('pause')
        snapshot=Stored(store.connection,*record(game,store,'manual'))
        if snapshot.wars():
            break
    options=available(snapshot)
    print('date',snapshot.date,'wars',snapshot.wars(),
          'mobilized',[f for f in options['demobilize']])
    for name in ('propose_peace','white_peace','capitulate','toggle_accept_peace','back_down','declare_neutrality','toggle_press_war_goal','make_primary_demand'):
        for combo in options[name]:
            try:
                print(name,combo,executor.run(name,check=True,**combo))
            except LookupError as error:
                print(name,combo,error)
    print(f'{time.monotonic()-started:.1f}s')
    return 0


if __name__=='__main__':
    sys.exit(main(int(sys.argv[1]) if len(sys.argv)>1 else 0))
