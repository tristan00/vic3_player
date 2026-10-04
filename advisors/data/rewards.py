import bisect
from itertools import groupby
import math

from interface.common import DEFAULT_GAME, timed, timed_often
from interface.script import construction_costs

MIN_RATIO=1e-12
ALPHA_RANGE=(.5,1.)
HOURS_PER_YEAR=365*24
OUTCOMES=('time','years','defeated','debt_cap')
DEBT_CAP_FROM_RUN=1

ENDED='''from run r join snapshot s on s.run_id=r.run_id
where r.run_id>=%(first)s and r.kind='mini' and r.ended_at is not null'''
PLAYED='''group by r.run_id
having r.end_reason = any(%(outcomes)s) or max(s.game_date)-min(s.game_date)>=%(hours)s
order by r.run_id'''
HISTORY=f'''select r.run_id,min(s.game_date),max(s.game_date)
{ENDED}
{PLAYED}'''

POPULATION='''select p.run_id,s.game_date,p.lower_strata+p.middle_strata+p.upper_strata
from player_population p join snapshot s on s.run_id=p.run_id and s.seq=p.seq
where p.run_id = any(%s)
order by p.run_id,p.seq'''

GDP='''select e.run_id,s.game_date,e.gdp
from country_economy_report e join run r on r.run_id=e.run_id and e.country=r.player_country join snapshot s on s.run_id=e.run_id and s.seq=e.seq
where e.run_id = any(%s) and e.present
order by e.run_id,e.seq'''

SOL='''select e.run_id,s.game_date,e.average_standard_of_living_by_population
from country_standard_of_living_report e join run r on r.run_id=e.run_id and e.country=r.player_country join snapshot s on s.run_id=e.run_id and s.seq=e.seq
where e.run_id = any(%s) and e.present
order by e.run_id,e.seq'''

BUILDINGS='''select b.run_id,b.seq,b.building,b.present,t.name,b.state,b.levels
from building_history b left join building_type t on t.building_type=b.building_type
where b.run_id = any(%s)'''
OWNERS='select run_id,seq,state,present,country from state_history where run_id = any(%s)'
SNAPSHOTS='select run_id,seq,game_date from snapshot where run_id = any(%s)'
PLAYERS='select run_id,player_country from run where run_id = any(%s)'
COSTS=construction_costs(DEFAULT_GAME/'game')
MIN_YEARS=1


@timed_often
def built(events,player,dates):
    owner,value,placed,points={},{},{},[]
    total=0.0
    for seq,group in groupby(sorted(events,key=lambda event:event[:2]),key=lambda event:event[0]):
        for _,kind,key,found in group:
            if kind==0:
                if (owner.get(key)==player)!=(found==player):
                    total+=value.get(key,0.0) if found==player else -value.get(key,0.0)
                owner[key]=found
                continue
            old=placed.pop(key,None)
            if old:
                value[old[0]]-=old[1]
                total-=old[1] if owner.get(old[0])==player else 0.0
            if found:
                placed[key]=found
                value[found[0]]=value.get(found[0],0.0)+found[1]
                total+=found[1] if owner.get(found[0])==player else 0.0
        if seq in dates:
            points.append((dates[seq],total))
    return points


@timed
def stock(connection,runs):
    players=dict(connection.execute(PLAYERS,(runs,)).fetchall())
    dates={}
    for run_id,seq,date in connection.execute(SNAPSHOTS,(runs,)).fetchall():
        dates.setdefault(run_id,{})[seq]=date
    events={}
    for run_id,seq,state,present,country in connection.execute(OWNERS,(runs,)).fetchall():
        events.setdefault(run_id,[]).append((seq,0,state,country if present else None))
    for run_id,seq,building,present,kind,state,levels in connection.execute(BUILDINGS,(runs,)).fetchall():
        if present and kind not in COSTS:
            continue
        events.setdefault(run_id,[]).append((seq,1,building,(state,COSTS[kind]*levels) if present else None))
    return {run_id:built(found,players[run_id],dates[run_id]) for run_id,found in events.items()}


COMPONENTS={'gdp':GDP,'population':POPULATION,'sol':SOL,'stock':stock}



@timed_often
def value_at(points,date):
    return points[bisect.bisect_right([when for when,_ in points],date)-1][1]


@timed_often
def mean_log(points,start,end,base=None):
    initial=value_at(points,start)
    base=initial if base is None else base
    if base<=0 or end<=start:
        raise ValueError('Log growth requires a positive starting value and duration')
    path=[(start,initial)]+[(date,value) for date,value in points if start<date<end]
    stops=[date for date,_ in path[1:]]+[end]
    if any(value<0 for (date,value),stop in zip(path,stops) if stop>date):
        raise ValueError('Log growth cannot score negative values')
    return sum((stop-date)*math.log(max(value/base,MIN_RATIO)) for (date,value),stop in zip(path,stops) if stop>date)/(end-start)


@timed_often
def growth(first,last,points):
    if points[0][0]!=first:
        raise RuntimeError(f'the value was not recorded at the first snapshot (hour {first})')
    return mean_log(points,first,last,base=points[0][1])


@timed_often
def scored_runs():
    return {'first':DEBT_CAP_FROM_RUN,'outcomes':list(OUTCOMES),'hours':MIN_YEARS*HOURS_PER_YEAR}


@timed
def series(connection,component,runs):
    if callable(COMPONENTS[component]):
        return COMPONENTS[component](connection,runs)
    points={}
    for run_id,date,value in connection.execute(COMPONENTS[component],(runs,)).fetchall():
        points.setdefault(run_id,[]).append((date,value))
    return points


@timed_often
def draw_objective(rng):
    draws={component:rng.gammavariate(1,1) for component in COMPONENTS}
    total=sum(draws.values())
    return {component:value/total for component,value in draws.items()},rng.uniform(*ALPHA_RANGE)


@timed_often
def horizon(years,alpha):
    return years**alpha


@timed_often
def reward(years,parts,objective):
    weights,alpha=objective
    factor=horizon(years,alpha)
    return sum(weights[component]*parts[component]*factor for component in COMPONENTS)


@timed_often
def combine(changes,objective):
    return {run:reward(years,parts,objective) for run,(years,parts) in changes.items()}


@timed_often
def breakdown(changes,objective,run):
    weights,alpha=objective
    years,raw=changes[run]
    factor=horizon(years,alpha)
    return years,[{'component':component,'weight':weights[component],'gain':raw[component],'years_alpha':factor,
                   'gain_times_years_alpha':raw[component]*factor,'contribution':weights[component]*raw[component]*factor} for component in COMPONENTS]


@timed
def outcomes(connection):
    found=connection.execute(HISTORY,scored_runs()).fetchall()
    points={component:series(connection,component,[row[0] for row in found]) for component in COMPONENTS}
    return {run_id:((last-first)/HOURS_PER_YEAR,{component:growth(first,last,points[component][run_id]) for component in COMPONENTS})
            for run_id,first,last in found if last>first and all(run_id in points[component] and points[component][run_id][0][1]>0 for component in COMPONENTS)}


@timed_often
def rewards(connection,objective):
    return combine(outcomes(connection),objective)


