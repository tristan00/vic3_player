import numpy as np

from interface.common import evidence, timed_often
from advisors.models.validation import entropy
from .schema import HORIZONS


@timed_often
def scale_targets(y,mask):
    count=mask.sum(0)
    if np.any(count<2):
        raise ValueError(evidence(count=count))
    mean=(y*mask).sum(0)/count
    scale=np.sqrt((((y-mean)*mask)**2).sum(0)/count)
    return mean,np.maximum(scale,.01)


@timed_often
def utility(y):
    values=np.concatenate((np.zeros((*y.shape[:-2],1,4)),y),axis=-2)
    days=np.r_[0,HORIZONS]
    integral=((values[...,:-1,:]+values[...,1:,:])*.5*np.diff(days)[:,None]).sum(axis=-2)/days[-1]
    return integral.mean(axis=-1)*np.sqrt(days[-1]/365)


@timed_often
def accuracy(prediction,y,mask,scale,reward_scale):
    if prediction.shape!=y.shape or not np.isfinite(prediction).all():
        raise ValueError(evidence(prediction=prediction.shape,y=y.shape,finite=bool(np.isfinite(prediction).all())))
    errors=prediction-y
    count=mask.sum(0)
    mse=((errors*mask)**2).sum(0)/np.maximum(count,1)
    mae=(abs(errors)*mask).sum(0)/np.maximum(count,1)
    complete=mask.all(axis=(1,2))
    reward_error=utility(prediction[complete])-utility(y[complete])
    reward_rmse=float(np.sqrt(np.mean(reward_error**2))) if complete.any() else None
    return {'sequence_nrmse':float(np.sqrt(np.sum(((errors/scale)*mask)**2)/mask.sum())),
            'log_rmse':np.sqrt(mse).tolist(),'log_mae':mae.tolist(),'observed_cells':count.tolist(),
            'reward_rmse':reward_rmse,'reward_loss':None if reward_rmse is None else reward_rmse/reward_scale,
            'complete_trajectories':int(complete.sum())}


@timed_often
def differentiation(predictions,reward_scale):
    scores=[utility(p) for p in predictions]
    values=np.array([entropy(row) for row in scores])
    return {'mean_pause_entropy':float(values.mean()),'median_pause_entropy':float(np.median(values)),
            'tied_pause_fraction':float(np.mean(values==0)),'entropy_pauses':len(values),
            'normalized_candidate_std':float(np.mean([np.std(row)/reward_scale for row in scores])),
            'entropy_values':values.tolist()}


@timed_often
def combined(accuracy_result,entropy_result):
    return {**accuracy_result,**entropy_result,'score':.1*accuracy_result['reward_loss']+.9*(1-entropy_result['mean_pause_entropy'])}
