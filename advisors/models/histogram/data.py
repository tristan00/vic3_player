import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from catboost import FeaturesData, Pool

from interface.common import timed, timed_often
from ...data.features import CATEGORIES, INSTITUTIONS, NUMBERS, PRICES, TARIFFS, TAXES, History, LiveLookup, categories
from ...data.histograms import Histograms, Holdings, entries, live_holdings
from ...data.endgame import HISTORY, NAME, OBJECTIVE, Trajectories, reward, scored_runs
from ...data import features as state, histograms as hist
from ..row.features import Selection, context

LOG=logging.getLogger('loop')
DESIGN=json.loads((Path(__file__).parent/'parameters.json').read_text(encoding='utf-8'))
SIZES=DESIGN['sizes']
PARAMS={'loss_function':'RMSE','random_seed':0,'thread_count':os.cpu_count(),**DESIGN['params']}
STATE=NUMBERS+PRICES+INSTITUTIONS+TARIFFS+TAXES
BATCH_SIZE='batch_size'

RUNS=HISTORY

PAUSES='''select la.run_id,la.before_seq,s.game_date,la.n,ac.name,p.name,p.integer_value,p.text_value
from loop_action la join advisor_action ac on ac.advisor_action=la.advisor_action
join snapshot s on s.run_id=la.run_id and s.seq=la.before_seq
left join loop_decision_param p on p.run_id=la.run_id and p.n=la.n
where la.run_id = any(%s)'''


@timed_often
def frame(state,categorical,held,sizes,actions,names,y=None):
    return Pool(FeaturesData(num_feature_data=np.hstack([state,held,sizes,actions]),cat_feature_data=categorical,num_feature_names=names,cat_feature_names=CATEGORIES),label=y)


@timed_often
def names(actions,held,sizes):
    return STATE+held.labels(sizes)+[BATCH_SIZE]+actions.labels(sizes)


@timed_often
def pool(data,sizes):
    chosen,held,labels=data.actions.columns(sizes),data.held.columns(sizes),names(data.actions,data.held,sizes)
    return lambda state,actions,y=None:frame(data.state[state],data.categories[state],data.held.counts[np.ix_(state,held)],data.sizes[actions],data.actions.counts[np.ix_(actions,chosen)],labels,y)


@timed
def training_rows(connection,runs,columns=None,families=None,snapshots=None):
    ids=list(runs)
    columns=STATE+CATEGORIES if columns is None else columns
    selection=Selection(columns)
    actions=None if families is None else families['actions']
    held=None if families is None else families['held']
    needed=set(selection.history)
    if actions is None:
        needed=None
    else:
        for names,required in (
            (hist.ANSWER,{'events','options','defined'}),
            (hist.LEADERS,{'groups','characters','traits','movements','law_rows'}),
            (hist.QUEUE,{'queue'}),
            (hist.PLAY,{'states','relations','countries','gdp','prestige'}),
            ((*hist.PLAY_CONTEXT,*hist.PLAY_PACTS),{'states','relations','hours','pacts','treaties','articles','provinces','colors','edges'}),
            (state.SITE,{'states','buildings','people','living','literate','shares'})):
            if actions.intersection(names):
                needed.update(required)
        for action,params in state.KINDS.items():
            for param,kind in params:
                if f'{action}.{param}' in actions:
                    needed.update({'state':{'states','terrain'},'building':{'buildings'},'character':{'characters'},'country':{'countries'}}.get(kind,{'types'} if kind in state.TYPED else set()))
        if held is None or held.intersection((hist.BUILDINGS,hist.METHODS)):
            needed.add('states')
    outcomes=Trajectories(connection,ids)
    pauses={}
    dates={}
    query,arguments=PAUSES,[ids]
    if snapshots is not None:
        selected=[(run,seq) for run in ids for seq in snapshots[run]]
        query+=' and (la.run_id,la.before_seq) in (select * from unnest(%s::integer[],%s::integer[]))'
        arguments.extend([[run for run,seq in selected],[seq for run,seq in selected]])
    query+=' order by la.run_id,la.before_seq,la.n'
    for run_id,seq,date,n,name,param,integer,text in connection.execute(query,arguments).fetchall():
        dates[(run_id,seq)]=date
        batch=pauses.setdefault((run_id,seq),{})
        batch.setdefault(n,(name,{}))
        if param is not None:
            batch[n][1][param]=integer if text is None else text
    history=History(connection,ids,needed)
    holdings=Holdings(connection,ids,held)
    rows={run_id:[] for run_id in runs}
    for (run_id,seq),recorded in pauses.items():
        lookup=history.at(run_id,seq)
        date=dates[(run_id,seq)]
        if not lookup.available:
            continue
        baseline=outcomes.baseline(run_id,date)
        last=runs[run_id][1]
        if outcomes.reason(run_id,date,last,baseline) is not None:
            continue
        _,years,parts=outcomes.target(run_id,date,last,baseline)
        batch=list(recorded.values())
        acted=entries(batch,lookup,actions)
        values=context(SimpleNamespace(state=lookup),selection)
        rows[run_id].append(([values.get(name,np.nan) for name in STATE],[values.get(name,'none') for name in CATEGORIES],acted,holdings.at(lookup),
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
        database=(connection.info.dsn,NAME)
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
    state,categorical,acted,held,sizes,groups,changes,pauses=[],[],[],[],[],[],[],[]
    for run_id in runs:
        for numbers,active,actions,holdings,size,years,raw,seq in rows[run_id]:
            state.append(numbers)
            categorical.append(active)
            acted.append(actions)
            held.append(holdings)
            sizes.append(size)
            groups.append(run_id)
            pauses.append((run_id,seq))
            changes.append(reward(years,raw))
    y=changes
    return SimpleNamespace(y=np.array(y),runs=np.array(groups),played=len(runs),state=np.array(state,np.float32).reshape(len(y),len(STATE)),categories=np.array(categorical,object).reshape(len(y),len(CATEGORIES)),
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
        state=np.array([lookup.numbers+lookup.prices+lookup.institutions+lookup.tariffs+lookup.taxes]*count,np.float32)
        held=np.repeat(self.held.count([live_holdings(snapshot)],self.held_columns),count,0)
        actions=self.actions.count([entries(batch,lookup) for batch in batches],self.action_columns)
        sizes=np.array([[len(batch)] for batch in batches],np.float32)
        return frame(state,np.array([categories(lookup)]*count,object),held,sizes,actions,self.labels)
