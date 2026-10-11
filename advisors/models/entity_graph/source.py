import argparse
import bisect
from collections import Counter
import gzip
import json
from pathlib import Path
import pickle
import time

import numpy as np
import psycopg

from interface.common import evidence, timed, timed_often
from interface.recording.spec import TABLE
from interface.recording.store import DSN
from .schema import COMPONENTS, HORIZONS, PARAMETERS


@timed_often
def save(path, value):
    with gzip.open(path,'wb',compresslevel=1) as stream:
        pickle.dump(value,stream,pickle.HIGHEST_PROTOCOL)


@timed_often
def load(path):
    with gzip.open(path,'rb') as stream:
        return pickle.load(stream)


def keys(table):
    return ([] if table.owner is None else [table.owner])+[col.name for col in table.keys]


@timed_often
def replay(rows, key_count, versioned, sequences):
    result={}
    current={}
    position=0
    for seq in sequences:
        while position<len(rows) and rows[position][0]<=seq:
            row=rows[position]
            key=tuple(row[1:1+key_count])
            if versioned and not row[1+key_count]:
                current.pop(key,None)
            else:
                current[key]=tuple(row[1+key_count+int(versioned):])
            position+=1
        result[seq]=current.copy()
    return result


@timed_often
def records(snapshot, name):
    table=TABLE[name]
    names=[*keys(table),*[col.name for col in table.columns]]
    return [dict(zip(names,(*key,*value))) for key,value in snapshot.get(name,{}).items()]


@timed
def blocks(connection,run,start=None,stop=None):
    bounds=''
    args=[run]
    if start is not None:
        bounds+=' and la.before_seq>=%s'
        args.append(start)
    if stop is not None:
        bounds+=' and la.before_seq<%s'
        args.append(stop)
    rows=connection.execute('''select la.before_seq,la.n,a.name,p.name,p.integer_value,p.text_value
        from loop_action la join advisor_action a using(advisor_action)
        left join loop_decision_param p on p.run_id=la.run_id and p.n=la.n
        where la.run_id=%s '''+bounds+' order by la.n,p.name',args).fetchall()
    found={}
    for seq,n,name,param,integer,text in rows:
        action=found.setdefault(seq,{}).setdefault(n,[name,{}])
        if param is not None:
            action[1][param]=integer if text is None else text
    return {seq:list(actions.values()) for seq,actions in found.items()}


@timed
def outcomes(connection,run,player):
    from advisors.data.rewards import COSTS, built
    dates=dict(connection.execute('select seq,game_date from snapshot where run_id=%s order by seq',(run,)))
    series={}
    for name,query in {
        'gdp':'select seq,gdp from country_economy_report where run_id=%s and country=%s and present order by seq',
        'sol':'select seq,average_standard_of_living_by_population from country_standard_of_living_report where run_id=%s and country=%s and present order by seq',
        'population':'select seq,lower_strata+middle_strata+upper_strata from player_population where run_id=%s order by seq'
    }.items():
        series[name]=connection.execute(query,(run,) if name=='population' else (run,player)).fetchall()
    events=[]
    for seq,state,present,country in connection.execute('select seq,state,present,country from state_history where run_id=%s',(run,)):
        events.append((seq,0,state,country if present else None))
    for seq,building,present,kind,state,levels in connection.execute('''select b.seq,b.building,b.present,t.name,b.state,b.levels
        from building_history b left join building_type t using(building_type) where run_id=%s''',(run,)):
        if present and kind not in COSTS:
            continue
        events.append((seq,1,building,(state,COSTS[kind]*levels) if present else None))
    series['stock']=built(events,player,{seq:seq for seq in dates})
    return dates,series


@timed
def geography(connection,run):
    from .spatial import map_geometry
    provinces=connection.execute('''select p.province,w.state_region,t.name,w.area_pixels,w.x,w.y
        from province p join world_province w using(world_id,color) left join terrain t using(terrain)
        where p.run_id=%s order by p.province''',(run,)).fetchall()
    adjacency=connection.execute('''select a.province,b.province,w.shared_border_pixels
        from world_adjacency w join province a on a.world_id=w.world_id and a.color=w.first_color
        join province b on b.run_id=a.run_id and b.world_id=w.world_id and b.color=w.second_color
        where a.run_id=%s''',(run,)).fetchall()
    identities=dict(connection.execute('select color,province from province where run_id=%s',(run,)))
    files=dict(connection.execute('''select name,data from world_asset join run using(world_id)
        where run_id=%s and name in ('default.map','provinces.png','adjacencies.csv')''',(run,)))
    geometry=map_geometry(files,identities)
    borders=Counter({tuple(sorted((a,b))):n for a,b,n in adjacency})
    for a,b,n in geometry['seam']:
        borders[a,b]+=n
    return {'provinces':provinces,'adjacency':[(a,b,n) for (a,b),n in sorted(borders.items())],'map':geometry}


