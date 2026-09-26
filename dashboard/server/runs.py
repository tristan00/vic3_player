import statistics

from interface.actions.catalogue import GROUP
from interface.common import STALL_LIMIT
from interface.recording.spec import F, I2, I4, I8, TABLE

from . import db
from .models import (EntityKindRow, Ref, Facet, GroupStatus, Rate, RoundRow, RoundsPage, RunDetail, RunRow, RunsPage, Scope, Series, SeriesChoice,
                     SnapshotRow, SnapshotsPage, StatusCount, Count, Weight, ParamWeight)
from .names import ENTITIES, game_date, labels, owned_tables

LOST_AFTER=.5
STATUSES=('done','invalid','raced','no_object','ui_leftover')
SORTS={'run_id':'r.run_id','started_at':'r.started_at','wall':'wall_s','end_reason':'r.end_reason','tag':'d.name','round':'r.cli_seed'}
PLAYER_OWNED=('country',)
LOOP_PARAMS={'run_days':('days:int',),'diplomatic_action_state':('country','diplomatic_action','state','side:choice')}
GROUPS={**GROUP,'run_days':'time','diplomatic_action_state':'diplomacy'}

RUN_SELECT='''
select r.run_id,r.cli_seed,r.kind,d.name as tag,r.world_file,r.started_at,r.ended_at,r.minutes,r.years,r.end_reason,r.end_detail,
       extract(epoch from coalesce(r.ended_at,now())-r.started_at) as wall_s,
       extract(epoch from now()-r.heartbeat_at) as heartbeat_age,extract(epoch from now()-r.progress_at) as progress_age,
       array(select a.name from run_advisor ra join advisor a using (advisor) where ra.run_id=r.run_id order by ra.position) as advisors
from run r join country_definition d on d.country_definition=r.tag
'''


def live_state(found):
    if found['ended_at'] is not None:
        return 'ended'
    if found['heartbeat_age']>LOST_AFTER:
        return 'lost'
    if found['progress_age']>STALL_LIMIT:
        return 'stalled'
    return 'running'


def iso(value):
    return None if value is None else value.isoformat()


@db.timed
def run_rows(found):
    ids=[f['run_id'] for f in found]
    if not ids:
        return []
    extra={e['run_id']:e for e in db.rows('''
        select r.run_id,
               (select count(*) from snapshot s where s.run_id=r.run_id) as snapshots,
               (select game_date from snapshot s where s.run_id=r.run_id order by seq limit 1) as game_from,
               (select game_date from snapshot s where s.run_id=r.run_id order by seq desc limit 1) as game_to,
               (select count(*) from loop_action a where a.run_id=r.run_id) as actions,
               (select count(*) from loop_action a where a.run_id=r.run_id and a.status='done') as done
        from run r where r.run_id=any(%s)''',(ids,))}
    gdp={}
    dated_gdp={}
    for g in db.rows('''select e.run_id,e.gdp,s.game_date from country_economy_report e join run r on r.run_id=e.run_id and e.country=r.player_country
                        join snapshot s on s.run_id=e.run_id and s.seq=e.seq where e.run_id=any(%s) and e.present order by e.run_id,e.seq''',(ids,)):
        gdp.setdefault(g['run_id'],[]).append(g['gdp'])
        dated_gdp.setdefault(g['run_id'],[]).append((g['game_date'],g['gdp']))
    people={}
    for g in db.rows('''select p.run_id,s.game_date,p.lower_strata+p.middle_strata+p.upper_strata as people from player_population p
                        join snapshot s on s.run_id=p.run_id and s.seq=p.seq where p.run_id=any(%s) order by p.run_id,p.seq''',(ids,)):
        people.setdefault(g['run_id'],[]).append((g['game_date'],float(g['people'])))
    return [RunRow(run_id=f['run_id'],round=f['cli_seed'],kind=f['kind'],tag=f['tag'],world=f['world_file'],advisors=f['advisors'],
                   started_at=iso(f['started_at']),ended_at=iso(f['ended_at']),wall_s=float(f['wall_s']),minutes=f['minutes'],years=f['years'],
                   end_reason=f['end_reason'],end_detail=f['end_detail'],state=live_state(f),snapshots=extra[f['run_id']]['snapshots'],
                   game_from=game_date(extra[f['run_id']]['game_from']),game_to=game_date(extra[f['run_id']]['game_to']),
                   actions=extra[f['run_id']]['actions'],
                   done=Rate(n=extra[f['run_id']]['done'],of=extra[f['run_id']]['actions'],noun='actions done',population='actions this run logged'),
                   gdp_start=gdp[f['run_id']][0] if f['run_id'] in gdp else None,gdp_end=gdp[f['run_id']][-1] if f['run_id'] in gdp else None,
                   gdp_peak=max(gdp[f['run_id']]) if f['run_id'] in gdp else None,
                   gdp_yoy=median_yoy(dated_gdp.get(f['run_id'],[])),population_yoy=median_yoy(people.get(f['run_id'],[])))
            for f in found]


