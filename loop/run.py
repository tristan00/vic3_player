import argparse
from collections import namedtuple
from datetime import datetime, timezone
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
import json
import logging
import os
import random
import shutil
import sys
import threading
import time

from advisors.catalogue import ANSWERS as ANSWER_ACTIONS, LEVER, NAMES, PROPOSALS
from advisors.initializers import ADVISORS, RandomAdvisor
from advisors.pickers import PICKERS
from advisors.data.rewards import draw_objective
from interface import GameInterface, generate, record
from interface.actions import Executor
from interface.actions.catalogue import BY_NAME, GROUP
from interface.common import STALL_LIMIT, GameCrashed, progress, progress_age, timed, timed_often
from interface.recording.store import Store
from interface.timing import RECORDER, current, span
from interface.world.sampling import SLIDERS, SAMPLING, PER_COUNTRY, world_size
from interface.world.cache import Cached
from interface.recording.record import prepare as prepare_recording
from interface.options import available
from interface.options.stored import Shared, Stored
from interface.runner.memory import MONTH_STARTS
from loop import supervise
from loop.diagnostics import clock_failure
from loop.translate import offer

LOG=logging.getLogger('loop')


from interface.options.available import FASTEST_SPEED as FASTEST, event_options
SETTLE=.25
SETTLE_LIMIT=3
TICK_LIMIT=5
NO_OBJECT_STREAK=5
STUCK_SNAPSHOTS=2
ACTIONS_PER_PAUSE=(6,16)
ENDS_PAUSE={'capitulate','back_down','white_peace','declare_bankruptcy','leave_power_bloc'}
EVENT='choose_event_option'
QUICK='quick_decline_proposal'
PROPOSAL_ANSWERS=(('accept_treaty','decline_treaty'),('accept_demand','reject_demand'),('accept_action_proposal','decline_action_proposal'),('accept_sway','reject_sway'))
ANSWERS=(EVENT,QUICK,*(name for pair in PROPOSAL_ANSWERS for name in pair))
HOURS_PER_DAY=24
Decision=namedtuple('Decision','action params command')
CANDIDATES=(8,50)
HOURS_PER_YEAR=365*HOURS_PER_DAY


class Defeated(Exception):
    pass


@timed_often
def ramp(rng,bounds,rising):
    values=range(bounds[0],bounds[1]+1)
    weights=range(1,len(values)+1)
    return rng.choices(values,weights=weights if rising else weights[::-1])[0]


class Stuck(Exception):
    pass


class ClockStalled(RuntimeError):
    pass


