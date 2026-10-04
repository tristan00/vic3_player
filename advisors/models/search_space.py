import numpy as np

from interface.common import timed_often

RANGES={'depth':(3,10),'learning_rate':(.002,.3),'l2_leaf_reg':(.01,100),
        'rsm':(.1,1.),'random_strength':(.001,10),'one_hot_max_size':[2,8,32,128,512],'max_ctr_complexity':[1,2,3],
        'boosting_type':['Plain','Ordered'],'bootstrap_type':['MVS','Bernoulli','Bayesian','No'],
        'subsample':(.5,1.),'bagging_temperature':(0.,5.),'border_count':[32,64,128,254],
        'leaf_estimation_iterations':[1,3,5,10],'grow_policy':['SymmetricTree','Depthwise','Lossguide'],
        'min_data_in_leaf':[1,5,20,100],'max_leaves':[16,32,64]}
LOGARITHMIC={'iterations','learning_rate','l2_leaf_reg','random_strength'}
DEFAULTS={'max_ctr_complexity':1,'boosting_type':'Plain','bootstrap_type':'MVS','subsample':.8,'bagging_temperature':1.,
          'border_count':254,'leaf_estimation_iterations':1,'grow_policy':'SymmetricTree','min_data_in_leaf':1,'max_leaves':32}


@timed_often
def conditional(params):
    params=dict(params)
    if params['bootstrap_type']!='Bayesian':
        params.pop('bagging_temperature',None)
    if params['bootstrap_type'] not in ('MVS','Bernoulli'):
        params.pop('subsample',None)
    if params['grow_policy']=='SymmetricTree':
        params.pop('min_data_in_leaf',None)
    else:
        params['boosting_type']='Plain'
    if params['grow_policy']!='Lossguide':
        params.pop('max_leaves',None)
    return params


@timed_often
def space(ranges):
    bounds=[(-.499,len(values)-.501) if isinstance(values,list) else
            tuple(np.log10(values)) if name in LOGARITHMIC else values
            for name,values in ranges.items() if isinstance(values,(list,tuple))]
    return tuple(np.array(values,float) for values in zip(*bounds))


@timed_often
def decode(point,ranges):
    params={name:value for name,value in ranges.items() if not isinstance(value,(list,tuple))}
    names=[name for name,value in ranges.items() if isinstance(value,(list,tuple))]
    for name,value in zip(names,point):
        if isinstance(ranges[name],list):
            params[name]=ranges[name][int(round(value))]
        else:
            value=float(10**value if name in LOGARITHMIC else value)
            params[name]=int(round(value)) if name in ('depth','iterations') else value
    return conditional(params)


@timed_often
def encode(params,ranges):
    params={**DEFAULTS,**params}
    return [values.index(params[name]) if isinstance(values,list) else float(np.log10(params[name])) if name in LOGARITHMIC else params[name]
            for name,values in ranges.items() if isinstance(values,(list,tuple))]
