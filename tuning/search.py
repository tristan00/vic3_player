import numpy as np
from sklearn.ensemble import RandomForestRegressor

from interface.common import timed
from . import RANDOM_TRIALS
from .space import identity
from .metrics import loss

CANDIDATES=256
FAILURE_SCORE=2.
UNCERTAINTY_WEIGHT=1.


@timed
def propose(space,history,seed,model,weighting):
    rng=np.random.default_rng(seed)
    random_trials=RANDOM_TRIALS[model]
    count=1 if len(history)<random_trials else CANDIDATES
    seen={identity(trial['config']) for trial in history}
    candidates=[]
    while len(candidates)<count:
        config,sampling=space.draw(rng)
        key=identity(config)
        if key not in seen:
            candidates.append({'index':len(candidates),'config':config,'sampling':sampling})
            seen.add(key)
    observations=[{'trial':trial['trial'],'state':trial['state'],
                   'score':loss(trial['metrics'],weighting['weights']) if trial['state']=='completed' else FAILURE_SCORE} for trial in history]
    proposal={'method':'random','seed':seed,'observations':len(history),'candidates':count,'selected_index':0,
              'failure_score':FAILURE_SCORE,'uncertainty_weight':UNCERTAINTY_WEIGHT,'random_trials':random_trials,'weighting':weighting}
    if len(history)>=random_trials:
        x=np.asarray([space.vector(trial['config']) for trial in history],np.float32)
        y=np.asarray([observation['score'] for observation in observations])
        forest=RandomForestRegressor(n_estimators=64,min_samples_leaf=2,max_features=.75,n_jobs=1,random_state=seed).fit(x,y)
        encoded=np.asarray([space.vector(candidate['config']) for candidate in candidates],np.float32)
        predictions=np.stack([tree.predict(encoded) for tree in forest.estimators_])
        means,uncertainties=predictions.mean(0),predictions.std(0)
        scores=means-UNCERTAINTY_WEIGHT*uncertainties
        for candidate,mean,uncertainty,score in zip(candidates,means,uncertainties,scores):
            candidate.update(predicted_score=float(mean),uncertainty=float(uncertainty),selection_score=float(score))
        chosen=int(np.argmin(scores))
        proposal.update(method='forest',selected_index=chosen,**{name:candidates[chosen][name]
                        for name in ('predicted_score','uncertainty','selection_score')})
    trace={**proposal,'observations':observations,'candidates':candidates}
    return candidates[proposal['selected_index']]['config'],proposal,trace
