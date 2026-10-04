import numpy as np

from interface.common import timed, timed_often
from interface.timing import current
from ..models.row.data import TrainingCache, load
from ..models.row.features import live
from ..models.row.model import Model


class CatBoostPiecewisePicker:
    name='catboost_piecewise'

    @timed_often
    def __init__(self):
        self.model=None
        self.trained=None
        self.cache=TrainingCache()

    @timed
    def start_run(self,store,objective):
        data=load(store.connection,cache=self.cache)
        self.model=Model().fit(data.X,data.y)
        params={name:value for name,value in self.model.params.items() if name!='allow_writing_files'}
        params.update(model_kind='row',training_rows=len(data.y))
        starts=len(data.meta[['run','before_seq']].drop_duplicates())
        self.trained=(starts,len(np.unique(data.runs)),current().seconds,params,self.model.importance())

    @timed
    def pick(self,candidates,snapshot):
        counts=np.array([len(candidate) for candidate in candidates])
        if not len(counts) or (counts==0).any():
            raise ValueError('Candidate sequences must contain at least one action')
        actions=[]
        unique={}
        indices=[]
        for candidate in candidates:
            for name,params in candidate:
                key=(name,tuple(sorted(params.items())))
                if key not in unique:
                    unique[key]=len(actions)
                    actions.append((name,params))
                indices.append(unique[key])
        predictions=self.model.predict(live(snapshot,actions))[indices]
        scores=np.add.reduceat(predictions,np.r_[0,np.cumsum(counts)[:-1]])/counts
        return int(np.argmax(scores)),scores.tolist()
