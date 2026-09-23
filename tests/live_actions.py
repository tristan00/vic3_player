import logging
import random
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from interface import GameInterface, record
from interface.actions import Executor
from interface.actions.catalogue import BY_NAME, KEYS
from interface.actions.gui import split
from interface.options import available
from interface.options.stored import Stored
from interface.recording.store import Store
from datetime import datetime, timezone
from loop.effects import EFFECTS, FLIPS, queue, verify

EXCLUSIVE=({'research','queue_research','dequeue_research'},{'build','cancel_construction'},{'issue_decree','remove_decree'},
           {'pause_ship_construction','resume_ship_construction'},
           {'pause_construction','resume_construction','pause_all_construction','resume_all_construction'},
           {'set_default_construction_fleet','clear_default_construction_fleet'},{'build_ship','cancel_ship'})


UNSAFE={'declare_bankruptcy','capitulate','abandon_colony','unincorporate','leave_power_bloc','disband_regulars','pause','unpause','set_speed',
        'cancel_queue_item','raise_queue_item','lower_queue_item','first_queue_item','last_queue_item','remove_company','kick_from_power_bloc'}


def objects(action,combo):
    return {(split(param)[1],combo[split(param)[0]]) for param in action.params if split(param)[1] not in {*KEYS,'int','choice','event'} and split(param)[0] in combo}


def verdict(executor,name,combo):
    try:
        return executor.run(name,check=True,**combo)
    except LookupError:
        return None


def pick(executor,name,combos,rng,tries,used):
    candidates=[combo for combo in combos if not objects(BY_NAME[name],combo)&used]
    for combo in rng.sample(candidates,min(tries,len(candidates))):
        result=verdict(executor,name,combo)
        if result and result['valid']:
            return combo
    return None


def queue_sequence(game,store,executor,rng):
    snapshot=Stored(store.connection,*record(game,store,'manual'))
    builds=available(snapshot)['build']
    added=0
    for combo in rng.sample(builds,len(builds)):
        if added==2:
            break
        if (verdict(executor,'build',combo) or {}).get('valid'):
            executor.run('build',**combo);added+=1
    first=Stored(store.connection,*record(game,store,'manual'))
    executor.run('lower_queue_item',index=0)
    second=Stored(store.connection,*record(game,store,'manual'))
    executor.run('cancel_queue_item',index=0)
    third=Stored(store.connection,*record(game,store,'manual'))
    results={'lower_queue_item':queue(second)[:2]==queue(first)[:2][::-1],'cancel_queue_item':queue(third)==queue(second)[1:]}
    for name,ok in results.items():
        print(f'{name:32s} {"OK  " if ok else "FAIL"}')
    return sum(not ok for ok in results.values())


def main(seed=0,tries=6,budget=45):
    logging.basicConfig(level=logging.WARNING)
    game=GameInterface('actions');store=Store();store.begin_run(kind='attached',started_at=datetime.now(timezone.utc));rng=random.Random(seed)
    started=time.monotonic()
    before=Stored(store.connection,*record(game,store,'manual'))
    options=available(before)
    executor=Executor(game)
    chosen={};used=set();missing=[]
    names=[name for name in (*EFFECTS,*sorted(FLIPS)) if name not in UNSAFE]
    rng.shuffle(names)
    for name in names:
        if time.monotonic()-started>budget:
            missing.append(name)
            continue
        if any(name in group and group&set(chosen) for group in EXCLUSIVE):
            missing.append(name)
            continue
        combo=pick(executor,name,options[name],rng,tries,used)
        if combo is None:
            missing.append(name)
            continue
        used|=objects(BY_NAME[name],combo)
        chosen[name]=(combo,executor.run(name,**combo))
    executor.run('unpause');time.sleep(2);executor.run('pause')
    after=Stored(store.connection,*record(game,store,'manual'))
    failures=0;unverified=[]
    for name,(combo,result) in chosen.items():
        ok=verify(name,combo,before,after,result,executor)
        if ok is None:
            unverified.append(name)
            continue
        failures+=not ok
        print(f'{name:32s} {"OK  " if ok else "FAIL"} {"db  " if name in EFFECTS else "flip"} {combo}')
    print('executed without an observable effect:',unverified)
    failures+=queue_sequence(game,store,executor,rng)
    print(f'{len(chosen)+2} executed, {failures} failed, {len(missing)} without a valid option: {sorted(missing)}')
    print(f'{time.monotonic()-started:.1f}s')
    return failures


if __name__=='__main__':
    sys.exit(main(int(sys.argv[1]) if len(sys.argv)>1 else 0))
