import numpy as np

from interface.common import timed_often

SPEC={'name':'option_separation_v1','candidates':100,'entropy_resolution':.01,'spread_scale':.1,
      'aggregation':'equal snapshots within equal runs',
      'formula':'differentiation_weight * (1 - mean(sqrt(entropy * spread))) + reward_weight * normalized_rmse / (1 + normalized_rmse)'}


@timed_often
def loss(metrics,weights):
    return weights['differentiation']*(1-metrics['differentiation'])+weights['reward']*metrics['reward_loss']


@timed_often
def scale(targets,weights=None):
    values=np.asarray(targets,dtype=float)
    if values.ndim!=1 or len(values)<2 or not np.isfinite(values).all():
        raise ValueError('Training targets must be a finite vector with at least two observations')
    result=float(np.sqrt(np.average((values-np.average(values,weights=weights))**2,weights=weights)))
    if result<=np.finfo(float).eps*max(1.,float(np.max(np.abs(values)))):
        raise ValueError('Training rewards have no usable variation')
    return result


@timed_often
def differentiation(predictions,training_scale):
    values=np.asarray(predictions,dtype=float)
    if values.shape!=(100,) or not np.isfinite(values).all() or not np.isfinite(training_scale) or training_scale<=0:
        raise ValueError('Differentiation requires 100 finite predictions and a positive training scale')
    ordered=np.sort(values)
    tolerance=training_scale*SPEC['entropy_resolution']
    counts=[]
    anchor=ordered[0]
    count=0
    for value in ordered:
        if value-anchor>tolerance:
            counts.append(count)
            anchor=value
            count=0
        count+=1
    counts.append(count)
    probabilities=np.asarray(counts)/100
    entropy=float(-np.dot(probabilities,np.log(probabilities))/np.log(100))
    std=float(np.std(values/training_scale))
    spread=std/(std+SPEC['spread_scale'])
    return {'entropy':entropy,'std':std,'spread':spread,'differentiation':float(np.sqrt(entropy*spread))}


@timed_often
def summarize(points,weights):
    if not points:
        raise ValueError('Validation requires held-out snapshots')
    runs=sorted({point['run'] for point in points})
    by_run=[{key:float(np.mean([p[key] for p in points if p['run']==run]))
             for key in ('mse','normalized_mse','entropy','std','spread','differentiation')} for run in runs]
    means={key:float(np.mean([r[key] for r in by_run])) for key in by_run[0]}
    normalized_rmse=float(np.sqrt(means.pop('normalized_mse')))
    rmse=float(np.sqrt(means.pop('mse')))
    reward_loss=normalized_rmse/(1+normalized_rmse)
    score=loss({**means,'reward_loss':reward_loss},weights)
    result={**means,'rmse':rmse,'normalized_rmse':normalized_rmse,'reward_loss':reward_loss,'score':score,
            'snapshots':len(points),'runs':len(runs),'collapsed_fraction':float(np.mean([p['differentiation']==0 for p in points]))}
    if not all(np.isfinite(value) for value in result.values()):
        raise ValueError('Nonfinite validation metrics')
    return result
