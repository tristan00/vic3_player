import numpy as np
import torch
from botorch.acquisition import LogExpectedImprovement, UpperConfidenceBound
from botorch.fit import fit_gpytorch_mll
from botorch.models import SingleTaskGP
from botorch.models.transforms import Standardize
from gpytorch.kernels import RBFKernel
from gpytorch.mlls import ExactMarginalLogLikelihood

from interface.common import timed


@timed
def suggest(space,configs,scores,seed,params,draw):
    torch.manual_seed(seed)
    candidates=draw(params['candidates'])
    x=torch.tensor(np.asarray([space.vector(config) for config in configs]),dtype=torch.double)
    y=-torch.tensor(np.asarray(scores),dtype=torch.double).unsqueeze(-1)
    model=SingleTaskGP(x,y,outcome_transform=Standardize(1),covar_module=None if params['ard'] else RBFKernel())
    fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood,model))
    acquisition=LogExpectedImprovement(model,best_f=y.max()) if params['acquisition']=='log_ei' else UpperConfidenceBound(model,beta=params['beta'])
    encoded=torch.tensor(np.asarray([space.vector(candidate['config']) for candidate in candidates]),dtype=torch.double)
    with torch.no_grad():
        posterior=model.posterior(encoded)
        means,uncertainties=-posterior.mean.squeeze(-1),posterior.variance.sqrt().squeeze(-1)
        selection=acquisition(encoded.unsqueeze(1))
    for candidate,mean,uncertainty,score in zip(candidates,means.tolist(),uncertainties.tolist(),selection.tolist()):
        candidate.update(predicted_score=mean,uncertainty=uncertainty,selection_score=score)
    chosen=int(selection.argmax())
    found={'selected_index':chosen,**{name:candidates[chosen][name] for name in ('predicted_score','uncertainty','selection_score')}}
    return candidates[chosen]['config'],found,{'candidates':candidates}
