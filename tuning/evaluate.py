import gc
import time

import numpy as np

from interface.common import evidence, timed
from .data import stored, training, validate_manifest
from .features import loaded_columns, selected_families
from .metrics import SPEC, differentiation, summarize
from .model import Monitor, PickerModel
from .storage import load, save, write


@timed
def evaluate(connection,directory,manifest,model,config,threads,seed,progress_path,output,loss_weights):
    started=time.monotonic()
    validate_manifest(manifest)
    points,baseline=[],[]
    groups=manifest['groups'][model]
    bounds={run:dates for run,*dates in manifest['bounds']}
    columns=loaded_columns(groups,config)
    families=None if model=='row' else selected_families(groups,config)
    stage={'training_runs':len(manifest['train']),'validation_runs':len(manifest['validation']),'timings':{}}
    def progress(step):
        now=time.time()
        if 'step' in stage:
            stage['timings'][stage['step']]=now-stage['step_started']
        stage.update(step=step,step_started=now,updated=now)
        write(progress_path,stage)
    progress('assemble training rows')
    if model=='row':
        features,y,_,weights=training(connection,{run:bounds[run] for run in manifest['train']},model,columns)
    else:
        features,y,weights=stored(directory,model,families)
    progress('fit')
    fitted=PickerModel(model,config,groups,threads,seed)
    fitted.fit(features,y,weights,Monitor(progress_path,stage,config['iterations']))
    rows=len(y)
    check=features.iloc[:min(100,len(y))].copy() if model=='row' else features[:min(100,len(y))]
    before=fitted.predict(check)
    del features,y,weights
    gc.collect()
    progress('score snapshots')
    candidates=load(directory/f'scoring_{model}.pkl.gz')
    targets,keys=candidates['targets'],candidates['pauses']
    predicted=fitted.predict(candidates['validation'],threads)
    options=fitted.predict(candidates['features'],threads).reshape(len(candidates['keys']),SPEC['candidates'][model])
    for (run,seq),scores in zip(candidates['keys'],options):
        mask=(keys[:,0]==run)&(keys[:,1]==seq)
        if not mask.any():
            raise ValueError(evidence(run=run,seq=seq))
        mse=float(np.mean((predicted[mask]-targets[mask])**2))
        constant_mse=float(np.mean((fitted.mean-targets[mask])**2))
        points.append({'run':run,'seq':seq,'mse':mse,'normalized_mse':mse/fitted.scale**2,'differentiation':differentiation(scores)})
        baseline.append({'run':run,'mse':constant_mse,'normalized_mse':constant_mse/fitted.scale**2,'differentiation':0.})
    del candidates
    progress('save model')
    save(output.with_suffix('.model.pkl.gz'),fitted)
    restored=load(output.with_suffix('.model.pkl.gz'))
    if not np.array_equal(before,restored.predict(check)):
        raise ValueError(evidence(output=output))
    save(output.with_suffix('.points.pkl.gz'),points)
    progress('completed')
    return {'metrics':summarize(points,loss_weights),'baseline':summarize(baseline,loss_weights),'training_rows':rows,'features':fitted.feature_count,
            'trees':fitted.estimator.tree_count_,'training_scale':fitted.scale,'train_ids':manifest['train'],
            'validation_ids':manifest['validation'],'timings':stage['timings'],'seconds':time.monotonic()-started}
