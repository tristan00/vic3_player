import numpy as np
import pandas as pd

from interface.common import timed_often
from ..validation import entropy

METRIC={'name':'reward_entropy_v1','reward_weight':.5,'entropy_weight':.5,
        'reward_loss':'rmse / training_reward_std',
        'entropy_loss':'1 - mean(-sum(p * log(p)) / log(action_count))',
        'tie_tolerance_fraction':1e-6,'tie_groups':'sorted groups with maximum span at most tie_tolerance',
        'pause_keys':['run','before_seq'],'minimum_actions':2,'pause_weighting':'equal'}


class Validation:
    @timed_often
    def __init__(self,training,targets,metadata):
        training=np.asarray(training,dtype=float)
        self.targets=np.asarray(targets,dtype=float)
        if training.ndim!=1 or self.targets.ndim!=1 or not len(training) or not len(self.targets):
            raise ValueError('Reward arrays must be nonempty vectors')
        if not np.isfinite(training).all() or not np.isfinite(self.targets).all():
            raise ValueError('Rewards must be finite')
        if len(metadata)!=len(self.targets) or metadata[['run','before_seq']].isna().any().any():
            raise ValueError('Every validation row needs its run and starting snapshot')
        self.scale=float(training.std())
        if self.scale<=0:
            raise ValueError('Training rewards must have positive standard deviation')
        self.groups=pd.factorize(pd.MultiIndex.from_frame(metadata[['run','before_seq']]))[0]
        self.counts=np.bincount(self.groups)
        self.multiple=self.counts>=METRIC['minimum_actions']
        if not self.multiple.any():
            raise ValueError('Validation needs a pause with at least two actions')
        ordered=np.argsort(self.groups,kind='stable')
        self.pauses=[rows for rows in np.split(ordered,np.cumsum(self.counts)[:-1]) if len(rows)>=2]
        self.tolerance=self.scale*METRIC['tie_tolerance_fraction']
        self.mean=float(training.mean())

    @timed_often
    def score(self,predictions):
        predictions=np.asarray(predictions,dtype=float)
        if predictions.shape!=self.targets.shape or not np.isfinite(predictions).all():
            raise ValueError('Predictions must be finite and match validation rows')
        entropies=np.array([entropy(predictions[rows],self.tolerance) for rows in self.pauses])
        rmse=float(np.sqrt(np.mean((predictions-self.targets)**2)))
        reward_loss=rmse/self.scale
        entropy_loss=1-float(entropies.mean())
        return {'score':.5*reward_loss+.5*entropy_loss,'rmse':rmse,'reward_loss':reward_loss,
                'entropy_loss':entropy_loss,'mean_pause_entropy':float(entropies.mean()),
                'median_pause_entropy':float(np.median(entropies)),'entropy_pauses':len(self.pauses),
                'tied_pause_fraction':float(np.mean(entropies==0)),
                'singleton_pauses':int((~self.multiple).sum())}

    @timed_often
    def configuration(self):
        return {**METRIC,'training_reward_std':self.scale,'tie_tolerance':self.tolerance,
                'constant':self.score(np.full_like(self.targets,self.mean))}


@timed_often
def winner(trials):
    completed=[row for row in trials if row.get('stop') is None and 'score' in row
               and np.isfinite(row['score']) and row['iterations']==row['params']['iterations']]
    if not completed:
        raise ValueError('No complete trial has a finite blended validation score')
    return min(completed,key=lambda row:row['score'])
