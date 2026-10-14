import numpy as np
from scipy.stats import norm
from sklearn.ensemble import RandomForestRegressor

from interface.common import evidence, timed, timed_often

TREES=50
LEAF=2
FEATURES='sqrt'
CANDIDATES=2000

@timed_often
def predict(forest,points,best):
    points=forest._validate_X_predict(points)
    per_tree=np.stack([tree.predict(points,check_input=False) for tree in forest.estimators_])
    mean,spread=per_tree.mean(0),per_tree.std(0)+1e-9
    z=(mean-best)/spread
    beat=norm.cdf(z)
    return mean,spread,(mean-best)*beat+spread*norm.pdf(z),beat


@timed
def fit(X,y,rng):
    if not len(y):
        raise ValueError(evidence(observations=len(y)))
    return RandomForestRegressor(n_estimators=TREES,min_samples_leaf=LEAF,max_features=FEATURES,random_state=int(rng.integers(2**31))).fit(X,y)


@timed
def propose(forest,y,names,candidates):
    points=np.asarray(candidates)
    mean,spread,improvement,beat=predict(forest,points,y.max())
    order=np.argsort(-improvement,kind='stable')
    rows=[(rank,'random',float(mean[i]),float(spread[i]),float(improvement[i]),float(beat[i])) for rank,i in enumerate(order)]
    record={'observations':len(y),'best_reward':float(y.max()),'candidates':len(points),'candidate_rows':rows,
            'importance':[(name,float(value)) for name,value in zip(names,forest.feature_importances_)],'method':'expected_improvement',
            **dict(zip(('predicted_reward','uncertainty','expected_improvement','beat_probability'),rows[0][2:]))}
    return points[order[0]],record
