import argparse
import json
from pathlib import Path
import time
from types import SimpleNamespace

import numpy as np
import psycopg
import torch

from interface.common import evidence, timed
from interface.recording.store import DSN
from .inference import Forecaster
from .source import candidates
from .summarize import summarize
from .world_data import read


@timed
def verify(root):
    torch.set_num_threads(4)
    output=root/'world_experiments'
    results=[]
    expected=np.load(output/'full_world/test.npz')
    run,seq=map(int,expected['candidate_pauses'][0])
    recorded=read(root/'world_packed'/f'{run}_{seq}.pkl')
    with psycopg.connect(DSN) as connection:
        connection.execute('set transaction isolation level repeatable read read only')
        blocks=candidates(connection,run,seq,30,20261001+run*1009+seq)
    if blocks!=recorded['actions']:
        raise ValueError(evidence(run=run,seq=seq,drawn=len(blocks),recorded=len(recorded['actions'])))
    names=[r['name'] for r in json.loads((output/'results.json').read_text())]
    for name in names:
        started=time.monotonic()
        forecaster=Forecaster(output/name/'model.pt',root/'world_packed/encoder.pkl.gz')
        with psycopg.connect(DSN) as connection:
            connection.execute('set transaction isolation level repeatable read read only')
            found=forecaster.from_snapshot(SimpleNamespace(connection=connection,run_id=run,seq=seq),blocks)
        saved=np.load(output/name/'test.npz')['candidates'][0]
        np.testing.assert_allclose(found['log_ratios'],saved,atol=5e-5,rtol=1e-5)
        result={'name':name,'run':run,'seq':seq,'candidates':len(blocks),'finite':bool(np.isfinite(found['values']).all()),
                'max_log_ratio_difference':float(abs(found['log_ratios']-saved).max()),'seconds':time.monotonic()-started}
        results.append(result)
        print(json.dumps(result),flush=True)
        del forecaster
        torch.cuda.empty_cache()
    (root/'world_verification.json').write_text(json.dumps(results,indent=2))
    summarize(root)


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--wait-for',type=Path)
    args=parser.parse_args()
    while args.wait_for:
        status=json.loads(args.wait_for.read_text())
        if status['state']=='failed':
            raise RuntimeError(evidence(status=status))
        if status['state']=='complete':
            break
        time.sleep(5)
    verify(args.root)


if __name__=='__main__':
    main()
