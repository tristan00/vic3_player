import numpy as np
from scipy.optimize import minimize
from sklearn.svm import SVR

from interface.common import timed, timed_often

KERNEL='rbf'
C=.1
EPSILON=.5
SAMPLES=2000
STARTS=8


class Surface:
    @timed
    def __init__(self,X,target):
        self.seen=X
        self.centre,self.spread=X.mean(0),X.std(0)
        self.spread[self.spread==0]=1
        scaled=self.scaled(X)
        spread=scaled.var()
        self.gamma=1/(X.shape[1]*spread) if spread else 1.
        model=SVR(kernel=KERNEL,gamma=self.gamma,C=C,epsilon=EPSILON).fit(scaled,target)
        self.vectors,self.weights,self.level=model.support_vectors_,model.dual_coef_[0],float(model.intercept_[0])

    @timed_often
    def scaled(self,points):
        return (points-self.centre)/self.spread

    @timed_often
    def pull(self,point):
        apart=self.scaled(point)-self.vectors
        return apart,self.weights*np.exp(-self.gamma*(apart**2).sum(1))

    @timed_often
    def value(self,point):
        return float(self.pull(point)[1].sum())+self.level

    @timed_often
    def slope(self,point):
        apart,pull=self.pull(point)
        return pull@(-2*self.gamma*apart)/self.spread

    @timed_often
    def curve(self,point):
        apart,pull=self.pull(point)
        return pull@(2*self.gamma**2*apart**2-self.gamma)/self.spread**2


@timed
def best(surface,low,high,candidates):
    starts=np.vstack([surface.seen,candidates])
    values=np.array([surface.value(point) for point in starts])
    found=[minimize(lambda point:(-surface.value(point),-surface.slope(point)),starts[index],jac=True,method='L-BFGS-B',bounds=[(low,high)]*starts.shape[1])
           for index in np.argsort(values)[::-1][:STARTS]]
    return min(found,key=lambda result:result.fun).x
