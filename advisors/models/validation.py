import numpy as np

from interface.common import timed_often


@timed_often
def entropy(predictions):
    probabilities=np.unique(predictions,return_counts=True)[1]/len(predictions)
    return float(np.clip(np.dot(probabilities,np.log(1/probabilities))/np.log(len(predictions)),0.,1.))
