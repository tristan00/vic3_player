import logging
import numpy as np

from interface.common import timed
from interface.timing import current
from .random import HIGH, LOW, RandomAdvisor
from ..data.weights import history, normalized
from ..data.endgame import NAME
from ..models import forest

LOG=logging.getLogger('loop')


class RandomForestWeightingAdvisor(RandomAdvisor):
    name='random_forest_weighting'

    @timed
    def fit(self,store,space):
        X,y,runs=history(store.connection,space)
        target=normalized(y)
        return forest.fit(X,target,np.random.default_rng(self.random.randrange(2**32))),X,y,target,runs

    @timed
    def start_run(self,store,actions,objective,kept):
        space=[name for name in actions if name not in self.excluded]
        if kept is None:
            kept=self.fit(store,space)
        model,X,y,target,runs=kept
        rng=np.random.default_rng(self.random.randrange(2**32))
        x,record=forest.propose(model,X,target,np.full(len(space),LOW),np.full(len(space),HIGH),rng,space,self.candidates(space,forest.CANDIDATES))
        record['initializer']=self.name
        record['reward']='composite'
        record['observed']=[(run_id,float(reward)) for run_id,reward in zip(runs,y)]
        record['seconds']=current().seconds
        self.proposal=record
        chosen=(10**x).tolist()
        self.weights={**{name:0 for name in actions if name in self.excluded},**dict(zip(space,chosen))}
        LOG.info('random_forest_weighting proposal (%s) from %d scored runs, best %s %.3f, predicted %s',
                 record['method'],len(y),NAME,record['best_reward'],f"{record['predicted_reward']:.3f}")
        return kept
