import logging
import time

import numpy as np
from scipy.stats import norm
from sklearn.ensemble import RandomForestRegressor

from interface.common import timed
from .random_picker import RandomAdvisor

LOG=logging.getLogger('loop')
LOW,HIGH=-2.,2.
INITIAL=10
RANDOM_SHARE=.2
TREES=50
CANDIDATES=2000
STARTS=10
NEIGHBOURS=50
LOCAL_STEPS=20
STEP=.125
HOURS_PER_YEAR=365*24
SCORED=('time','years','defeated','debt_cap')
DEBT_CAP_FROM_RUN=104
GROUPS={'build:construction_sector':[('build','building_type','building_construction_sector')],
        'build:government_administration':[('build','building_type','building_government_administration')]}

HISTORY='''select r.run_id,min(s.game_date),max(s.game_date)
from run r
join snapshot s on s.run_id=r.run_id
where r.run_id>=%s and r.kind='mini' and r.end_reason = any(%s) and (select count(*) from run_advisor ra where ra.run_id=r.run_id)=1
group by r.run_id
order by r.run_id'''

POPULATION='''select p.run_id,s.game_date,p.lower_strata+p.middle_strata+p.upper_strata
from player_population p join snapshot s on s.run_id=p.run_id and s.seq=p.seq
where p.run_id = any(%s)
order by p.run_id,p.seq'''

WEIGHTS='''select w.run_id,a.name,w.weight from run_weight w join action a on a.action=w.action where w.run_id = any(%s)'''

PARAM_WEIGHTS='''select p.run_id,a.name,p.param,p.value,p.weight from run_param_weight p join action a on a.action=p.action where p.run_id = any(%s)'''

GDP='''select e.run_id,s.game_date,e.gdp
from country_economy_report e join run r on r.run_id=e.run_id and e.country=r.player_country join snapshot s on s.run_id=e.run_id and s.seq=e.seq
where e.run_id = any(%s) and e.present
order by e.run_id,e.seq'''

SOL='''select e.run_id,s.game_date,e.average_standard_of_living_by_population
from country_standard_of_living_report e join run r on r.run_id=e.run_id and e.country=r.player_country join snapshot s on s.run_id=e.run_id and s.seq=e.seq
where e.run_id = any(%s) and e.present
order by e.run_id,e.seq'''

COMPONENTS={'gdp':GDP,'population':POPULATION,'sol':SOL}
MIN_YEARS=1


def peak(first,last,points):
    window=max(first,last-HOURS_PER_YEAR)
    carried=[people for date,people in points if date<=window][-1]
    return max([carried]+[people for date,people in points if date>window])


def change(first,last,points):
    start_date,start=points[0]
    if start_date!=first:
        raise RuntimeError(f'the value was not recorded at the first snapshot (hour {first})')
    return (peak(first,last,points)/start-1)*100


def series(connection,component,runs):
    points={}
    for run_id,date,value in connection.execute(COMPONENTS[component],(runs,)).fetchall():
        points.setdefault(run_id,[]).append((date,value))
    return points


def draw_objective(rng):
    draws={component:rng.gammavariate(1,1) for component in COMPONENTS}
    total=sum(draws.values())
    return {component:value/total for component,value in draws.items()},rng.random()


def discount(years,alpha):
    return max(MIN_YEARS,years)**alpha


def discounted(changes,alpha):
    return {run:{component:value/discount(years,alpha) for component,value in found.items()} for run,(years,found) in changes.items()}


def scales(values):
    return {component:float(np.std([found[component] for found in values.values()])) for component in COMPONENTS}


def combine(changes,objective):
    weights,alpha=objective
    values=discounted(changes,alpha)
    spread=scales(values)
    return {run:sum(weights[component]*found[component]/spread[component] for component in COMPONENTS) for run,found in values.items()}


def breakdown(changes,objective,run):
    weights,alpha=objective
    values=discounted(changes,alpha)
    spread=scales(values)
    years,raw=changes[run]
    return years,[{'component':component,'weight':weights[component],'change':raw[component],'divisor':discount(years,alpha),
                   'discounted':values[run][component],'scale':spread[component],'normalized':values[run][component]/spread[component],
                   'contribution':weights[component]*values[run][component]/spread[component]} for component in COMPONENTS]


@timed
def outcomes(connection):
    found=connection.execute(HISTORY,(DEBT_CAP_FROM_RUN,list(SCORED))).fetchall()
    points={component:series(connection,component,[row[0] for row in found]) for component in COMPONENTS}
    return {run_id:((last-first)/HOURS_PER_YEAR,{component:change(first,last,points[component][run_id]) for component in COMPONENTS})
            for run_id,first,last in found if all(run_id in points[component] and points[component][run_id][0][1]>0 for component in COMPONENTS)}


def rewards(connection,objective):
    return combine(outcomes(connection),objective)


