from importlib import import_module
import math

from interface.common import evidence, timed_often

COMMON={'random_trials':40,'failure_score':2.}
PARAMS={'random_forest':{'candidates':256,'uncertainty_weight':1.,'trees':64,'min_samples_leaf':2,'max_features':.75},
        'optuna_tpe':{'n_ei_candidates':24,'gamma':.1,'gamma_cap':25,'multivariate':True,'group':True,'prior_weight':1.},
        'botorch':{'candidates':256,'acquisition':'log_ei','beta':2.,'ard':True},
        'smac':{'random_probability':.2,'xi':0.,'trees':10,'ratio_features':1.,'min_samples_leaf':1,'challengers':10000,'local_search_iterations':10}}
CHOICES={'acquisition':('log_ei','ucb')}
SHARES=('max_features','gamma','ratio_features')


@timed_often
def configured(name,overrides):
    params={**COMMON,**PARAMS[name]}
    for item in overrides:
        key,given,text=item.partition('=')
        if key not in params or not given:
            raise ValueError(evidence(tuner=name,item=item,known=sorted(params)))
        kind=type(params[key])
        if kind is bool and text not in ('true','false'):
            raise ValueError(evidence(tuner=name,item=item))
        params[key]=text=='true' if kind is bool else kind(text)
    for key,value in params.items():
        allowed=(value in CHOICES[key] if key in CHOICES else True if isinstance(value,bool) else value>=1 if isinstance(value,int)
                 else math.isfinite(value) and value>=0 and (key!='random_probability' or value<=1) and (key not in SHARES or 0<value<=1))
        if not allowed:
            raise ValueError(evidence(tuner=name,key=key,value=value))
    if params['random_trials']<2 or (name=='optuna_tpe' and params['group'] and not params['multivariate']):
        raise ValueError(evidence(tuner=name,params=params))
    return {'name':name,'params':params}


@timed_often
def suggester(name):
    return import_module(f'{__name__}.{name}').suggest
