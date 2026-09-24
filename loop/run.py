import argparse
from datetime import datetime, timezone
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
import json
import logging
import os
import psycopg
import random
import shutil
import threading
import time

from advisors import ADVISORS
from interface import GameInterface, generate, record
from interface.actions import Executor
from interface.actions.catalogue import BY_NAME, GROUP
from interface.common import DEFAULT_DATA, STALL_LIMIT, GameCrashed, progress, progress_age, timed
from interface.recording.store import DSN, Store
from interface.runner.screen import shot
from interface.options import available
from interface.options.stored import Stored
from loop.effects import verify

LOG=logging.getLogger('loop')


from interface.options.available import FASTEST_SPEED as FASTEST
SETTLE=.25
SETTLE_LIMIT=3
TICK_LIMIT=5
NO_OBJECT_STREAK=5
STUCK_SNAPSHOTS=2
ACTIONS_PER_PAUSE=(6,16)
ENDS_PAUSE={'capitulate','back_down','white_peace','declare_bankruptcy','leave_power_bloc'}
PARKED=set()
RUN_DAYS=(10,90)
WORLD_STATES=(80,150)
PROPOSAL_ANSWERS=(('accept_treaty','decline_treaty'),('accept_demand','reject_demand'),('accept_action_proposal','decline_action_proposal'),('accept_sway','reject_sway'))
WEIGHTS={'cancel_enactment':.1,'nationalize':.1,'bulk_nationalize_state':.1,'build':3,'research':3,'enact_law':2,'switch_production_method':3,'bulk_switch_production_method_state':3,'deploy_to_front':5,'set_strategic_objective':3,'start_play_country':.1,'start_play_state':.1,'mobilize':5,'mobilize_all':5,'raise_conscripts':3,'demobilize':.2,'demobilize_all':.2,'cancel_construction':.1,'cancel_queue_item':.1,'downsize':.1,'pause_construction':.1,'dequeue_research':.1,'pause_all_construction':.05}
UNVERIFIED_WEIGHT=10
NAVY_WEIGHT=3
HOURS_PER_DAY=24
MAX_TECH=1.5
HOURS_PER_YEAR=365*HOURS_PER_DAY


class Defeated(Exception):
    pass


class Stuck(Exception):
    pass


SLOTS={'queue':('raise_queue_item','lower_queue_item','first_queue_item','last_queue_item','cancel_construction','cancel_queue_item','declare_bankruptcy','disband_formation','disband_regulars','disband_conscripts'),
       'authority':('toggle_bolster_movement','toggle_suppress_movement','issue_decree','toggle_monopoly','toggle_charter','toggle_consumption_tax',
                    'set_government_wages','character_interaction'),
       'pausing':('pause_all_construction','resume_all_construction','pause_ship_construction','resume_ship_construction','declare_bankruptcy'),
       'bureaucracy':('set_tax_level','set_institution_level'),
       'money':('nationalize','bulk_nationalize_state','declare_bankruptcy'),
       'companies':('create_company','remove_company'),
       'decisions':('take_decision','toggle_ignore_decision'),
       'retrofit':('retrofit_fleet','cancel_retrofit_fleet','retrofit_all','cancel_retrofit_all','decommission_ship','disband_formation',
                   'build_ship','build_ship_for','cancel_ship','raise_ship_item','lower_ship_item','first_ship_item','last_ship_item','cancel_ship_item',
                   'start_naval_mission','start_naval_mission_selected'),
       'influence':('diplomatic_action','diplomatic_action_state','diplomatic_action_obligation','request_join_power_bloc'),
       'research':('research','queue_research','dequeue_research'),
       'imposition':('impose_law',),
       'play':('start_play_country','start_play_state','start_play_confirmed','abandon_colony'),
       'bloc':('form_power_bloc','leave_power_bloc','request_join_power_bloc','kick_from_power_bloc','pick_principle','upgrade_principle'),
       'enactment':('enact_law','cancel_enactment','negotiate','reform_government'),
       'commanders':('hire_commander','hire_commander_for','unassign_commander'),
       'army_state':('raise_conscripts','raise_conscripts_selected','mobilize','mobilize_all','mobilize_selected','demobilize','demobilize_all','demobilize_selected','station_formation','rehome_formation','back_down','capitulate','disband_formation','disband_regulars',
                     'deploy_to_front','deploy_selected_to_front','defend_invasion'),
       'map_list':('create_army','station_formation','rehome_formation','deploy_to_front','set_strategic_objective','recruit_from_formation','activate_conscription_center'),
       'shipbuilding':('build_ship','build_ship_for','cancel_ship','pause_ship_construction','resume_ship_construction','raise_ship_item',
                       'lower_ship_item','first_ship_item','last_ship_item','cancel_ship_item','declare_bankruptcy','decommission_ship','disband_formation'),
       'templates':('design_ship_template','edit_ship_template','set_default_ship_template','set_fleet_ship_template','delete_ship_template')}


