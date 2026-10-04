import numpy as np

from interface.common import timed, timed_often
from ..validation import entropy
from . import data as histogram

METRIC={'name':'reward_candidate_entropy_v2','reward_weight':.1,'entropy_weight':.9,
        'reward_loss':'mean(fold_rmse / fold_training_reward_std), weighted by validation rows',
        'entropy_loss':'1 - mean(normalized candidate prediction tie-group entropy)',
        'tie_tolerance_fraction':1e-6,'tie_groups':'sorted groups with maximum span at most tie_tolerance',
        'pause_weighting':'equal','minimum_candidates':2}


@timed_often
def candidate_pool(data,fold,sizes):
    rows=np.repeat(fold['pauses'],data.sampling['candidates'])
    actions=data.actions.columns(sizes)
    held=data.held.columns(sizes)
    return histogram.frame(data.state[rows],data.laws[rows],data.held.counts[np.ix_(rows,held)],
                           fold['sizes'],fold['actions'][:,actions].toarray(),histogram.names(data.actions,data.held,sizes))


class Validation:
    @timed
    def __init__(self,data):
        self.data=data
        if data.metric!=METRIC or not np.isfinite(data.y).all() or not len(data.y):
            raise ValueError('A finite dataset prepared for candidate entropy is required')
        if data.sampling['candidates']<2:
            raise ValueError('Entropy needs at least two candidates per pause')
        seen=[]
        self.scales=[]
        for fold in data.folds:
            train,test=fold['train'],fold['test']
            if not len(train) or not len(test) or set(data.runs[train])&set(data.runs[test]):
                raise ValueError('Training and validation runs must be disjoint')
            if not len(fold['pauses']) or not set(fold['pauses'])<=set(test) or len(set(fold['pauses']))!=len(fold['pauses']):
                raise ValueError('Entropy pauses must be distinct held-out rows')
            if not np.array_equal(np.sort(np.r_[train,test]),np.arange(len(data.y))):
                raise ValueError('Each fold must partition the dataset')
            count=len(fold['pauses'])*data.sampling['candidates']
            if fold['sizes'].shape!=(count,1) or fold['actions'].shape!=(count,data.actions.total):
                raise ValueError('Frozen candidate rows do not match the sampled pauses')
            scale=float(np.std(data.y[train]))
            if scale<=0:
                raise ValueError('Training rewards must have positive standard deviation')
            self.scales.append(scale)
            seen.extend(test)
        if not np.array_equal(np.sort(seen),np.arange(len(data.y))):
            raise ValueError('Every reward row must be held out exactly once')

    @timed_often
    def score(self,predictions,candidates):
        predictions=np.asarray(predictions,float)
        if predictions.shape!=self.data.y.shape or not np.isfinite(predictions).all() or len(candidates)!=len(self.data.folds):
            raise ValueError('Predictions must be finite and match validation rows and folds')
        losses=[]
        entropies=[]
        for fold,scale,batch in zip(self.data.folds,self.scales,candidates):
            batch=np.asarray(batch,float)
            if batch.shape!=(len(fold['pauses']),self.data.sampling['candidates']) or not np.isfinite(batch).all():
                raise ValueError('Candidate predictions must match the frozen sets')
            test=fold['test']
            losses.append(float(np.sqrt(np.mean((predictions[test]-self.data.y[test])**2)))/scale)
            entropies.extend(entropy(row,scale*METRIC['tie_tolerance_fraction']) for row in batch)
        reward_loss=float(np.average(losses,weights=[len(fold['test']) for fold in self.data.folds]))
        entropies=np.asarray(entropies)
        entropy_loss=1-float(entropies.mean())
        return {'score':METRIC['reward_weight']*reward_loss+METRIC['entropy_weight']*entropy_loss,
                'rmse':float(np.sqrt(np.mean((predictions-self.data.y)**2))),
                'reward_loss':reward_loss,'entropy_loss':entropy_loss,'mean_pause_entropy':float(entropies.mean()),
                'median_pause_entropy':float(np.median(entropies)),'entropy_pauses':len(entropies),
                'tied_pause_fraction':float(np.mean(entropies==0))}

    @timed_often
    def configuration(self):
        predicted=np.empty_like(self.data.y,dtype=float)
        candidates=[]
        for fold in self.data.folds:
            mean=float(self.data.y[fold['train']].mean())
            predicted[fold['test']]=mean
            candidates.append(np.full((len(fold['pauses']),self.data.sampling['candidates']),mean))
        return {**METRIC,'sampling':self.data.sampling,'training_reward_std':self.scales,'constant':self.score(predicted,candidates)}