HOURS_PER_YEAR=365*24


def median_yoy(points):
    changes=[]
    earlier=0
    for hours,value in points:
        while earlier+1<len(points) and points[earlier+1][0]<=hours-HOURS_PER_YEAR:
            earlier+=1
        base=points[earlier]
        if base[0]<=hours-HOURS_PER_YEAR and base[1]>0:
            changes.append(value/base[1]-1)
    return statistics.median(changes) if changes else None




def filters(kind=None,end_reason=None,tag=None,round=None):
    clauses,params=[],[]
    if kind:
        clauses.append('r.kind=%s')
        params.append(kind)
    if end_reason=='open':
        clauses.append('r.ended_at is null')
    elif end_reason:
        clauses.append('r.end_reason=%s')
        params.append(end_reason)
    if tag:
        clauses.append('d.name=%s')
        params.append(tag)
    if round is not None:
        clauses.append('r.cli_seed=%s')
        params.append(round)
    return (' where '+' and '.join(clauses)) if clauses else '',params


def facets(column,where,params):
    return [Facet(value=str(f['value']),count=f['count']) for f in
            db.rows(f'select {column} as value,count(*) as count from run r join country_definition d on d.country_definition=r.tag {where} '
                    f'group by 1 order by 2 desc,1',params)]


@db.timed
def runs_page(offset,limit,sort,desc,kind=None,end_reason=None,tag=None,round=None):
    where,params=filters(kind,end_reason,tag,round)
    total=db.value(f'select count(*) from run r join country_definition d on d.country_definition=r.tag {where}',params)
    order=f'{SORTS[sort]} {"desc" if desc else "asc"},r.run_id desc'
    found=db.rows(f'{RUN_SELECT} {where} order by {order} limit %s offset %s',[*params,limit,offset])
    described=[part for part in (kind and f'kind {kind}',end_reason and f'ended by {end_reason}',tag and f'playing {tag}',
                                 round is not None and f'round {round}') if part]
    return RunsPage(scope=Scope(text='every recorded run'+(', '+', '.join(described) if described else ''),
                                detail='a round is one launch of the loop; its runs share the launch seed'),
                    total=Count(value=total,noun='runs',population='matching the filters'),rows=run_rows(found),
                    kinds=facets('r.kind',where,params),
                    end_reasons=facets("coalesce(r.end_reason,'open')",where,params),tags=facets('d.name',where,params))


@db.timed
def rounds_page(offset,limit):
    total=db.value('select count(distinct cli_seed) from run')
    found=db.rows('''
        select r.cli_seed,count(*) as runs,count(*) filter (where r.ended_at is null) as live,min(r.started_at) as started_at,
               max(coalesce(r.ended_at,r.heartbeat_at)) as last_at,array_agg(distinct d.name) as tags
        from run r join country_definition d on d.country_definition=r.tag group by r.cli_seed order by min(r.started_at) desc limit %s offset %s''',
                  (limit,offset))
    rows=[round_row(f) for f in found]
    return RoundsPage(scope=Scope(text='every launch of the loop, newest first',detail='runs group into a round by the launch seed they share'),
                      total=Count(value=total,noun='rounds',population='with a recorded run'),rows=rows)


def round_row(found,actions=False):
    seed=found['cli_seed']
    kinds=[Facet(value=f['value'],count=f['count']) for f in db.rows('select kind as value,count(*) as count from run where cli_seed=%s group by 1 order by 2 desc',(seed,))]
    ends=[Facet(value=f['value'],count=f['count']) for f in
          db.rows("select coalesce(end_reason,'open') as value,count(*) as count from run where cli_seed=%s group by 1 order by 2 desc",(seed,))]
    count=db.value('select count(*) from loop_action a join run r using (run_id) where r.cli_seed=%s',(seed,)) if actions else None
    return RoundRow(round=seed,runs=found['runs'],live=found['live'],started_at=iso(found['started_at']),last_at=iso(found['last_at']),kinds=kinds,
                    tags=sorted(found['tags']),end_reasons=ends,actions=count)