@timed
def candidates(connection,run,seq,count,seed,snapshot=None):
    from loop.run import redraw
    snapshot,drawn=redraw(connection,run,seq,count,seed,snapshot=snapshot)
    if len(drawn)!=count:
        raise ValueError(evidence(run=run,seq=seq,drawn=len(drawn),count=count))
    for block in drawn:
        if not block:
            raise ValueError(evidence(run=run,seq=seq,block=block))
        for name,params in block:
            if set(params)!=set(PARAMETERS[name]):
                raise ValueError(evidence(name=name,params=params,expected=PARAMETERS[name]))
    return drawn


@timed_often
def labels(seq,dates,series):
    start=dates[seq]
    last=max(dates.values())
    baseline=np.zeros(len(COMPONENTS),np.float64)
    target=np.zeros((len(HORIZONS),len(COMPONENTS)),np.float32)
    mask=np.zeros_like(target,dtype=bool)
    ages=np.zeros_like(target)
    for j,name in enumerate(COMPONENTS):
        points=series[name]
        before=bisect.bisect_right([s for s,_ in points],seq)-1
        if before<0 or points[before][1] is None or not np.isfinite(points[before][1]) or points[before][1]<=0:
            continue
        base=points[before][1]
        baseline[j]=base
        hours=[dates[s] for s,_ in points]
        for i,days in enumerate(HORIZONS):
            hour=start+days*24
            if hour>last:
                continue
            at=bisect.bisect_right(hours,hour)-1
            value=points[at][1]
            if value is None or not np.isfinite(value) or value<0:
                continue
            target[i,j]=np.log(max(value/base,1e-12))
            mask[i,j]=True
            ages[i,j]=(hour-hours[at])/24
    return baseline,target,mask,ages


@timed
def prepare(output,seed=20261001):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic()
    with psycopg.connect(DSN) as connection:
        connection.execute('set transaction isolation level repeatable read read only')
        connection.execute('set statement_timeout=120000')
        runs=connection.execute("select run_id,player_country from run where kind='mini' and ended_at is not null order by run_id").fetchall()
        ordering=np.random.default_rng(seed).permutation([r for r,_ in runs])
        a,b=int(len(runs)*.6),int(len(runs)*.8)
        splits={int(run):'train' if i<a else 'validation' if i<b else 'test' for i,run in enumerate(ordering)}
        index=[]
        total_pauses=0
        for run,player in runs:
            actions=blocks(connection,run)
            dates,series=outcomes(connection,run,player)
            total_pauses+=len(actions)
            tasks=[]
            for seq in sorted(actions):
                base,y,mask,age=labels(seq,dates,series)
                tasks.append({'run':run,'seq':seq,'hour':dates[seq],'split':splits[run],'history':[],
                              'actions':actions[seq],'baseline':base,'y':y,'mask':mask,'age':age})
                index.append({'run':run,'seq':seq,'split':splits[run],'actions':len(actions[seq]),
                              'history':[],'observed':mask[:,0].tolist()})
            save(output/f'run_{run}.pkl.gz',{'run':run,'player':player,'dates':dates,'tasks':tasks})
            print(json.dumps({'stage':'source','run':run,'tasks':len(tasks),'total_tasks':len(index),'seconds':round(time.monotonic()-started,2)}),flush=True)
        result={'seed':seed,'horizons_days':HORIZONS,'components':COMPONENTS,
                'frozen_runs':[r for r,_ in runs],'split_runs':splits,'total_recorded_pauses':total_pauses,
                'coverage':'all_recorded_decisions',
                'tasks':index,'seconds':time.monotonic()-started}
        (output/'dataset.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    prepare(args.output)


if __name__=='__main__':
    main()
