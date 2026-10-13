import numpy as np

from advisors.catalogue import LENGTHS
from interface.common import evidence, timed_often

SPEC={'name':'option_entropy_v2','candidates':{'histogram':100,'row':100,'size':len(LENGTHS)},
      'aggregation':'equal snapshots within equal runs',
      'formula':'differentiation_weight * (1 - mean(entropy / log(candidates))) + reward_weight * normalized_rmse / (1 + normalized_rmse)'}


@timed_often
def loss(metrics,weights):
    return weights['differentiation']*(1-metrics['differentiation'])+weights['reward']*metrics['reward_loss']


@timed_often
def scale(targets,weights=None):
    values=np.asarray(targets,dtype=float)
    if values.ndim!=1 or len(values)<2 or not np.isfinite(values).all():
        raise ValueError(evidence(shape=values.shape,finite=bool(np.isfinite(values).all())))
    result=float(np.sqrt(np.average((values-np.average(values,weights=weights))**2,weights=weights)))
    if result<=np.finfo(float).eps*max(1.,float(np.max(np.abs(values)))):
        raise ValueError(evidence(result=result))
    return result


@timed_often
def differentiation(predictions):
    values=np.asarray(predictions,dtype=float)
    if values.ndim!=1 or len(values)<2 or not np.isfinite(values).all():
        raise ValueError(evidence(shape=values.shape,finite=bool(np.isfinite(values).all())))
    probabilities=np.unique(values,return_counts=True)[1]/len(values)
    return float(np.dot(probabilities,np.log(1/probabilities))/np.log(len(values)))


@timed_often
def summarize(points,weights):
    if not points:
        raise ValueError(evidence(points=points))
    runs=sorted({point['run'] for point in points})
    by_run=[{key:float(np.mean([p[key] for p in points if p['run']==run]))
             for key in ('mse','normalized_mse','differentiation')} for run in runs]
    means={key:float(np.mean([r[key] for r in by_run])) for key in by_run[0]}
    normalized_rmse=float(np.sqrt(means.pop('normalized_mse')))
    rmse=float(np.sqrt(means.pop('mse')))
    reward_loss=normalized_rmse/(1+normalized_rmse)
    score=loss({**means,'reward_loss':reward_loss},weights)
    result={**means,'rmse':rmse,'normalized_rmse':normalized_rmse,'reward_loss':reward_loss,'score':score,
            'snapshots':len(points),'runs':len(runs),'collapsed_fraction':float(np.mean([p['differentiation']==0 for p in points]))}
    if not all(np.isfinite(value) for value in result.values()):
        raise ValueError(evidence(result=result))
    return result
