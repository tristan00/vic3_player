from concurrent.futures import ProcessPoolExecutor
import logging

import numpy as np
import psycopg

from interface.common import evidence, timed, timed_often
from interface.timing import RECORDER, current
from ..data.endgame import NAME
from ..models.row.features import live
from tuning.runtime import train as train_model

LOG=logging.getLogger('loop')


@timed
def train(dsn):
    RECORDER.reset()
    with psycopg.connect(dsn,autocommit=True,options='-c default_transaction_read_only=on') as connection:
        model,rows,starts,runs,loaded,fitted=train_model(connection,'row')
    return model,rows,starts,runs,loaded,fitted,RECORDER.take()


class CatBoostPiecewisePicker:
    name='catboost_piecewise'

    @timed_often
    def __init__(self):
        self.model=None
        self.trained=None

    @timed
    def start_run(self,store,objective,kept):
        if kept is None:
            *kept,timings=self.fit_apart(store.connection.info.dsn)
            RECORDER.merge(timings)
        self.model,rows,starts,runs,loaded,fitted=kept
        params={name:value for name,value in self.model.params.items() if name not in ('allow_writing_files','verbose')}
        params.update(model_kind='row',training_rows=rows)
        self.trained=(starts,runs,current().seconds,params,self.model.importance())
        LOG.info('%s picker model of %d rows from %d runs ready in %.1fs using %s (cold load %.1fs, fit %.1fs)',
                 self.name,rows,runs,self.trained[2],NAME,loaded,fitted)
        return kept

    @timed
    def fit_apart(self,dsn):
        with ProcessPoolExecutor(1) as fresh:
            return fresh.submit(train,dsn).result()

    @timed
    def pick(self,candidates,snapshot):
        counts=np.array([len(candidate) for candidate in candidates])
        if not len(counts) or (counts==0).any():
            raise ValueError(evidence(counts=counts))
        if (counts!=counts[0]).any():
            raise ValueError(evidence(counts=counts))
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
        scores=np.add.reduceat(predictions,np.r_[0,np.cumsum(counts)[:-1]])
        return int(np.argmax(scores)),scores.tolist()