@db.timed
def round_of(seed):
    found=db.row('''
        select r.cli_seed,count(*) as runs,count(*) filter (where r.ended_at is null) as live,min(r.started_at) as started_at,
               max(coalesce(r.ended_at,r.heartbeat_at)) as last_at,array_agg(distinct d.name) as tags
        from run r join country_definition d on d.country_definition=r.tag where r.cli_seed=%s group by r.cli_seed''',(seed,))
    return None if found is None else round_row(found,actions=True)


def one_run(run_id):
    found=db.rows(f'{RUN_SELECT} where r.run_id=%s',(run_id,))
    return run_rows(found)[0] if found else None


def status_counts(where,params):
    counts={f['status']:f['count'] for f in db.rows(f'select status,count(*) as count from loop_action a {where} group by 1',params)}
    return [StatusCount(status=s,count=counts.get(s,0)) for s in STATUSES]


def group_statuses(found):
    groups={}
    for f in found:
        group=groups.setdefault(GROUPS[f['action']],{})
        group[f['status']]=group.get(f['status'],0)+f['count']
    return sorted([GroupStatus(group=g,statuses=[StatusCount(status=s,count=c.get(s,0)) for s in STATUSES],total=sum(c.values()))
                   for g,c in groups.items()],key=lambda g:-g.total)


def numeric(column):
    return column.kind in (F,I2,I4,I8) and not column.entity and not column.vocabulary and not column.enum


TITLES={('player_treasury','principal'):'debt (loan principal)',('player_treasury','money'):'gold reserves',
        ('player_treasury','balance'):'balance (reserves − debt)',('player_treasury','credit'):'credit limit',
        ('player_budget_line','interest'):'interest paid per week'}
DERIVED={('player_treasury','balance'):('t.money-t.principal','gold reserves minus the principal of loans; negative when the country is in debt'),
         ('player_budget_line','interest'):("case when t.present then t.amount else 0 end","the interest expense line of the player's weekly budget; 0 when the line is absent")}
FILTERS={('player_budget_line','interest'):" and t.direction='expense' and t.line=10"}


def series_choices():
    out=[SeriesChoice(table=table,column=column,kind='singleton',label=f'{table}.{column}') for table,column in DERIVED]
    for table in TABLE.values():
        if table.kind=='singleton' or (table.kind=='sample' and table.owner is None and not table.keys):
            out+=[SeriesChoice(table=table.name,column=c.name,kind=table.kind,label=f'{table.name}.{c.name}') for c in table.columns if numeric(c)]
        elif table.owner in PLAYER_OWNED and not table.keys and table.kind in ('subject','sample','history','child'):
            out+=[SeriesChoice(table=table.name,column=c.name,kind=table.kind,label=f'{table.name}.{c.name}') for c in table.columns if numeric(c)]
    return out


@db.timed
def entity_kinds(run_id):
    last=db.value('select max(seq) from snapshot where run_id=%s',(run_id,))
    out=[]
    for kind in ENTITIES:
        ever=db.value(f'select count(*) from {kind} where run_id=%s',(run_id,))
        live=db.value(f'select count(*) from (select distinct on ({kind}) present from {kind}_history where run_id=%s order by {kind},seq desc) v where present',
                      (run_id,)) if ever else 0
        out.append(EntityKindRow(kind=kind,live=live,ever=ever,tables=len(owned_tables(kind))))
    return out if last is not None else []