def targets(name,params,links={}):
    kinds=dict(spec.partition(':')[::2] if ':' in spec else (spec,spec) for spec in BY_NAME[name].params)
    objects={(kinds[key],value) for key,value in params.items() if kinds.get(key) not in (None,'int','choice')}
    objects|={links[item] for item in objects if item in links}
    return (objects or {('group',GROUP[name])})|{('shared',slot) for slot,names in SLOTS.items() if name in names}


@timed
def unverified_actions():
    with psycopg.connect(DSN) as connection:
        return {name for name, in connection.execute('select action from action_verification where not verified_by_standard')}


def game_hours(snapshot):
    return snapshot.hours


class Loop:
    def __init__(self,game,advisors,rng,run,journal=None,context=None):
        self.game=game
        self.context=context or {}
        self.advisors=advisors
        self.rng=rng
        self.store=Store()
        self.store.catalogue([name for name in BY_NAME if GROUP[name]!='time'])
        self.executor=Executor(game)
        self.process=game.reader().process
        self.watching=self.process.watch(self.crashed)
        self.journal=journal or DEFAULT_DATA/'loop'/f'{time.strftime("%Y%m%dT%H%M%S")}.jsonl'
        self.journal.parent.mkdir(parents=True,exist_ok=True)
        self.attached=run['kind']=='attached'
        loop={} if self.attached else {'journal':self.journal.name,'advisors':[advisor.name for advisor in advisors]}
        self.store.begin_run(started_at=datetime.now(timezone.utc),**run,**loop)
        self.counts={}
        self.misses=0
        self.dirty=0
        self.turn=0
        self.seq=0

    def entry(self,source,name,params,snapshot):
        self.seq+=1
        return {'turn':self.turn,'seq':self.seq,'advisor':source,'action':name,'params':params,'snapshot':snapshot.seq,'date':snapshot.date}

    def note(self,entry,after=None):
        self.counts[entry['status']]=self.counts.get(entry['status'],0)+1
        self.store.log_action(entry,after.seq if after else None)
        entry={**self.context,**entry,'after':after.seq if after else None}
        with open(self.journal,'a',encoding='utf-8') as handle:
            handle.write(json.dumps(entry,ensure_ascii=False)+'\n')
        if entry['status'] not in ('verified','unverified'):
            LOG.warning('%s %s %s %s',entry['status'],entry['action'],entry['params'],entry.get('detail',''))

    def capture(self,name):
        screens=DEFAULT_DATA/'screens'
        screens.mkdir(parents=True,exist_ok=True)
        shot(screens/f'{self.journal.stem}_{name}.png')

    def snapshot(self,phase):
        try:
            return Stored(self.store.connection,*record(self.game,self.store,'manual' if self.attached else phase))
        except RuntimeError as error:
            if 'no longer owns any state' in str(error):
                raise Defeated() from error
            raise

    @timed
    def perform(self,source,name,params,snapshot,pending,raced=None):
        entry=self.entry(source,name,params,snapshot)
        LOG.info('action %s %s %s',entry['seq'],name,params)
        try:
            result=self.executor.run(name,**params)
        except LookupError as error:
            if dead(self.game.reader()):
                raise Defeated() from error
            self.note({**entry,'status':'no_object','detail':str(error)})
            self.capture(f'{entry["seq"]}_{name}')
            self.misses+=1
            if self.misses>=NO_OBJECT_STREAK:
                raise RuntimeError(f'{self.misses} actions in a row found no game object; the executor or GUI is not responding') from error
            return
        self.misses=0
        entry['ms']=result['ms']
        if not result['valid']:
            self.note({**entry,'status':'raced' if raced and result['desc']==raced else 'invalid','detail':result['desc']})
            return
        pending.append((entry,snapshot,result))

    @timed
    def turn_actions(self,snapshot,carried):
        batch=[]
        touched=set()
        options=available(snapshot)
        events=options['choose_event_option']
        for event in sorted({combo['event'] for combo in events}):
            name,params=self.advisors[0].choose({'choose_event_option':[combo for combo in events if combo['event']==event]},snapshot)
            touched|=targets(name,params)
            self.perform(self.advisors[0].name,name,params,snapshot,batch)
        if batch:
            snapshot=self.snapshot('post_action')
            options=available(snapshot)
        options={name:combos for name,combos in options.items() if name not in PARKED and name!='choose_event_option'}
        links={**{('building',ident):('building_type',kind) for ident,kind,_ in snapshot.buildings()},
               **{('character',ident):('military_formation',formation) for ident,formation in snapshot.rows('character','character,formation',country=snapshot.player) if formation},
               **{('war',war):('diplomatic_play',play) for play,war in snapshot.rows('diplomatic_play','diplomatic_play,war') if war is not None},
               **{('ship',ship):('military_formation',fleet) for ship,fleet in snapshot.rows('ship','ship,fleet') if fleet is not None}}
        answers={name:options.pop(name,[]) for pair in PROPOSAL_ANSWERS for name in pair}
        quick=options.pop('quick_decline_proposal',[])
        for pair in PROPOSAL_ANSWERS:
            for combo in sorted({tuple(combo.items()) for name in pair for combo in answers[name]}):
                choices={name:[dict(combo)] for name in pair if dict(combo) in answers[name]}
                name,params=self.advisors[0].choose({**choices,**({'quick_decline_proposal':[dict(combo)]} if dict(combo) in quick else {})},snapshot)
                self.perform(self.advisors[0].name,name,params,snapshot,batch)
        for _ in range(self.rng.randint(*ACTIONS_PER_PAUSE)):
            advisor=self.rng.choice(self.advisors)
            pick=advisor.choose({name:[combo for combo in combos if not targets(name,combo,links)&touched] for name,combos in options.items()},snapshot)
            if pick is None:
                break
            touched|=targets(*pick,links)
            self.perform(advisor.name,*pick,snapshot,batch)
            if pick[0] in ENDS_PAUSE:
                break
        if not batch and not carried:
            return snapshot,[]
        after=self.snapshot('post_action')
        left=self.open_ui(after)
        if left:
            for entry,_,_ in batch:
                self.note({**entry,'status':'ui_leftover','detail':f'{"+".join(left)} open after the pause: {" ".join(item["action"] for item,_,_ in batch)}'},after)
            batch=[]
            self.stuck(left)
        later=[]
        for entry,before,result in carried+batch:
            verdict=verify(entry['action'],entry['params'],before,after)
            if verdict is False:
                later.append((entry,before,result))
            else:
                self.note({**entry,'status':'verified' if verdict else 'unverified'},after)
        return after,later

    def open_ui(self,snapshot):
        meta=snapshot.meta
        left=sorted({name for name in ('panel','interaction','map_list') if meta[f'ui_{name}_open']}|{window for window, in snapshot.rows('ui_open_window','ui_window')})
        self.dirty=self.dirty+1 if left else 0
        if left:
            self.capture(f'ui_{snapshot.seq}')
        return left

    def stuck(self,left):
        if self.dirty>=STUCK_SNAPSHOTS:
            LOG.error('%s stayed open for %s snapshots in a row; ending the round',"+".join(left),self.dirty)
            raise Stuck()

    @timed
    def run_days(self,snapshot):
        days=self.rng.randint(*RUN_DAYS)
        entry=self.entry('loop','run_days',{'days':days},snapshot)
        started=time.monotonic()
        reader=self.game.reader()
        target=reader.date()[0]+days*HOURS_PER_DAY
        pending=[]
        if self.turn==1:
            self.perform('loop','set_speed',{'speed':FASTEST},snapshot,pending)
        self.perform('loop','unpause',{},snapshot,pending,raced='running')
        hours=reader.date()[0]
        moved=time.monotonic()
        longest_gap=0
        while reader.date()[0]<target:
            if dead(reader):
                raise Defeated()
            if reader.date()[0]!=hours:
                longest_gap=max(longest_gap,time.monotonic()-moved)
                hours,moved=reader.date()[0],time.monotonic()
            elif time.monotonic()-moved>TICK_LIMIT:
                reader.check()
                raise RuntimeError(f'The game date stopped at {reader.date()[1]} for {TICK_LIMIT} s after unpausing; '
                                   f'the longest earlier gap between ticks was {longest_gap*1000:.0f} ms')
            progress('run_days')
            time.sleep(.02)
        paused=[]
        if running(reader):
            self.perform('loop','pause',{},snapshot,paused,raced='paused')
            settle(reader)
        after=self.snapshot('post_run')
        left=self.open_ui(after)
        if left:
            detail=f'{"+".join(left)} open after running days'
            for item,_,_ in pending+[(item,None,None) for item,_,_ in paused]:
                self.note({**item,'status':'ui_leftover','detail':detail},after)
            self.note({**entry,'ms':round((time.monotonic()-started)*1000),'status':'ui_leftover','detail':detail},after)
            self.stuck(left)
            return after,[],[]
        reached=game_hours(after)
        self.note({**entry,'ms':round((time.monotonic()-started)*1000),'status':'verified' if reached>=target else 'no_effect',
                   'detail':f'{(reached-target)/HOURS_PER_DAY:+.1f} days past the target, longest tick gap {longest_gap*1000:.0f} ms'},after)
        return after,[(entry,after,result) for entry,_,result in paused],pending

    def crashed(self):
        noticed=datetime.now(timezone.utc)
        LOG.error('GAME CRASHED: process %s is gone, noticed at %s UTC by the watcher',self.process.pid,noticed.strftime('%H:%M:%S.%f'))
        try:
            self.store.flag_game_exit(None)
        except Exception:
            LOG.exception('The game exit could not be written to the run row')
        exited_at=self.exit_time()
        if exited_at is None:
            LOG.critical('GAME UNREADABLE: process %s stopped answering memory reads but has not exited within %d ms',self.process.pid,EXIT_GRACE_MS)
            return
        latency=round((noticed-exited_at).total_seconds()*1000)
        LOG.error('GAME CRASHED: process %s exited at %s UTC per the OS, noticed %d ms after that',self.process.pid,exited_at.strftime('%H:%M:%S.%f'),latency)
        if latency>LATE_FLAG_MS:
            LOG.critical('LATE FLAG: %d ms between the game exit and the flag; the limit is %d ms',latency,LATE_FLAG_MS)
        try:
            self.store.flag_game_exit(exited_at)
        except Exception:
            LOG.exception('The game exit time could not be written to the run row')

    def exit_time(self):
        return self.process.exit_time() if self.process.exits_within(EXIT_GRACE_MS) else None

    def end(self,reason,detail=None,game_exited_at=None):
        self.watching.set()
        self.counts['end']=reason
        self.store.end_run(reason,detail,game_exited_at)
        return self.counts

    @timed
    def run(self,years,seconds):
        try:
            return self.play(years,seconds)
        except Defeated:
            return self.end('defeated')
        except Stuck:
            return self.end('ui_stuck')
        except BaseException as error:
            reacted=datetime.now(timezone.utc)
            if not isinstance(error,GameCrashed) and not self.process.gone() and not self.process.exits_within(EXIT_GRACE_MS):
                LOG.error('LOOP CRASHED: %s: %s',type(error).__name__,error)
                self.end('loop_crashed',f'{type(error).__name__}: {error}'[:500])
                raise
            exited_at=self.exit_time()
            LOG.error('GAME CRASHED: %s; the loop stopped at %s UTC, %s ms after the exit the OS reports',error,reacted.strftime('%H:%M:%S.%f'),
                      None if exited_at is None else round((reacted-exited_at).total_seconds()*1000))
            self.end('game_crashed',str(error)[:500],exited_at)
            if isinstance(error,GameCrashed):
                raise
            raise GameCrashed(f'The game process {self.process.pid} died while the loop hit {type(error).__name__}: {error}') from error

    def play(self,years,seconds):
        deadline=time.monotonic()+seconds
        self.executor.run('pause')
        snapshot=self.snapshot('start')
        left=self.open_ui(snapshot)
        if left:
            raise RuntimeError(f'The round starts with {"+".join(left)} open')
        start=game_hours(snapshot)
        carried=[]
        while True:
            if time.monotonic()>deadline:
                return self.end('time')
            if game_hours(snapshot)-start>=years*HOURS_PER_YEAR:
                return self.end('years')
            self.turn+=1
            snapshot,later=self.turn_actions(snapshot,carried)
            snapshot,carried,pending=self.run_days(snapshot)
            for entry,before,result in later+pending:
                verdict=verify(entry['action'],entry['params'],before,snapshot)
                self.note({**entry,'status':'verified' if verdict else 'no_effect' if verdict is False else 'unverified'},snapshot)


