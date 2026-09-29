import bisect
import json
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from catboost import CatBoostRegressor, FeaturesData, Pool

from interface.common import progress, timed, timed_often
from interface.timing import current, span
from .features import INSTITUTIONS, LAWS, NUMBERS, PRICES, History, LiveLookup
from .histograms import ANSWER, COUNTRY, Histograms, Holdings, entries, live_holdings
from .random_smac_weighting import COMPONENTS, ENDED, HOURS_PER_YEAR, PLAYED, discount, peak, scored_runs, series

LOG=logging.getLogger('loop')
ANSWERS=('choose_event_option','quick_decline_proposal','accept_treaty','decline_treaty','accept_demand','reject_demand',
         'accept_action_proposal','decline_action_proposal','accept_sway','reject_sway')
MIN_PAUSES=200
DESIGN=json.loads((Path(__file__).parent/'picker_design.json').read_text(encoding='utf-8'))
SIZES={**DESIGN['sizes'],**{name:sys.maxsize for name in COUNTRY},**{name:sys.maxsize for name in ANSWER}}
PARAMS={**DESIGN['params'],'loss_function':'RMSE','random_seed':0,'thread_count':os.cpu_count()}
BATCH_SIZE='batch_size'
WAIT='run_days'

RUNS=f'''select r.run_id,min(s.game_date),max(s.game_date)
{ENDED}
{PLAYED}'''

PAUSES='''select la.run_id,la.before_seq,s.game_date,la.n,ac.name,p.name,p.integer_value,p.text_value
from loop_action la join advisor ad on ad.advisor=la.advisor join action ac on ac.action=la.action
join snapshot s on s.run_id=la.run_id and s.seq=la.before_seq
left join loop_action_param p on p.run_id=la.run_id and p.n=la.n
where la.run_id = any(%s) and ad.name<>'loop'
order by la.run_id,la.before_seq,la.n'''


class PickFirst:
    name='first'

    trained=None

    @timed_often
    def start_run(self,store,objective):
        pass

    @timed_often
    def pick(self,candidates,snapshot):
        return 0,None


class Beat:
    @timed_often
    def after_iteration(self,info):
        progress('catboost fit')
        return True


def value_at(points,date):
    return points[bisect.bisect_right([when for when,_ in points],date)-1][1]


@timed_often
def frame(state,laws,held,sizes,actions,names,y=None):
    return Pool(FeaturesData(num_feature_data=np.hstack([state,held,sizes,actions]),cat_feature_data=laws,num_feature_names=names,cat_feature_names=LAWS),label=y)


@timed_often
def names(actions,held,sizes):
    return NUMBERS+PRICES+INSTITUTIONS+held.labels(sizes)+[BATCH_SIZE,WAIT]+actions.labels(sizes)


@timed_often
def pool(data,sizes):
    chosen,held,labels=data.actions.columns(sizes),data.held.columns(sizes),names(data.actions,data.held,sizes)
    return lambda state,actions,y=None:frame(data.state[state],data.laws[state],data.held.counts[np.ix_(state,held)],data.sizes[actions],data.actions.counts[np.ix_(actions,chosen)],labels,y)


@timed
def training_data(connection,objective):
    weights,alpha=objective
    runs={run_id:(first,last) for run_id,first,last in connection.execute(RUNS,scored_runs()).fetchall()}
    ids=list(runs)
    points={component:series(connection,component,ids) for component in COMPONENTS}
    pauses={}
    dates={}
    for run_id,seq,date,n,name,param,integer,text in connection.execute(PAUSES,(ids,)).fetchall():
        dates[(run_id,seq)]=date
        actions=pauses.setdefault((run_id,seq),{})
        actions.setdefault(n,(name,{}))
        if param is not None:
            actions[n][1][param]=integer if text is None else text
    history=History(connection,ids)
    holdings=Holdings(connection,ids)
    state,laws,acted,held,sizes,groups,changes=[],[],[],[],[],[],[]
    for (run_id,seq),actions in pauses.items():
        lookup=history.at(run_id,seq)
        numbers=lookup.numbers
        date=dates[(run_id,seq)]
        if numbers is None or not all(run_id in points[component] and points[component][run_id][0][0]<=date for component in COMPONENTS):
            continue
        now={component:value_at(points[component][run_id],date) for component in COMPONENTS}
        days=[params['days'] for name,params in actions.values() if name==WAIT]
        if min(now.values())<=0 or not days:
            continue
        first,last=runs[run_id]
        batch=[found for found in actions.values() if found[0]!=WAIT]
        state.append(numbers+lookup.prices+lookup.institutions)
        laws.append(lookup.laws)
        acted.append(entries(batch,lookup))
        held.append(holdings.at(lookup))
        sizes.append([len(batch),days[0]])
        groups.append(run_id)
        changes.append({component:(peak(first,last,points[component][run_id])/now[component]-1)/discount((last-date)/HOURS_PER_YEAR,alpha) for component in COMPONENTS})
    scales={component:float(np.std([found[component] for found in changes])) for component in COMPONENTS}
    y=[sum(weights[component]*found[component]/scales[component] for component in COMPONENTS) for found in changes]
    return SimpleNamespace(y=np.array(y),runs=np.array(groups),played=len(runs),state=np.array(state,np.float32).reshape(len(y),len(NUMBERS+PRICES+INSTITUTIONS)),laws=np.array(laws,object).reshape(len(y),len(LAWS)),
                           sizes=np.array(sizes,np.float32).reshape(len(y),2),actions=Histograms(acted),held=Histograms(held))


class CatBoostPicker:
    name='catboost'

    @timed_often
    def __init__(self):
        self.model=None
        self.trained=None
        self.actions=None
        self.held=None

    @timed
    def start_run(self,store,objective):
        data=training_data(store.connection,objective)
        if len(data.y)<MIN_PAUSES:
            raise RuntimeError(f'the catboost picker needs {MIN_PAUSES} scored pauses to train on, found {len(data.y)} in {data.played} runs')
        self.actions,self.held=data.actions,data.held
        self.model=CatBoostRegressor(**PARAMS,verbose=False)
        rows=np.arange(len(data.y))
        with span('advisors.pickers.CatBoostPicker.fit','loop'):
            self.model.fit(pool(data,SIZES)(rows,rows,data.y),callbacks=[Beat()])
        importance=list(zip(self.model.feature_names_,(float(value) for value in self.model.get_feature_importance())))
        self.trained=(len(data.y),data.played,current().seconds,PARAMS,importance)
        LOG.info('catboost picker trained for the composite objective on %d pauses from %d runs in %.1fs',*self.trained[:3])

    @timed
    def pick(self,candidates,snapshot):
        lookup=LiveLookup(snapshot)
        batches=[[(name,params) for _,name,params in batch[:-1]] for batch in candidates]
        count=len(batches)
        state=np.array([lookup.numbers+lookup.prices+lookup.institutions]*count,np.float32)
        held=np.repeat(self.held.count([live_holdings(snapshot)])[:,self.held.columns(SIZES)],count,0)
        actions=self.actions.count([entries(batch,lookup) for batch in batches])[:,self.actions.columns(SIZES)]
        sizes=np.array([[len(batch),candidate[-1][2]['days']] for batch,candidate in zip(batches,candidates)],np.float32)
        predictions=self.model.predict(frame(state,np.array([lookup.laws]*count,object),held,sizes,actions,names(self.actions,self.held,SIZES)))
        return int(np.argmax(predictions)),[float(value) for value in predictions]


PICKERS={picker.name:picker for picker in (PickFirst,CatBoostPicker)}