@timed
def history(connection,space,objective):
    scored=rewards(connection,objective)
    weights={}
    for run_id,action,weight in connection.execute(WEIGHTS,(list(scored),)).fetchall():
        weights.setdefault(run_id,{})[action]=weight
    params={}
    for run_id,action,param,value,weight in connection.execute(PARAM_WEIGHTS,(list(scored),)).fetchall():
        params.setdefault(run_id,{})[(action,param,value)]=weight
    grouped={key for members in GROUPS.values() for key in members}
    dimensions={**GROUPS,**{f'{action}:{param}={value}':[(action,param,value)] for action,param,value in sorted({key for found in params.values() for key in found}-grouped)}}
    def levels(run_id):
        return [{params.get(run_id,{}).get(key,1) for key in members} for members in dimensions.values()]
    runs=[run_id for run_id in scored if all(weights.get(run_id,{}).get(action,0)>0 for action in space) and all(len(level)==1 for level in levels(run_id))]
    X=np.array([[np.log10(weights[run_id][action]) for action in space]+[np.log10(level.pop()) for level in levels(run_id)] for run_id in runs])
    return X.reshape(len(runs),len(space)+len(dimensions)),np.array([scored[run_id] for run_id in runs]),dimensions,runs


def predict(forest,points,best):
    per_tree=np.stack([tree.predict(points) for tree in forest.estimators_])
    mean,spread=per_tree.mean(0),per_tree.std(0)+1e-9
    z=(mean-best)/spread
    return mean,spread,(mean-best)*norm.cdf(z)+spread*norm.pdf(z),norm.cdf(z)


def expected_improvement(forest,points,best):
    return predict(forest,points,best)[2]


def local_search(forest,starts,best,low,high,rng):
    points=starts.copy()
    scores=expected_improvement(forest,points,best)
    for _ in range(LOCAL_STEPS):
        moves=rng.normal(0,1,(len(points),NEIGHBOURS,points.shape[1]))*STEP*(high-low)*(rng.random((len(points),NEIGHBOURS,points.shape[1]))<.1)
        neighbours=np.clip(points[:,None,:]+moves,low,high)
        found=expected_improvement(forest,neighbours.reshape(-1,points.shape[1]),best).reshape(len(points),NEIGHBOURS)
        pick=found.argmax(1)
        better=found[np.arange(len(points)),pick]>scores
        points[better]=neighbours[np.arange(len(points)),pick][better]
        scores[better]=found[np.arange(len(points)),pick][better]
    return points,scores


class RandomSmacWeightingAdvisor(RandomAdvisor):
    name='random_smac_weighting'

    def __init__(self,seed=None,weights=None,param_weights=None):
        super().__init__(seed)
        self.excluded={name for name,weight in (weights or {}).items() if weight==0}

    @timed
    def propose(self,X,y,low,high,names=None):
        rng=np.random.default_rng(self.random.randrange(2**32))
        names=names or [str(i) for i in range(len(low))]
        record={'observations':len(y),'best_reward':float(y.max()) if len(y) else None,'predicted_reward':None,'uncertainty':None,
                'expected_improvement':None,'beat_probability':None,'candidates':0,'candidate_rows':[],'importance':[]}
        forest=None
        if len(y)>=INITIAL:
            forest=RandomForestRegressor(n_estimators=TREES,min_samples_leaf=2,max_features=5/6,random_state=int(rng.integers(2**31))).fit(X,y)
            record['importance']=[(name,float(value)) for name,value in zip(names,forest.feature_importances_)]
        if not (X==0).all(1).any():
            x,method=np.zeros(len(low)),'default'
        elif forest is None or self.random.random()<RANDOM_SHARE:
            x,method=rng.uniform(low,high),'random'
        else:
            random_points=rng.uniform(low,high,(CANDIDATES,len(low)))
            climbed,_=local_search(forest,np.clip(X[np.argsort(y)[-STARTS:]],low,high),y.max(),low,high,rng)
            points=np.vstack([random_points,climbed])
            sources=['random']*len(random_points)+['local_search']*len(climbed)
            mean,spread,improvement,beat=predict(forest,points,y.max())
            order=np.argsort(-improvement,kind='stable')
            record['candidates']=len(points)
            record['candidate_rows']=[(rank,sources[i],float(mean[i]),float(spread[i]),float(improvement[i]),float(beat[i])) for rank,i in enumerate(order)]
            x,method=points[order[0]],'expected_improvement'
        if forest is not None:
            chosen=record['candidate_rows'][0][2:] if method=='expected_improvement' else [float(value[0]) for value in predict(forest,x[None,:],y.max())]
            record.update(zip(('predicted_reward','uncertainty','expected_improvement','beat_probability'),chosen))
        record['method']=method
        return x,record

    @timed
    def start_run(self,store,actions,objective):
        started=time.perf_counter()
        space=[name for name in actions if name not in self.excluded]
        X,y,dimensions,runs=history(store.connection,space,objective)
        names=space+list(dimensions)
        x,record=self.propose(X,y,np.full(len(names),LOW),np.full(len(names),HIGH),names)
        record['reward']='composite'
        record['observed']=[(run_id,float(reward)) for run_id,reward in zip(runs,y)]
        record['seconds']=time.perf_counter()-started
        self.proposal=record
        chosen=(10**x).tolist()
        self.weights={**{name:0 for name in actions if name in self.excluded},**dict(zip(space,chosen))}
        self.param_weights={}
        for members,weight in zip(dimensions.values(),chosen[len(space):]):
            for action,param,value in members:
                self.param_weights.setdefault(action,{}).setdefault(param,{})[value]=weight
        LOG.info('random_smac_weighting proposal (%s) from %d scored runs, best %s %.3f, predicted %s',
                 record['method'],len(y),'composite',record['best_reward'] or 0,'none' if record['predicted_reward'] is None else f"{record['predicted_reward']:.3f}")
        return self.weights
