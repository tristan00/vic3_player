from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import logging
import time

import numpy as np
import pandas as pd
import psycopg

from advisors.catalogue import LENGTHS, NAMES
from advisors.data.endgame import HISTORY, OBJECTIVE, REWARD_COMPONENTS, reward, scored_runs
from advisors.data.features import CATEGORIES, LiveLookup, categories
from advisors.data.histograms import entries, live_holdings
from advisors.models.histogram import data as batch
from advisors.models.row import data as action
from advisors.models.row import features as row
from interface.common import evidence, timed, timed_often
from interface.options.stored import Shared, Stored
from interface.recording.store import DSN
from . import VERSION
from .features import taxonomy
from .storage import digest, load, read, save, source_digest, write

LOG=logging.getLogger('tuning')
DRAWN=frozenset({'histogram','row'})
DRAWERS=12


@timed
def batch_records(rows):
    return [{'state':{**dict(zip(batch.STATE,numbers)),**dict(zip(CATEGORIES,categorical))},'actions':acted,'held':held,
             'size':size[0],'y':float(reward(years,parts)),'seq':int(seq)}
            for numbers,categorical,acted,held,size,years,parts,seq in rows]


@timed
def blueprint(bounds,seed,points_per_run,models):
    return {'version':VERSION,'seed':seed,'points_per_run':points_per_run,'objective':OBJECTIVE,'bounds':bounds,'empty':[],
              'created_at':datetime.now(timezone.utc).isoformat(),'source_digest':source_digest(),
              'weights':{name:1. for name in NAMES},'groups':{model:taxonomy(model) for model in models},'runs':[],'files':{}}


@timed
def prepare(directory,models,seed=19,points_per_run=12,progress=None):
    if points_per_run<1:
        raise ValueError(evidence(points_per_run=points_per_run))
    directory.mkdir(parents=True,exist_ok=True)
    checkpoint=directory/'preparation.json'
    with psycopg.connect(DSN,connect_timeout=5) as connection:
        connection.execute('set transaction isolation level repeatable read read only')
        if checkpoint.exists():
            manifest=read(checkpoint)
            if manifest['seed']!=seed or manifest['points_per_run']!=points_per_run or manifest['objective']!=OBJECTIVE or manifest['groups']!={model:taxonomy(model) for model in models}:
                raise ValueError(evidence(seed=manifest['seed'],given_seed=seed,points_per_run=manifest['points_per_run'],given_points_per_run=points_per_run,objective_match=manifest['objective']==OBJECTIVE,groups_match=manifest['groups']=={model:taxonomy(model) for model in models}))
            for name,expected in manifest['files'].items():
                if digest(directory/name)!=expected:
                    raise ValueError(evidence(name=name,digest=digest(directory/name),expected=expected))
        else:
            manifest=blueprint(connection.execute(HISTORY,scored_runs()).fetchall(),seed,points_per_run,models)
            write(checkpoint,manifest)
        if not manifest['runs']:
            if progress:
                progress({'phase':'prepare','step':'pauses','total':len(manifest['bounds'])})
            found=batch.training_rows(connection,{run:dates for run,*dates in manifest['bounds']},[],{'actions':set(),'held':set()})
            manifest['empty']=[run for run,rows in found.items() if not rows]
            for run,rows in found.items():
                records=batch_records(rows)
                available=sorted({record['seq'] for record in records})
                if available:
                    selected=sorted(np.random.default_rng(np.random.SeedSequence([seed,run])).choice(available,min(points_per_run,len(available)),replace=False).tolist())
                    manifest['runs'].append({'run':run,'batch_rows':len(records),'action_rows':sum(record['size'] for record in records),'snapshots':selected})
            write(checkpoint,manifest)
        partition(manifest)
        if DRAWN.intersection(models):
            draw(connection,directory,manifest,progress)
        validate_manifest(manifest)
        needed={f'candidates_{run}.pkl.gz' for run in manifest['validation']}
        manifest['files']={name:value for name,value in manifest['files'].items() if name in needed}
        pack(connection,directory,manifest)
    write(directory/'dataset.json',manifest)
    return manifest


