from datetime import datetime, timezone
import logging

import numpy as np
import psycopg

from advisors.catalogue import NAMES
from advisors.data.endgame import HISTORY, OBJECTIVE, REWARD_COMPONENTS, reward, scored_runs
from advisors.data.features import CATEGORIES, LiveLookup, categories
from advisors.data.histograms import entries, live_holdings
from advisors.models.histogram import data as batch
from advisors.models.row import data as action
from advisors.models.row import features as row
from interface.common import timed
from interface.options.stored import Shared, Stored
from interface.recording.store import DSN
from . import VERSION
from .features import taxonomy
from .storage import digest, read, save, source_digest, write

LOG=logging.getLogger('tuning')


@timed
def batch_records(rows):
    return [{'state':{**dict(zip(batch.STATE,numbers)),**dict(zip(CATEGORIES,categorical))},'actions':acted,'held':held,
             'size':size[0],'y':float(reward(years,parts)),'seq':int(seq)}
            for numbers,categorical,acted,held,size,years,parts,seq in rows]


@timed
def blueprint(bounds,seed,points_per_run):
    return {'version':VERSION,'seed':seed,'points_per_run':points_per_run,'objective':OBJECTIVE,'bounds':bounds,'empty':[],
              'created_at':datetime.now(timezone.utc).isoformat(),'source_digest':source_digest(),
              'weights':{name:1. for name in NAMES},'groups':{model:taxonomy(model) for model in ('histogram','row')},'runs':[],'files':{}}


@timed
def prepare(directory,seed=19,points_per_run=12,progress=None):
    if points_per_run<1:
        raise ValueError('Preparation needs at least one snapshot per validation run')
    directory.mkdir(parents=True,exist_ok=True)
    checkpoint=directory/'preparation.json'
    with psycopg.connect(DSN,connect_timeout=5) as connection:
        connection.execute('set transaction isolation level repeatable read read only')
        if checkpoint.exists():
            manifest=read(checkpoint)
            if manifest['seed']!=seed or manifest['points_per_run']!=points_per_run or manifest['objective']!=OBJECTIVE or manifest['groups']!={model:taxonomy(model) for model in ('histogram','row')}:
                raise ValueError('Preparation settings or schema changed')
            for name,expected in manifest['files'].items():
                if digest(directory/name)!=expected:
                    raise ValueError(f'Prepared file changed: {name}')
        else:
            manifest=blueprint(connection.execute(HISTORY,scored_runs()).fetchall(),seed,points_per_run)
            write(checkpoint,manifest)
        finished={item['run'] for item in manifest['runs']}|set(manifest['empty'])
        for index,(run,*dates) in enumerate(manifest['bounds']):
            if run in finished:
                continue
            if progress:
                progress({'phase':'prepare','step':'training rows','run':run,'done':index,'total':len(manifest['bounds'])})
            records=batch_records(batch.training_rows(connection,{run:dates})[run])
            if not records:
                manifest['empty'].append(run)
                write(checkpoint,manifest)
                continue
            available=sorted({record['seq'] for record in records})
            selected=sorted(np.random.default_rng(np.random.SeedSequence([seed,run])).choice(available,min(points_per_run,len(available)),replace=False).tolist())
            manifest['runs'].append({'run':run,'batch_rows':len(records),'action_rows':sum(record['size'] for record in records),'snapshots':selected})
            write(checkpoint,manifest)
        partition(manifest)
        shared=Shared(connection)
        try:
            for index,run in enumerate(manifest['validation']):
                path=directory/f'candidates_{run}.pkl.gz'
                if path.name in manifest['files']:
                    continue
                selected=next(item['snapshots'] for item in manifest['runs'] if item['run']==run)
                candidates=[]
                for number,seq in enumerate(selected):
                    if progress:
                        progress({'phase':'prepare','step':'100 candidate batches and 100 actions','run':run,'snapshot':seq,
                                  'done':index,'total':len(manifest['validation']),'snapshot_done':number,'snapshot_total':len(selected)})
                    from loop.run import redraw
                    snapshot=Stored(connection,run,seq,shared)
                    draw_seed=int(np.random.SeedSequence([seed,run,seq]).generate_state(1)[0])
                    _,blocks=redraw(connection,run,seq,100,draw_seed,weights=manifest['weights'],snapshot=snapshot)
                    if len(blocks)!=100 or any(not block for block in blocks):
                        raise ValueError(f'Candidate generator failed at {run}/{seq}')
                    lookup=LiveLookup(snapshot)
                    context={**dict(zip(batch.STATE,lookup.numbers+lookup.prices+lookup.institutions+lookup.tariffs+lookup.taxes)),
                             **dict(zip(CATEGORIES,categories(lookup)))}
                    held=live_holdings(snapshot)
                    generated=[{'state':context,'actions':entries(block,lookup),'held':held,'size':len(block)} for block in blocks]
                    flattened=[item for block in blocks for item in block]
                    chosen=np.random.default_rng(draw_seed).choice(len(flattened),100,replace=False)
                    sampled=[flattened[i] for i in chosen]
                    candidates.append({'run':run,'seq':seq,'seed':draw_seed,'batch_lengths':[len(block) for block in blocks],
                                       'action_indices':chosen.tolist(),'histogram':generated,'row':row.live(snapshot,sampled)})
                save(path,candidates)
                manifest['files'][path.name]=digest(path)
                write(checkpoint,manifest)
        finally:
            shared.close()
    validate_manifest(manifest)
    needed={f'candidates_{run}.pkl.gz' for run in manifest['validation']}
    manifest['files']={name:value for name,value in manifest['files'].items() if name in needed}
    write(directory/'dataset.json',manifest)
    return manifest


