import argparse
import hashlib
import json
import logging
from pathlib import Path
import pickle
import subprocess
import sys
import time

import numpy as np
from interface.common import timed, timed_often
from . import data as histogram
from .validation import Validation, candidate_pool
from ..boosting import Regressor
from ..forest import propose
from .. import search_space

LOG=logging.getLogger('interface')
TRIALS=400
BUDGET=400*2**10
BASE={'loss_function':'RMSE','random_seed':0,'counter_calc_method':'SkipTest'}
INCUMBENT={name:value for name,value in histogram.PARAMS.items() if name!='thread_count'}
RANGES={'iterations':(100,1000),**search_space.RANGES}
NAMES=list(RANGES)


@timed_often
def available(data):
    return {name:len(histograms.bins[name]) for histograms in (data.actions,data.held) for name in histograms.names}


@timed
def evaluate(data,sizes,params,threads=8):
    started=time.monotonic()
    metric=Validation(data)
    pool=histogram.pool(data,sizes)
    predicted=np.zeros(len(data.y))
    candidates=[]
    trees=[]
    for fold in data.folds:
        train,test=fold['train'],fold['test']
        model=Regressor({**BASE,**params,'thread_count':threads,'allow_writing_files':False,'use_best_model':False}).fit(pool(train,train,data.y[train]))
        trees.append(model.estimator.tree_count_)
        if trees[-1]!=model.params['iterations']:
            raise RuntimeError('Every fold must retain all requested trees')
        predicted[test]=model.predict(pool(test,test))
        batch=model.predict(candidate_pool(data,fold,sizes))
        candidates.append(batch.reshape(len(fold['pauses']),data.sampling['candidates']))
    return {**metric.score(predicted,candidates),'trees':trees,'seconds':time.monotonic()-started}


@timed_often
def space(bins):
    low,high=(values.tolist() for values in search_space.space(RANGES))
    names=NAMES.copy()
    for name in bins:
        low+=[-1,-1]
        high+=[1,0]
        names+=[f'{name}.included',f'{name}.size']
    return np.array(low,float),np.array(high,float),names


@timed_often
def decode(x,bins):
    params=search_space.decode(x[:len(NAMES)],RANGES)
    params['iterations']=min(params['iterations'],BUDGET//2**params['depth'])
    sizes={}
    for position,name in enumerate(bins):
        included,size=x[len(NAMES)+2*position:len(NAMES)+2*position+2]
        if included>=0:
            sizes[name]=max(1,round(bins[name]**(1+size)))
    return params,sizes


@timed_often
def initial(bins):
    params={**INCUMBENT,'one_hot_max_size':min(RANGES['one_hot_max_size'],key=lambda value:abs(value-INCUMBENT['one_hot_max_size']))}
    point=np.array([*search_space.encode(params,RANGES),*np.zeros(2*len(bins))])
    low,high,_=space(bins)
    return np.clip(point,low,high)


@timed
def run_trial(number,params,sizes,source,output,seconds,threads):
    request=output/f'request_{number:04d}.json'
    result=output/f'result_{number:04d}.json'
    request.write_text(json.dumps({'params':params,'sizes':sizes,'data':str(source.resolve()),
                                  'threads':threads,'output':str(result.resolve())},indent=2))
    started=time.monotonic()
    try:
        subprocess.run([sys.executable,'-m','advisors.models.histogram.worker','--request',str(request.resolve())],
                       check=True,timeout=seconds)
    except subprocess.TimeoutExpired:
        found={'stop':'time_limit'}
    else:
        found={'stop':None,**json.loads(result.read_text())}
    return {**found,'trial':number,'params':params,'sizes':sizes,'wall_seconds':time.monotonic()-started}


@timed
def search(data,source,output,trials=TRIALS,seconds=30,threads=8):
    bins=available(data)
    low,high,names=space(bins)
    validation=Validation(data).configuration()
    config={'validation':validation,'trials':trials,'seconds_per_trial':seconds,'threads':threads,
            'data':str(source.resolve()),'data_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'parameters':NAMES,'ranges':RANGES,'low':low.tolist(),'high':high.tolist(),'names':names,
            'incumbent':{'params':INCUMBENT,'sizes':histogram.SIZES}}
    with (output/'search.json').open('x') as stream:
        json.dump(config,stream,indent=2)
    done=[]
    rng=np.random.default_rng(0)
    best=None
    for number in range(trials):
        if done:
            rewards=-np.array([found.get('score',10*validation['constant']['score']) for found in done])
            x,record=propose(np.array([found['x'] for found in done]),rewards,low,high,rng,names)
        else:
            x,record=initial(bins),{'method':'initial'}
        params,sizes=decode(x,bins)
        found={**run_trial(number,params,sizes,source,output,seconds,threads),'method':record['method'],
               'histograms':len(sizes),'bins':sum(sizes.values()),'x':x.tolist()}
        done.append(found)
        if found['stop'] is None and (best is None or found['score']<best['score']):
            best=found
        (output/f'trial_{number:04d}.json').write_text(json.dumps(found,indent=2))
        status={'finished':len(done),'requested':trials,'completed_fits':sum(row['stop'] is None for row in done),'best':best}
        (output/'status.json').write_text(json.dumps(status,indent=2))
        LOG.info('trial %d %s score %s entropy %s in %.2fs',number,found['stop'] or 'completed',found.get('score'),found.get('mean_pause_entropy'),found['wall_seconds'])
    return best


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--data',type=Path,default=Path(__file__).resolve().parents[3]/'artifacts'/'histogram_tuning_data'/'data.pkl')
    parser.add_argument('--trials',type=int,default=TRIALS)
    parser.add_argument('--seconds',type=float,default=30)
    parser.add_argument('--threads',type=int,default=8)
    args=parser.parse_args()
    if min(args.trials,args.seconds,args.threads)<=0:
        raise ValueError('Trial count, threads and timeout must be positive')
    args.output.mkdir(parents=True,exist_ok=False)
    logging.basicConfig(filename=args.output/'tune.log',level=logging.INFO,format='%(asctime)s %(message)s')
    with args.data.open('rb') as stream:
        data=pickle.load(stream)
    selected=search(data,args.data,args.output,args.trials,args.seconds,args.threads)
    if selected is None:
        raise RuntimeError('No trial completed within the hard limit')
    production=run_trial(-1,INCUMBENT,histogram.SIZES,args.data,args.output,args.seconds,args.threads)
    (args.output/'report.json').write_text(json.dumps({'winner':selected,'production':production,'available':available(data)},indent=2))


if __name__=='__main__':
    main()
