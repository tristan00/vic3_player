import math

import optuna
from optuna.distributions import CategoricalDistribution, FloatDistribution, IntDistribution

from interface.common import timed, timed_often


@timed_often
def distribution(spec):
    if spec['kind']=='choice':
        return CategoricalDistribution(spec['values'])
    return (IntDistribution if spec['kind']=='integer' else FloatDistribution)(spec['low'],spec['high'],log=bool(spec.get('log')))


@timed
def suggest(space,configs,scores,seed,params,draw,step):
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    good=lambda count:min(math.ceil(params['gamma']*count),params['gamma_cap'])
    with step('build'):
        distributions={name:distribution(spec) for name,spec in space.parameters.items()}
        sampler=optuna.samplers.TPESampler(seed=seed,n_startup_trials=0,n_ei_candidates=params['n_ei_candidates'],gamma=good,multivariate=params['multivariate'],
                                           group=params['group'],prior_weight=params['prior_weight'],warn_independent_sampling=False,constant_liar=False)
        study=optuna.create_study(direction='minimize',sampler=sampler)
    with step('history'):
        study.add_trials([optuna.trial.create_trial(params=config,distributions={name:distributions[name] for name in config},value=float(score))
                          for config,score in zip(configs,scores)])
    with step('select'):
        trial=study.ask()
        config={}
        for name,spec in space.parameters.items():
            if all(config[parent] in values for parent,values in spec.get('when',{}).items()):
                config[name]=trial._suggest(name,distributions[name])
    return config,{'good_trials':good(len(configs))},{}
