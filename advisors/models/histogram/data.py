import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from catboost import FeaturesData, Pool

from interface.common import timed, timed_often
from ...data.features import INSTITUTIONS, LAWS, NUMBERS, PRICES, TARIFFS, History, LiveLookup
from ...data.histograms import Histograms, Holdings, entries, live_holdings
from ...data.endgame import COMPONENTS, HISTORY, OBJECTIVE, Trajectories, reward, scored_runs

LOG=logging.getLogger('loop')
DESIGN=json.loads((Path(__file__).parent/'parameters.json').read_text(encoding='utf-8'))
SIZES=DESIGN['sizes']
PARAMS={'loss_function':'RMSE','random_seed':0,'thread_count':os.cpu_count(),**DESIGN['params']}
STATE=NUMBERS+PRICES+INSTITUTIONS+TARIFFS
BATCH_SIZE='batch_size'

RUNS=HISTORY

PAUSES='''select la.run_id,la.before_seq,s.game_date,la.n,ac.name,p.name,p.integer_value,p.text_value
from loop_action la join advisor_action ac on ac.advisor_action=la.advisor_action
join snapshot s on s.run_id=la.run_id and s.seq=la.before_seq
left join loop_decision_param p on p.run_id=la.run_id and p.n=la.n
where la.run_id = any(%s)
order by la.run_id,la.before_seq,la.n'''


@timed_often
def frame(state,laws,held,sizes,actions,names,y=None):
    return Pool(FeaturesData(num_feature_data=np.hstack([state,held,sizes,actions]),cat_feature_data=laws,num_feature_names=names,cat_feature_names=LAWS),label=y)


@timed_often
def names(actions,held,sizes):
    return STATE+held.labels(sizes)+[BATCH_SIZE]+actions.labels(sizes)


@timed_often
def pool(data,sizes):
    chosen,held,labels=data.actions.columns(sizes),data.held.columns(sizes),names(data.actions,data.held,sizes)
    return lambda state,actions,y=None:frame(data.state[state],data.laws[state],data.held.counts[np.ix_(state,held)],data.sizes[actions],data.actions.counts[np.ix_(actions,chosen)],labels,y)


@timed
def training_rows(connection,runs):
    ids=list(runs)
    outcomes=Trajectories(connection,ids)
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
    rows={run_id:[] for run_id in runs}
    for (run_id,seq),actions in pauses.items():
        lookup=history.at(run_id,seq)
        numbers=lookup.numbers
        date=dates[(run_id,seq)]
        if numbers is None:
            continue
        baseline=outcomes.baseline(run_id,date)
        last=runs[run_id][1]
        if outcomes.reason(run_id,date,last,baseline) is not None:
            continue
        _,years,parts=outcomes.target(run_id,date,last,baseline,runs[run_id][2]=='defeated')
        batch=list(actions.values())
        acted=entries(batch,lookup)
        rows[run_id].append((numbers+lookup.prices+lookup.institutions+lookup.tariffs,lookup.laws,acted,holdings.at(lookup),
                            [len(batch)],years,parts,seq))
    return rows


class TrainingCache:
    @timed_often
    def __init__(self):
        self.rows={}
        self.versions={}
        self.database=None

    @timed
    def load(self,connection,runs):
        database=connection.info.dsn
        if self.database!=database:
            self.rows={}
            self.versions={}
            self.database=database
        missing={run:dates for run,dates in runs.items() if self.versions.get(run)!=dates}
        if missing:
            found=training_rows(connection,missing)
            self.rows.update(found)
            self.versions.update(missing)
        self.rows={run:self.rows[run] for run in runs}
        self.versions=dict(runs)
        LOG.info('picker training rows reused %d runs, loaded %d runs',len(runs)-len(missing),len(missing))
        return self.rows


@timed
def training_data(connection,cache=None):
    runs={run_id:(first,last,reason) for run_id,first,last,reason in connection.execute(RUNS,scored_runs()).fetchall()}
    rows=training_rows(connection,runs) if cache is None else cache.load(connection,runs)
    state,laws,acted,held,sizes,groups,changes,pauses=[],[],[],[],[],[],[],[]
    for run_id in runs:
        for numbers,active,actions,holdings,size,years,raw,seq in rows[run_id]:
            state.append(numbers)
            laws.append(active)
            acted.append(actions)
            held.append(holdings)
            sizes.append(size)
            groups.append(run_id)
            pauses.append((run_id,seq))
            changes.append(reward(years,raw))
    y=changes
    return SimpleNamespace(y=np.array(y),runs=np.array(groups),played=len(runs),state=np.array(state,np.float32).reshape(len(y),len(STATE)),laws=np.array(laws,object).reshape(len(y),len(LAWS)),
                           sizes=np.array(sizes,np.float32).reshape(len(y),1),actions=Histograms(acted),held=Histograms(held),pauses=np.array(pauses,int).reshape(len(y),2),objective=OBJECTIVE)


class Encoder:
    @timed_often
    def __init__(self,actions,held,sizes):
        self.actions,self.held=actions,held
        self.action_columns=actions.selected(sizes)
        self.held_columns=held.selected(sizes)
        self.labels=names(actions,held,sizes)

    @timed
    def live(self,snapshot,batches):
        lookup=LiveLookup(snapshot)
        count=len(batches)
        state=np.array([lookup.numbers+lookup.prices+lookup.institutions+lookup.tariffs]*count,np.float32)
        held=np.repeat(self.held.count([live_holdings(snapshot)],self.held_columns),count,0)
        actions=self.actions.count([entries(batch,lookup) for batch in batches],self.action_columns)
        sizes=np.array([[len(batch)] for batch in batches],np.float32)
        return frame(state,np.array([lookup.laws]*count,object),held,sizes,actions,self.labels)