@timed
def candidates(dsn,directory,seed,weights,run,selected):
    from loop.run import redraw
    started=time.monotonic()
    found,rows=[],[]
    with psycopg.connect(dsn,connect_timeout=5) as connection:
        connection.execute('set transaction isolation level repeatable read read only')
        shared=Shared(connection,1)
        try:
            for seq in selected:
                snapshot=Stored(connection,run,seq,shared)
                draw_seed=int(np.random.SeedSequence([seed,run,seq]).generate_state(1)[0])
                _,blocks=redraw(connection,run,seq,100,draw_seed,weights=weights,snapshot=snapshot)
                if len(blocks)!=100 or any(not block for block in blocks):
                    raise ValueError(evidence(run=run,seq=seq,blocks=len(blocks),empty=sum(not block for block in blocks)))
                lookup=LiveLookup(snapshot)
                context={**dict(zip(batch.STATE,lookup.numbers+lookup.prices+lookup.institutions+lookup.tariffs+lookup.taxes)),
                         **dict(zip(CATEGORIES,categories(lookup)))}
                held=live_holdings(snapshot)
                generated=[{'state':context,'actions':entries(block,lookup),'held':held,'size':len(block)} for block in blocks]
                flattened=[item for block in blocks for item in block]
                chosen=np.random.default_rng(draw_seed).choice(len(flattened),100,replace=False)
                rows+=row.described(snapshot,[flattened[i] for i in chosen])
                found.append({'run':run,'seq':seq,'seed':draw_seed,'batch_lengths':[len(block) for block in blocks],
                              'action_indices':chosen.tolist(),'histogram':generated})
        finally:
            shared.close()
    path=directory/f'candidates_{run}.pkl.gz'
    save(path,{'snapshots':found,'row':row.frame(rows)})
    return path.name,digest(path),time.monotonic()-started


@timed
def draw(connection,directory,manifest,progress):
    validation=set(manifest['validation'])
    pending=[item for item in manifest['runs'] if item['run'] in validation and f"candidates_{item['run']}.pkl.gz" not in manifest['files']]
    if not pending:
        return
    with ProcessPoolExecutor(min(DRAWERS,len(pending))) as pool:
        jobs=[pool.submit(candidates,connection.info.dsn,directory,manifest['seed'],manifest['weights'],item['run'],item['snapshots']) for item in pending]
        for done,job in enumerate(as_completed(jobs),1):
            name,found,seconds=job.result()
            manifest['files'][name]=found
            write(directory/'preparation.json',manifest)
            LOG.info('%s drawn in %.1fs, %d of %d',name,seconds,done,len(pending))
            if progress:
                progress({'phase':'prepare','step':'100 candidate batches and 100 actions','done':done,'total':len(pending)})


@timed
def pack(connection,directory,manifest):
    bounds={run:dates for run,*dates in manifest['bounds']}
    snapshots={item['run']:item['snapshots'] for item in manifest['runs']}
    drawn={}
    if DRAWN.intersection(manifest['groups']):
        keys,records,frames=[],[],[]
        for run in manifest['validation']:
            found=load(directory/f'candidates_{run}.pkl.gz')
            frames.append(found['row'])
            for candidate in found['snapshots']:
                keys.append((candidate['run'],candidate['seq']))
                records.extend(candidate['histogram'])
        joined={}
        for name in frames[0].columns:
            parts=[frame[name] for frame in frames]
            joined[name]=pd.api.types.union_categoricals(parts) if isinstance(parts[0].dtype,pd.CategoricalDtype) else np.concatenate([part.to_numpy() for part in parts])
        drawn={'histogram':(keys,records),'row':(keys,pd.DataFrame(joined,copy=False))}
    for model in manifest['groups']:
        validation,targets,pauses,_=training(connection,{run:bounds[run] for run in manifest['validation']},model,snapshots=snapshots)
        if model=='size':
            drawn[model]=([tuple(pause) for pause in pauses.tolist()],[{**record,'size':length} for record in validation for length in LENGTHS])
        keys,features=drawn[model]
        path=directory/f'scoring_{model}.pkl.gz'
        save(path,{'keys':keys,'features':features,'validation':validation,'targets':targets,'pauses':pauses})
        manifest['files'][path.name]=digest(path)
        if model!='row':
            records,targets,_,weights=training(connection,{run:bounds[run] for run in manifest['train']},model)
            path=directory/f'training_{model}.pkl.gz'
            save(path,{'records':[{'state':record['state'],'size':record['size'],**{source:grouped(record[source]) for source in ('actions','held')}} for record in records],
                       'targets':targets,'weights':weights})
            manifest['files'][path.name]=digest(path)


