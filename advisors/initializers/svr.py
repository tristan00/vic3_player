import logging
import numpy as np

from interface.common import evidence, timed
from interface.timing import current
from .random import HIGH, LOW, RandomAdvisor
from ..data.weights import history, normalized
from ..models.svr import C, EPSILON, SAMPLES, Surface, best

LOG=logging.getLogger('loop')


class RandomSvrWeightingAdvisor(RandomAdvisor):
    name='random_svr_weighting'

    @timed
    def fit(self,store,space):
        X,y,runs=history(store.connection,space)
        if not len(y):
            raise ValueError(evidence(name=self.name,scored=len(y)))
        target=normalized(y)
        rows=np.random.default_rng(self.random.randrange(2**32)).integers(len(y),size=len(y))
        return Surface(X[rows],target[rows]),y,target,runs,np.bincount(rows,minlength=len(y))

    @timed
    def start_run(self,store,actions,objective,kept):
        space=[name for name in actions if name not in self.excluded]
        if kept is None:
            kept=self.fit(store,space)
        surface,y,target,runs,draws=kept
        x=best(surface,LOW,HIGH,self.candidates(space,SAMPLES))
        record={'initializer':self.name,'method':'bootstrap_svr','observations':len(y),'c':C,'epsilon':EPSILON,'predicted_reward':surface.value(x),
                'bounded':int(np.sum((x==LOW)|(x==HIGH))),
                'coefficients':[(name,float(a),float(b),float(chosen)) for name,a,b,chosen in zip(space,surface.slope(x),surface.curve(x),x)]}
        record['observed']=[(run_id,float(reward),float(value),int(count)) for run_id,reward,value,count in zip(runs,y,target,draws)]
        record['seconds']=current().seconds
        self.proposal=record
        self.weights={**{name:0 for name in actions if name in self.excluded},**dict(zip(space,(10**x).tolist()))}
        LOG.info('random_svr_weighting proposal (%s) from %d scored runs, predicted %.3f, in %.1fs',record['method'],len(y),record['predicted_reward'],record['seconds'])
        return kept
