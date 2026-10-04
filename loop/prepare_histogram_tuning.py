import argparse
import json
from pathlib import Path
import pickle
import time

import numpy as np
import psycopg
from scipy.sparse import csr_matrix, vstack
from sklearn.model_selection import GroupKFold

from advisors.data.features import LiveLookup
from advisors.data.histograms import entries
from advisors.data.endgame import OBJECTIVE
from advisors.models.histogram import data as histogram
from advisors.models.histogram.validation import METRIC, Validation
from interface.common import timed
from interface.recording.store import DSN
from .run import redraw

OUTPUT=Path(__file__).resolve().parents[1]/'artifacts'/'histogram_tuning_data'


@timed
def prepare(connection,data,folds=4,pauses=300,candidates=30,seed=0):
    if folds<2 or pauses<1 or candidates<2:
        raise ValueError('Preparation requires two folds, one pause and two candidates at minimum')
    rng=np.random.default_rng(seed)
    data.metric=METRIC.copy()
    data.sampling={'folds':folds,'pauses_per_fold':pauses,'candidates':candidates,'seed':seed,
                   'generator':'loop.run.redraw','weights':'recorded run weights'}
    data.folds=[]
    for train,test in GroupKFold(folds).split(data.y,groups=data.runs):
        sampled=np.sort(rng.choice(test,min(pauses,len(test)),replace=False))
        actions=[]
        sizes=[]
        seeds=[]
        for row in sampled:
            run,seq=map(int,data.pauses[row])
            draw_seed=int(rng.integers(2**31))
            snapshot,blocks=redraw(connection,run,seq,candidates,draw_seed)
            lookup=LiveLookup(snapshot)
            if len(blocks)!=candidates or any(not block for block in blocks):
                raise ValueError('Every generated candidate must contain an action')
            actions.append(csr_matrix(data.actions.count([entries(block,lookup) for block in blocks])))
            sizes.extend([len(block)] for block in blocks)
            seeds.append(draw_seed)
            if len(seeds)%25==0:
                print(json.dumps({'fold':len(data.folds)+1,'prepared_pauses':len(seeds),'requested_pauses':len(sampled)}),flush=True)
        data.folds.append({'train':train,'test':test,'pauses':sampled,'seeds':seeds,
                           'actions':vstack(actions,format='csr'),'sizes':np.asarray(sizes,np.float32)})
    Validation(data)
    return data


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--folds',type=int,default=4)
    parser.add_argument('--pauses',type=int,default=300)
    parser.add_argument('--candidates',type=int,default=30)
    parser.add_argument('--seed',type=int,default=0)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic()
    with psycopg.connect(DSN) as connection:
        data=prepare(connection,histogram.training_data(connection),args.folds,args.pauses,args.candidates,args.seed)
    with (args.output/'data.pkl').open('wb') as stream:
        pickle.dump(data,stream,pickle.HIGHEST_PROTOCOL)
    report={'rows':len(data.y),'runs':data.played,'objective':OBJECTIVE,'validation':Validation(data).configuration(),
            'pauses':[data.pauses[fold['pauses']].tolist() for fold in data.folds],
            'candidate_seeds':[fold['seeds'] for fold in data.folds],'seconds':time.monotonic()-started}
    (args.output/'dataset.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
