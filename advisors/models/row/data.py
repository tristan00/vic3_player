from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat
import logging
from pathlib import Path
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd
import psycopg

from interface.common import evidence, timed, timed_often
from interface.timing import RECORDER
from ...data.endgame import COMPONENTS, HISTORY, NAME, OBJECTIVE, REWARD_COMPONENTS, Trajectories, reward, scored_runs
from .features import CATEGORICAL, NUMERIC, PLAYER_FIELDS, SITE, STATE_REPORTS, Historical, Selection, action_features, context, frame
from .batch import characters, parameters, sites

LOG=logging.getLogger('loop')
LOADERS=8
OUTPUT=Path(__file__).resolve().parents[3]/'artifacts/row_model'
METADATA=['run','action_number','before_seq','baseline_seq','start_hour','end_hour','years',
          *[f'baseline.{name}' for name in COMPONENTS],*[f'reward_part.{name}' for name in REWARD_COMPONENTS]]
ACTIONS='''select la.run_id,la.n,la.before_seq,s.game_date,a.name,p.name,p.integer_value,p.text_value
from loop_action la join advisor_action a using(advisor_action)
join snapshot s on s.run_id=la.run_id and s.seq=la.before_seq
left join loop_decision_param p on p.run_id=la.run_id and p.n=la.n
where la.run_id=any(%s)'''


@timed
def training_rows(connection,bounds,columns=None,snapshots=None):
    columns=NUMERIC+CATEGORICAL if columns is None else columns
    selection=Selection(columns)
    site_columns=SITE+[f'site.{name}' for names in STATE_REPORTS.values() for name in names]
    remaining=[name for name in columns if name not in site_columns and not name.startswith(('parameter.','target_character.trait.','site.trait.'))]
    special=Selection([name for name in remaining if name not in PLAYER_FIELDS])
    started=time.monotonic()
    ids=list(bounds)
    history=Historical(connection,ids,Selection(remaining))
    outcomes=Trajectories(connection,ids)
    actions={}
    query,arguments=ACTIONS,[ids]
    if snapshots is not None:
        selected=[(run,seq) for run in ids for seq in snapshots[run]]
        query+=' and (la.run_id,la.before_seq) in (select * from unnest(%s::integer[],%s::integer[]))'
        arguments.extend([[run for run,seq in selected],[seq for run,seq in selected]])
    query+=' order by la.run_id,la.n,p.name'
    for run,n,seq,date,name,param,integer,text in connection.execute(query,arguments).fetchall():
        item=actions.setdefault((run,n),(seq,date,name,{}))
        if param is not None:
            item[3][param]=integer if text is None else text
    LOG.info('row source runs %d actions %d %.3fs',len(ids),len(actions),time.monotonic()-started)
    rows,metadata,omitted=[],[],{run:defaultdict(int) for run in bounds}
    requested=[]
    contexts,indices=[],[]
    starts={}
    counts=Counter((run,seq) for (run,n),(seq,date,name,params) in actions.items())
    for (run,n),(seq,date,name,params) in actions.items():
        key=(run,seq)
        if key not in starts:
            point=history.at(run,seq)
            baseline=outcomes.baseline(run,date)
            last=bounds[run][1]
            reason=outcomes.reason(run,date,last,baseline)
            if reason is None and not point.state.available:
                reason='missing_start_state'
            if reason:
                starts[key]=(reason,None)
            else:
                _,years,parts=outcomes.target(run,date,last,baseline)
                starts[key]=(None,(point,len(contexts),years,baseline,parts))
                contexts.append(context(point,selection))
        reason,prepared=starts[key]
        counts[key]-=1
        if not counts[key]:
            del starts[key]
        if reason:
            omitted[run][reason]+=1
            continue
        point,state,years,baseline,parts=prepared
        rows.append(action_features(name,params,point,special))
        requested.append((run,seq,date,name,params))
        indices.append(state)
        metadata.append({'run':run,'action_number':n,'before_seq':seq,'baseline_seq':outcomes.starts[run,date],'start_hour':date,'end_hour':bounds[run][1],
                         'years':years,**{f'baseline.{c}':baseline[c] for c in COMPONENTS},**{f'reward_part.{c}':parts[c] for c in REWARD_COMPONENTS}})
    LOG.info('row assembled rows %d snapshots %d columns %d %.3fs',len(rows),len(contexts),len(columns),time.monotonic()-started)
    states=frame(contexts,[name for name in PLAYER_FIELDS if name in columns]).iloc[indices].reset_index(drop=True)
    actions=frame(rows,[name for name in columns if name in special.names])
    selected=parameters(connection,requested,selection)
    placed=sites(connection,requested,selection)
    traits=characters(connection,requested,selection)
    features=pd.concat([states,actions,selected,placed,traits],axis=1).reindex(columns=columns)
    return SimpleNamespace(X=features,meta=pd.DataFrame(metadata,columns=METADATA),omitted=omitted)


@timed
def share(dsn,bounds,columns,snapshots):
    RECORDER.reset()
    with psycopg.connect(dsn,connect_timeout=5) as connection:
        connection.execute('set transaction isolation level repeatable read read only')
        data=training_rows(connection,bounds,columns,snapshots)
    return data,RECORDER.take()


@timed
def gathered(connection,bounds,columns=None,snapshots=None):
    ids=sorted(bounds)
    count=min(LOADERS,len(ids))
    if count<2:
        return training_rows(connection,bounds,columns,snapshots)
    shares=[{run:bounds[run] for run in ids[start::count]} for start in range(count)]
    with ProcessPoolExecutor(count) as pool:
        found=list(pool.map(share,repeat(connection.info.dsn),shares,repeat(columns),repeat(snapshots)))
    for _,timings in found:
        RECORDER.merge(timings)
    omitted={run:counts for data,_ in found for run,counts in data.omitted.items()}
    parts=[data for data,_ in found if len(data.meta)] or [found[0][0]]
    meta=pd.concat([part.meta for part in parts],ignore_index=True)
    order=np.lexsort((meta.action_number.to_numpy(),meta.run.to_numpy()))
    joined={}
    for name in parts[0].X.columns:
        pieces=[part.X[name] for part in parts]
        whole=(pd.api.types.union_categoricals(pieces,sort_categories=True) if isinstance(pieces[0].dtype,pd.CategoricalDtype)
               else np.concatenate([piece.to_numpy() for piece in pieces]))
        joined[name]=whole.take(order)
    LOG.info('row gathered rows %d runs %d loaders %d',len(meta),len(ids),count)
    return SimpleNamespace(X=pd.DataFrame(joined,index=range(len(meta)),copy=False),meta=meta.iloc[order].reset_index(drop=True),
                           omitted={run:omitted[run] for run in bounds})


class TrainingCache:
    @timed_often
    def __init__(self):
        self.data=None
        self.versions={}
        self.database=None

    @timed
    def load(self,connection,bounds):
        database=(connection.info.dsn,NAME)
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
        raise ValueError(evidence(rows=len(data.meta),runs=len(bounds)))
    meta=data.meta.copy()
    y=reward(meta.years.to_numpy(),{name:meta[f'reward_part.{name}'].to_numpy() for name in REWARD_COMPONENTS})
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
        raise ValueError(evidence(runs=unique))
    chosen=np.random.default_rng(seed).permutation(unique)[:max(1,round(len(unique)*fraction))]
    test=np.isin(runs,chosen)
    return np.flatnonzero(~test),np.flatnonzero(test)
