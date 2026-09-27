import bisect
import logging
import os

import numpy as np
from catboost import CatBoostRegressor, Pool

from interface.common import progress, timed, timed_often
from interface.timing import current, span
from .features import CATEGORIES, FEATURES, LAWS, NUMBERS, History, LiveLookup, categories
from .random_smac_weighting import COMPONENTS, ENDED, HOURS_PER_YEAR, PLAYED, discount, peak, scored_runs, series

LOG=logging.getLogger('loop')
ANSWERS={'choose_event_option','quick_decline_proposal','accept_treaty','decline_treaty','accept_demand','reject_demand',
         'accept_action_proposal','decline_action_proposal','accept_sway','reject_sway'}
CATEGORICAL=list(range(len(NUMBERS),len(NUMBERS)+len(CATEGORIES)+len(LAWS)))
MIN_PAUSES=200
PARAMS={'iterations':200,'depth':9,'learning_rate':.0688,'l2_leaf_reg':13.2451,'rsm':.77,'random_strength':5.8403,'one_hot_max_size':32,'loss_function':'RMSE','random_seed':0,
        'thread_count':os.cpu_count()}

RUNS=f'''select r.run_id,min(s.game_date),max(s.game_date)
{ENDED}
{PLAYED}'''

PAUSES='''select la.run_id,la.before_seq,s.game_date,la.n,ac.name,p.name,p.integer_value,p.text_value
from loop_action la join advisor ad on ad.advisor=la.advisor join action ac on ac.action=la.action
join snapshot s on s.run_id=la.run_id and s.seq=la.before_seq
left join loop_action_param p on p.run_id=la.run_id and p.n=la.n
where la.run_id = any(%s) and ad.name<>'loop' and ac.name <> all(%s)
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


@timed_often
def pool(rows,y=None):
    return Pool([list(row) for row in rows],label=y,cat_features=CATEGORICAL,feature_names=FEATURES)


def value_at(points,date):
    return points[bisect.bisect_right([when for when,_ in points],date)-1][1]


@timed
def training_rows(connection,objective):
    weights,alpha=objective
    runs={run_id:(first,last) for run_id,first,last in connection.execute(RUNS,scored_runs()).fetchall()}
    ids=list(runs)
    points={component:series(connection,component,ids) for component in COMPONENTS}
    pauses={}
    dates={}
    for run_id,seq,date,n,name,param,integer,text in connection.execute(PAUSES,(ids,sorted(ANSWERS))).fetchall():
        dates[(run_id,seq)]=date
        actions=pauses.setdefault((run_id,seq),{})
        actions.setdefault(n,(name,{}))
        if param is not None:
            actions[n][1][param]=integer if text is None else text
    history=History(connection,ids)
    rows,changes=[],[]
    for (run_id,seq),actions in pauses.items():
        lookup=history.at(run_id,seq)
        numbers=lookup.numbers
        date=dates[(run_id,seq)]
        if numbers is None or not all(run_id in points[component] and points[component][run_id][0][0]<=date for component in COMPONENTS):
            continue
        now={component:value_at(points[component][run_id],date) for component in COMPONENTS}
        if min(now.values())<=0:
            continue
        first,last=runs[run_id]
        rows.append(numbers+categories(list(actions.values()),lookup)+lookup.laws+lookup.prices+lookup.institutions)
        changes.append({component:(peak(first,last,points[component][run_id])/now[component]-1)/discount((last-date)/HOURS_PER_YEAR,alpha) for component in COMPONENTS})
    scales={component:float(np.std([found[component] for found in changes])) for component in COMPONENTS}
    y=[sum(weights[component]*found[component]/scales[component] for component in COMPONENTS) for found in changes]
    return rows,np.array(y),len(runs)


class CatBoostPicker:
    name='catboost'

    @timed_often
    def __init__(self):
        self.model=None
        self.trained=None

    @timed
    def start_run(self,store,objective):
        rows,y,runs=training_rows(store.connection,objective)
        if len(y)<MIN_PAUSES:
            raise RuntimeError(f'the catboost picker needs {MIN_PAUSES} scored pauses to train on, found {len(y)} in {runs} runs')
        self.model=CatBoostRegressor(**PARAMS,verbose=False)
        with span('advisors.pickers.CatBoostPicker.fit','loop'):
            self.model.fit(pool(rows,y),callbacks=[Beat()])
        importance=list(zip(FEATURES,(float(value) for value in self.model.get_feature_importance())))
        self.trained=(len(y),runs,current().seconds,PARAMS,importance)
        LOG.info('catboost picker trained for the composite objective on %d pauses from %d runs in %.1fs',*self.trained[:3])

    @timed
    def pick(self,candidates,snapshot):
        lookup=LiveLookup(snapshot)
        rows=[lookup.numbers+categories([(name,params) for _,name,params in batch],lookup)+lookup.laws+lookup.prices+lookup.institutions for batch in candidates]
        predictions=self.model.predict(pool(rows))
        return int(np.argmax(predictions)),[float(value) for value in predictions]


PICKERS={picker.name:picker for picker in (PickFirst,CatBoostPicker)}
