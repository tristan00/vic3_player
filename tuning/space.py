import hashlib
import json

import numpy as np

from interface.common import evidence, timed_often

MODEL={
    'iterations':{'kind':'integer','low':10,'high':1000,'log':True},
    'depth':{'kind':'integer','low':3,'high':10},
    'learning_rate':{'kind':'real','low':.005,'high':.3,'log':True},
    'l2_leaf_reg':{'kind':'real','low':.01,'high':100.,'log':True},
    'random_strength':{'kind':'real','low':.001,'high':10.,'log':True},
    'rsm':{'kind':'real','low':.15,'high':1.},
    'border_count':{'kind':'choice','values':[32,64,128,254]},
    'one_hot_max_size':{'kind':'choice','values':[2,8,32,128]},
    'max_ctr_complexity':{'kind':'choice','values':[1,2]},
    'grow_policy':{'kind':'choice','values':['SymmetricTree','Depthwise','Lossguide']},
    'min_data_in_leaf':{'kind':'choice','values':[1,8,32,128],'when':{'grow_policy':['Depthwise','Lossguide']}},
    'max_leaves':{'kind':'choice','values':[16,32,64,128],'when':{'grow_policy':['Lossguide']}},
    'bootstrap_type':{'kind':'choice','values':['Bayesian','Bernoulli','MVS','No']},
    'subsample':{'kind':'real','low':.5,'high':1.,'when':{'bootstrap_type':['Bernoulli','MVS']}},
    'bagging_temperature':{'kind':'real','low':0.,'high':5.,'when':{'bootstrap_type':['Bayesian']}},
    'leaf_estimation_iterations':{'kind':'choice','values':[1,3,5]}}


class Space:
    @timed_often
    def __init__(self,groups):
        self.groups=groups
        self.parameters={name:dict(spec) for name,spec in MODEL.items()}
        for name,group in groups.items():
            values=['off','on'] if group['kind']=='columns' else ['off','count','share'] if group['role']=='option' else ['off','count']
            self.parameters['feature.'+name]={'kind':'choice','values':values}
            if group['kind']=='histogram':
                self.parameters['bins.'+name]={'kind':'choice','values':[8,32,128,0],
                                               'when':{'feature.'+name:values[1:]}}

    @timed_often
    def canonical(self,config):
        unknown=set(config)-set(self.parameters)
        if unknown:
            raise ValueError(evidence(unknown=unknown))
        result={}
        for name,spec in self.parameters.items():
            if any(config[parent] not in values for parent,values in spec.get('when',{}).items()):
                continue
            if name not in config:
                raise ValueError(evidence(name=name))
            value=config[name]
            if spec['kind']=='choice':
                if value not in spec['values']:
                    raise ValueError(evidence(name=name,value=value,values=spec['values']))
            elif not np.isfinite(value) or not spec['low']<=value<=spec['high'] or (spec['kind']=='integer' and int(value)!=value):
                raise ValueError(evidence(name=name,value=value,spec=spec))
            result[name]=value
        if not any(result['feature.'+name]!='off' for name,group in self.groups.items() if group['role']=='option'):
            raise ValueError(evidence(features={name:result['feature.'+name] for name,group in self.groups.items() if group['role']=='option'}))
        return result

    @timed_often
    def draw(self,rng):
        config={}
        density=float(rng.uniform(.15,.95))
        for name,spec in self.parameters.items():
            if spec['kind']=='choice':
                choices=spec['values']
                value=choices[int(rng.integers(len(choices)))]
                if name.startswith('feature.'):
                    value='off' if rng.random()>density else choices[int(rng.integers(1,len(choices)))]
            else:
                value=float(np.exp(rng.uniform(np.log(spec['low']),np.log(spec['high']))) if spec.get('log') else rng.uniform(spec['low'],spec['high']))
                if spec['kind']=='integer':
                    value=int(round(value))
            config[name]=value
        repaired=all(config['feature.'+name]=='off' for name,group in self.groups.items() if group['role']=='option')
        sampled=dict(config)
        if repaired:
            config['feature.option.action']=self.parameters['feature.option.action']['values'][1]
        return self.canonical(config),{'feature_probability':density,'action_required':repaired,'sampled':sampled}

    @timed_often
    def vector(self,config):
        values=[]
        for name,spec in self.parameters.items():
            active=name in config
            values.append(float(active))
            if spec['kind']=='choice':
                values.extend(float(active and config[name]==value) for value in spec['values'])
            else:
                if not active:
                    values.append(0.)
                    continue
                low,high=spec['low'],spec['high']
                value=config[name]
                if spec.get('log'):
                    low,high,value=np.log([low,high,value])
                values.append(float((value-low)/(high-low)))
        return values


@timed_often
def identity(config):
    return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]


@timed_often
def model_params(config,threads,seed):
    return {**{name:config[name] for name,spec in MODEL.items() if all(config[parent] in values for parent,values in spec.get('when',{}).items())},'loss_function':'RMSE','random_seed':seed,
            'thread_count':threads,'allow_writing_files':False,'verbose':False,'boosting_type':'Plain','counter_calc_method':'SkipTest'}