@db.timed
def run_detail(run_id):
    run=one_run(run_id)
    if run is None:
        return None
    found=db.row('''select r.*,extract(epoch from now()-r.heartbeat_at) as heartbeat_age,extract(epoch from now()-r.progress_at) as progress_age,
                           array(select s.name from run_game_rule g join game_rule_setting s using (game_rule_setting) where g.run_id=r.run_id order by 1) as rules
                    from run r where run_id=%s''',(run_id,))
    by_action=db.rows('select a.name as action,l.status,count(*) as count from loop_action l join action a using (action) where l.run_id=%s group by 1,2',(run_id,))
    reads=db.rows('select seq,read_ms from snapshot where run_id=%s order by seq',(run_id,))
    player=labels(run_id,'country',[found['player_country']])
    weights=[Weight(action=w['name'],weight=w['weight']) for w in
             db.rows('select a.name,w.weight from run_weight w join action a using (action) where w.run_id=%s and w.weight<>1 order by w.weight desc,a.name',(run_id,))]
    return RunDetail(run=run,runs_requested=found['runs_requested'],world_seed=found['world_seed'],countries=found['countries'],states=found['states'],
                     tech=found['tech'],pop=found['pop'],weights=weights,
                     param_weights=[ParamWeight(**w) for w in db.rows('select a.name as action,w.param,w.value,w.weight from run_param_weight w join action a using (action) '
                                                                       'where w.run_id=%s order by 1,2,3',(run_id,))],player=Ref(kind='country',id=found['player_country'],label=player[found['player_country']]),
                     world_id=found['world_id'],ruleset_id=found['ruleset_id'],run_seed=found['run_seed'],cli_seed=found['cli_seed'],profile=found['profile'],
                     pool=found['pool'],game_speed=found['game_speed'],custom_rng_seed=found['custom_rng_seed'],rules=found['rules'],
                     progress_step=found['progress_step'],heartbeat_age_s=float(found['heartbeat_age']),progress_age_s=float(found['progress_age']),
                     longest_step=found['longest_step'],longest_step_ms=found['longest_step_ms'],game_exited_at=iso(found['game_exited_at']),
                     statuses=status_counts('where a.run_id=%s',(run_id,)),groups=group_statuses(by_action),
                     read_ms=[r['read_ms'] for r in reads],read_seq=[r['seq'] for r in reads],series=series_choices(),entities=entity_kinds(run_id))


@db.timed
def snapshots_page(run_id,offset,limit):
    total=db.value('select count(*) from snapshot where run_id=%s',(run_id,))
    found=db.rows('''select s.*,(select count(*) from loop_action a where a.run_id=s.run_id and a.after_seq=s.seq) as actions
                     from snapshot s where s.run_id=%s order by seq desc limit %s offset %s''',(run_id,limit,offset))
    return SnapshotsPage(scope=Scope(text=f'every snapshot run {run_id} recorded, newest first',
                                     detail='actions counts the logged actions whose after-snapshot this is'),
                         total=Count(value=total,noun='snapshots',population=f'in run {run_id}'),rows=[snapshot_row(f) for f in found])


def snapshot_row(found):
    return SnapshotRow(seq=found['seq'],phase=found['phase'],game_date=game_date(found['game_date']),taken_at=iso(found['taken_at']),read_ms=found['read_ms'],
                       paused=found['paused'],speed=found['speed'],ui_panel_open=found['ui_panel_open'],ui_interaction_open=found['ui_interaction_open'],
                       ui_map_list_open=found['ui_map_list_open'],actions=found.get('actions',0))


@db.timed
def series(run_id,table_name,column):
    table=TABLE[table_name]
    derived=DERIVED.get((table_name,column))
    if derived is None and column not in [c.name for c in table.columns if numeric(c)]:
        return None
    expression=derived[0] if derived else f't.{column}'
    player=db.value('select player_country from run where run_id=%s',(run_id,))
    owner='' if table.owner is None else f' and t.{table.owner}=%s'
    owner+=FILTERS.get((table_name,column),'')
    params=(run_id,) if table.owner is None else (run_id,player)
    if table.kind=='sample':
        found=db.rows(f'select t.seq,t.n as x,t.date as hours,{expression} as value from {table_name} t '
                      f'where t.run_id=%s{owner} and {expression} is not null order by t.n',params)
        detail='each point is one sample in the trend the game keeps, in sample order; the game dates only some samples'
    else:
        found=db.rows(f'select t.seq,s.game_date as x,s.game_date as hours,{expression} as value from {table_name} t join snapshot s on s.run_id=t.run_id and s.seq=t.seq '
                      f'where t.run_id=%s{owner} and {expression} is not null order by t.seq',params)
        detail=(derived[1]+'; ' if derived else '')+'values are stored only when they change, so the line holds each value until the next change'
    who='the player' if table.owner is None else f'the player country {player}'
    return Series(table=table_name,column=column,label=f'{table_name}.{column}',title=TITLES.get((table_name,column),column.replace('_',' ')),x='sample' if table.kind=='sample' else 'game_hours',
                  xs=[f['x'] for f in found],values=[f['value'] for f in found],seqs=[f['seq'] for f in found],hours=[f['hours'] for f in found],
                  scope=Scope(text=f'{column} of {who} in run {run_id}',detail=detail))