@timed
def partition(manifest):
    runs=np.random.default_rng(manifest['seed']).permutation([item['run'] for item in manifest['runs']]).tolist()
    if len(runs)<3:
        raise ValueError('Need at least three eligible runs')
    count=max(1,int(round(len(runs)*.2)))
    manifest['validation'],manifest['train']=runs[:count],runs[count:]


@timed
def validate_manifest(manifest):
    runs={item['run'] for item in manifest['runs']}
    train,validation=set(manifest['train']),set(manifest['validation'])
    if manifest['version']!=VERSION or len(train)<2 or not validation or train&validation or train|validation!=runs:
        raise ValueError('Training and validation runs must form a disjoint partition')
    if len(train)!=len(manifest['train']) or len(validation)!=len(manifest['validation']) or len(runs)!=len(manifest['runs']):
        raise ValueError('Duplicate run assignments')


@timed
def verify(directory):
    manifest=read(directory/'dataset.json')
    validate_manifest(manifest)
    if manifest['objective']!=OBJECTIVE or manifest['groups']!={model:taxonomy(model) for model in ('histogram','row')}:
        raise ValueError('Dataset objective or feature schema changed; prepare a fresh dataset')
    for run in manifest['validation']:
        name=f'candidates_{run}.pkl.gz'
        if digest(directory/name)!=manifest['files'][name]:
            raise ValueError(f'Dataset checksum mismatch: {name}')
    return manifest


@timed
def training(connection,bounds,model,columns=None,snapshots=None,families=None):
    if model=='histogram':
        found={run:batch_records(rows) for run,rows in batch.training_rows(connection,bounds,columns,families,snapshots).items()}
        features=[record for records in found.values() for record in records]
        y=np.asarray([record['y'] for record in features])
        keys=np.asarray([(run,record['seq']) for run,records in found.items() for record in records])
    else:
        data=action.training_rows(connection,bounds,columns,snapshots)
        features=data.X
        meta=data.meta
        y=reward(meta.years.to_numpy(),{name:meta[f'reward_part.{name}'].to_numpy() for name in REWARD_COMPONENTS})
        keys=meta[['run','before_seq']].to_numpy()
    if not len(y) or not np.isfinite(y).all():
        raise ValueError('Database training rows require finite reward targets')
    starts,indices,counts=np.unique(keys,axis=0,return_inverse=True,return_counts=True)
    runs,run_indices,snapshots=np.unique(starts[:,0],return_inverse=True,return_counts=True)
    weights=len(y)/len(runs)/(counts[indices]*snapshots[run_indices[indices]])
    return features,y,keys,weights
