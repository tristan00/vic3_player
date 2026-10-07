import argparse
import json
import logging
import pickle
import time

import numpy as np
import pandas as pd
import psycopg

from interface.common import timed
from interface.recording.store import DSN
from .data import OUTPUT, load, split
from .features import CATEGORICAL, NUMERIC, PLAYER_FIELDS


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runs',type=int,nargs='+')
    args=parser.parse_args()
    started=time.monotonic()
    with psycopg.connect(DSN,connect_timeout=3) as connection:
        connection.execute('set transaction isolation level repeatable read read only')
        connection.execute("set statement_timeout='15s'")
        data=load(connection,runs=args.runs)
    train,test=split(data.runs)
    data.train,data.test=train,test
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with (OUTPUT/'data.pkl').open('wb') as output:
        pickle.dump(data,output)
    catalogue=[{'name':name,'type':'categorical' if name in CATEGORICAL else 'numeric','group':'state' if name in PLAYER_FIELDS else 'action'} for name in data.X.columns]
    summary={'rows':len(data.y),'features':len(data.X.columns),'numeric':len(NUMERIC),'categorical':len(CATEGORICAL),
             'state_features':sum(row['group']=='state' for row in catalogue),'action_features':sum(row['group']=='action' for row in catalogue),
             'train_rows':len(train),'validation_rows':len(test),'train_runs':np.unique(data.runs[train]).tolist(),'validation_runs':np.unique(data.runs[test]).tolist(),
             'objective':data.objective,'omitted':data.omitted,'seconds':time.monotonic()-started,'catalogue':catalogue}
    (OUTPUT/'dataset.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    example=pd.concat([data.meta.head(64),data.X.head(64)],axis=1)
    example['sample_weight']=1.
    example.to_csv(OUTPUT/'rows.csv',index=False)
    example.to_html(OUTPUT/'rows.html',index=False)
    print(json.dumps({key:value for key,value in summary.items() if key!='catalogue'}),flush=True)


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    main()
