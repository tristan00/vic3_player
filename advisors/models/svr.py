import numpy as np
from sklearn.svm import LinearSVR

from interface.common import timed, timed_often

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
    spread[spread==0]=1
    model=LinearSVR(C=C,epsilon=EPSILON,max_iter=ITERATIONS,dual='auto',random_state=int(rng.integers(2**31))).fit((features-centre)/spread,target[rows])
    coefficients=model.coef_/spread
    return coefficients[:X.shape[1]],coefficients[X.shape[1]:],lambda points:model.predict((expand(points)-centre)/spread)


@timed_often
def best(linear,squared,low,high):
    vertex=np.clip(np.divide(-linear,2*squared,out=np.full_like(linear,low),where=squared<0),low,high)
    candidates=np.stack([np.full_like(linear,low),np.full_like(linear,high),vertex])
    values=linear*candidates+squared*candidates**2
    return candidates[values.argmax(0),np.arange(len(linear))]


