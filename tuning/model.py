import time

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

from interface.common import evidence, timed, timed_often
from .features import Encoder
from .metrics import scale
from .space import model_params
from .storage import write


@timed
def pool(frame,y=None,weights=None,threads=1):
    categorical=[name for name,dtype in frame.dtypes.items() if isinstance(dtype,pd.CategoricalDtype) or dtype==object or pd.api.types.is_string_dtype(dtype)]
    return Pool(frame,label=y,weight=weights,cat_features=categorical,thread_count=threads)


class Monitor:
    @timed_often
    def __init__(self,path,stage):
        self.path,self.stage=path,stage
        self.started=time.monotonic()
        self.last=0.

    @timed_often
    def after_iteration(self,info):
        elapsed=time.monotonic()-self.started
        if elapsed-self.last>=5 or info.iteration==1:
            write(self.path,{**self.stage,'step':'fit','iteration':info.iteration,'fit_seconds':elapsed,'updated':time.time()})
            self.last=elapsed
        return True


class PickerModel:
    @timed
    def __init__(self,model,config,groups,threads=4,seed=19):
        self.encoder=Encoder(model,config,groups)
        self.params=model_params(config,threads,seed)
        self.estimator=None

    @timed
    def fit(self,features,y,weights,monitor=None):
        self.mean=float(np.average(y,weights=weights))
        self.scale=scale(y,weights)
        frame=self.encoder.fit(features).transform(features)
        self.estimator=CatBoostRegressor(**self.params)
        self.estimator.fit(pool(frame,(y-self.mean)/self.scale,weights,self.params['thread_count']),
                           callbacks=[] if monitor is None else [monitor])
        if self.estimator.tree_count_!=self.params['iterations']:
            raise ValueError(evidence(trees=self.estimator.tree_count_,iterations=self.params['iterations']))
        self.feature_count=len(frame.columns)
        if self.encoder.model=='row':
            self.estimator.drop_unused_features()
        return self

    @timed
    def predict(self,features):
        frame=features.loc[:,self.estimator.feature_names_ or self.encoder.columns[:1]] if self.encoder.model=='row' else self.encoder.transform(features)
        return np.asarray(self.estimator.predict(pool(frame),thread_count=1))*self.scale+self.mean

    @timed
    def live(self,snapshot,candidates):
        frame=self.encoder.live(snapshot,candidates)
        return np.asarray(self.estimator.predict(pool(frame),thread_count=1))*self.scale+self.mean

    @timed
    def importance(self):
        names=self.encoder.columns if self.encoder.model=='row' else self.estimator.feature_names_
        return list(zip(names,map(float,self.estimator.feature_importances_)))