def build(seed,countries,states,tech,pop):
    return generate(seed,countries,states,tech,pop)


def world_size(rng,levels):
    states=rng.randint(*WORLD_STATES)
    tech,pop=levels
    return (rng.randrange(10**9),rng.randint(states//6,states//3),states,
            round(rng.uniform(0,MAX_TECH),2) if tech is None else tech,round(rng.uniform(0,1),2) if pop is None else pop)


class WorldPool:
    def __init__(self,rng,workers,levels):
        self.rng=rng
        self.levels=levels
        self.executor=ProcessPoolExecutor(workers)
        self.pending={self.submit() for _ in range(workers)}

    def submit(self):
        return self.executor.submit(build,*world_size(self.rng,self.levels))

    @timed
    def take(self):
        while not (done:=wait(self.pending,timeout=1,return_when=FIRST_COMPLETED)[0]):
            progress('world generation')
        self.pending-=done
        finished=done.pop()
        self.pending|=done|{self.submit()}
        return finished.result()


WATCH=.1
STALLED_EXIT=3


class Watchdog:
    def __init__(self,game):
        self.game=game
        self.store=None

    def start(self):
        threading.Thread(target=self.watch,daemon=True,name='watchdog').start()

    def watch(self):
        while True:
            time.sleep(WATCH)
            step,age=progress_age()
            if age>STALL_LIMIT:
                self.trip(step,age)
                os._exit(STALLED_EXIT)

    def trip(self,step,age):
        LOG.critical('LOOP STALLED: %s made no progress for %.1f s; the limit is %d s',step,age,STALL_LIMIT)
        try:
            if self.store is not None and self.store.run_id is not None:
                self.store.flag_stalled(step,age)
        except Exception:
            LOG.exception('The stall could not be written to the run row')
        self.game.close()


RUNNING_PROBE=1
DEATH_READS=3
DEATH_READ_GAP=.2
LATE_FLAG_MS=1000
EXIT_GRACE_MS=1000
CRASHES_IN_A_ROW=3


def dead(reader):
    started=time.monotonic()
    for _ in range(DEATH_READS):
        if reader.alive():
            return False
        time.sleep(DEATH_READ_GAP)
    LOG.error('DEFEATED: the played country owned no state in %d reads over %.0f ms',DEATH_READS,(time.monotonic()-started)*1000)
    return True


@timed
def settle(reader):
    deadline=time.monotonic()+SETTLE_LIMIT
    hours,steady=reader.date()[0],time.monotonic()
    while time.monotonic()-steady<SETTLE:
        if time.monotonic()>deadline:
            raise RuntimeError(f'The game date kept moving {SETTLE_LIMIT} s after pausing')
        time.sleep(.02)
        if reader.date()[0]!=hours:
            hours,steady=reader.date()[0],time.monotonic()


def running(reader):
    hours=reader.date()[0]
    deadline=time.monotonic()+RUNNING_PROBE
    while time.monotonic()<deadline:
        if reader.date()[0]!=hours:
            return True
        time.sleep(.05)
    return False


class Fresh:
    def __init__(self,rng,levels):
        self.rng=rng
        self.levels=levels

    @timed
    def take(self):
        with ThreadPoolExecutor(1) as executor:
            future=executor.submit(build,*world_size(self.rng,self.levels))
            while not wait([future],timeout=1)[0]:
                progress('world generation')
        return future.result()


class Vanilla:
    def __init__(self,rng):
        self.rng=rng

    def take(self):
        return None


TOP_PRESTIGE=('GBR','CHI','FRA','RUS','BIC','PRU','AUS','TUR','USA','EGY','JAP','NET','SWE','PAN','SPA','BRZ','SIA','SIC','PER','POR')


RECENT_ROUNDS=5
MIN_SESSION_SECONDS=240


def recent_tags():
    rounds=[]
    for path in sorted((DEFAULT_DATA/'loop').glob('*.jsonl'),reverse=True):
        with open(path,encoding='utf-8') as handle:
            line=handle.readline()
        if line:
            rounds.append(json.loads(line)['tag'])
        if len(rounds)==RECENT_ROUNDS:
            break
    return rounds


@timed
def session(game,watchdog,rng,worlds,advisors,arguments,chosen,seconds):
    world=worlds.take()
    recent=recent_tags()
    if chosen in recent:
        raise ValueError(f'{chosen} was played in one of the last {RECENT_ROUNDS} rounds: {recent}')
    countries=[country for country in json.loads(world.read_text(encoding='utf-8'))['countries'] if country['country_type']!='decentralized'] if world else []
    tag=chosen or (rng.choices([country['tag'] for country in countries],weights=[NAVY_WEIGHT if country['navy'] else 1 for country in countries])[0] if world else
                   rng.choice([tag for tag in TOP_PRESTIGE if tag not in recent]))
    game.close()
    game.campaign(tag,world=str(world) if world else None,debug=False)
    seed=rng.randrange(10**9)
    name=world.parent.name if world else 'vanilla'
    loop=Loop(game,advisors,random.Random(seed),run_record(arguments,'vanilla' if world is None else 'mini',name,tag,seed),
              context={'world':name,'tag':tag})
    watchdog.store=loop.store
    counts=loop.run(arguments.years,seconds)
    if isinstance(worlds,(WorldPool,Fresh)):
        game.close()
        shutil.rmtree(world.parent)
    return counts,loop.journal


def run_record(arguments,kind,world,tag,seed):
    if kind=='attached':
        return {'kind':kind}
    return {'kind':kind,'world':world,'tag':tag,'cli_seed':arguments.seed,'run_seed':seed,
            'years':arguments.years,'minutes':arguments.minutes,'profile':arguments.profile,'pool':arguments.pool}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--profile',default='actions')
    parser.add_argument('--advisors',nargs='+',default=['random'])
    parser.add_argument('--years',type=float,default=20)
    parser.add_argument('--minutes',type=float,default=10)
    parser.add_argument('--seed',type=int,default=int(time.strftime('%Y%m%d%H%M%S')))
    parser.add_argument('--attach',action='store_true')
    parser.add_argument('--pool',type=int,default=0)
    parser.add_argument('--vanilla',action='store_true')
    parser.add_argument('--tag')
    parser.add_argument('--weight',nargs='+',default=[])
    parser.add_argument('--tech',type=float)
    parser.add_argument('--pop',type=float)
    arguments=parser.parse_args()
    if arguments.vanilla and (arguments.tech is not None or arguments.pop is not None):
        parser.error('--tech and --pop only apply to generated mini worlds')
    levels=(arguments.tech,arguments.pop)
    logging.basicConfig(level=logging.WARNING,format='%(asctime)s %(message)s')
    logging.getLogger('interface').setLevel(logging.INFO)
    logging.getLogger('loop').setLevel(logging.INFO)
    game=GameInterface(arguments.profile)
    watchdog=Watchdog(game)
    watchdog.start()
    rng=random.Random(arguments.seed)
    weights={**WEIGHTS,**{name:UNVERIFIED_WEIGHT for name in unverified_actions()},**{name:float(value) for name,_,value in (item.partition('=') for item in arguments.weight)}}
    advisors=[ADVISORS[name](rng.randrange(10**9),weights) for name in arguments.advisors]
    if arguments.attach:
        seed=rng.randrange(10**9)
        loop=Loop(game,advisors,random.Random(seed),run_record(arguments,'attached',None,None,seed))
        watchdog.store=loop.store
        print(json.dumps(loop.run(arguments.years,arguments.minutes*60)),loop.journal)
        return
    worlds=Vanilla(rng) if arguments.vanilla else WorldPool(rng,arguments.pool,levels) if arguments.pool else Fresh(rng,levels)
    deadline=time.monotonic()+arguments.minutes*60
    chosen=arguments.tag
    crashes=0
    while (remaining:=deadline-time.monotonic())>=MIN_SESSION_SECONDS:
        try:
            counts,journal=session(game,watchdog,rng,worlds,advisors,arguments,chosen,remaining)
        except GameCrashed as error:
            crashes+=1
            LOG.error('GAME CRASHED (%d in a row): %s',crashes,error)
            game.close()
            if crashes>=CRASHES_IN_A_ROW:
                raise
            print(json.dumps({'end':'game_crashed','crashes_in_a_row':crashes}),flush=True)
            continue
        except BaseException:
            game.close()
            raise
        chosen=None
        crashes=0
        print(json.dumps(counts),journal,flush=True)


if __name__=='__main__':
    main()
