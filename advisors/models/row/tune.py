import argparse
import json
import logging
from pathlib import Path
import pickle
import subprocess
import sys
import time

import numpy as np

from interface.common import timed, timed_often
from ..boosting import Regressor
from ..forest import propose
from .. import search_space
from ..search_space import DEFAULTS, conditional
from .data import OUTPUT
from .model import Model, PARAMETERS
from .validation import Validation, winner

RANGES={'iterations':50,**search_space.RANGES}
NAMES=list(RANGES)[1:]
CHOICES={name for name,values in RANGES.items() if isinstance(values,list)}


@timed_often
def space():
    return search_space.space(RANGES)


@timed_often
def decode(point):
    return search_space.decode(point,RANGES)


@timed_often
def encode(params):
    return search_space.encode(params,RANGES)


@timed_often
def initial():
    current=json.loads(PARAMETERS.read_text())
    low,high=space()
    rows=[decode(np.clip(encode(current),low,high))]
    rng=np.random.default_rng(19)
    for number in range(15):
        params=decode(rng.uniform(low,high))
        params.update(iterations=50,depth=max(RANGES['depth'][0],3+number%8),
                      learning_rate=[.003,.01,.03,.1,.3][number%5],
                      bootstrap_type=RANGES['bootstrap_type'][number%4],
                      grow_policy=RANGES['grow_policy'][number%3])
        params={**DEFAULTS,**params}
        params['boosting_type']='Ordered' if number%4==0 and params['grow_policy']=='SymmetricTree' else 'Plain'
        rows.append(conditional(params))
    return rows


class Monitor:
    @timed_often
    def __init__(self,number):
        self.number=number
        self.started=time.monotonic()
        self.last=0.
        self.completed=0

    @timed_often
    def after_iteration(self,info):
        elapsed=time.monotonic()-self.started
        self.completed=info.iteration
        if elapsed-self.last>=5 or info.iteration in (1,RANGES['iterations']):
            print(json.dumps({'trial':self.number,'iteration':info.iteration,'seconds':round(elapsed,3),
                              'rmse':info.metrics['validation']['RMSE'][-1]}),flush=True)
            self.last=elapsed
        return True


@timed
def trial(number,params,training,validation,metric,threads):
    params={**params,'counter_calc_method':'SkipTest'}
    model=Model({**params,'thread_count':threads,'use_best_model':False})
    monitor=Monitor(number)
    Regressor.fit(model,training,validation=validation,monitor=monitor)
    fitted=time.monotonic()-monitor.started
    result={'trial':number,'params':params,'x':encode(params),'iterations':model.estimator.tree_count_,
            'completed':monitor.completed,'stop':None,'fit_seconds':fitted,'threads':threads}
    if model.estimator.tree_count_!=params['iterations']:
        raise RuntimeError('The completed trial did not retain every requested tree')
    started=time.monotonic()
    predicted=Regressor.predict(model,validation)
    result.update(metric.score(predicted),predict_seconds=time.monotonic()-started)
    return result


@timed
def run_trial(number,params,data,output,seconds,threads):
    request=output/f'request_{number:03d}.json'
    result_path=output/f'result_{number:03d}.json'
    request.write_text(json.dumps({'trial':number,'params':params,'data':str(data.resolve()),
                                   'threads':threads,'output':str(result_path.resolve())},indent=2))
    started=time.monotonic()
    try:
        subprocess.run([sys.executable,'-m','advisors.models.row.worker','--request',str(request.resolve())],
                       check=True,timeout=seconds)
    except subprocess.TimeoutExpired:
        elapsed=time.monotonic()-started
        result={'trial':number,'params':{**params,'counter_calc_method':'SkipTest'},'x':encode(params),
                'iterations':None,'completed':None,'stop':'time_limit','fit_seconds':None,'threads':threads}
        print(json.dumps({'trial':number,'stop':'time_limit','wall_seconds':elapsed}),flush=True)
    else:
        result=json.loads(result_path.read_text())
    result['wall_seconds']=time.monotonic()-started
    return result


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--data',type=Path,default=OUTPUT/'data.pkl')
    parser.add_argument('--trials',type=int,default=128)
    parser.add_argument('--threads',type=int,default=8)
    parser.add_argument('--seconds',type=float,default=20)
    parser.add_argument('--min-depth',type=int,default=RANGES['depth'][0])
    parser.add_argument('--min-learning-rate',type=float,default=RANGES['learning_rate'][0])
    args=parser.parse_args()
    if min(args.trials,args.threads,args.seconds)<=0:
        raise ValueError('Search counts and timing limits must be positive')
    if not 1<=args.min_depth<=RANGES['depth'][1] or not 0<args.min_learning_rate<=.002:
        raise ValueError('Minimum depth must be 1–10 and minimum learning rate must be positive and at most 0.002')
    RANGES['depth']=(args.min_depth,RANGES['depth'][1])
    RANGES['learning_rate']=(args.min_learning_rate,RANGES['learning_rate'][1])
    args.output.mkdir(parents=True,exist_ok=True)
    path=args.output/'search.json'
    if path.exists():
        raise FileExistsError(path)
    with args.data.open('rb') as source:
        data=pickle.load(source)
    if set(data.runs[data.train])&set(data.runs[data.test]):
        raise ValueError('Training and validation runs overlap')
    metric=Validation(data.y[data.train],data.y[data.test],data.meta.iloc[data.test])
    baseline=metric.configuration()
    config={'ranges':RANGES,'method':'random_forest_expected_improvement','initial':initial(),'trials':args.trials,
            'data':str(args.data.resolve()),'threads':args.threads,'seconds_per_trial':args.seconds,
            'training_rows':len(data.train),'validation_rows':len(data.test),'validation':baseline,
            'incumbent_params':json.loads(PARAMETERS.read_text())}
    path.write_text(json.dumps(config,indent=2))
    low,high=space()
    rng=np.random.default_rng(19)
    started=time.monotonic()
    results=[]
    seeds=initial()
    for number in range(args.trials):
        proposal=None
        if number<len(seeds):
            params=seeds[number]
        else:
            observed=np.array([row['x'] for row in results])
            scores=-np.array([row['score'] if 'score' in row else 10*baseline['constant']['score'] for row in results])
            point,proposal=propose(observed,scores,low,high,rng,NAMES)
            params=decode(point)
        result=run_trial(number,params,args.data,args.output,args.seconds,args.threads)
        result['method']='initial' if proposal is None else proposal['method']
        if proposal is not None:
            result['proposal']={key:value for key,value in proposal.items() if key!='candidate_rows'}
        results.append(result)
        (args.output/f'trial_{number:03d}.json').write_text(json.dumps(result,indent=2))
        completed=[row for row in results if 'score' in row]
        status={'finished':len(results),'requested':args.trials,'completed_fits':len(completed),
                'seconds':time.monotonic()-started,'best':winner(results) if completed else None}
        (args.output/'status.json').write_text(json.dumps(status,indent=2))
        print(json.dumps(status),flush=True)


if __name__=='__main__':
    logging.basicConfig(level=logging.WARNING)
    main()
