import logging
import numpy as np

from interface.common import timed, timed_often
from interface.timing import current
from ..models.boosting import Regressor
from ..data.endgame import NAME
from ..models.histogram.data import Encoder, PARAMS, SIZES, TrainingCache, pool, training_data

LOG=logging.getLogger('loop')


class CatBoostPicker:
    name='catboost'

    @timed_often
    def __init__(self):
        self.model=None
        self.trained=None
        self.encoder=None
        self.cache=TrainingCache()

    @timed
    def start_run(self,store,objective):
        data=training_data(store.connection,self.cache)
        self.encoder=Encoder(data.actions,data.held,SIZES)
        rows=np.arange(len(data.y))
        self.model=Regressor(PARAMS).fit(pool(data,SIZES)(rows,rows,data.y))
        self.trained=(len(data.y),data.played,current().seconds,PARAMS,self.model.importance())
        LOG.info('%s picker trained on %d rows from %d runs in %.1fs using %s',self.name,*self.trained[:3],NAME)

    @timed
    def pick(self,candidates,snapshot):
        predictions=self.model.predict(self.encoder.live(snapshot,candidates))
        return int(np.argmax(predictions)),predictions.tolist()
