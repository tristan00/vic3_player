import numpy as np
from sklearn.ensemble import RandomForestRegressor

from interface.common import timed


@timed
def suggest(space,configs,scores,seed,params,draw,step):
    candidates=draw(params['candidates'])
    with step('history'):
        x=np.asarray([space.vector(config) for config in configs],np.float32)
    with step('fit'):
        forest=RandomForestRegressor(n_estimators=params['trees'],min_samples_leaf=params['min_samples_leaf'],max_features=params['max_features'],n_jobs=1,random_state=seed).fit(x,scores)
    with step('candidates'):
        encoded=np.asarray([space.vector(candidate['config']) for candidate in candidates],np.float32)
    with step('score'):
        predictions=np.stack([tree.predict(encoded) for tree in forest.estimators_])
        means,uncertainties=predictions.mean(0),predictions.std(0)
        selection=means-params['uncertainty_weight']*uncertainties
        for candidate,mean,uncertainty,score in zip(candidates,means,uncertainties,selection):
            candidate.update(predicted_score=float(mean),uncertainty=float(uncertainty),selection_score=float(score))
        chosen=int(np.argmin(selection))
    found={'selected_index':chosen,**{name:candidates[chosen][name] for name in ('predicted_score','uncertainty','selection_score')}}
    return candidates[chosen]['config'],found,{'candidates':candidates}
