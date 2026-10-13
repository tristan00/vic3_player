from pathlib import Path
from tempfile import TemporaryDirectory

from ConfigSpace import AndConjunction, Categorical, Configuration, ConfigurationSpace, Float, InCondition, Integer
import numpy as np
from smac import HyperparameterOptimizationFacade, Scenario

from interface.common import timed, timed_often


@timed_often
def hyperparameter(name,spec):
    if spec['kind']=='choice':
        return Categorical(name,spec['values'])
    return (Integer if spec['kind']=='integer' else Float)(name,(spec['low'],spec['high']),log=bool(spec.get('log')))


@timed
def suggest(space,configs,scores,seed,params,draw):
    known={name:hyperparameter(name,spec) for name,spec in space.parameters.items()}
    configspace=ConfigurationSpace(seed=seed)
    configspace.add(list(known.values()))
    conditions=[[InCondition(known[name],known[parent],values) for parent,values in spec['when'].items()] for name,spec in space.parameters.items() if 'when' in spec]
    configspace.add([needed[0] if len(needed)==1 else AndConjunction(*needed) for needed in conditions])
    facade=HyperparameterOptimizationFacade
    with TemporaryDirectory() as output:
        scenario=Scenario(configspace,output_directory=Path(output),deterministic=True,n_trials=len(configs)+1,seed=seed)
        search=facade(scenario,lambda config,seed:0.,logging_level=False,overwrite=True,
                      model=facade.get_model(scenario,n_trees=params['trees'],ratio_features=params['ratio_features'],min_samples_leaf=params['min_samples_leaf']),
                      acquisition_function=facade.get_acquisition_function(scenario,xi=params['xi']),
                      acquisition_maximizer=facade.get_acquisition_maximizer(scenario,challengers=params['challengers'],local_search_iterations=params['local_search_iterations']),
                      initial_design=facade.get_initial_design(scenario,n_configs=0),
                      random_design=facade.get_random_design(scenario,probability=params['random_probability']))
        for config,score in zip(configs,scores):
            search.runhistory.add(Configuration(configspace,values=config),float(score),seed=0)
        chosen=next(iter(search.intensifier.config_selector))
    config={name:value.item() if isinstance(value,np.generic) else value for name,value in dict(chosen).items()}
    return config,{'origin':chosen.origin},{}
