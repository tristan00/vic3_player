import argparse
import json
from pathlib import Path
import pickle

from interface.common import timed
from .features import CATEGORICAL
from .model import pool
from .tune import trial
from .validation import Validation


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',type=Path,required=True)
    args=parser.parse_args()
    request=json.loads(args.request.read_text())
    with Path(request['data']).open('rb') as source:
        data=pickle.load(source)
    features=data.X.astype({name:'category' for name in CATEGORICAL})
    metric=Validation(data.y[data.train],data.y[data.test],data.meta.iloc[data.test])
    training=pool(features.iloc[data.train],data.y[data.train])
    validation=pool(features.iloc[data.test],data.y[data.test])
    result=trial(request['trial'],request['params'],training,validation,metric,request['threads'])
    Path(request['output']).write_text(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