SLOTS={'queue':('raise_queue_item','lower_queue_item','first_queue_item','last_queue_item','cancel_construction','cancel_queue_item','declare_bankruptcy','disband_formation','disband_regulars','disband_conscripts'),
       'authority':('toggle_bolster_movement','toggle_suppress_movement','issue_decree','toggle_monopoly','toggle_charter','toggle_consumption_tax',
                    'set_government_wages','character_interaction'),
       'pausing':('pause_all_construction','resume_all_construction','pause_ship_construction','resume_ship_construction','declare_bankruptcy'),
       'bureaucracy':('set_tax_level','set_institution_level','switch_production_method','bulk_switch_production_method_state'),
       'money':('nationalize','bulk_nationalize_state','declare_bankruptcy'),
       'companies':('create_company','remove_company'),
       'decisions':('take_decision','toggle_ignore_decision'),
       'retrofit':('retrofit_fleet','cancel_retrofit_fleet','retrofit_all','cancel_retrofit_all','decommission_ship','disband_formation',
                   'build_ship','build_ship_for','cancel_ship','raise_ship_item','lower_ship_item','first_ship_item','last_ship_item','cancel_ship_item',
                   'start_naval_mission','start_naval_mission_selected'),
       'influence':('diplomatic_action','diplomatic_action_obligation','request_join_power_bloc'),
       'research':('research','queue_research','dequeue_research'),
       'imposition':('impose_law',),
       'play':('start_play_country','start_play_state','start_play_confirmed','abandon_colony'),
       'bloc':('form_power_bloc','leave_power_bloc','request_join_power_bloc','kick_from_power_bloc','pick_principle','upgrade_principle'),
       'enactment':('enact_law','cancel_enactment','negotiate','reform_government','reform_government_party'),
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


@timed_often
def game_hours(snapshot):
    return snapshot.hours


@timed_often
def next_quarter(hours):
    year,day=divmod(hours//HOURS_PER_DAY,365)
    return (year*365+next((start for start in MONTH_STARTS[::3] if start>day),365))*HOURS_PER_DAY


@timed_often
def questions(offered):
    events={}
    for choice in offered.get('answer_event',[]):
        events.setdefault(choice.params['event'],[]).append(('answer_event',choice))
    asked=[events[event] for event in sorted(events)]
    for pair in PROPOSALS:
        for country in sorted({choice.params['country'] for name in pair for choice in offered.get(name,[])}):
            asked.append([(name,choice) for name in pair for choice in offered.get(name,[]) if choice.params['country']==country])
    return asked


@timed_often
def unanswered(entry,events,proposers):
    return entry['params']['event'] in events if entry['action']==EVENT else entry['action'] in ANSWERS and entry['params']['country'] in proposers


class Drawer:
    @timed_often
    def __init__(self,advisor,offered,snapshot,links):
        self.advisor=advisor
        self.seq=snapshot.seq
        self.links=links
        self.names,self.base,self.choices,self.commands,self.targets=[],[],[],[],[]
        self.index={}
        self.questions=questions(offered)
        levers={}
        for name in sorted(offered):
            if name not in ANSWER_ACTIONS:
                levers.setdefault(LEVER[name],[]).extend((name,choice) for choice in offered[name])
        for lever in sorted(levers):
            action=len(self.names)
            self.names.append(lever)
            self.base.append(advisor.weights[lever])
            self.choices.append(levers[lever])
            self.commands.append([choice.commands for _,choice in levers[lever]])
            self.targets.append([[targets(*command,links) for command in choice.commands] for _,choice in levers[lever]])
            for position,found in enumerate(self.targets[action]):
                for slot,items in enumerate(found):
                    for item in items:
                        self.index.setdefault(item,[]).append((action,position,slot))

    @timed_often
    def draw(self,rng):
        alive=[[[True]*len(commands) for commands in choices] for choices in self.commands]
        left=[[len(commands) for commands in choices] for choices in self.commands]
        count=[len(choices) for choices in self.commands]
        pick=self.advisor.random
        batch=[]
        def claim(items):
            for item in items:
                for action,position,slot in self.index.get(item,()):
                    if alive[action][position][slot]:
                        alive[action][position][slot]=False
                        left[action][position]-=1
                        if not left[action][position]:
                            count[action]-=1
        for question in self.questions[:ACTIONS_PER_PAUSE[1]]:
            names=list(dict.fromkeys(name for name,_ in question))
            name=names[0] if len(names)==1 else pick.choices(names,weights=[self.advisor.weights[LEVER[name]] for name in names])[0]
            choice=pick.choice([choice for found,choice in question if found==name])
            command=pick.choice(choice.commands)
            batch.append(Decision(name,choice.params,command))
            claim(targets(*command,self.links))
        for n in range(max(0,ramp(rng,ACTIONS_PER_PAUSE,False)-len(batch))):
            progress('sample_batch')
            offered=[action for action in range(len(self.names)) if count[action] and self.base[action]>0]
            if not offered:
                if not batch:
                    raise GameCrashed(f'No selectable action during the pause at snapshot {self.seq}')
                break
            action=pick.choices(offered,weights=[self.base[action] for action in offered])[0]
            open_=[position for position,live in enumerate(left[action]) if live]
            name=pick.choice(sorted({self.choices[action][position][0] for position in open_}))
            position=pick.choice([position for position in open_ if self.choices[action][position][0]==name])
            slot=pick.choice([slot for slot,live in enumerate(alive[action][position]) if live])
            command=self.commands[action][position][slot]
            batch.append(Decision(name,self.choices[action][position][1].params,command))
            claim(self.targets[action][position][slot])
            if command[0] in ENDS_PAUSE:
                break
        return batch


RECORDED='select a.name,w.weight from run_weight w join advisor_action a on a.advisor_action=w.advisor_action where w.run_id=%s'


@timed_often
def linked(snapshot):
    return {**{('building',ident):('building_type',kind) for ident,kind,_ in snapshot.buildings()},
            **{('character',ident):('military_formation',formation) for ident,formation in snapshot.rows('character','character,formation',country=snapshot.player) if formation},
            **{('war',war):('diplomatic_play',play) for play,war in snapshot.rows('diplomatic_play','diplomatic_play,war') if war is not None},
            **{('ship',ship):('military_formation',fleet) for ship,fleet in snapshot.rows('ship','ship,fleet') if fleet is not None}}


@timed
def redraw(connection,run_id,seq,count,seed,weights=None,snapshot=None):
    if snapshot is None:
        snapshot=Stored(connection,run_id,seq)
    advisor=RandomAdvisor(seed)
    advisor.weights=dict(connection.execute(RECORDED,(run_id,)).fetchall()) if weights is None else weights
    drawer=Drawer(advisor,offer(snapshot,available(snapshot)),snapshot,linked(snapshot))
    rng=random.Random(seed)
    return snapshot,[[(decision.action,decision.params) for decision in drawer.draw(rng)] for _ in range(count)]


class Loop:
    @timed
    def __init__(self,game,advisors,rng,store,run,picker,candidates):
        self.game=game
        self.advisors=advisors
        self.picker=picker
        self.candidates=candidates
        self.rng=rng
        self.store=store
        self.executor=Executor(game)
        self.process=game.reader().process
        self.watching=self.process.watch(self.crashed)
        self.store.begin_run(started_at=datetime.now(timezone.utc),advisors=[advisor.name for advisor in advisors],**run)
        self.shared=None
        self.counts={}
        self.misses=0
        self.dirty=0
        self.turn=0
        self.seq=0

    @timed_often
    def entry(self,source,name,params,snapshot,decision):
        self.seq+=1
        return {'turn':self.turn,'seq':self.seq,'advisor':source,'action':name,'params':params,'snapshot':snapshot.seq,'decision':decision}

    @timed_often
    def note(self,entry,after=None):
        self.counts[entry['status']]=self.counts.get(entry['status'],0)+1
        self.store.log_action(entry,after.seq if after else None)
        if entry['status']!='done':
            LOG.warning('%s %s %s %s',entry['status'],entry['action'],entry['params'],entry.get('detail',''))

    @timed_often
    def snapshot(self,phase):
        try:
            taken=record(self.game,self.store,phase)
            self.shared=self.shared or Shared(self.store.connection)
            return Stored(self.store.connection,*taken,self.shared)
        except RuntimeError as error:
            if 'no longer owns any state' in str(error):
                raise Defeated() from error
            raise

    @timed
    def perform(self,source,name,params,snapshot,pending,raced=None,decision=None):
        entry=self.entry(source,name,params,snapshot,decision)
        LOG.info('action %s %s %s',entry['seq'],name,params)
        try:
            result=self.executor.run(name,**params)
        except LookupError as error:
            if dead(self.game.reader()):
                raise Defeated() from error
            self.note({**entry,'status':'no_object','detail':str(error)})
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
    def turn_actions(self,snapshot):
        batch=[]
        options=available(snapshot)
        with span('loop.run.Loop.draw_candidates','loop'):
            drawer=Drawer(self.advisors[0],offer(snapshot,options),snapshot,linked(snapshot))
            drawn=[drawer.draw(self.rng) for _ in range(self.candidates)]
        chosen,predictions=self.picker.pick([[(decision.action,decision.params) for decision in block] for block in drawn],snapshot)
        if predictions is not None:
            self.store.record_pick(snapshot.seq,[[decision.action for decision in block] for block in drawn],predictions,chosen)
        for decision in drawn[chosen]:
            self.perform(self.advisors[0].name,*decision.command,snapshot,batch,decision=(decision.action,decision.params))
        if not batch:
            return snapshot
        after=self.snapshot('post_action')
        left=self.open_ui(after)
        if left:
            for entry,_,_ in batch:
                self.note({**entry,'status':'ui_leftover','detail':f'{"+".join(left)} open after the pause: {" ".join(item["action"] for item,_,_ in batch)}'},after)
            self.stuck(left)
            return after
        events={combo['event'] for combo in event_options(after)}
        proposers={country for country, in after.rows('player_proposal','country')}
        for entry,_,_ in batch:
            if unanswered(entry,events,proposers):
                self.note({**entry,'status':'ui_leftover','detail':'still waiting for an answer after the pause'},after)
            else:
                self.note({**entry,'status':'done'},after)
        return after

    @timed_often
    def open_ui(self,snapshot):
        meta=snapshot.meta
        left=sorted({name for name in ('panel','interaction','map_list') if meta[f'ui_{name}_open']}|{window for window, in snapshot.rows('ui_open_window','ui_window')})
        self.dirty=self.dirty+1 if left else 0
        return left

    @timed_often
    def stuck(self,left):
        if self.dirty>=STUCK_SNAPSHOTS:
            LOG.error('%s stayed open for %s snapshots in a row; ending the round',"+".join(left),self.dirty)
            raise Stuck()

    @timed
    def advance_quarter(self,snapshot):
        reader=self.game.reader()
        target=next_quarter(reader.date()[0])
        pending=[]
        if self.turn==1:
            self.perform('loop','set_speed',{'speed':FASTEST},snapshot,pending)
        self.perform('loop','unpause',{},snapshot,pending,raced='running')
        longest_gap=self.days(reader,target)
        settle(reader)
        after=self.snapshot('post_run')
        if not target<=game_hours(after)<target+HOURS_PER_DAY:
            raise RuntimeError(f'Quarterly pause missed its first-day target: {reader.date()[1]}, target hour {target}')
        left=self.open_ui(after)
        if left:
            detail=f'{"+".join(left)} open after advancing to the next quarter'
            for item,_,_ in pending:
                self.note({**item,'status':'ui_leftover','detail':detail},after)
            self.stuck(left)
            return after
        for item,_,_ in pending:
            self.note({**item,'status':'done'},after)
        LOG.info('quarterly pause at %s, longest tick gap %.0f ms',reader.date()[1],longest_gap*1000)
        return after

    @timed
    def days(self,reader,target):
        hours=reader.date()[0]
        moved=time.monotonic()
        longest_gap=0
        while True:
            date=reader.date()
            if date[0]>=target:
                break
            if dead(reader):
                raise Defeated()
            if date[0]!=hours:
                longest_gap=max(longest_gap,time.monotonic()-moved)
                hours,moved=date[0],time.monotonic()
            elif time.monotonic()-moved>TICK_LIMIT:
                reader.check()
                raise ClockStalled(f'The game date stopped at {date[1]} for {TICK_LIMIT} s after unpausing; '
                                   f'the longest earlier gap between ticks was {longest_gap*1000:.0f} ms')
            progress('advance_quarter')
            time.sleep(.02)
        return longest_gap

    @timed
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

    @timed_often
    def exit_time(self):
        return self.process.exit_time() if self.process.exits_within(EXIT_GRACE_MS) else None

    @timed_often
    def end(self,reason,detail=None,game_exited_at=None):
        self.watching.set()
        self.counts['end']=reason
        self.store.end_run(reason,detail,game_exited_at)
        if self.shared is not None:
            self.shared.close()
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
            if isinstance(error,ClockStalled):
                try:
                    clock_failure(self.game,self.store.run_id,error)
                except Exception:
                    LOG.exception('Clock-stall evidence could not be saved')
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
        while True:
            if time.monotonic()>deadline:
                return self.end('time')
            if game_hours(snapshot)-start>=years*HOURS_PER_YEAR:
                return self.end('years')
            if at_debt_cap(snapshot):
                LOG.info('debt cap reached at snapshot %s: principal %s, credit %s',snapshot.seq,*snapshot.rows('player_treasury','principal,credit')[0])
                return self.end('debt_cap')
            self.turn+=1
            snapshot=self.turn_actions(snapshot)
            snapshot=self.advance_quarter(snapshot)


@timed_often
def at_debt_cap(snapshot):
    rows=snapshot.rows('player_treasury','principal,credit')
    return bool(rows) and rows[0][0]>0 and rows[0][0]>=rows[0][1]


@timed_often
def build(*size):
    return generate(*size)


def build_apart(*size):
    world=build(*size)
    return world,RECORDER.take()


@timed_often
def log_timings():
    logging.basicConfig(level=logging.WARNING,format='%(asctime)s %(message)s')
    logging.getLogger('interface').setLevel(logging.INFO)
    logging.getLogger('loop').setLevel(logging.INFO)


class WorldPool:
    @timed_often
    def __init__(self,rng,workers,levels):
        self.rng=rng
        self.levels=levels
        self.executor=ProcessPoolExecutor(workers,initializer=log_timings)
        self.pending={self.submit() for _ in range(workers)}

    @timed_often
    def submit(self):
        return self.executor.submit(build_apart,*world_size(self.rng,self.levels))

    @timed
    def take(self):
        while not (done:=wait(self.pending,timeout=1,return_when=FIRST_COMPLETED)[0]):
            progress('world generation')
        self.pending-=done
        finished=done.pop()
        self.pending|=done|{self.submit()}
        world,spans=finished.result()
        RECORDER.merge(spans)
        return world


WATCH=.1
STALLED_EXIT=3


class Watchdog:
    @timed_often
    def __init__(self,game,supervisor=None):
        self.game=game
        self.store=None
        self.supervisor=supervisor

    @timed_often
    def start(self):
        threading.Thread(target=self.watch,daemon=True,name='watchdog').start()

    def watch(self):
        while True:
            time.sleep(WATCH)
            if self.supervisor is not None and not self.supervisor.is_running():
                try:
                    self.trip('supervisor exited',0)
                finally:
                    os._exit(STALLED_EXIT)
            step,age=progress_age()
            if age>STALL_LIMIT:
                self.trip(step,age)
                os._exit(STALLED_EXIT)

    @timed
    def trip(self,step,age):
        LOG.critical('LOOP STALLED: %s made no progress for %.1f s; the limit is %d s',step,age,STALL_LIMIT)
        try:
            if self.store is not None and self.store.run_id is not None:
                self.store.flag_stalled(step,age)
        except Exception:
            LOG.exception('The stall could not be written to the run row')
        self.game.close()


DEATH_READS=3
DEATH_READ_GAP=.2
LATE_FLAG_MS=1000
EXIT_GRACE_MS=1000
CRASHES_IN_A_ROW=3


@timed_often
def dead(reader):
    for _ in range(DEATH_READS):
        if reader.alive():
            return False
        time.sleep(DEATH_READ_GAP)
    LOG.error('DEFEATED: the played country owned no state in %d reads over %.0f ms',DEATH_READS,current().ms)
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


class Fresh:
    @timed_often
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
    @timed_often
    def __init__(self,rng):
        self.rng=rng

    @timed_often
    def take(self):
        return None


TOP_PRESTIGE=('GBR','CHI','FRA','RUS','BIC','PRU','AUS','TUR','USA','EGY','JAP','NET','SWE','PAN','SPA','BRZ','SIA','SIC','PER','POR')


RECENT_ROUNDS=5


@timed_often
def lineup(arguments,completed):
    return (['random'],['first']) if completed<arguments.warmup else (arguments.advisors,arguments.pickers)


@timed
def session(game,watchdog,rng,worlds,advisors,pickers,arguments,chosen,seconds,completed):
    RECORDER.reset()
    store=Store()
    objective=draw_objective(rng)
    advisor_names,picker_names=lineup(arguments,completed)
    advisor=advisors[rng.choice(advisor_names)]
    advisor.start_run(store,NAMES,objective)
    picker=pickers[rng.choice(picker_names)]
    candidates=1 if picker.name=='first' else rng.randint(*CANDIDATES)
    with ThreadPoolExecutor(3) as trainer:
        training=trainer.submit(picker.start_run,store,objective)
        world=worlds.take()
        recent=store.recent_tags(RECENT_ROUNDS)
        if chosen in recent:
            raise ValueError(f'{chosen} was played in one of the last {RECENT_ROUNDS} rounds: {recent}')
        manifest=json.loads(world.read_text(encoding='utf-8')) if world else {'countries':[]}
        tag=chosen or (rng.choice([country['tag'] for country in manifest['countries'] if country['country_type']!='decentralized']) if world else
                       rng.choice([tag for tag in TOP_PRESTIGE if tag not in recent]))
        game.close()
        game.campaign(tag,world=str(world) if world else None,debug=False,wait=False)
        registration=trainer.submit(prepare_recording,game,store,world)
        loading=trainer.submit(game.campaign_ready,tag,world)
        deadline=time.monotonic()+180
        while wait([training,registration,loading],timeout=1)[1]:
            progress('run preparation')
            if time.monotonic()>deadline:
                raise TimeoutError('Run preparation exceeded 180 seconds')
        training.result()
        registration.result()
        loading.result()
    if world:
        store.world_reports(world)
    seed=rng.randrange(10**9)
    name=world.parent.name if world else 'vanilla'
    generated=None if world is None else {'seed':manifest['seed'],'countries':len(manifest['countries']),'states':len(manifest['states']),
                                          'pop':1,'diversity':None,'military':None,
                                          **{name:next(country for country in manifest['countries'] if country['tag']==tag)[name] if name in PER_COUNTRY else manifest[name] for name in SLIDERS}}
    loop=Loop(game,[advisor],random.Random(seed),store,run_record(arguments,'vanilla' if world is None else 'mini',name,tag,seed,generated,advisor,picker,candidates,objective),picker,candidates)
    watchdog.store=store
    counts=loop.run(arguments.years,seconds)
    game.close()
    if isinstance(worlds,(WorldPool,Fresh)):
        shutil.rmtree(world.parent)
    return counts


@timed_often
def run_record(arguments,kind,world,tag,seed,generated,advisor,picker,candidates,objective):
    return {'kind':kind,'world':world,'tag':tag,'cli_seed':arguments.seed,'run_seed':seed,
            'years':arguments.years,'minutes':arguments.minutes,'profile':arguments.profile,'pool':arguments.pool,'runs_requested':arguments.runs,
            'generated':generated,'picker':picker.name,'candidates':candidates,'objective':objective,'weights':{name:advisor.weights[name] for name in NAMES},
            'proposal':advisor.proposal,'pick_model':picker.trained}


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--profile',default='actions')
    parser.add_argument('--advisors',nargs='+',choices=sorted(ADVISORS),default=['random'])
    parser.add_argument('--pickers',nargs='+',choices=sorted(PICKERS),default=['first'])
    parser.add_argument('--runs',type=int,required=True)
    parser.add_argument('--warmup',type=int,default=0)
    parser.add_argument('--progress-file',help=argparse.SUPPRESS)
    parser.add_argument('--years',type=float,default=100)
    parser.add_argument('--minutes',type=float,default=30)
    parser.add_argument('--seed',type=int,default=int(time.strftime('%Y%m%d%H%M%S')))
    parser.add_argument('--pool',type=int,default=0)
    parser.add_argument('--world-cache',help='reuse a completed cache containing at least 1000 worlds')
    parser.add_argument('--vanilla',action='store_true')
    parser.add_argument('--tag')
    parser.add_argument('--weight',nargs='+',default=[])
    supervision=parser.add_mutually_exclusive_group()
    supervision.add_argument('--no-supervisor',action='store_true',help='explicitly run without crash recovery supervision')
    supervision.add_argument('--supervisor',nargs=2,metavar=('PID','CREATED'),help=argparse.SUPPRESS)
    for name in SLIDERS:
        parser.add_argument(*dict.fromkeys(('--'+name.replace('_','-'),'--'+name)),dest=name,type=int if name=='source_regions' else float)
    argv=list(sys.argv[1:] if argv is None else argv)
    arguments=parser.parse_args(argv)
    levels=[getattr(arguments,name) for name in SLIDERS]
    if arguments.vanilla and any(value is not None for value in levels):
        parser.error('world sliders only apply to generated mini worlds')
    if arguments.world_cache and (arguments.vanilla or arguments.pool or arguments.tag or any(value is not None for value in levels)):
        parser.error('--world-cache requires random players and cannot be combined with --vanilla, --pool, --tag or world sliders')
    weights={name:float(value) for name,_,value in (item.partition('=') for item in arguments.weight)}
    if set(weights)-set(NAMES):
        parser.error(f'--weight takes lever names; unknown: {sorted(set(weights)-set(NAMES))}')
    silenced=sorted({(LEVER[accept],LEVER[decline]) for accept,decline in PROPOSALS if weights.get(LEVER[accept])==0 and weights.get(LEVER[decline])==0})
    if silenced:
        parser.error(f'--weight cannot switch off both answers to a proposal: {silenced}')
    log_timings()
    supervisor=None
    if arguments.supervisor:
        supervisor=supervise.owner(*arguments.supervisor)
    elif not arguments.no_supervisor:
        return supervise.start(argv)
    game=GameInterface(arguments.profile,quarterly_pause=True)
    watchdog=Watchdog(game,supervisor)
    watchdog.start()
    rng=random.Random(arguments.seed)
    advisors={name:ADVISORS[name](rng.randrange(10**9),weights) for name in sorted(set(arguments.advisors)|{'random'})}
    pickers={name:PICKERS[name]() for name in set(arguments.pickers)|{'first'}}
    worlds=Cached(arguments.world_cache,rng) if arguments.world_cache else Vanilla(rng) if arguments.vanilla else WorldPool(rng,arguments.pool,levels) if arguments.pool else Fresh(rng,levels)
    chosen=arguments.tag
    crashes=0
    completed=supervise.read_progress(arguments.progress_file) if arguments.progress_file else 0
    while completed<arguments.runs:
        try:
            counts=session(game,watchdog,rng,worlds,advisors,pickers,arguments,chosen,arguments.minutes*60,completed)
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
        completed+=1
        if arguments.progress_file:
            supervise.save_progress(arguments.progress_file,completed)
        print(json.dumps(counts),flush=True)


if __name__=='__main__':
    main()
