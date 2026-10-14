import logging
import numpy as np

from interface.common import timed, timed_often
from interface.timing import current
from ..data.endgame import NAME
from tuning.runtime import train

LOG=logging.getLogger('loop')


class CatBoostPicker:
    name='catboost'

    @timed_often
    def __init__(self):
        self.model=None
        self.trained=None

    @timed
    def start_run(self,store,objective,kept):
        if kept is None:
            kept=train(store.connection,'histogram')
        self.model,rows,starts,runs,loaded,fitted=kept
        params={name:value for name,value in self.model.params.items() if name not in ('verbose','allow_writing_files')}
        self.trained=(rows,runs,current().seconds,params,self.model.importance())
        LOG.info('%s picker model of %d rows from %d runs ready in %.1fs using %s',self.name,*self.trained[:3],NAME)
        return kept

    @timed
    def pick(self,candidates,snapshot):
        predictions=self.model.live(snapshot,candidates)
        return int(np.argmax(predictions)),predictions.tolist()
