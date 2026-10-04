from interface.actions.catalogue import GROUP
from interface.common import STALL_LIMIT
from interface.recording.spec import F, I2, I4, I8, TABLE
from psycopg.rows import tuple_row
from threading import Lock

from advisors.data.endgame import COMPONENTS, HISTORY, NAME, Trajectories, outcomes, scored_runs
from advisors.data.rewards import series as component_series

from . import db
from .grid import Spec, grid
from .models import OpenRun, RunInfo, RunReward, Series, SeriesChoice
from .names import LAYOUTS, labels

LOST_AFTER=.5
STATUSES=('done','invalid','raced','no_object','ui_leftover')
END_REASONS=('time','years','defeated','debt_cap','ui_stuck','game_crashed','loop_crashed','loop_lost','loop_stalled')
PLAYER_OWNED=('country',)
LOOP_PARAMS={'diplomatic_action_state':('country','diplomatic_action','state','side:choice')}
GROUPS={**GROUP,'diplomatic_action_state':'diplomacy'}
STATE=(f"case when r.ended_at is not null then 'ended' when extract(epoch from now()-r.heartbeat_at)>{LOST_AFTER} then 'lost' "
       f"when extract(epoch from now()-r.progress_at)>{STALL_LIMIT} then 'stalled' else 'running' end")
RUN_FROM='from run r join country_definition d on d.country_definition=r.tag'
REWARD_LOCK=Lock()
REWARD_POOL=None
REWARD_VERSIONS={}
REWARD_SCORES={}


@db.timed
def runs_grid(filters,sort,desc,offset,limit):
    specs=[Spec('run','run','r.run_id'),Spec('round','round','r.cli_seed',hidden=True),Spec('kind','text','r.kind'),Spec('country','ref','r.player_country',entity='country',run='run'),
           Spec('state','text',STATE),Spec('end_reason','text','r.end_reason'),
           Spec('started_at','time','r.started_at'),Spec('ended_at','time','r.ended_at'),
           Spec('wall_s','number','extract(epoch from coalesce(r.ended_at,now())-r.started_at)'),Spec('minutes','number','r.minutes'),Spec('years','number','r.years'),
           Spec('game_from','date','(select game_date from snapshot s where s.run_id=r.run_id order by seq limit 1)'),
           Spec('game_to','date','(select game_date from snapshot s where s.run_id=r.run_id order by seq desc limit 1)'),
           Spec('snapshots','number','(select count(*) from snapshot s where s.run_id=r.run_id)'),
           Spec('actions','number','(select count(*) from loop_action a where a.run_id=r.run_id)')]
    return grid(specs,RUN_FROM,{},filters,sort or 'run',True if sort is None else desc,offset,limit,None,['run'])


@db.timed
def rounds_grid(filters,sort,desc,offset,limit):
    specs=[Spec('round','round','r.cli_seed'),Spec('runs','number','count(*)'),Spec('open','number','count(*) filter (where r.ended_at is null)'),
           Spec('started_at','time','min(r.started_at)'),Spec('last_at','time','max(coalesce(r.ended_at,r.heartbeat_at))')]
    specs+=[Spec(reason,'number',f"count(*) filter (where r.end_reason='{reason}')") for reason in END_REASONS]
    return grid(specs,f'{RUN_FROM} group by r.cli_seed',{},filters,sort or 'started_at',True if sort is None else desc,offset,limit,None,['round'])


@db.timed
def open_runs():
    return [OpenRun(run=f['run_id'],country=f['name'],state=f['state']) for f in
            db.rows(f'select r.run_id,d.name,{STATE} as state {RUN_FROM} where r.ended_at is null order by r.run_id desc')]


@db.timed
def reward_scores():
    global REWARD_POOL,REWARD_VERSIONS,REWARD_SCORES
    with REWARD_LOCK:
        with db.POOL.connection() as connection:
            cursor=connection.cursor(row_factory=tuple_row)
            versions={row[0]:tuple(row[1:]) for row in cursor.execute(HISTORY,scored_runs()).fetchall()}
            previous=REWARD_VERSIONS if REWARD_POOL is db.POOL else {}
            changed=[run for run,version in versions.items() if previous.get(run)!=version]
            scores={run:score for run,score in REWARD_SCORES.items() if run in versions and run not in changed and run in previous}
            if changed:
                scores.update(outcomes(cursor,changed))
            REWARD_POOL,REWARD_VERSIONS,REWARD_SCORES=db.POOL,versions,scores
            return scores


@db.timed
def run_info(run_id):
    found=db.row(f'select r.*,d.name as country,{STATE} as state {RUN_FROM} where r.run_id=%s',(run_id,))
    if found is None:
        return None
    player=labels(run_id,'country',[found['player_country']])[found['player_country']]
    near=db.row('''select (select max(seq) from snapshot where run_id=%(run)s) as last_seq,(select max(n) from loop_action where run_id=%(run)s) as last_action,
                          (select max(run_id) from run where run_id<%(run)s) as previous,(select min(run_id) from run where run_id>%(run)s) as next''',{'run':run_id})
    return RunInfo(run=run_id,country=found['country'],player=found['player_country'],player_label=player,state=found['state'],**near)


