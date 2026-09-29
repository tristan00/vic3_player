import logging

import numpy as np
from sklearn.svm import LinearSVR

from interface.common import timed, timed_often
from interface.timing import current
from .random_picker import HIGH, LOW, RandomAdvisor
from .random_smac_weighting import INITIAL, RANDOM_SHARE, history, normalized

LOG=logging.getLogger('loop')
C=.1
EPSILON=.5
ITERATIONS=100000


@timed_often
def expand(X):
    return np.hstack([X,X**2])


@timed
def fit(X,target,rows,rng):
    features=expand(X[rows])
    centre,spread=features.mean(0),features.std(0)
    model=LinearSVR(C=C,epsilon=EPSILON,max_iter=ITERATIONS,dual='auto',random_state=int(rng.integers(2**31))).fit((features-centre)/spread,target[rows])
    coefficients=model.coef_/spread
    return coefficients[:X.shape[1]],coefficients[X.shape[1]:],lambda points:model.predict((expand(points)-centre)/spread)


@timed_often
def best(linear,squared,low,high):
    vertex=np.clip(np.divide(-linear,2*squared,out=np.full_like(linear,low),where=squared<0),low,high)
    candidates=np.stack([np.full_like(linear,low),np.full_like(linear,high),vertex])
    values=linear*candidates+squared*candidates**2
    return candidates[values.argmax(0),np.arange(len(linear))]


class RandomSvrWeightingAdvisor(RandomAdvisor):
    name='random_svr_weighting'

    @timed_often
    def __init__(self,seed=None,weights=None):
        super().__init__(seed)
        self.excluded={name for name,weight in (weights or {}).items() if weight==0}

    @timed
    def start_run(self,store,actions,objective):
        space=[name for name in actions if name not in self.excluded]
        X,y,runs=history(store.connection,space,objective)
        target=normalized(y)
        rng=np.random.default_rng(self.random.randrange(2**32))
        record={'initializer':self.name,'observations':len(y),'c':C,'epsilon':EPSILON,'predicted_reward':None,'bounded':None,'coefficients':[]}
        draws=np.zeros(len(y),int)
        if len(y)<INITIAL or self.random.random()<RANDOM_SHARE:
            x,record['method']=rng.uniform(LOW,HIGH,len(space)),'random'
        else:
            rows=rng.integers(len(y),size=len(y))
            draws=np.bincount(rows,minlength=len(y))
            linear,squared,predict=fit(X,target,rows,rng)
            x,record['method']=best(linear,squared,LOW,HIGH),'bootstrap_svr'
            record.update(predicted_reward=float(predict(x[None,:])[0]),bounded=int(np.sum((x==LOW)|(x==HIGH))),
                          coefficients=[(name,float(a),float(b),float(chosen)) for name,a,b,chosen in zip(space,linear,squared,x)])
        record['observed']=[(run_id,float(reward),float(value),int(count)) for run_id,reward,value,count in zip(runs,y,target,draws)]
        record['seconds']=current().seconds
        self.proposal=record
        self.weights={**{name:0 for name in actions if name in self.excluded},**dict(zip(space,(10**x).tolist()))}
        LOG.info('random_svr_weighting proposal (%s) from %d scored runs, predicted %s, in %.1fs',record['method'],len(y),
                 'none' if record['predicted_reward'] is None else f"{record['predicted_reward']:.3f}",record['seconds'])
        return self.weights
