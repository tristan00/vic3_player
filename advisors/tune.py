import json
import logging
import math
import time

import numpy as np
import psycopg
from catboost import CatBoostRegressor
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold

from interface.common import DEFAULT_DATA, timed, timed_often, write_json
from interface.recording.store import DSN
from . import pickers
from .random_smac_weighting import COMPONENTS, RandomSmacWeightingAdvisor

LOG=logging.getLogger('interface')
OUT=DEFAULT_DATA.parent/'tuning'
RESULTS=OUT/'results.jsonl'
OBJECTIVE=({component:1/len(COMPONENTS) for component in COMPONENTS},.5)
FOLDS=4
BATCH=30
SAMPLED=300
TRIALS=1000
SPREAD_WEIGHT=.05
SPREAD_FLOOR=1e-6
BUDGET=400*2**10
NUMERIC=(math.log10,lambda value:10**value)
LINEAR=(float,float)
BASE={name:value for name,value in pickers.PARAMS.items() if name!='thread_count'}
SETTINGS=(('iterations',100,1000,NUMERIC,round),('depth',4,10,LINEAR,round),('learning_rate',10**-1.7,10**-.5,NUMERIC,float),('l2_leaf_reg',1,10**1.5,NUMERIC,float),
          ('rsm',.3,1,LINEAR,float),('random_strength',.1,10,NUMERIC,float),('one_hot_max_size',13,32,NUMERIC,round))


@timed_often
def available(data):
    return {name:len(histograms.bins[name]) for histograms in (data.actions,data.held) for name in histograms.names}


@timed
def evaluate(data,pool,params):
    started=time.monotonic()
    rng=np.random.default_rng(0)
    predicted=np.zeros(len(data.y))
    spreads=[]
    for train,test in GroupKFold(FOLDS).split(data.y,data.y,data.runs):
        model=CatBoostRegressor(**{**BASE,**params},verbose=False)
        model.fit(pool(train,train,data.y[train]))
        predicted[test]=model.predict(pool(test,test))
        pauses=rng.choice(test,min(SAMPLED,len(test)),replace=False)
        donors=np.concatenate([rng.choice(test,BATCH,replace=False) for _ in pauses])
        batch=model.predict(pool(np.repeat(pauses,BATCH),donors)).reshape(len(pauses),BATCH)
        spreads.append(batch.max(1)-batch.min(1))
    spearman=float(spearmanr(predicted,data.y)[0])
    spread=float(np.mean(np.concatenate(spreads)))/float(np.std(data.y))
    return {'score':spearman+SPREAD_WEIGHT*math.log2(max(spread,SPREAD_FLOOR)),'spearman':spearman,'spread':spread,'seconds':time.monotonic()-started}


@timed_often
def space(bins):
    low,high,names=[],[],[]
    for name,least,most,(forward,_),_ in SETTINGS:
        centre=forward(pickers.PARAMS[name])
        low.append(forward(least)-centre)
        high.append(forward(most)-centre)
        names.append(name)
    for name in bins:
        low+=[-1,-1]
        high+=[1,0]
        names+=[f'{name}.included',f'{name}.size']
    return np.array(low,float),np.array(high,float),names


@timed_often
def decode(x,bins):
    params={name:kind(round(back(x[position]+forward(pickers.PARAMS[name])),4)) for position,(name,_,_,(forward,back),kind) in enumerate(SETTINGS)}
    params['iterations']=min(params['iterations'],BUDGET//2**params['depth'])
    sizes={}
    for position,name in enumerate(bins):
        included,size=x[len(SETTINGS)+2*position:len(SETTINGS)+2*position+2]
        if included>=0:
            sizes[name]=max(1,round(bins[name]**(1+size)))
    return params,sizes


@timed
def search(data):
    bins=available(data)
    low,high,names=space(bins)
    done=[json.loads(line) for line in RESULTS.read_text(encoding='utf-8').splitlines()] if RESULTS.exists() else []
    advisor=RandomSmacWeightingAdvisor(len(done))
    while len(done)<TRIALS:
        x,record=advisor.propose(np.array([found['x'] for found in done]).reshape(len(done),len(low)),np.array([found['score'] for found in done]),low,high,names)
        params,sizes=decode(x,bins)
        found={'trial':len(done)+1,'method':record['method'],**evaluate(data,pickers.pool(data,sizes),params),'histograms':len(sizes),'bins':sum(sizes.values()),
               'params':params,'sizes':sizes,'x':x.tolist()}
        done.append(found)
        with open(RESULTS,'a',encoding='utf-8') as out:
            out.write(json.dumps(found)+'\n')
        LOG.info('trial %d %s score %.4f spearman %.4f spread %.4f histograms %d bins %d in %.0fs',found['trial'],found['method'],found['score'],found['spearman'],found['spread'],
                 found['histograms'],found['bins'],found['seconds'])
    return max(done,key=lambda found:found['score'])


@timed
def main():
    with psycopg.connect(DSN) as connection:
        data=pickers.training_data(connection,OBJECTIVE)
    bins=available(data)
    LOG.info('%d pauses from %d runs, %d histograms with %d bins',len(data.y),data.played,len(bins),sum(bins.values()))
    winner=search(data)
    production=evaluate(data,pickers.pool(data,pickers.SIZES),{})
    write_json(OUT/'report.json',{'winner':{key:value for key,value in winner.items() if key!='x'},'production':{**production,'params':BASE,'sizes':pickers.SIZES},'available':bins})
    LOG.info('FINISHED winner %.4f production %.4f',winner['score'],production['score'])


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=OUT/'tune.log',level=logging.INFO,format='%(asctime)s %(message)s')
    try:
        main()
    except BaseException:
        LOG.exception('FAILED')
        raise
