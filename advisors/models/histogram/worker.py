import argparse
import json
from pathlib import Path
import pickle
import time

import numpy as np

from interface.common import timed
from . import data as histogram
from .tune import BASE, evaluate
from ..boosting import Regressor


@timed
def fit(data,sizes,params,threads,output):
    started=time.monotonic()
    rows=np.arange(len(data.y))
    pool=histogram.pool(data,sizes)(rows,rows,data.y)
    model=Regressor({**BASE,**params,'thread_count':threads,'allow_writing_files':False,'use_best_model':False}).fit(pool)
    if model.estimator.tree_count_!=params['iterations']:
        raise RuntimeError('The production fit did not retain all requested trees')
    predictions=model.predict(pool)
    path=output.with_suffix('.cbm')
    model.save(path)
    loaded=Regressor.load(path)
    np.testing.assert_array_equal(loaded.predict(pool),predictions)
    return {'rows':len(rows),'trees':model.estimator.tree_count_,'seconds':time.monotonic()-started,
            'features':model.estimator.feature_names_,'model':str(path)}


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--fit',action='store_true')
    args=parser.parse_args()
    request=json.loads(args.request.read_text())
    with Path(request['data']).open('rb') as stream:
        data=pickle.load(stream)
    result=(fit(data,request['sizes'],request['params'],request['threads'],Path(request['output'])) if args.fit else
            evaluate(data,request['sizes'],request['params'],request['threads']))
    Path(request['output']).write_text(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
