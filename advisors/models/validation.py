import numpy as np

from interface.common import timed_often


@timed_often
def entropy(predictions,tolerance):
    values=np.sort(predictions)
    counts=[1]
    anchor=values[0]
    for value in values[1:]:
        if value-anchor>tolerance:
            counts.append(1)
            anchor=value
        else:
            counts[-1]+=1
    probabilities=np.asarray(counts,dtype=float)/len(values)
    return float(np.clip(-np.dot(probabilities,np.log(probabilities))/np.log(len(values)),0.,1.))
