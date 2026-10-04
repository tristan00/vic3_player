import argparse
import json
import multiprocessing
from pathlib import Path
import pickle
import time

import numpy as np
import pandas as pd

from interface.common import timed
from .features import CATEGORICAL
from .model import Model, PARAMETERS
from .validation import METRIC, Validation, winner


@timed
def fit_stage(source,params,output,name):
    with source.open('rb') as stream:
        data=pickle.load(stream)
    if set(data.runs[data.train])&set(data.runs[data.test]):
        raise ValueError('Training and validation runs overlap')
    metric=Validation(data.y[data.train],data.y[data.test],data.meta.iloc[data.test])
    data.X=data.X.astype({column:'category' for column in CATEGORICAL})
    started=time.monotonic()
    model=Model(params).fit(data.X if name=='model' else data.X.iloc[data.train],
                            data.y if name=='model' else data.y[data.train])
    seconds=time.monotonic()-started
    if model.estimator.tree_count_!=50:
        raise RuntimeError('Finalization must retain exactly 50 trees')
    predictions=model.predict(data.X.iloc[data.test])
    model.save(output/f'{name}.cbm')
    loaded=Model.load(output/f'{name}.cbm')
    np.testing.assert_array_equal(loaded.predict(data.X.iloc[data.test]),predictions)
    if name=='validation':
        observed=data.meta.iloc[data.test].copy()
        observed['prediction']=predictions
        observed.to_csv(output/'validation.csv',index=False)
    result={'metrics':metric.score(predictions),'validation':metric.configuration(),'fit_seconds':seconds,
            'training_rows':len(data.train),'validation_rows':len(data.test),'production_rows':len(data.y)}
    if name=='model':
        result['importance']=sorted(model.importance(),key=lambda row:-row[1])
    (output/f'{name}_metrics.json').write_text(json.dumps(result,indent=2))


@timed
def run_fit(source,params,output,name,seconds):
    started=time.monotonic()
    process=multiprocessing.get_context('spawn').Process(target=fit_stage,args=(source,params,output,name))
    process.start()
    process.join(max(0,seconds-(time.monotonic()-started)))
    if process.is_alive():
        process.kill()
        process.join()
        raise TimeoutError(f'{name} exceeded its {seconds}-second hard wall-clock limit')
    if process.exitcode:
        raise RuntimeError(f'{name} worker exited with code {process.exitcode}')
    return json.loads((output/f'{name}_metrics.json').read_text())


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args()
    output=args.directory
    started=time.monotonic()
    if (output/'cancelled.json').exists():
        raise RuntimeError('This search was cancelled and cannot be finalized')
    config=json.loads((output/'search.json').read_text())
    if config['validation']['name']!=METRIC['name']:
        raise RuntimeError('This search used a different validation metric')
    status=json.loads((output/'status.json').read_text())
    if status['finished']!=status['requested']:
        raise RuntimeError('The parameter search is still running')
    trials=[json.loads(path.read_text()) for path in output.glob('trial_*.json')]
    if len(trials)!=status['requested']:
        raise RuntimeError('The search is missing trial results')
    selected=winner(trials)
    params={**selected['params'],'thread_count':selected['threads']}
    source=Path(config['data'])
    seconds=config['seconds_per_trial']
    validation=run_fit(source,params,output,'validation',seconds)
    if validation['validation']!=config['validation']:
        raise RuntimeError('Validation data or objective differs from the parameter search')
    metrics=validation['metrics']
    for name,value in metrics.items():
        if not np.isclose(value,selected[name],rtol=1e-6,atol=1e-7):
            raise RuntimeError(f'Selected model did not reproduce {name}: {value} versus {selected[name]}')
    previous=run_fit(source,config['incumbent_params'],output,'incumbent',seconds)['metrics']
    final=run_fit(source,params,output,'model',seconds)
    report={'trials':len(trials),'winner':selected,'selected_params':params,'validation':config['validation'],
            'selected_metrics':metrics,'incumbent_metrics':previous,'score_improvement':1-metrics['score']/previous['score'],
            'training_rows':final['training_rows'],'validation_rows':final['validation_rows'],
            'production_rows':final['production_rows'],'production_fit_seconds':final['fit_seconds'],
            'search_wall_seconds':status['seconds'],'trial_seconds':sum(row['wall_seconds'] for row in trials),
            'finalization_seconds':time.monotonic()-started,'importance':final['importance']}
    (output/'report.json').write_text(json.dumps(report,indent=2))
    pd.DataFrame([{key:value for key,value in row.items() if key!='params'}|row.get('params',{}) for row in trials]).sort_values('trial').to_csv(output/'trials.csv',index=False)
    temporary=PARAMETERS.with_suffix('.tmp')
    temporary.write_text(json.dumps(params,indent=2)+'\n')
    temporary.replace(PARAMETERS)
    print(json.dumps({key:value for key,value in report.items() if key not in ('importance','winner')}),flush=True)


if __name__=='__main__':
    main()
