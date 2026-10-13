import argparse, json, logging, math, msvcrt, random, sys, time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
import psutil, psycopg
from advisors.catalogue import NAMES
from advisors.initializers import ADVISORS
from advisors.pickers import PICKERS
from advisors.data.rewards import draw_objective
from interface import GameInterface, record
from interface.actions import Executor
from interface.common import DEFAULT_DATA, Defeated, GameCrashed, evidence, timed, write_json
from interface.options.available import FASTEST_SPEED, RULES, committed_plays, live_wars
from interface.options.effects import LATER, took_effect, took_effect_later
from interface.options.stored import Shared, Stored
from interface.recording.store import Store, DSN
from interface.timing import RECORDER, span
from interface.runner.session import _spawn, process as owner
from interface.world.bank import take
from interface.world.sampling import SLIDERS, PER_COUNTRY
from loop.sampling import batches, block_length

STATE=DEFAULT_DATA/'collection.json'
DEFAULTS=dict(profile='actions',world_cache=[],runs=1,warmup=0,years=100.,minutes=30.,seed=int(time.time()),advisors=['random'],pickers=['first'])

@contextmanager
def state():
    STATE.parent.mkdir(parents=True,exist_ok=True)
    with open(STATE.with_suffix('.lock'),'a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_LOCK,1)
        original=STATE.read_text(encoding='utf-8') if STATE.exists() else '{}'
        data=json.loads(original)
        yield data
        if data!=json.loads(original):
            write_json(STATE.with_suffix('.tmp'),data)
            STATE.with_suffix('.tmp').replace(STATE)

@timed
def launch(data):
    process=_spawn([sys.executable,'-m','loop.run','_work'],Path(__file__).resolve().parents[1])
    data.update(pid=process.pid,created=process.create_time(),active=data['settings'],phase='starting',stop=False,restart=False,error=None,run_id=None,snapshot=None,game_hours=None)


@timed
def redraw(connection,run_id,seq,count,seed,weights=None,snapshot=None):
    snapshot=Stored(connection,run_id,seq) if snapshot is None else snapshot
    advisor=ADVISORS['random'](seed)
    advisor.weights=weights if weights is not None else dict(connection.execute(
        'select a.name,w.weight from run_weight w join advisor_action a using(advisor_action) where w.run_id=%s',(run_id,)))
    return snapshot,[[(name,params) for name,params,_ in block] for block in batches(snapshot,advisor,count)]


@timed
def mobilization(snapshot,fought):
    hostile={('play',play) for play in committed_plays(snapshot)}|{('war',war) for war in live_wars(snapshot)}
    forced=[('mobilize_all',{})] if hostile-fought and RULES['mobilize_all'](snapshot) else []
    return forced,hostile if forced else fought&hostile


@timed
def play(game,store,advisor,picker,settings):
    executor=Executor(game)
    shared=Shared(store.connection)
    def capture(phase):
        snapshot=Stored(store.connection,*record(game,store,phase),shared)
        with state() as data: data.update(run_id=store.run_id,snapshot=snapshot.seq,step=phase,game_hours=snapshot.hours)
        return snapshot
    try:
        executor.run('pause')
        snapshot=capture('start')
        start,deadline=snapshot.hours,time.monotonic()+settings['minutes']*60
        seq,turn,dirty,late,fought=0,0,0,[],set()
        while time.monotonic()<deadline and snapshot.hours-start<settings['years']*8760:
            treasury=snapshot.rows('player_treasury','principal,credit')
            if treasury and 0<treasury[0][0]>=treasury[0][1]: return 'debt_cap'
            turn+=1
            snapshot.load()
            forced,fought=mobilization(snapshot,fought)
            length=block_length(advisor.random) if picker.name=='catboost_piecewise' else None
            drawn=batches(snapshot,advisor,1 if picker.name=='first' else 100,length,forced)
            chosen,predictions=picker.pick([[(n,p) for n,p,_ in b] for b in drawn],snapshot)
            if predictions is not None:
                store.record_pick(snapshot.seq,[[n for n,_,_ in b] for b in drawn],predictions,chosen)
            for phase in ('post_action','post_run'):
                if phase=='post_run': forced,fought=mobilization(snapshot,fought)
                block=[(None,None,command) for command in forced]+(drawn[chosen] if phase=='post_action' else [(None,None,('set_speed',{'speed':FASTEST_SPEED})),(None,None,('unpause',{}))])
                pending=[]
                for decision,params,(name,arguments) in block:
                    if name=='set_speed' and snapshot.meta['speed']==int(arguments['speed']): continue
                    seq+=1
                    entry=dict(seq=seq,turn=turn,advisor=advisor.name if decision else 'loop',action=name,params=arguments,
                               snapshot=snapshot.seq,decision=(decision,params) if decision else None,status='done',unverified=False)
                    try:
                        result=executor.run(name,**arguments)
                        entry.update(ms=result['ms'],status='done' if result['valid'] else 'invalid',detail=result['desc'] or None)
                    except LookupError as error:
                        entry.update(status='no_object',detail=str(error))
                    pending.append(entry)
                if phase=='post_run':
                    reader=game.reader()
                    year,day=divmod(snapshot.hours//24,365)
                    target=(year*365+next(d for d in (90,181,273,365) if d>day))*24
                    with span('loop.run.wait_quarter','loop'):
                        hours,moved=reader.date()[0],time.monotonic()
                        while (current:=reader.date()[0])<target:
                            if not reader.alive(): return 'defeated'
                            if current!=hours:
                                hours,moved=current,time.monotonic()
                            if time.monotonic()-moved>5:
                                raise TimeoutError(evidence(hours=hours,target=target,stalled=time.monotonic()-moved))
                            time.sleep(.02)
                        time.sleep(.25)
                after=capture(phase)
                if phase=='post_run' and not target<=after.hours<target+24:
                    raise RuntimeError(evidence(target=target,hours=after.hours))
                open_ui=any(after.meta['ui_'+name+'_open'] for name in ('panel','interaction','map_list')) or bool(after.rows('ui_open_window','ui_window'))
                for entry in pending:
                    entry['unverified']=entry['status']=='done' and not took_effect(entry['action'],snapshot,after,entry['params'])
                    if open_ui and entry['status']=='done': entry.update(status='ui_leftover')
                    store.log_action(entry,after.seq)
                    if entry['unverified'] and entry['action'] in LATER:
                        late.append((entry,snapshot))
                for entry,before in late:
                    if took_effect_later(entry['action'],before,after,entry['params']):
                        store.verify_action(entry['seq'])
                if phase=='post_run': late=[]
                snapshot=after
                dirty=dirty+1 if open_ui else 0
                if dirty>=2: return 'ui_stuck'
        return 'time' if time.monotonic()>=deadline else 'years'
    finally:
        shared.close()

@timed
def collect(settings,completed):
    RECORDER.reset()
    rng=random.Random(settings['seed']+completed)
    world=take(settings['world_cache'],rng)
    manifest=json.loads(world.read_text(encoding='utf-8'))
    country=rng.choice([c for c in manifest['countries'] if c['country_type']!='decentralized'])
    objective=draw_objective(rng)
    advisor=ADVISORS[rng.choice(['random'] if completed<settings['warmup'] else settings['advisors'])](rng.randrange(10**9))
    picker=PICKERS[rng.choice(['first'] if completed<settings['warmup'] else settings['pickers'])]()
    game=GameInterface(settings['profile'])
    store=Store()
    try:
        advisor.start_run(store,NAMES,objective)
        with ThreadPoolExecutor(1) as preparing:
            training=preparing.submit(picker.start_run,store,objective)
            game.campaign(country['tag'],world,lock=state)
            Executor(game).run('pause')
            training.result()
        generated=dict(seed=manifest['seed'],countries=len(manifest['countries']),states=len(manifest['states']),pop=1,diversity=None,
                       **{n:country[n] if n in PER_COUNTRY else manifest[n] for n in SLIDERS if n in (country if n in PER_COUNTRY else manifest)})
        store.begin_run(started_at=datetime.now(timezone.utc),kind='mini',advisors=[advisor.name],tag=country['tag'],world=world.parent.name,
                        cli_seed=settings['seed'],run_seed=settings['seed']+completed,years=settings['years'],minutes=settings['minutes'],
                        profile=settings['profile'],pool=0,runs_requested=settings['runs'],generated=generated,weights=advisor.weights,
                        centres=advisor.used,picker=picker.name,candidates=1 if picker.name=='first' else 100,objective=objective,
                        proposal=advisor.proposal,pick_model=picker.trained)
        reason=play(game,store,advisor,picker,settings)
        store.world_reports(world)
        store.end_run(reason)
    except BaseException as error:
        defeated=isinstance(error,Defeated)
        store.end_run('defeated' if defeated else 'game_crashed' if isinstance(error,GameCrashed) else 'loop_crashed',None if defeated else str(error)[:500])
        if not defeated: raise
    finally:
        try:
            game.close()
        finally:
            store.connection.close()

@timed
def work():
    try:
        while True:
            with state() as data:
                if owner(data)!=psutil.Process(): raise RuntimeError(evidence(owner=owner(data),process=psutil.Process()))
                if data['stop']:
                    data['phase']='stopped'
                    return
                if data['restart']:
                    launch(data)
                    return
                if data['completed']>=data['settings']['runs']:
                    data['phase']='completed'
                    return
                settings,completed=data['settings'].copy(),data['completed']
                data.update(active=settings,phase='running',step='preparing',run_id=None,snapshot=None,game_hours=None)
            collect(settings,completed)
            with state() as data: data['completed']+=1
    except BaseException as error:
        with state() as data:
            if owner(data)==psutil.Process():
                data.update(phase='failed',error=f'{type(error).__name__}: {error}')
        logging.exception(evidence())
        raise

def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('command',choices=('start','resume','status','configure','restart','stop','cancel','_work'))
    parser.add_argument('--now',action='store_true')
    parser.add_argument('--completed',type=int)
    for name,value in DEFAULTS.items():
        parser.add_argument('--'+name.replace('_','-'),type=str if isinstance(value,list) else type(value),
                            nargs='+' if isinstance(value,list) else None,default=argparse.SUPPRESS)
    args=vars(parser.parse_args(argv))
    command,now,completed=args.pop('command'),args.pop('now'),args.pop('completed')
    if (args and command not in ('start','resume','configure','restart')) or (now and command!='stop'):
        parser.error(evidence(command=command,settings=sorted(args),now=now))
    if completed is not None and (command!='start' or completed<0): parser.error(evidence(command=command,completed=completed))
    if command=='_work':
        with open(DEFAULT_DATA/'collection.log','a',encoding='utf-8',buffering=1) as log,redirect_stdout(log),redirect_stderr(log):
            logging.basicConfig(level=logging.INFO,stream=log,format='%(asctime)s %(message)s',force=True)
            return work()
    with state() as data:
        running=owner(data)
        if command=='status':
            phase='lost' if not running and data.get('phase') in ('starting','running') else data.get('phase','absent')
            print(json.dumps({**data,'alive':bool(running),'phase':phase},indent=2))
            return
        if not data and command!='start': parser.error(evidence(command=command,path=STATE))
        if running and command in ('start','resume'): parser.error(evidence(command=command,pid=running.pid))
        settings={**(DEFAULTS if command=='start' else data['settings']),**args}
        if command in ('start','resume','configure','restart'):
            if settings['runs']<1 or settings['warmup']<0 or any(not math.isfinite(settings[n]) or settings[n]<=0 for n in ('years','minutes')):
                parser.error(evidence(runs=settings['runs'],warmup=settings['warmup'],years=settings['years'],minutes=settings['minutes']))
            if not settings['profile'] or Path(settings['profile']).name!=settings['profile'] or settings['profile'] in ('.','..'):
                parser.error(evidence(profile=settings['profile']))
            if not set(settings['advisors'])<=ADVISORS.keys() or not set(settings['pickers'])<=PICKERS.keys(): parser.error(evidence(advisors=settings['advisors'],pickers=settings['pickers'],known_advisors=sorted(ADVISORS),known_pickers=sorted(PICKERS)))
            if not settings['world_cache'] or any(not (Path(directory)/'bank.json').is_file() for directory in settings['world_cache']):
                parser.error(evidence(world_cache=settings['world_cache']))
            settings['world_cache']=sorted({str(Path(directory).resolve()) for directory in settings['world_cache']})
            data['settings']=settings
        if command=='cancel': data.update(stop=False,restart=False,settings=data['active'].copy() if running else settings)
        if command in ('stop','restart'): data.update(stop=command=='stop',restart=command=='restart')
        if (not running and command in ('start','resume','restart','stop')) or now:
            if running:
                running.kill()
                running.wait(timeout=10)
            if data.get('active'):
                GameInterface(data['active']['profile']).close()
                with psycopg.connect(DSN) as connection:
                    connection.execute("update run set ended_at=now(),end_reason='loop_lost' where ended_at is null and profile=%s and started_at>=to_timestamp(%s)",(data['active']['profile'],data['created']))
            if command=='start': data['completed']=completed or 0
            if command=='stop': data['phase']='stopped'
            else: launch(data)
    print(json.dumps(data,indent=2),flush=True)

if __name__=='__main__':
    main()
