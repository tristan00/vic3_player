import numpy as np
from scipy.stats import norm
from sklearn.ensemble import RandomForestRegressor

from interface.common import evidence, timed, timed_often

TREES=50
LEAF=2
FEATURES='sqrt'
CANDIDATES=2000
STARTS=10
NEIGHBOURS=50
LOCAL_STEPS=20
STEP=.125

@timed_often
def predict(forest,points,best):
    points=forest._validate_X_predict(points)
    per_tree=np.stack([tree.predict(points,check_input=False) for tree in forest.estimators_])
    mean,spread=per_tree.mean(0),per_tree.std(0)+1e-9
    z=(mean-best)/spread
    beat=norm.cdf(z)
    return mean,spread,(mean-best)*beat+spread*norm.pdf(z),beat


@timed_often
def expected_improvement(forest,points,best):
    return predict(forest,points,best)[2]


@timed
def local_search(forest,starts,best,low,high,rng):
    points=starts.copy()
    scores=expected_improvement(forest,points,best)
    for _ in range(LOCAL_STEPS):
        moves=rng.normal(0,1,(len(points),NEIGHBOURS,points.shape[1]))*STEP*(high-low)*(rng.random((len(points),NEIGHBOURS,points.shape[1]))<.1)
        neighbours=np.clip(points[:,None,:]+moves,low,high)
        found=expected_improvement(forest,neighbours.reshape(-1,points.shape[1]),best).reshape(len(points),NEIGHBOURS)
        pick=found.argmax(1)
        better=found[np.arange(len(points)),pick]>scores
        points[better]=neighbours[np.arange(len(points)),pick][better]
        scores[better]=found[np.arange(len(points)),pick][better]
    return points,scores


@timed
def fit(X,y,rng):
    if not len(y):
        raise ValueError(evidence(observations=len(y)))
    return RandomForestRegressor(n_estimators=TREES,min_samples_leaf=LEAF,max_features=FEATURES,random_state=int(rng.integers(2**31))).fit(X,y)


@timed
def propose(forest,X,y,low,high,rng,names,random_points):
    climbed,_=local_search(forest,np.clip(X[np.argsort(y)[-STARTS:]],low,high),y.max(),low,high,rng)
    points=np.vstack([random_points,climbed])
    sources=['random']*len(random_points)+['local_search']*len(climbed)
    mean,spread,improvement,beat=predict(forest,points,y.max())
    order=np.argsort(-improvement,kind='stable')
    rows=[(rank,sources[i],float(mean[i]),float(spread[i]),float(improvement[i]),float(beat[i])) for rank,i in enumerate(order)]
    record={'observations':len(y),'best_reward':float(y.max()),'candidates':len(points),'candidate_rows':rows,
            'importance':[(name,float(value)) for name,value in zip(names,forest.feature_importances_)],'method':'expected_improvement',
            **dict(zip(('predicted_reward','uncertainty','expected_improvement','beat_probability'),rows[0][2:]))}
    return points[order[0]],record

