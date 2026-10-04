import numpy as np
from catboost import CatBoostRegressor

from interface.common import progress, timed, timed_often


class Beat:
    @timed_often
    def after_iteration(self,info):
        progress('catboost fit')
        return True


class Regressor:
    @timed_often
    def __init__(self,params):
        self.params=dict(params)
        self.estimator=None

    @timed
    def fit(self,features,targets=None,validation=None,monitor=None):
        self.estimator=CatBoostRegressor(**self.params,verbose=False)
        self.estimator.fit(features,targets,eval_set=validation,callbacks=[Beat(),*([monitor] if monitor is not None else [])])
        return self

    @timed_often
    def predict(self,features):
        return np.asarray(self.estimator.predict(features,thread_count=1))

    @timed_often
    def importance(self):
        return list(zip(self.estimator.feature_names_,map(float,self.estimator.get_feature_importance())))

    @timed
    def save(self,path):
        self.estimator.save_model(str(path))

    @classmethod
    @timed
    def load(cls,path):
        model=cls({})
        model.estimator=CatBoostRegressor().load_model(str(path))
        model.params=model.estimator.get_params()
        return model
