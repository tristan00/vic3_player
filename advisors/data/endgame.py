from collections import defaultdict
import math

from interface.common import evidence, timed, timed_often
from .construction import ConstructionActivity, ConstructionSectors
from .military import MilitaryStrength
from .rewards import BUILDINGS, COSTS, ENDED, HOURS_PER_YEAR, OWNERS, PLAYED, PLAYERS, SNAPSHOTS, built, scored_runs, value_at

COMPONENTS=('stock','population','gdp')
LEVELS=('military','sectors')
REWARD_COMPONENTS=(*COMPONENTS,'construction',*LEVELS)
NAME='endgame_sectors_v6'
OBJECTIVE={'name':NAME,'weights':{'stock':1/9,'population':6/9,'gdp':2/9,'construction':.5,'military':.05,'sectors':.1},
           'alphas':{'stock':.5,'population':1.,'gdp':-.5,'construction':0.,'military':0.,'sectors':0.},'window_years':1.}
HISTORY=f'''select r.run_id,min(s.game_date),max(s.game_date),r.end_reason
{ENDED}
{PLAYED}'''
POPULATION='''select run_id,seq,lower_strata+middle_strata+upper_strata
from player_population where run_id=any(%s) order by run_id,seq'''
GDP='''select e.run_id,e.seq,e.gdp from country_economy_report e
join run r on r.run_id=e.run_id and r.player_country=e.country
where e.run_id=any(%s) and e.present order by e.run_id,e.seq'''


@timed_often
def reward(years,parts):
    root=years**.5
    return ((root*parts['stock']+6*years*parts['population']+2*parts['gdp']/root)/9
            +sum(OBJECTIVE['weights'][name]*parts[name] for name in ('construction',*LEVELS)))


@timed_often
def breakdown(start,end,baseline,points,active_fraction,mean_logs):
    years=(end-start)/HOURS_PER_YEAR
    if years<=0 or not math.isfinite(years):
        raise ValueError(evidence(start=start,end=end,years=years))
    window=min(1.,years)
    beginning=max(start,end-HOURS_PER_YEAR)
    parts=[]
    for name in COMPONENTS:
        base=baseline[name]
        if base<=0 or not math.isfinite(base):
            raise ValueError(evidence(name=name,base=base))
        last=value_at(points[name],end)/base
        previous=1. if beginning==start else value_at(points[name],beginning)/base
        if min(last,previous)<0 or not all(math.isfinite(v) for v in (last,previous)):
            raise ValueError(evidence(name=name,last=last,previous=previous))
        change=(last-previous)/window
        part=change if name=='population' else (last+change)/2
        weight=OBJECTIVE['weights'][name]
        alpha=OBJECTIVE['alphas'][name]
        factor=years**alpha
        parts.append({'component':name,'start_value':base,'end_ratio':last,'recent_change':change,'part':part,
                      'weight':weight,'alpha':alpha,'duration_factor':factor,'contribution':weight*factor*part})
    if active_fraction is None or not math.isfinite(active_fraction) or not 0<=active_fraction<=1:
        raise ValueError(evidence(active_fraction=active_fraction))
    weight=OBJECTIVE['weights']['construction']
    parts.append({'component':'construction','start_value':None,'end_ratio':None,'recent_change':None,
                  'active_fraction':active_fraction,'part':active_fraction-1,'weight':weight,'alpha':0.,
                  'duration_factor':1.,'contribution':weight*(active_fraction-1)})
    for name in LEVELS:
        mean_log=mean_logs[name]
        if mean_log is None or not math.isfinite(mean_log) or mean_log<0:
            raise ValueError(evidence(name=name,mean_log=mean_log))
        weight=OBJECTIVE['weights'][name]
        parts.append({'component':name,'start_value':None,'end_ratio':None,'recent_change':None,
                      'part':mean_log,'weight':weight,'alpha':0.,'duration_factor':1.,'contribution':weight*mean_log})
    raw={part['component']:part['part'] for part in parts}
    return {'years':years,'window_years':window,'score':reward(years,raw),'parts':parts}


