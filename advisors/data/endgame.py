from collections import defaultdict
import math

from interface.common import timed, timed_often
from .rewards import BUILDINGS, COSTS, ENDED, HOURS_PER_YEAR, OWNERS, PLAYED, PLAYERS, SNAPSHOTS, built, scored_runs, value_at

COMPONENTS=('stock','population','gdp')
NAME='endgame_three_v1'
OBJECTIVE={'name':NAME,'weights':{'stock':1/9,'population':6/9,'gdp':2/9},
           'alphas':{'stock':.5,'population':1.,'gdp':-.5},'window_years':1.,'defeat':'zero_terminal'}
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
    return (root*parts['stock']+6*years*parts['population']+2*parts['gdp']/root)/9


@timed_often
def breakdown(start,end,baseline,points,defeated=False):
    years=(end-start)/HOURS_PER_YEAR
    if years<=0 or not math.isfinite(years):
        raise ValueError('Endgame reward requires positive duration')
    window=min(1.,years)
    beginning=max(start,end-HOURS_PER_YEAR)
    parts=[]
    for name in COMPONENTS:
        base=baseline[name]
        if base<=0 or not math.isfinite(base):
            raise ValueError('Endgame reward requires positive finite baselines')
        last=0. if defeated else value_at(points[name],end)/base
        previous=1. if beginning==start else value_at(points[name],beginning)/base
        if min(last,previous)<0 or not all(math.isfinite(v) for v in (last,previous)):
            raise ValueError('Endgame reward requires nonnegative finite outcomes')
        change=(last-previous)/window
        part=change if name=='population' else (last+change)/2
        weight=OBJECTIVE['weights'][name]
        alpha=OBJECTIVE['alphas'][name]
        factor=years**alpha
        parts.append({'component':name,'start_value':base,'end_ratio':last,'recent_change':change,'part':part,
                      'weight':weight,'alpha':alpha,'duration_factor':factor,'contribution':weight*factor*part})
    raw={part['component']:part['part'] for part in parts}
    return {'years':years,'window_years':window,'score':reward(years,raw),'defeated':defeated,'parts':parts}


@timed_often
def target(start,end,baseline,points,defeated=False):
    result=breakdown(start,end,baseline,points,defeated)
    return result['score'],result['years'],{part['component']:part['part'] for part in result['parts']}


class Trajectories:
    @timed
    def __init__(self,connection,runs):
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
        return None

    @timed_often
    def target(self,run,start,end,baseline,defeated):
        return target(start,end,baseline,{name:self.points[name][run] for name in COMPONENTS},defeated)

    @timed_often
    def breakdown(self,run,start,end,baseline,defeated):
        return {'baseline_seq':self.starts[run,start],**breakdown(start,end,baseline,{name:self.points[name][run] for name in COMPONENTS},defeated)}


@timed
def outcomes(connection,runs=None):
    found=connection.execute(HISTORY,scored_runs()).fetchall()
    if runs is not None:
        found=[row for row in found if row[0] in runs]
    history=Trajectories(connection,[run for run,*_ in found])
    scores={}
    for run,first,last,reason in found:
        baseline=history.baseline(run,first)
        if history.reason(run,first,last,baseline) is None:
            scores[run]=history.breakdown(run,first,last,baseline,reason=='defeated')
    return scores


@timed
def rewards(connection):
    return {run:result['score'] for run,result in outcomes(connection).items()}
