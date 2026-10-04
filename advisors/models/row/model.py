import json
import os
from pathlib import Path

from catboost import Pool

from interface.common import timed, timed_often
from ..boosting import Regressor
from .features import CATEGORICAL

PARAMETERS=Path(__file__).with_name('parameters.json')
BASE={'loss_function':'RMSE','random_seed':0,'thread_count':os.cpu_count(),'allow_writing_files':False}


@timed_often
def pool(features,targets=None):
    return Pool(features,label=targets,cat_features=[name for name in CATEGORICAL if name in features.columns])


class Model(Regressor):
    @timed_often
    def __init__(self,params=None):
        super().__init__({**BASE,**(json.loads(PARAMETERS.read_text()) if params is None else params)})

    @timed
    def fit(self,features,targets,validation=None,monitor=None):
        check=None if validation is None else pool(*validation)
        return super().fit(pool(features,targets),validation=check,monitor=monitor)

    @timed_often
    def predict(self,features):
        return super().predict(pool(features))
