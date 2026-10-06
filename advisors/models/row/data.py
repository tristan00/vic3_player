from collections import defaultdict
import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from interface.common import timed, timed_often
from ...data.endgame import COMPONENTS, HISTORY, HOURS_PER_YEAR, OBJECTIVE, Trajectories, reward, scored_runs, target
from .features import CATEGORICAL, Historical, action_features, context, frame

LOG=logging.getLogger('loop')
OUTPUT=Path(__file__).resolve().parents[3]/'artifacts/row_model'
METADATA=['run','action_number','before_seq','baseline_seq','start_hour','end_hour','years',
          *[f'baseline.{name}' for name in COMPONENTS],*[f'reward_part.{name}' for name in COMPONENTS]]
ACTIONS='''select la.run_id,la.n,la.before_seq,s.game_date,a.name,p.name,p.integer_value,p.text_value
from loop_action la join advisor_action a using(advisor_action)
join snapshot s on s.run_id=la.run_id and s.seq=la.before_seq
left join loop_decision_param p on p.run_id=la.run_id and p.n=la.n
where la.run_id=any(%s)
order by la.run_id,la.n,p.name'''


@timed
def training_rows(connection,bounds):
    ids=list(bounds)
    history=Historical(connection,ids)
    outcomes=Trajectories(connection,ids)
    actions={}
    for run,n,seq,date,name,param,integer,text in connection.execute(ACTIONS,(ids,)).fetchall():
        item=actions.setdefault((run,n),(seq,date,name,{}))
        if param is not None:
            item[3][param]=integer if text is None else text
    rows,metadata,omitted=[],[],{run:defaultdict(int) for run in bounds}
    starts={}
    for (run,n),(seq,date,name,params) in actions.items():
        key=(run,seq)
        if key not in starts:
            point=history.at(run,seq)
            baseline=outcomes.baseline(run,date)
            last=bounds[run][1]
            reason=outcomes.reason(run,date,last,baseline)
            if reason is None and point.state.numbers is None:
                reason='missing_start_state'
            if reason:
                starts[key]=(reason,None)
            else:
                _,years,parts=outcomes.target(run,date,last,baseline)
                starts[key]=(None,(point,context(point),years,baseline,parts))
        reason,prepared=starts[key]
        if reason:
            omitted[run][reason]+=1
            continue
        point,state,years,baseline,parts=prepared
        rows.append({**state,**action_features(name,params,point)})
        metadata.append({'run':run,'action_number':n,'before_seq':seq,'baseline_seq':outcomes.starts[run,date],'start_hour':date,'end_hour':bounds[run][1],
                         'years':years,**{f'baseline.{c}':baseline[c] for c in COMPONENTS},**{f'reward_part.{c}':parts[c] for c in COMPONENTS}})
    return SimpleNamespace(X=frame(rows),meta=pd.DataFrame(metadata,columns=METADATA),omitted=omitted)


class TrainingCache:
    @timed_often
    def __init__(self):
        self.data=None
        self.versions={}
        self.database=None

    @timed
    def load(self,connection,bounds):
        database=connection.info.dsn
        if database!=self.database:
            self.data=None
            self.versions={}
            self.database=database
        missing={run:dates for run,dates in bounds.items() if self.versions.get(run)!=dates}
        if self.data is not None and self.versions==bounds:
            LOG.info('row training data reused %d runs, loaded 0 runs',len(bounds))
            return self.data
        found=training_rows(connection,missing) if missing else None
        kept=set(bounds)-set(missing)
        parts=[]
        if self.data is not None and kept:
            mask=self.data.meta.run.isin(kept)
            parts.append(SimpleNamespace(X=self.data.X.loc[mask],meta=self.data.meta.loc[mask],
                                         omitted={run:self.data.omitted[run] for run in kept}))
        if found is not None:
            parts.append(found)
        if parts:
            meta=pd.concat([part.meta for part in parts],ignore_index=True)
            order=np.lexsort((meta.action_number,meta.run))
            features=pd.concat([part.X for part in parts],ignore_index=True).iloc[order].reset_index(drop=True)
            features=features.astype({name:'category' for name in CATEGORICAL})
            data=SimpleNamespace(X=features,meta=meta.iloc[order].reset_index(drop=True),
                                 omitted={run:counts for part in parts for run,counts in part.omitted.items()})
        else:
            data=SimpleNamespace(X=frame([]),meta=pd.DataFrame(columns=METADATA),omitted={})
        self.data=data
        self.versions=dict(bounds)
        LOG.info('row training data reused %d runs, loaded %d runs',len(kept),len(missing))
        return data


@timed
def load(connection,runs=None,cache=None):
    bounds={run:(first,last,reason) for run,first,last,reason in connection.execute(HISTORY,scored_runs()).fetchall()}
    if runs is not None:
        bounds={run:bounds[run] for run in runs}
    data=training_rows(connection,bounds) if cache is None else cache.load(connection,bounds)
    if data.meta.empty:
        raise ValueError('No action rows have the required starting state and future outcomes')
    meta=data.meta.copy()
    y=reward(meta.years.to_numpy(),{name:meta[f'reward_part.{name}'].to_numpy() for name in COMPONENTS})
    meta.insert(5,'target',y)
    omitted=defaultdict(int)
    for counts in data.omitted.values():
        for reason,count in counts.items():
            omitted[reason]+=count
    LOG.info('row data: %d actions from %d runs; omitted %s',len(y),meta.run.nunique(),dict(omitted))
    return SimpleNamespace(X=data.X,y=y,runs=meta.run.to_numpy(),meta=meta,objective=OBJECTIVE,omitted=dict(omitted))


@timed_often
def split(runs,seed=19,fraction=.2):
    unique=np.unique(runs)
    if len(unique)<2:
        raise ValueError('Training and validation need at least two complete runs')
    chosen=np.random.default_rng(seed).permutation(unique)[:max(1,round(len(unique)*fraction))]
    test=np.isin(runs,chosen)
    return np.flatnonzero(~test),np.flatnonzero(test)