@timed_often
def target(start,end,baseline,points,active_fraction,mean_logs):
    result=breakdown(start,end,baseline,points,active_fraction,mean_logs)
    return result['score'],result['years'],{part['component']:part['part'] for part in result['parts']}


class Trajectories:
    @timed
    def __init__(self,connection,runs):
        self.construction=ConstructionActivity(connection,runs)
        self.levels={'military':MilitaryStrength(connection,runs),'sectors':ConstructionSectors(connection,runs)}
        self.dates=defaultdict(dict)
        self.starts={}
        for run,seq,date in sorted(connection.execute(SNAPSHOTS,(runs,)).fetchall()):
            self.dates[run][seq]=date
            self.starts.setdefault((run,date),seq)
        self.values={name:defaultdict(list) for name in COMPONENTS}
        for name,query in [('gdp',GDP),('population',POPULATION)]:
            for run,seq,value in connection.execute(query,(runs,)).fetchall():
                self.values[name][run].append((seq,value))
        players=dict(connection.execute(PLAYERS,(runs,)).fetchall())
        events=defaultdict(list)
        for run,seq,state,present,country in connection.execute(OWNERS,(runs,)).fetchall():
            events[run].append((seq,0,state,country if present else None))
        for run,seq,building,present,kind,state,levels in connection.execute(BUILDINGS,(runs,)).fetchall():
            if present and kind not in COSTS:
                continue
            events[run].append((seq,1,building,(state,COSTS[kind]*levels) if present else None))
        for run,found in events.items():
            self.values['stock'][run]=built(found,players[run],{seq:seq for seq in self.dates[run]})
        self.points={name:{run:[(self.dates[run][seq],value) for seq,value in points] for run,points in histories.items()}
                     for name,histories in self.values.items()}

    @timed_often
    def baseline(self,run,date):
        seq=self.starts[run,date]
        return {name:value_at(points,seq) if points and points[0][0]<=seq else None
                for name in COMPONENTS for points in [self.values[name].get(run,[])]}

    @timed_often
    def reason(self,run,date,last,baseline):
        if date>=last:
            return 'no_future_duration'
        if any(value is None for value in baseline.values()):
            return 'missing_start_measurement'
        if any(value<=0 or not math.isfinite(value) for value in baseline.values()):
            return 'nonpositive_baseline'
        if self.construction.fraction(run,date,last) is None:
            return 'missing_construction_measurement'
        for name in LEVELS:
            if self.levels[name].mean_log(run,date,last) is None:
                return f'missing_{name}_measurement'
        return None

    @timed_often
    def mean_logs(self,run,start,end):
        return {name:self.levels[name].mean_log(run,start,end) for name in LEVELS}

    @timed_often
    def target(self,run,start,end,baseline):
        return target(start,end,baseline,{name:self.points[name][run] for name in COMPONENTS},
                      self.construction.fraction(run,start,end),self.mean_logs(run,start,end))

    @timed_often
    def breakdown(self,run,start,end,baseline):
        return {'baseline_seq':self.starts[run,start],**breakdown(start,end,baseline,{name:self.points[name][run] for name in COMPONENTS},
                                                               self.construction.fraction(run,start,end),self.mean_logs(run,start,end))}


@timed
def outcomes(connection,runs=None):
    found=connection.execute(HISTORY,scored_runs()).fetchall()
    if runs is not None:
        found=[row for row in found if row[0] in runs]
    history=Trajectories(connection,[run for run,*_ in found])
    scores={}
    for run,first,last,_ in found:
        baseline=history.baseline(run,first)
        if history.reason(run,first,last,baseline) is None:
            scores[run]=history.breakdown(run,first,last,baseline)
    return scores


@timed
def rewards(connection):
    return {run:result['score'] for run,result in outcomes(connection).items()}
