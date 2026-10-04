import logging
import numpy as np

from interface.common import timed
from interface.timing import current
from .random import HIGH, LOW, RandomAdvisor
from ..data.weights import history, normalized
from ..data.endgame import NAME
from ..models import forest

LOG=logging.getLogger('loop')


class RandomSmacWeightingAdvisor(RandomAdvisor):
    name='random_smac_weighting'

    @timed
    def propose(self,X,y,low,high,names=None):
        return forest.propose(X,y,low,high,np.random.default_rng(self.random.randrange(2**32)),names)

    @timed
    def start_run(self,store,actions,objective):
        space=[name for name in actions if name not in self.excluded]
        X,y,runs=history(store.connection,space)
        x,record=self.propose(X,normalized(y),np.full(len(space),LOW),np.full(len(space),HIGH),space)
        record['initializer']=self.name
        record['reward']='composite'
        record['observed']=[(run_id,float(reward)) for run_id,reward in zip(runs,y)]
        record['seconds']=current().seconds
        self.proposal=record
        chosen=(10**x).tolist()
        self.weights={**{name:0 for name in actions if name in self.excluded},**dict(zip(space,chosen))}
        LOG.info('random_smac_weighting proposal (%s) from %d scored runs, best %s %.3f, predicted %s',
                 record['method'],len(y),NAME,record['best_reward'],f"{record['predicted_reward']:.3f}")
        return self.weights