@timed_often
def grouped(entries):
    found={}
    for entry in entries:
        found.setdefault(entry[0],[]).append(entry)
    return found


@timed
def stored(directory,model,families):
    found=load(directory/f'training_{model}.pkl.gz')
    records=[{'state':record['state'],'size':record['size'],**{source:[entry for family in families[source] for entry in record[source].get(family,())] for source in ('actions','held')}}
             for record in found['records']]
    return records,found['targets'],found['weights']


@timed
def partition(manifest):
    runs=np.random.default_rng(manifest['seed']).permutation([item['run'] for item in manifest['runs']]).tolist()
    if len(runs)<3:
        raise ValueError(evidence(runs=runs))
    count=max(1,int(round(len(runs)*.2)))
    manifest['validation'],manifest['train']=runs[:count],runs[count:]


@timed
def validate_manifest(manifest):
    runs={item['run'] for item in manifest['runs']}
    train,validation=set(manifest['train']),set(manifest['validation'])
    if manifest['version']!=VERSION or len(train)<2 or not validation or train&validation or train|validation!=runs:
        raise ValueError(evidence(version=manifest['version'],expected=VERSION,train=len(train),validation=len(validation),shared=sorted(train&validation),unassigned=sorted(runs^(train|validation))))
    if len(train)!=len(manifest['train']) or len(validation)!=len(manifest['validation']) or len(runs)!=len(manifest['runs']):
        raise ValueError(evidence(train=len(train),listed_train=len(manifest['train']),validation=len(validation),listed_validation=len(manifest['validation']),runs=len(runs),listed_runs=len(manifest['runs'])))


@timed
def verify(directory,models):
    manifest=read(directory/'dataset.json')
    validate_manifest(manifest)
    if manifest['objective']!=OBJECTIVE or not set(models)<=set(manifest['groups']) or manifest['groups']!={model:taxonomy(model) for model in manifest['groups']}:
        raise ValueError(evidence(objective=manifest['objective'],current_objective=OBJECTIVE,models=models,prepared=sorted(manifest['groups']),
                                  groups_match=manifest['groups']=={model:taxonomy(model) for model in manifest['groups']}))
    for name,expected in manifest['files'].items():
        if digest(directory/name)!=expected:
            raise ValueError(evidence(name=name,digest=digest(directory/name),expected=expected))
    return manifest


@timed
def training(connection,bounds,model,columns=None,snapshots=None,families=None):
    if model!='row':
        if model=='size' and families is None:
            families={'actions':set(),'held':None}
        found={run:batch_records(rows) for run,rows in batch.training_rows(connection,bounds,columns,families,snapshots).items()}
        features=[record for records in found.values() for record in records]
        y=np.asarray([record['y'] for record in features])
        keys=np.asarray([(run,record['seq']) for run,records in found.items() for record in records])
    else:
        data=action.gathered(connection,bounds,columns,snapshots)
        features=data.X
        meta=data.meta
        y=reward(meta.years.to_numpy(),{name:meta[f'reward_part.{name}'].to_numpy() for name in REWARD_COMPONENTS})
        keys=meta[['run','before_seq']].to_numpy()
    if not len(y) or not np.isfinite(y).all():
        raise ValueError(evidence(rows=len(y),finite=bool(np.isfinite(y).all())))
    starts,indices,counts=np.unique(keys,axis=0,return_inverse=True,return_counts=True)
    runs,run_indices,snapshots=np.unique(starts[:,0],return_inverse=True,return_counts=True)
    weights=len(y)/len(runs)/(counts[indices]*snapshots[run_indices[indices]])
    return features,y,keys,weights