@db.timed
def run_reward(run_id,seq=None):
    found=db.row('select ended_at,end_reason from run where run_id=%s',(run_id,))
    if found is None:
        return None
    date=None if seq is None else db.value('select game_date from snapshot where run_id=%s and seq=%s',(run_id,seq))
    if seq is not None and date is None:
        return None
    empty=RunReward(name=NAME,years=None,window_years=None,baseline_seq=None,score=None,defeated=found['end_reason']=='defeated',parts=[],
                    unavailable_reason='Reward is available after the run ends.' if found['ended_at'] is None else 'This run has no eligible scoring interval.')
    with db.POOL.connection() as connection:
        cursor=connection.cursor(row_factory=tuple_row)
        bounds=[row for row in cursor.execute(HISTORY,scored_runs()).fetchall() if row[0]==run_id]
        if not bounds:
            return empty
        _,first,last,reason=bounds[0]
        start=first if date is None else date
        history=Trajectories(cursor,[run_id])
        baseline=history.baseline(run_id,start)
        omitted=history.reason(run_id,start,last,baseline)
        if omitted is not None:
            empty.unavailable_reason={'no_future_duration':'No game time remains after this snapshot.',
                                      'missing_start_measurement':'A starting metric was not recorded.',
                                      'nonpositive_baseline':'All three starting metrics must be positive and finite.'}[omitted]
            return empty
        result=history.breakdown(run_id,start,last,baseline,reason=='defeated')
    return RunReward(name=NAME,**result)


@db.timed
def run_outcomes(run_id):
    seqs={}
    for f in db.rows('select seq,game_date from snapshot where run_id=%s order by seq',(run_id,)):
        seqs.setdefault(f['game_date'],f['seq'])
    out=[]
    with db.POOL.connection() as connection:
        cursor=connection.cursor(row_factory=tuple_row)
        for component in COMPONENTS:
            points=component_series(cursor,component,[run_id]).get(run_id,[])
            out.append(Series(table=component,column=component,x='game_hours',xs=[h for h,_ in points],values=[float(v) for _,v in points],
                              seqs=[seqs[h] for h,_ in points],hours=[h for h,_ in points]))
    return out


@db.timed
def run_groups(run_id,filters,sort,desc,offset,limit):
    values='(values '+','.join(f"('{name}','{group}')" for name,group in GROUPS.items())+') grp(name,grp)'
    specs=[Spec('group','text','grp.grp'),Spec('actions','number','count(*)')]+[Spec(s,'number',f"count(*) filter (where l.status='{s}')") for s in STATUSES]
    source=f'from loop_action l join action a using (action) join {values} on grp.name=a.name where l.run_id=%(run)s group by grp.grp'
    return grid(specs,source,{'run':run_id},filters,sort or 'actions',True if sort is None else desc,offset,limit,run_id,['group'])


@db.timed
def numeric(column):
    return column.kind in (F,I2,I4,I8) and not column.entity and not column.vocabulary and not column.enum


@db.timed
def series_choices():
    out=[]
    for table in TABLE.values():
        player=table.kind=='singleton' or (table.kind=='sample' and table.owner is None and not table.keys) or \
               (table.owner in PLAYER_OWNED and not table.keys and table.kind in ('subject','sample','history','child'))
        if player:
            out+=[SeriesChoice(table=table.name,column=c.name) for c in table.columns if numeric(c)]
    return out


@db.timed
def key_filter(table,filters):
    layout=LAYOUTS[table.name]
    columns={c.name:c for c in table.keys}
    clauses,params=[],{}
    for i,(name,value) in enumerate(filters):
        if name not in layout.keys:
            raise ValueError(f'{name} is not a key of {table.name}')
        vocabulary=(columns[name].vocabulary or columns[name].enum) if name in columns else None
        clauses.append(f' and t.{name}=(select {vocabulary} from {vocabulary} where name=%(k{i})s)' if vocabulary else f' and t.{name}=%(k{i})s')
        params[f'k{i}']=value if vocabulary else int(value)
    return ''.join(clauses),params


@db.timed
def series(run_id,name,column,filters,player):
    table=TABLE[name]
    if column not in [c.name for c in table.columns if numeric(c)]:
        return None
    if player and table.owner in PLAYER_OWNED:
        filters=[(table.owner,str(db.value('select player_country from run where run_id=%s',(run_id,))))]
    where,params=key_filter(table,filters)
    params['run']=run_id
    if table.kind=='sample':
        found=db.rows(f'select t.seq,t.n as x,t.date as hours,t.{column} as value from {name} t where t.run_id=%(run)s{where} and t.{column} is not null order by t.n',params)
    else:
        found=db.rows(f'select t.seq,s.game_date as x,s.game_date as hours,t.{column} as value from {name} t join snapshot s on s.run_id=t.run_id and s.seq=t.seq '
                      f'where t.run_id=%(run)s{where} and t.{column} is not null order by t.seq',params)
    return Series(table=name,column=column,x='sample' if table.kind=='sample' else 'game_hours',xs=[f['x'] for f in found],values=[f['value'] for f in found],
                  seqs=[f['seq'] for f in found],hours=[f['hours'] for f in found])
